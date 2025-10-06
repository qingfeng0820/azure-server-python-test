import os

import chromadb
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

from comm import llm_provider

CHUNK_SIZE = os.environ["EMBED_CHUNK_SIZE"] if "EMBED_CHUNK_SIZE" in os.environ else 500
CHUNK_OVERLAP = os.environ["EMBED_CHUNK_OVERLAP"] if "EMBED_CHUNK_OVERLAP" in os.environ else 20


def load_websites_to_index(collection_name, urls, chuck_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
                           embed_model=None, persist_directory="./chroma_db"):
    # Load
    docs = [WebBaseLoader(url).load() for url in urls]
    docs_list = [item for sublist in docs for item in sublist]
    # Split
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=chuck_size, chunk_overlap=chunk_overlap
    )
    doc_splits = text_splitter.split_documents(docs_list)
    if embed_model is None:
        embed_model = llm_provider.get_embedding_model()
    total_len = len(doc_splits)
    finished = 0
    while finished < total_len:
        batch = doc_splits[finished:min(finished + llm_provider.EMBED_MODEL_BATCH_SIZE, total_len)]
        Chroma.from_documents(
            documents=batch,
            collection_name=collection_name,
            embedding=embed_model,
            persist_directory=persist_directory
        )
        finished = min(finished + llm_provider.EMBED_MODEL_BATCH_SIZE, total_len)
    print(f"Finished loading {finished} docs")


def get_retriever(collection_name, embed_model=None, persist_directory="./chroma_db"):
    if embed_model is None:
        embed_model = llm_provider.get_embedding_model()
    return Chroma(
        collection_name=collection_name,
        embedding_function=embed_model,
        persist_directory=persist_directory
    ).as_retriever()


def get_collection(collection_name, persist_directory="./chroma_db"):
    client = chromadb.PersistentClient(path=persist_directory)
    try:
        return client.get_collection(collection_name)
    except Exception as e:
        if "does not exist" in str(e):
            return None
        else:
            raise e
