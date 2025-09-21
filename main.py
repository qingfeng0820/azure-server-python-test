from fastapi import FastAPI, Form, Request, status, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import traceback

# import test_sqlserver


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    print('Request for index page received')
    return templates.TemplateResponse('index.html', {"request": request})


@app.get('/favicon.ico')
async def favicon():
    file_name = 'favicon.ico'
    file_path = './static/' + file_name
    return FileResponse(path=file_path, headers={'mimetype': 'image/vnd.microsoft.icon'})


@app.post('/hello', response_class=HTMLResponse)
async def hello(request: Request, name: str = Form(...)):
    if name:
        print('Request for hello page received with name=%s' % name)
        return templates.TemplateResponse('hello.html', {"request": request, 'name': name})
    else:
        print('Request for hello page received with no name or blank name -- redirecting')
        return RedirectResponse(request.url_for("index"), status_code=status.HTTP_302_FOUND)


@app.get('/users/{user_id}')
async def get_user(user_id: int):
    try:
        import test_sqlserver
        return test_sqlserver.get_user_by_id(user_id)
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching user {user_id}: {str(e)}"
        )
    except Exception as e:
        # 记录完整错误信息到日志
        error_traceback = traceback.format_exc()
        print(f"Error fetching user {user_id}: {error_traceback}")

        raise HTTPException(
            status_code=500,
            detail=f"Error fetching user {user_id}: {str(e)}"
        )


if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8000)
