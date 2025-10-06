import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List, Iterator, Literal

from langchain_core.documents import Document
from typing_extensions import TypedDict
from langchain_community.tools import TavilySearchResults
from langgraph.graph import END, StateGraph, START
from langgraph.config import get_stream_writer

import chroma_db
import chains
from comm import llm_provider

os.environ["USER_AGENT"] = "my-rag-app/1.0.0 (contact: developer@example.com)"


def load_websites_to_index(collect_name):
    collection = chroma_db.get_collection(collect_name)
    if collection is None:
        # Docs to index
        urls = [
            "https://lilianweng.github.io/posts/2023-06-23-agent/",
            "https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/",
            "https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/",
        ]
        chroma_db.load_websites_to_index(collect_name, urls)


collect_name = "rag-chroma"
load_websites_to_index(collect_name)
retriever = chroma_db.get_retriever(collect_name)
question_router = chains.route_query_chain()
retrieval_grader = chains.retrieval_grader_chain()
generator = chains.generate_answer_chain()
answer_grader = chains.answer_grader_chain()
hallucination_grader = chains.hallucination_grader_chain()
question_rewriter = chains.question_rewriter_chain()
web_search_tool = TavilySearchResults(k=3)
CONVERSATION_HISTORY_STORE_FILE_DIR = "_conversation_history"
CONVERSATION_HISTORY_STORE_FILE_NAME_PATTERN = "dialogue_%s.json"
_executor = ThreadPoolExecutor(max_workers=3)


# Post-processing
def format_docs(docs):
    # return "\n\n".join(doc.page_content for doc in docs)
    ret = []
    for doc in docs:
        if hasattr(doc, "page_content"):
            ret.append(doc.page_content)
        else:
            pass
    return "\n\n".join(ret)


