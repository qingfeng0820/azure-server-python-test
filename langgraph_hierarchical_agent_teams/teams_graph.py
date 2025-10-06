import asyncio
from typing import Literal, Optional, AsyncGenerator

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.types import Command
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from pydantic import field_validator, BaseModel

from comm import llm_provider
from langgraph_hierarchical_agent_teams import tools


class State(MessagesState):
    next: str
    stream: bool = True
    stream_writer: Optional[callable] = None


async def stream_react_agent(node_name, agent, state: State):
    messages = []
    async for event in agent.astream_events(state):
        event_type = event.get("event", "")
        data = event.get("data", {})
        # print(event_type)
        if event_type == "on_chat_model_stream":
            chunk = data.get("chunk", {})
            if chunk and not getattr(chunk, "tool_calls", None) and not getattr(chunk, "tool_call_chunks", None):
                if chunk.content:
                    token = chunk.content
                    total_tokens = chunk.usage_metadata.get("total_tokens", 0)
                    input_tokens = chunk.usage_metadata.get("input_tokens", 0)
                    if total_tokens - input_tokens == 1 and token == "\n":
                        # ignore
                        continue
                    token_message = HumanMessage(token, name=node_name)
                    state["stream_writer"](token_message)
        elif event_type == "on_chain_end" and event.get("name", "") == "LangGraph":
            output = data.get("output", {})
            if "messages" in output:
                messages = output["messages"]
    return {"messages": messages}


def make_supervisor_node(llm: BaseChatModel, members: list[str]):
    options = ["FINISH"] + members
    system_prompt = (
        "You are a supervisor tasked with managing a conversation between the"
        f" following workers: {members}. Given the following user request,"
        " respond with the worker to act next. Each worker will perform a"
        " task and respond with their results and status. When finished,"
        " respond with FINISH."
    )

    class Router(BaseModel):
        """Worker to route to next. If no workers needed, route to FINISH."""

        next: str

        @field_validator('next')
        def validate_next(cls, v):
            if v not in options:
                raise ValueError(f"next must be one of {options}")
            return v

    def supervisor_node(state: State) -> Command:
        print("=== Supervisor routing ===")
        """An LLM-based router."""
        messages = [
            {"role": "system", "content": system_prompt},
        ] + state["messages"]
        response = llm.with_structured_output(Router).invoke(messages)
        goto = response.next
        if goto == "FINISH":
            goto = END

        print(f"{{\"supervisor\": \"next\": {goto}}}")
        return Command(goto=goto, update={"next": goto})

    return supervisor_node


llm = llm_provider.get_chat_model()

### Research Team ###
search_agent = create_react_agent(llm, tools=[tools.tavily_tool])


async def search_node(state: State) -> Command[Literal["supervisor"]]:
    # result = search_agent.invoke(state)
    print("=== Call search ===")
    result = await stream_react_agent("search", search_agent, state)
    return Command(
        update={
            "messages": [
                HumanMessage(content=result["messages"][-1].content, name="search")
            ]
        },
        # We want our workers to ALWAYS "report back" to the supervisor when done
        goto="supervisor",
    )


web_scraper_agent = create_react_agent(llm, tools=[tools.scrape_webpages])


async def web_scraper_node(state: State) -> Command[Literal["supervisor"]]:
    # result = web_scraper_agent.invoke(state)
    print("=== Call web scraper ===")
    result = await stream_react_agent("web_scraper", web_scraper_agent, state)
    return Command(
        update={
            "messages": [
                HumanMessage(content=result["messages"][-1].content, name="web_scraper")
            ]
        },
        # We want our workers to ALWAYS "report back" to the supervisor when done
        goto="supervisor",
    )


research_supervisor_node = make_supervisor_node(llm, ["search", "web_scraper"])


### Document Writing Team ###
doc_writer_agent = create_react_agent(
    llm,
    tools=[tools.write_document, tools.edit_document, tools.read_document],
    prompt=(
        "You can read, write and edit documents based on note-taker's outlines. "
        "Don't ask follow-up questions."
    ),
)


async def doc_writing_node(state: State) -> Command[Literal["supervisor"]]:
    # result = doc_writer_agent.invoke(state)
    print("=== Call doc writer ===")
    result = await stream_react_agent("doc_writer", doc_writer_agent, state)
    return Command(
        update={
            "messages": [
                HumanMessage(content=result["messages"][-1].content, name="doc_writer")
            ]
        },
        # We want our workers to ALWAYS "report back" to the supervisor when done
        goto="supervisor",
    )


note_taking_agent = create_react_agent(
    llm,
    tools=[tools.create_outline, tools.read_document],
    prompt=(
        "You can read documents and create outlines for the document writer. "
        "Don't ask follow-up questions."
    ),
)


async def note_taking_node(state: State) -> Command[Literal["supervisor"]]:
    # result = note_taking_agent.invoke(state)
    print("=== Call note taker ===")
    result = await stream_react_agent("note_taker", note_taking_agent, state)
    return Command(
        update={
            "messages": [
                HumanMessage(content=result["messages"][-1].content, name="note_taker")
            ]
        },
        # We want our workers to ALWAYS "report back" to the supervisor when done
        goto="supervisor",
    )


chart_generating_agent = create_react_agent(
    llm, tools=[tools.read_document, tools.python_repl_tool]
)


