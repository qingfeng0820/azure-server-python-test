import asyncio

from langgraph_hierarchical_agent_teams import teams_graph as graph


async def test_research_team():
    async for s in graph.research_graph.astream(
            {"messages": [("user", "when is Taylor Swift's next tour?")]},
            {"recursion_limit": 100},
    ):
        print(s)
        print("---")


async def test_paper_writing_team():
    async for s in graph.paper_writing_graph.astream(
            {
                "messages": [
                    (
                            "user",
                            "Write a outline for a poem about cats and then write the poem to disk.",
                    )
                ]
            },
            {"recursion_limit": 100},
    ):
        print(s)
        print("---")


async def test_super_graph():
    async for s in graph.super_graph.astream(
            {
                "messages": [
                    ("user", "Research AI agents and write a brief report about them.")
                ],
            },
            {"recursion_limit": 150},
    ):
        print(s)
        print("---")


async def test_super_graph_invoke():
    print(await graph.super_graph.ainvoke({
                "messages": [
                    ("user", "Research AI agents and write a brief report about them.")
                ],
            }))


async def test_graph_answer():
    async for m in graph.answer("Research AI agents and write a brief report about them."):
        print(m)


if __name__ == "__main__":
    asyncio.run(test_graph_answer())
