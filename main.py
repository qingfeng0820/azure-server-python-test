import os
import sys
import threading
import time
from urllib.parse import quote
from contextlib import asynccontextmanager

from bson import ObjectId
from fastapi import FastAPI, Form, Request, Response, status, HTTPException
from fastapi.params import Depends
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import traceback

import test_sqlserver
import mongodb_client
from auth.models import User
from auth.security import cleanup_expired_cache, require_login, logout_user, login_user, get_current_user

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "langgraph_adaptive_rag"))
from langgraph_adaptive_rag.api_router import router


SESSION_CLEANUP_PERIOD = os.environ["SESSION_CLEANUP_PERIOD"] if "SESSION_CLEANUP_PERIOD" in os.environ else 3600


@asynccontextmanager
async def lifespan(app: FastAPI):
    def periodic_cleanup():
        while True:
            try:
                cleanup_expired_cache()
            except Exception as e:
                print(f"Cache cleanup error: {e}")
            time.sleep(SESSION_CLEANUP_PERIOD)

    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()
    # the code before yield will be executed during the app running
    yield
    # the code after yield will be executed during the app shutdown


class ProtectedStaticFiles(StaticFiles):
    async def __call__(self, scope, receive, send) -> None:
        request = Request(scope, receive)
        redirect_url = f"/login?url={quote(str(request.url))}"
        try:
            current_user = await get_current_user(request)
            if not current_user:
                response = RedirectResponse(url=redirect_url)
                await response(scope, receive, send)
                return
        except:
            response = RedirectResponse(url=redirect_url)
            await response(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/rag", ProtectedStaticFiles(directory="front-rag-react/dist"), name="rag")
templates = Jinja2Templates(directory="templates")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://shmtest-ahepbqhwbbaxf3cy.eastasia-01.azurewebsites.net",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)

app.include_router(router, prefix='/ai', tags=['ai'])


@app.get("/", response_class=HTMLResponse)
@require_login("/login")
async def index(request: Request):
    return templates.TemplateResponse('index.html', {"request": request})


@app.get('/favicon.ico')
async def favicon():
    file_name = 'favicon.ico'
    file_path = './static/' + file_name
    return FileResponse(path=file_path, headers={'mimetype': 'image/vnd.microsoft.icon'})


@app.post('/hello', response_class=HTMLResponse)
@require_login()
async def hello(request: Request, name: str = Form(...)):
    if name:
        print('Request for hello page received with name=%s' % name)
        return templates.TemplateResponse('hello.html', {"request": request, 'name': name})
    else:
        print('Request for hello page received with no name or blank name -- redirecting')
        return RedirectResponse(request.url_for("index"), status_code=status.HTTP_302_FOUND)


@app.get('/test_users/{user_id}')
@require_login()
async def get_test_user(request: Request, user_id: int):
    try:
        return test_sqlserver.get_user_by_id(user_id)
    except Exception as e:
        # 记录完整错误信息到日志
        error_traceback = traceback.format_exc()
        print(f"Error fetching user {user_id}: {error_traceback}")

        raise HTTPException(
            status_code=500,
            detail=f"Error fetching user {user_id}: {str(e)}"
        )


@app.get('/test_products/{product_id}', response_model=dict)
@require_login()
async def get_test_product(request: Request, product_id: str):
    prod = await mongodb_client.AsyncMongoDBClient("testdb").find_one("product",
                                                                      {"_id": ObjectId(product_id)})
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    prod["id"] = str(prod["_id"])
    del prod["_id"]
    return prod


@app.post("/login")
async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    access_token = await login_user(form_data.username, form_data.password)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,     # 防止XSS攻击
        # secure=True,       # 仅在HTTPS下传输
        samesite="lax",    # 防止CSRF攻击
        max_age=3600,      # 过期时间（秒）
        path="/"           # Cookie路径
    )
    return {"message": "Login successful"}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/users/me", response_model=User)
@require_login()
async def read_users_me(request: Request):
    return await get_current_user(request)


@app.get("/logout")
@require_login()
async def logout(request: Request, response: Response):
    current_user = await get_current_user(request)
    await logout_user(current_user.username)
    response.delete_cookie(
        key="access_token",
        path="/",  # 与设置时保持一致
        # domain="example.com"  # 如果设置了domain也需要指定
    )
    return {"message": "Logout successful"}


if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8000)
