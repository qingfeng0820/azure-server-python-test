import os

from langchain_openai import OpenAIEmbeddings, ChatOpenAI

from comm.util import singleton

EMBED_MODEL_BATCH_SIZE = os.environ["EMBED_MODEL_BATCH_SIZE"] if "EMBED_MODEL_BATCH_SIZE" in os.environ else 32
MAX_CHAT_MODEL_INPUT_LENGTH = os.environ["MAX_CHAT_MODEL_INPUT_LENGTH"] \
    if "MAX_CHAT_MODEL_INPUT_LENGTH" in os.environ else 40960


@singleton
def get_chat_model():
    conf = _get_model_conf()
    return ChatOpenAI(
        model=conf["chat_model_name"],
        base_url=conf["base_url"],
        api_key=conf["api_key"],
        temperature=0
    )


@singleton
def get_embedding_model():
    conf = _get_model_conf()
    return OpenAIEmbeddings(
        model=conf["embed_model_name"],
        base_url=conf["base_url"],
        api_key=conf["api_key"]
    )


def _get_model_conf():
    return {
        "base_url": os.environ["MODEL_URL"],
        "api_key": os.environ["MODEL_API_KEY"],
        "embed_model_name": os.environ["EMBED_MODEL_NAME"] if "EMBED_MODEL_NAME" in os.environ else "text-embedding-ada-002",
        "chat_model_name": os.environ["CHAT_MODEL_NAME"] if "CHAT_MODEL_NAME" in os.environ else "gpt-4o-mini"
    }
