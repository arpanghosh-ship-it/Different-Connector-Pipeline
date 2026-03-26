import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import router as auth_router, load_credentials
from crawler import start_crawl, set_root_folder, get_root_folder, list_drive_folders
from poller import start_poller, stop_poller, is_polling, pause_poller, resume_poller
from storage import get_all_stored_files
from duplicate_check import total_visited
from events import add_listener, remove_listener
from config import FRONTEND_URL


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    stop_poller()


app = FastAPI(title='Drive Connector API', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, 'http://localhost:5173', 'http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)


class StartCrawlRequest(BaseModel):
    folder_id: str
    folder_name: str = ''


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/status')
def status():
    root = get_root_folder()
    return {
        'authenticated': load_credentials() is not None,
        'root_folder': root,
        'polling': is_polling(),
        'total_files_stored': total_visited(),
    }


@app.get('/api/folders')
async def get_folders(parent_id: str = 'root'):
    creds = load_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail='Not authenticated')
    folders = await list_drive_folders(parent_id)
    return {'folders': folders}


@app.post('/api/start-crawl')
async def trigger_crawl(body: StartCrawlRequest):
    creds = load_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail='Not authenticated')
    set_root_folder(body.folder_id, body.folder_name)
    start_poller(body.folder_id, body.folder_name)
    asyncio.create_task(start_crawl(body.folder_id, body.folder_name))
    return {'message': 'Crawl started', 'folder_id': body.folder_id, 'folder_name': body.folder_name}


@app.get('/api/files')
def list_files():
    return {'files': get_all_stored_files()}


@app.post('/api/stop-poll')
def stop_poll():
    pause_poller()
    return {'polling': False, 'message': 'Polling paused'}


@app.post('/api/start-poll')
def start_poll():
    resume_poller()
    return {'polling': True, 'message': 'Polling resumed'}


@app.get('/api/events')
async def sse_stream(request: Request):
    queue = add_listener()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        finally:
            remove_listener(queue)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
