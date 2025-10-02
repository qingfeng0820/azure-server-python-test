from typing import Union, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse

import graph
from auth.security import get_current_user, require_login

router = APIRouter()


class QuestionRequest(BaseModel):
    question: str
    stream: Union[Literal["answer", "detail"], bool] = False


@router.post('/chat/ask')
@require_login()
async def ask_question(request: Request, question: QuestionRequest):
    current_user = await get_current_user(request)
    if question.stream:
        def stream_generator():
            for chunk in graph.stream_answer(question.question, current_user.id):
                yield chunk
        return StreamingResponse(stream_generator(), media_type="application/json")
    else:
        answer = graph.answer(question.question, current_user.id)
        return {"answer": answer, "status": "success"}


@router.get("/chat/history")
@require_login()
async def conversation(request: Request):
    current_user = await get_current_user(request)
    conversation_list = graph.load_conversation_history(current_user.id)
    ret = []
    for i in range(0, len(conversation_list), 2):
        if i + 1 < len(conversation_list):
            ret.append({
                "question": conversation_list[i]["content"],
                "answer": conversation_list[i + 1]["content"]
            })
    return ret
