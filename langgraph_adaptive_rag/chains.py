from typing import Literal

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

import llm_provider

GENERATE_PROMPT = """You are an assistant for question-answering tasks.
Use the following pieces of retrieved context or conversation history to answer the question.
If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.

Question: {question}
Context: {context}
Conversation History:
{history}
Answer:
"""

ROUTE_PROMPT = """You are an expert at routing a user question to the most appropriate datasource.

The vectorstore contains documents related to agents, prompt engineering, and adversarial attacks.
Use the vectorstore ONLY for questions specifically about these topics.

For all other questions, follow this decision process:
1. If the question can be answered using general knowledge or the Conversation History, generate the answer directly
2. If the question requires up-to-date information or external facts not available in general knowledge or conversation history, use web-search

Special cases:
- Questions about previous interactions, conversation history, or meta-questions about the chat itself should be generated directly
- Questions that reference specific content from the conversation history should be generated directly

Conversation History: 
{history}

Question: {question}
"""

# ROUTE_PROMPT = """You are an expert at routing a user question to a vectorstore or web search or generating directly.
# The vectorstore contains documents related to agents, prompt engineering, and adversarial attacks.
# Use the vectorstore for questions on these topics.
# Otherwise, if you can answer it based on your knowledge or the Conversation History, generate the answer directly.
# If you can not answer the question, use web-search.
# Conversation History:
# {history}
# """


# Data model
class RouteQuery(BaseModel):
    """Route a user query to the most relevant datasource."""

    datasource: Literal["vectorstore", "web_search", "generate_directly"] = Field(
        ...,
        description="Given a user question choose to route it to web search or a vectorstore.",
    )


def route_query_chain():
    # LLM with function call
    llm = llm_provider.get_chat_model()
    # 0.3.27对with_structured_output没问题，0.3.33对with_structured_output有bug
    structured_llm_router = llm.with_structured_output(RouteQuery)

    # Prompt
    route_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ROUTE_PROMPT),
            ("human", "{question}"),
        ]
    )

    return route_prompt | structured_llm_router


# Data model
class GradeDocuments(BaseModel):
    """Binary score for relevance check on retrieved documents."""

    binary_score: str = Field(
        description="Documents are relevant to the question, 'yes' or 'no'"
    )


def retrieval_grader_chain():
    # LLM with function call
    llm = llm_provider.get_chat_model()
    structured_llm_grader = llm.with_structured_output(GradeDocuments)

    # Prompt
    system = """You are a grader assessing relevance of a retrieved document to a user question. \n 
        If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. \n
        It does not need to be a stringent test. The goal is to filter out erroneous retrievals. \n
        Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question."""
    grade_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", "Retrieved document: \n\n {document} \n\n User question: {question}"),
        ]
    )
    return grade_prompt | structured_llm_grader


def generate_answer_chain(streaming=True):
    # Prompt
    # prompt = util.get_prompt_from_hub("rlm/rag-prompt")
    prompt = ChatPromptTemplate.from_template(GENERATE_PROMPT)
    # LLM
    llm = llm_provider.get_chat_model()
    if streaming:
        llm = llm.bind(stream=streaming)
    return prompt | llm | StrOutputParser()


# Data model
class GradeAnswer(BaseModel):
    """Binary score to assess answer addresses question."""

    binary_score: str = Field(
        description="Answer addresses the question, 'yes' or 'no'"
    )


def answer_grader_chain():
    # LLM with function call
    llm = llm_provider.get_chat_model()
    structured_llm_grader = llm.with_structured_output(GradeAnswer)

    # Prompt
    system = """You are a grader assessing whether an answer addresses / resolves a question \n 
         Give a binary score 'yes' or 'no'. Yes' means that the answer resolves the question."""
    answer_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", "User question: \n\n {question} \n\n LLM generation: {generation}"),
        ]
    )

    return answer_prompt | structured_llm_grader


# Data model
class GradeHallucinations(BaseModel):
    """Binary score for hallucination present in generation answer."""

    binary_score: str = Field(
        description="Answer is grounded in the facts, 'yes' or 'no'"
    )


def hallucination_grader_chain():
    # LLM with function call
    llm = llm_provider.get_chat_model()
    structured_llm_grader = llm.with_structured_output(GradeHallucinations)

    # Prompt
    system = """You are a grader assessing whether an LLM generation is grounded in / supported by a set of retrieved facts. \n 
     Give a binary score 'yes' or 'no'. 'Yes' means that the answer is grounded in / supported by the set of facts."""
    hallucination_prompt = ChatPromptTemplate.from_messages (
        [
            ("system", system),
            ("human", "Set of facts: \n\n {documents} \n\n LLM generation: {generation}"),
        ]
    )
    return hallucination_prompt | structured_llm_grader


def question_rewriter_chain():
    # LLM
    llm = llm_provider.get_chat_model()

    # Prompt
    system = """You a question re-writer that converts an input question to a better version that is optimized \n 
         for vectorstore retrieval. Look at the input and try to reason about the underlying semantic intent / meaning."""
    re_write_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            (
                "human",
                "Here is the initial question: \n\n {question} \n Formulate an improved question.",
            ),
        ]
    )

    return re_write_prompt | llm | StrOutputParser()
