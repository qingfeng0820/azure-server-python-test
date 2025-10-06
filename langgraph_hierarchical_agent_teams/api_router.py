from typing import Union, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse

import teams_graph as graph
from auth.security import get_current_user, require_login

teams_router = APIRouter()


class QuestionRequest(BaseModel):
    question: str
    stream: Union[Literal["answer", "detail"], bool] = False


@teams_router.post('/chat/ask')
@require_login()
async def ask_question(request: Request, question: QuestionRequest):
    current_user = await get_current_user(request)
    return StreamingResponse(graph.answer(question.question, current_user.id), media_type="application/json")


@teams_router.get("/chat/history")
@require_login()
async def conversation(request: Request):
    current_user = await get_current_user(request)
    ret = []
    return ret
