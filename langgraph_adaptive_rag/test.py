
import graph


### test methods ###

def test_query_node():
    print(
        graph.question_router.invoke(
            {"question": "Who will the Bears draft first in the NFL draft?"}
        )
    )
    print(graph.question_router.invoke({"question": "What are the types of agent memory?"}))


def test_retrieval_grader(question):
    docs = graph.retriever.invoke(question)
    doc_txt = docs[1].page_content
    print(graph.retrieval_grader.invoke({"question": question, "document": doc_txt}))


def test_generate_in_stream(question):
    docs = graph.retriever.invoke(question)
    docs_txt = graph.format_docs(docs)
    generation = graph.generator.invoke({"context": docs_txt, "question": question})
    for token in generation:
        print(token, end="", flush=True)  # 实时显示


def test_generate(question):
    docs = graph.retriever.invoke(question)
    docs_txt = graph.format_docs(docs)
    generation = graph.generator.invoke({"context": docs_txt, "question": question})
    print(generation)
    return generation


def test_answer_grader(question):
    generation = test_generate(question)
    print(graph.answer_grader.invoke({"question": question, "generation": generation}))


def test_hallucination_grader(question):
    generation = test_generate(question)
    docs = graph.retriever.invoke(question)
    print(
        graph.hallucination_grader.invoke(
            {"documents": docs, "generation": generation}
        )
    )


def test_question_rewriter(question):
    print(graph.question_rewriter.invoke({"question": question}))


def test_web_search_tool(question):
    print(graph.web_search_tool.run(question))


def test_graph_stream_answer(question):
    for chunk in graph.stream_answer(question):
        print(f"\033[94m{chunk}\033[0m", end="")
    print("\n")


def test_graph_answer(question):
    print(graph.answer(question))


if __name__ == "__main__":
    test_graph_stream_answer("agent memory")
