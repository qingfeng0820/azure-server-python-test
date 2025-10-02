import os
import threading
from functools import wraps
from langchain import hub

os.environ["LANGCHAIN_HUB_CACHE"] = "./langchain_hub_cache"


def singleton(func):
    instances = {}
    lock = threading.Lock()

    @wraps(func)
    def wrapper(*args, **kwargs):
        key = (func.__name__, str(args), str(kwargs))
        if key not in instances:
            with lock:
                # 双重检查锁定
                if key not in instances:
                    instances[key] = func(*args, **kwargs)
        return instances[key]

    return wrapper


@singleton
def get_prompt_from_hub(prompt_id):
    return hub.pull(prompt_id)