# Graph State class
class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        question: question
        generation: LLM generation
        documents: list of documents
    """

    question: str
    org_question: str
    datasource: Literal["vectorstore", "web_search", "generate_directly"]
    generation: str
    documents: List[str]
    generate_count: int  # generate times
    max_generate_count: int
    conversation_history: List[dict]  # store conversation history
    max_context_length: int  # the max length of context
    user_id: str   # user id to isolate context


def get_coverage_history_txt(state: GraphState, question_len: int, prompt_len: int, docs_txt_len: int):
    """
    Get conversation history from the current state.

    Args:
        state: The current graph state
        question_len: length of current question
        prompt_len: length of prompt template
        docs_txt_len: length of referencing docs

    Returns:
        The conversation history text
    """
    conversation_history = state.get("conversation_history", [])
    conversation_history_txt = ""
    max_len = llm_provider.MAX_CHAT_MODEL_INPUT_LENGTH - question_len - prompt_len - docs_txt_len
    if conversation_history and max_len > 0:
        filter_conversation_history = state.get("conversation_history", []).copy()
        while calculate_context_length(filter_conversation_history) > max_len:
            if len(filter_conversation_history) > 2:
                filter_conversation_history = filter_conversation_history[2:]
            else:
                filter_conversation_history = []
        if filter_conversation_history:
            if filter_conversation_history:
                conversation_history_txt = "\n".join([
                    f"Turn {i//2 + 1} [{item['role']}]: {item['content']}"
                    for i, item in enumerate(filter_conversation_history)
                ])
    return conversation_history_txt


def add_qa_pair_to_context(state: GraphState) -> List[dict]:
    """
    manage dialogue context, controls its length to avoid exceeding the model's input limitations.

    Args:
        state: The current graph state

    Returns:
        updated dialogue history
    """
    # 获取当前对话历史
    history = state.get("conversation_history", []).copy()

    # 添加新的问答对
    history.append({
        "role": "user",
        "content": state["org_question"]
    })
    history.append({
        "role": "assistant",
        "content": state["generation"]
    })

    while calculate_context_length(history) > llm_provider.MAX_CHAT_MODEL_INPUT_LENGTH and len(history) > 2:
        history = history[2:]

    return history


def calculate_context_length(history: List[dict]) -> int:
    """
    Simply calculate context length (it's better to calculate the token length)

    Args:
        history: dialogue history

    Returns:
        the dialogue context length
    """
    total_length = 0
    for item in history:
        total_length += len(item.get("content", ""))
    return total_length


### Graph Nodes ###
def retrieve(state):
    """
    Retrieve documents

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, documents, that contains retrieved documents
    """
    print("---RETRIEVE---")
    question = state["question"]
    stream_writer = get_stream_writer()
    generation_id = state.get("generate_count", 0)
    stream_writer(f"{{\"type\": \"retrieve\", \"generate_id\": {generation_id}}}")

    # Retrieval
    documents = retriever.invoke(question)
    return {"documents": documents, "question": question, "datasource": "vectorstore"}


def generate(state):
    """
    Generate answer

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, generation, that contains LLM generation
    """
    print("---GENERATE---")
    question = state["question"]
    documents = state["documents"]

    # RAG generation
    docs_txt = format_docs(documents)
    generation = generator.invoke({"context": docs_txt, "question": question})
    return {"documents": documents, "question": question, "generation": generation}


def stream_generate(state):
    """
    Generate answer in streaming

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, generation, that contains LLM generation
    """
    print("---GENERATE (Streaming)---")
    question = state["question"]
    documents = state["documents"] if "documents" in state else []
    org_question = state.get("org_question", question)

    # RAG generation
    docs_txt = format_docs(documents)
    history_txt = get_coverage_history_txt(state, len(question), len(chains.GENERATE_PROMPT), len(docs_txt))
    collected = []
    stream_writer = get_stream_writer()
    generate_count = state.get("generate_count", 0) + 1
    stream_writer(f"{{\"type\": \"start\", \"generate_id\": {generate_count}}}")
    for chunk in generator.stream({"context": docs_txt, "question": question, "history": history_txt}):
        # streaming:
        stream_writer(f"{{\"type\": \"chunk\", \"generate_id\": {generate_count}, \"content\": \"{chunk}\"}}")
        collected.append(chunk)
    datasource = state.get("datasource", "generate_directly")
    return {"documents": documents, "question": question, "datasource": datasource, "generation": "".join(collected),
            "generate_count": generate_count, "max_generate_count": 15, "org_question": org_question}


def grade_documents(state):
    """
    Determines whether the retrieved documents are relevant to the question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates documents key with only filtered relevant documents
    """

    print("---CHECK DOCUMENT RELEVANCE TO QUESTION---")
    question = state["question"]
    documents = state["documents"]

    # Score each doc
    filtered_docs = []
    for d in documents:
        score = retrieval_grader.invoke(
            {"question": question, "document": d.page_content}
        )
        grade = score.binary_score
        if grade == "yes":
            print("---GRADE: DOCUMENT RELEVANT---")
            filtered_docs.append(d)
        else:
            print("---GRADE: DOCUMENT NOT RELEVANT---")
            continue
    return {"documents": filtered_docs, "question": question}


def transform_query(state):
    """
    Transform the query to produce a better question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates question key with a re-phrased question
    """

    print("---TRANSFORM QUERY---")
    question = state["question"]
    documents = state["documents"] if "documents" in state else []

    # Re-write question
    better_question = question_rewriter.invoke({"question": question})
    return {"documents": documents, "question": better_question}


def web_search(state):
    """
    Web search based on the re-phrased question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates documents key with appended web results
    """

    print("---WEB SEARCH---")
    question = state["question"]
    stream_writer = get_stream_writer()
    generation_id = state.get("generate_count", 0)
    stream_writer(f"{{\"type\": \"search\", \"generate_id\": {generation_id}}}")

    # Web search
    docs = web_search_tool.invoke({"query": question})
    documents = [Document(page_content=d["content"] if "content" in d else str(d)) for d in docs]
    return {"documents": documents, "question": question, "datasource": "web_search"}


def store_conversation(state):
    """
    store conversation history.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates conversation key with new question and answer
    """
    history = add_qa_pair_to_context(state)
    user_id = state.get("user_id", "default")

    def save_to_file():
        print("---Store CONVERSATION---")
        try:
            os.makedirs(CONVERSATION_HISTORY_STORE_FILE_DIR, exist_ok=True)
            store_path = os.path.join(CONVERSATION_HISTORY_STORE_FILE_DIR,
                                      CONVERSATION_HISTORY_STORE_FILE_NAME_PATTERN % user_id)
            # update history
            with open(store_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving conversation history: {e}")
    # async store history to file
    _executor.submit(save_to_file)


### Edges ###
def route_question(state):
    """
    Route question to web search or RAG.

    Args:
        state (dict): The current graph state

    Returns:
        str: Next node to call
    """

    print("---ROUTE QUESTION---")
    question = state["question"]
    stream_writer = get_stream_writer()
    stream_writer(f"{{\"type\": \"init\", \"generate_id\": 0}}")
    history_txt = get_coverage_history_txt(state, len(question), len(chains.ROUTE_PROMPT), 0)
    source = question_router.invoke({"question": question, "history": history_txt})
    if source.datasource == "web_search":
        print("---ROUTE QUESTION TO WEB SEARCH---")
        return "web_search"
    elif source.datasource == "vectorstore":
        print("---ROUTE QUESTION TO RAG---")
        return "vectorstore"
    elif source.datasource == "generate_directly":
        print("---ROUTE QUESTION TO GENERATE DIRECTLY---")
        return "generate_directly"


def decide_to_generate(state):
    """
    Determines whether to generate an answer, or re-generate a question.

    Args:
        state (dict): The current graph state

    Returns:
        str: Binary decision for next node to call
    """

    print("---ASSESS GRADED DOCUMENTS---")
    filtered_documents = state["documents"] if "documents" in state else []

    if not filtered_documents:
        # All documents have been filtered check_relevance
        # We will re-generate a new query
        print(
            "---DECISION: ALL DOCUMENTS ARE NOT RELEVANT TO QUESTION, TRANSFORM QUERY---"
        )
        return "transform_query"
    else:
        # We have relevant documents, so generate answer
        print("---DECISION: GENERATE---")
        return "generate"


def grade_generation_v_documents_and_question(state):
    """
    Determines whether the generation is grounded in the document and answers question.

    Args:
        state (dict): The current graph state

    Returns:
        str: Decision for next node to call
    """
    limit = state["max_generate_count"]
    current = state["generate_count"]
    stream_writer = get_stream_writer()
    if current >= limit:
        # 发送终止标记
        stream_writer(f"{{\"type\": \"final\", \"generate_id\": {current}}}")
        print("---Reach the generate limit, return---")
        store_conversation(state)
        return "useful"

    question = state["question"]
    documents = state["documents"]
    generation = state["generation"]

    if state["datasource"] == "generate_directly":
        grade = "yes"
    else:
        print("---CHECK HALLUCINATIONS---")
        score = hallucination_grader.invoke(
            {"documents": documents, "generation": generation}
        )
        grade = score.binary_score

    # Check hallucination
    if grade == "yes":
        if state["datasource"] != "generate_directly":
            print("---DECISION: GENERATION IS GROUNDED IN DOCUMENTS---")
        # Check question-answering
        print("---GRADE GENERATION vs QUESTION---")
        score = answer_grader.invoke({"question": question, "generation": generation})
        grade = score.binary_score
        if grade == "yes":
            # 发送终止标记
            stream_writer(f"{{\"type\": \"final\", \"generate_id\": {current}}}")
            print("---DECISION: GENERATION ADDRESSES QUESTION---")
            store_conversation(state)
            return "useful"
        else:
            # 发送结束标记
            stream_writer(f"{{\"type\": \"end\", \"generate_id\": {current}}}")
            print("---DECISION: GENERATION DOES NOT ADDRESS QUESTION---")
            return "not useful"
    else:
        # 发送结束标记
        stream_writer(f"{{\"type\": \"end\", \"generate_id\": {current}}}")
        print("---DECISION: GENERATION IS NOT GROUNDED IN DOCUMENTS, RE-TRY---")
        return "not supported"


def build_graph():

    workflow = StateGraph(GraphState)

    # Define the nodes
    workflow.add_node("web_search", web_search)  # web search
    workflow.add_node("retrieve", retrieve)  # retrieve
    workflow.add_node("grade_documents", grade_documents)  # grade documents
    workflow.add_node("generate", stream_generate)  # generate
    workflow.add_node("transform_query", transform_query)  # transform_query

    # Build graph
    workflow.add_conditional_edges(
        START,
        route_question,
        {
            "web_search": "web_search",
            "vectorstore": "retrieve",
            "generate_directly": "generate",
        },
    )
    workflow.add_edge("web_search", "generate")
    workflow.add_edge("retrieve", "grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {
            "transform_query": "transform_query",
            "generate": "generate",
        },
    )
    workflow.add_conditional_edges(
        "transform_query",
        lambda state: state["datasource"],
        {
            "web_search": "web_search",
            "vectorstore": "retrieve",
            "generate_directly": "generate",
        },
    )
    workflow.add_conditional_edges(
        "generate",
        grade_generation_v_documents_and_question,
        {
            "not supported": "generate",
            "useful": END,
            "not useful": "transform_query",
        },
    )

    # Compile
    return workflow.compile()


_app = build_graph()


def load_conversation_history(user_id: str = None) -> List[dict]:
    """
    gte conversion history for stored file

    Args:
        user_id: user id，default is 'default'

    Returns:
        List[dict]: conversation history list
    """
    user_id = user_id or 'default'
    try:
        os.makedirs(CONVERSATION_HISTORY_STORE_FILE_DIR, exist_ok=True)
        store_path = os.path.join(CONVERSATION_HISTORY_STORE_FILE_DIR,
                                  CONVERSATION_HISTORY_STORE_FILE_NAME_PATTERN % user_id)
        if os.path.exists(store_path):
            with open(store_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"Error loading conversation history: {e}")
        return []


def stream_answer(question: str, user_id: str = None) -> Iterator[str]:
    user_id = user_id or 'default'
    conversation_history = load_conversation_history(user_id)
    inputs = {
        "user_id": user_id,
        "question": question,
        "conversation_history": conversation_history,
    }
    for chunk in _app.stream(inputs, stream_mode="custom"):
        if isinstance(chunk, str):
            try:
                chunk_data = json.loads(chunk)
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse chunk as JSON: {chunk}. Error: {e}")
                continue
        else:
            chunk_data = chunk
        chunk_type = chunk_data.get("type", "")
        generate_id = chunk_data.get("generate_id", -1)
        if generate_id >= 0:
            if chunk_type == "init":
                # 初始化标记
                yield "[Thinking...]\n"
            elif chunk_type == "search":
                # 启动标记
                yield "[Searching on web...]\n"
            elif chunk_type == "retrieve":
                # 启动标记
                yield "[Referencing on knowledge base...]\n"
            elif chunk_type == "start":
                # 开始标记
                yield "[Answer]\n"
            elif chunk_type == "end":
                # 结束标记
                yield "\n[Re-thinking to find a better answer...]\n"
            elif chunk_type == "final":
                yield ""
            else:
                yield chunk_data.get("content", "")


def answer(question: str, user_id: str = None) -> str:
    user_id = user_id or 'default'
    conversation_history = load_conversation_history(user_id)
    inputs = {
        "user_id": user_id,
        "question": question,
        "conversation_history": conversation_history,
    }
    result = _app.invoke(inputs)
    if "generation" in result:
        return result["generation"]
    return ""