async def chart_generating_node(state: State) -> Command[Literal["supervisor"]]:
    # result = chart_generating_agent.invoke(state)
    print("=== Call chart generator ===")
    result = await stream_react_agent("chart_generator", chart_generating_agent, state)
    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=result["messages"][-1].content, name="chart_generator"
                )
            ]
        },
        # We want our workers to ALWAYS "report back" to the supervisor when done
        goto="supervisor",
    )


doc_writing_supervisor_node = make_supervisor_node(
    llm, ["doc_writer", "note_taker", "chart_generator"]
)


def build_research_graph():
    research_builder = StateGraph(State)
    research_builder.add_node("supervisor", research_supervisor_node)
    research_builder.add_node("search", search_node)
    research_builder.add_node("web_scraper", web_scraper_node)

    research_builder.add_edge(START, "supervisor")
    research_graph = research_builder.compile()
    return research_graph


def build_paper_writing_graph():
    paper_writing_builder = StateGraph(State)
    paper_writing_builder.add_node("supervisor", doc_writing_supervisor_node)
    paper_writing_builder.add_node("doc_writer", doc_writing_node)
    paper_writing_builder.add_node("note_taker", note_taking_node)
    paper_writing_builder.add_node("chart_generator", chart_generating_node)

    paper_writing_builder.add_edge(START, "supervisor")
    paper_writing_graph = paper_writing_builder.compile()
    return paper_writing_graph


research_graph = build_research_graph()
paper_writing_graph = build_paper_writing_graph()


# async def stream_graph(graph_app, state: State):
#     response = {}
#     messages = []
#     # stream_mode = "custom" if state["stream_writer"] else None
#     async for s in graph_app.astream(
#             {"messages": state["messages"][-1], "stream_writer": state["stream_writer"]},
#             {"recursion_limit": 150},
#             # stream_mode=stream_mode,
#     ):
#         if type(s) is dict and len(s) > 0:
#             v = next(iter(s.values()))
#             if type(v) is dict and "messages" in v:
#                 messages = v["messages"]
#     if messages:
#         response = {"messages": messages}
#     return response


async def call_research_team(state: State) -> Command[Literal["supervisor"]]:
    # response = await stream_graph(research_graph, state)
    print("=== Call research team ===")
    response = await research_graph.ainvoke({"messages": state["messages"][-1],
                                             "stream_writer": state["stream_writer"]},
                                            {"recursion_limit": 150})
    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=response["messages"][-1].content if response else "", name="research_team"
                )
            ]
        },
        goto="supervisor",
    )


async def call_paper_writing_team(state: State) -> Command[Literal["supervisor"]]:
    # response = await stream_graph(paper_writing_graph, state)
    print("=== Call document writing team ===")
    response = await paper_writing_graph.ainvoke({"messages": state["messages"][-1],
                                                  "stream_writer": state["stream_writer"]},
                                                 {"recursion_limit": 150})
    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=response["messages"][-1].content if response else "", name="writing_team"
                )
            ]
        },
        goto="supervisor",
    )


general_qa_agent = create_react_agent(
    llm,
    tools=[tools.tavily_tool],  # 可以添加适当的工具
    prompt=(
        "You are a helpful assistant that can answer general questions about the system when there is no response yet,"
        " explain behaviors, and provide detailed responses to user inquiries."
        " If you don't know the answer, just say that you don't know."
        " Use three sentences maximum and keep the answer concise."
    ),
)


async def general_qa_node(state: State) -> Command[Literal["supervisor"]]:
    print("=== Call general QA ===")
    result = await stream_react_agent("general_qa", general_qa_agent, state)
    return Command(
        update={
            "messages": [
                HumanMessage(content=result["messages"][-1].content, name="general_qa")
            ]
        },
        goto="supervisor",
    )


teams_supervisor_node = make_supervisor_node(llm, ["research_team", "writing_team",  "general_qa"])


# Define the parent teams graph.
def build_super_graph():
    super_builder = StateGraph(State)
    super_builder.add_node("supervisor", teams_supervisor_node)
    super_builder.add_node("research_team", call_research_team)
    super_builder.add_node("writing_team", call_paper_writing_team)
    super_builder.add_node("general_qa", general_qa_node)

    super_builder.add_edge(START, "supervisor")
    super_graph = super_builder.compile()
    return super_graph


super_graph = build_super_graph()


async def answer(question: str, user_id: str = None) -> AsyncGenerator[str, None]:
    user_id = user_id or 'default'

    # 使用队列收集流式数据
    queue = asyncio.Queue()

    def stream_writer(message):
        queue.put_nowait(message)

    inputs = {
        "user_id": user_id,
        "messages": [("user", question)],
        "stream_writer": stream_writer  # 传入 stream_writer
    }

    async def run_graph():
        try:
            await super_graph.ainvoke(inputs)
        finally:
            # 发送结束信号
            queue.put_nowait(None)

    task = asyncio.create_task(run_graph())
    previous_node_name = ""
    try:
        # 流式返回消息
        while True:
            message = await queue.get()
            if message is None:  # 结束信号
                break
            content = message.content
            node_name = message.name
            if node_name != previous_node_name:
                if previous_node_name:
                    yield f"\n[{node_name}]: "
                else:
                    yield f"[{node_name}]: "
                previous_node_name = node_name
            yield content
    finally:
        # 确保任务完成
        await task
