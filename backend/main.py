import asyncio
import hashlib
import hmac
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from auth import router as auth_router, load_credentials
from crawler import start_crawl, set_root_folder, get_root_folder, list_drive_folders
from storage import get_all_stored_files
from duplicate_check import total_visited
from events import add_listener, remove_listener
from webhook import (
    register_webhook,
    stop_webhook,
    process_drive_notification,
    webhook_status,
    stop_renewal_scheduler,
)
from config import FRONTEND_URL, DROPBOX_APP_SECRET

# ── Dropbox imports ────────────────────────────────────────────────────────────
from dropbox_auth import (
    router as dropbox_auth_router,
    load_dropbox_token,
    is_dropbox_authenticated,
)
from dropbox_crawler import (
    start_dropbox_crawl,
    set_dropbox_root,
    get_dropbox_root,
    list_dropbox_folders,
    is_dropbox_crawling,
)
from dropbox_webhook import router as dropbox_webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    stop_renewal_scheduler()
    await stop_webhook(quiet=True)


app = FastAPI(title='Connector Pipeline API — Drive + Dropbox', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL, 
        'http://localhost:5173', 
        'http://localhost:3000',
        'https://handsewn-kelvin-reservedly.ngrok-free.dev' # ngrok backend url
    ],
    # This regex allows ANY ngrok tunnel to work, saving you future headaches
    allow_origin_regex=r"https://.*\.ngrok-free\.dev",
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)
app.include_router(dropbox_auth_router)
app.include_router(dropbox_webhook_router, prefix="/api/webhook/dropbox")


# ── Request models ─────────────────────────────────────────────────────────────

class StartCrawlRequest(BaseModel):
    folder_id:   str
    folder_name: str = ''


class DropboxStartCrawlRequest(BaseModel):
    path: str        # e.g. "/My Project Folder"
    name: str = ''   # display name shown in UI


# ── Health / combined status ───────────────────────────────────────────────────

@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/status')
async def status():
    """Combined status for both connectors."""
    drive_root = get_root_folder()
    wh         = webhook_status()
    dbx_root   = get_dropbox_root()

    return {
        # Google Drive
        'authenticated':      load_credentials() is not None,
        'root_folder':        drive_root,
        'webhook':            wh,
        'total_files_stored': await total_visited(),

        # Dropbox
        'dropbox_authenticated': is_dropbox_authenticated(),
        'dropbox_root_folder':   dbx_root,
        'dropbox_crawling':      is_dropbox_crawling(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE DRIVE ROUTES (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

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
    asyncio.create_task(start_crawl(body.folder_id, body.folder_name))
    wh_result = await register_webhook()

    return {
        'message':     'Crawl started',
        'folder_id':   body.folder_id,
        'folder_name': body.folder_name,
        'webhook':     wh_result,
    }


@app.get('/api/files')
def list_files():
    return {'files': get_all_stored_files()}


@app.post('/api/webhook/drive')
async def drive_webhook(request: Request):
    resource_state = request.headers.get('X-Goog-Resource-State', '')
    channel_id     = request.headers.get('X-Goog-Channel-ID', '')
    message_number = request.headers.get('X-Goog-Message-Number', '?')
    asyncio.create_task(
        process_drive_notification(resource_state, channel_id, message_number)
    )
    return Response(status_code=200)


@app.get('/api/webhook/status')
def get_webhook_status():
    return webhook_status()


@app.post('/api/webhook/register')
async def manual_register_webhook():
    creds = load_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail='Not authenticated')
    result = await register_webhook()
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post('/api/webhook/stop')
async def manual_stop_webhook():
    await stop_webhook()
    return {'message': 'Webhook stopped'}


# ══════════════════════════════════════════════════════════════════════════════
# DROPBOX ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get('/api/dropbox/folders')
async def get_dropbox_folders(path: str = ''):
    """
    List immediate subfolders of `path`.
    path='' returns root folders.
    path='/My Folder' returns subfolders inside it.
    """
    token = await load_dropbox_token()
    if not token:
        raise HTTPException(status_code=401, detail='Dropbox: not authenticated')
    folders = await list_dropbox_folders(path)
    return {'folders': folders}


@app.post('/api/dropbox/start-crawl')
async def trigger_dropbox_crawl(body: DropboxStartCrawlRequest):
    """Start full recursive Dropbox crawl on the selected folder path."""
    token = await load_dropbox_token()
    if not token:
        raise HTTPException(status_code=401, detail='Dropbox: not authenticated')

    set_dropbox_root(body.path, body.name or body.path.split('/')[-1])
    asyncio.create_task(start_dropbox_crawl(body.path, body.name))

    return {
        'message':      'Dropbox crawl started',
        'path':         body.path,
        'name':         body.name,
        'webhook_note': (
            'Dropbox webhooks are registered via the App Console. '
            'Ensure your WEBHOOK_URL/api/webhook/dropbox is set there.'
        ),
    }


@app.get('/api/dropbox/files')
def list_dropbox_files():
    """
    Returns all stored files from BOTH Drive and Dropbox.
    Frontend can filter by source_type == 'dropbox'.
    """
    return {'files': get_all_stored_files()}


# ── SSE stream (shared by both Drive and Dropbox) ─────────────────────────────

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
                    yield f'data: {json.dumps(event)}\n\n'
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        finally:
            remove_listener(queue)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )