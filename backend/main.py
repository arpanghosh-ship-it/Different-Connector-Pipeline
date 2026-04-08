import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
from config import FRONTEND_URL


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Clean shutdown
    stop_renewal_scheduler()
    await stop_webhook(quiet=True)


app = FastAPI(title='Drive Connector API', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, 'http://localhost:5173', 'http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)


# ── Request models ─────────────────────────────────────────────────────────────

class StartCrawlRequest(BaseModel):
    folder_id: str
    folder_name: str = ''


# ── Health / status ────────────────────────────────────────────────────────────

@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/status')
async def status():
    root = get_root_folder()
    wh = webhook_status()
    return {
        'authenticated': load_credentials() is not None,
        'root_folder': root,
        'webhook': wh,
        'total_files_stored': await total_visited(),
    }


# ── Drive folder listing ───────────────────────────────────────────────────────

@app.get('/api/folders')
async def get_folders(parent_id: str = 'root'):
    creds = load_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail='Not authenticated')
    folders = await list_drive_folders(parent_id)
    return {'folders': folders}


# ── Crawl trigger ──────────────────────────────────────────────────────────────

@app.post('/api/start-crawl')
async def trigger_crawl(body: StartCrawlRequest):
    creds = load_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail='Not authenticated')

    set_root_folder(body.folder_id, body.folder_name)

    # Start initial crawl immediately
    asyncio.create_task(start_crawl(body.folder_id, body.folder_name))

    # Register Drive webhook for live change notifications
    wh_result = await register_webhook()

    return {
        'message': 'Crawl started',
        'folder_id': body.folder_id,
        'folder_name': body.folder_name,
        'webhook': wh_result,
    }


# ── File listing ───────────────────────────────────────────────────────────────

@app.get('/api/files')
def list_files():
    return {'files': get_all_stored_files()}


# ── Webhook endpoints ──────────────────────────────────────────────────────────

@app.post('/api/webhook/drive')
async def drive_webhook(request: Request):
    """
    Receives Google Drive push notifications.
    Google sends a POST with headers like:
      X-Goog-Channel-ID, X-Goog-Resource-State, X-Goog-Message-Number
    Body is usually empty — all info is in headers.
    Must respond 200 quickly; actual processing runs in background.
    """
    resource_state = request.headers.get('X-Goog-Resource-State', '')
    channel_id = request.headers.get('X-Goog-Channel-ID', '')
    message_number = request.headers.get('X-Goog-Message-Number', '?')

    # Fire-and-forget so Google doesn't wait and retry
    asyncio.create_task(
        process_drive_notification(resource_state, channel_id, message_number)
    )

    return Response(status_code=200)


@app.get('/api/webhook/status')
def get_webhook_status():
    """Returns current webhook channel status."""
    return webhook_status()


@app.post('/api/webhook/register')
async def manual_register_webhook():
    """
    Manually re-register the webhook channel.
    Useful after ngrok URL changes or channel expiry.
    """
    creds = load_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail='Not authenticated')

    result = await register_webhook()
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])

    return result


@app.post('/api/webhook/stop')
async def manual_stop_webhook():
    """Deregister the webhook channel."""
    await stop_webhook()
    return {'message': 'Webhook stopped'}


# ── SSE stream ─────────────────────────────────────────────────────────────────

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