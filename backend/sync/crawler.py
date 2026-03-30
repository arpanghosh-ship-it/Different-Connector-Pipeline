import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.credentials import load_credentials
from sync.drive_client import list_items, fetch_content, list_drive_folders
from normalize.document import build_normalized_document
from storage.file_store import save_file_pair, get_all_stored_files
from storage.visited import is_visited, mark_visited, total_visited
from storage.root_folder import set_root_folder, get_root_folder
from events.bus import broadcast
from sync.poller import start_poller, is_polling, pause_poller, resume_poller

router = APIRouter()
_is_crawling = False

def is_crawling() -> bool:
    return _is_crawling

async def _process_file(file: dict, full_path: str, token: str):
    source_id = file["id"]

    if is_visited(source_id):
        await broadcast({"type": "skipped", "path": full_path, "file_name": file["name"]})
        return

    await broadcast({"type": "file_found", "path": full_path, "file_name": file["name"]})
    await broadcast({"type": "processing", "path": full_path, "file_name": file["name"]})

    owner_email = None
    if file.get("owners"):
        owner_email = file["owners"][0].get("emailAddress")

    try:
        raw_bytes, raw_mime = await fetch_content(file, token)
        content_status = "accessible"
    except ValueError:
        raw_bytes = b""
        raw_mime = "application/octet-stream"
        content_status = "too_large"
    except PermissionError:
        raw_bytes = b""
        raw_mime = "application/octet-stream"
        content_status = "inaccessible"
    except FileNotFoundError:
        raw_bytes = b""
        raw_mime = "application/octet-stream"
        content_status = "deleted"
    except Exception:
        raw_bytes = b""
        raw_mime = "application/octet-stream"
        content_status = "error"

    normalized = build_normalized_document(file, full_path, content_status, owner_email)

    folder_number = await save_file_pair(source_id, normalized, raw_bytes, raw_mime)
    mark_visited(source_id, folder_number, file["name"], full_path)

    await broadcast({
        "type": "stored",
        "path": full_path,
        "file_name": file["name"],
        "folder_number": folder_number,
        "content_status": content_status,
        "mime_type": file.get("mimeType", ""),
    })

async def _crawl_folder(folder_id: str, folder_name: str, parent_path: str, token: str):
    current_path = f"{parent_path}/{folder_name}" if folder_name else parent_path

    await broadcast({"type": "scan_start", "path": current_path})

    try:
        items = await list_items(folder_id, token)
    except Exception as e:
        await broadcast({"type": "error", "path": current_path, "message": str(e)})
        return

    for item in items:
        mime = item.get("mimeType", "")
        if mime == "application/vnd.google-apps.folder":
            await _crawl_folder(item["id"], item["name"], current_path, token)
        else:
            file_path = f"{current_path}/{item['name']}"
            await _process_file(item, file_path, token)
            await asyncio.sleep(0.1)

async def start_crawl(folder_id: str, folder_name: str = ""):
    global _is_crawling
    if _is_crawling:
        return

    _is_crawling = True
    await broadcast({"type": "crawl_start", "folder_id": folder_id})

    try:
        creds = load_credentials()
        if not creds or not creds.token:
            await broadcast({"type": "error", "message": "Not authenticated"})
            return

        root = get_root_folder()
        name = root.get("name") or folder_name or "Root"

        await _crawl_folder(folder_id, "", name, creds.token)
        await broadcast({"type": "crawl_complete"})

    except Exception as e:
        await broadcast({"type": "error", "message": str(e)})
    finally:
        _is_crawling = False

class StartCrawlRequest(BaseModel):
    folder_id: str
    folder_name: str = ""

@router.get("/api/status")
def status():
    root = get_root_folder()
    return {
        "authenticated": load_credentials() is not None,
        "root_folder": root,
        "polling": is_polling(),
        "total_files_stored": total_visited(),
    }

@router.get("/api/folders")
async def get_folders(parent_id: str = "root"):
    creds = load_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    folders = await list_drive_folders(creds.token, parent_id)
    return {"folders": folders}

@router.post("/api/start-crawl")
async def trigger_crawl(body: StartCrawlRequest):
    creds = load_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    set_root_folder(body.folder_id, body.folder_name)
    start_poller(body.folder_id, body.folder_name)
    asyncio.create_task(start_crawl(body.folder_id, body.folder_name))
    return {"message": "Crawl started", "folder_id": body.folder_id, "folder_name": body.folder_name}

@router.get("/api/files")
def list_files():
    return {"files": get_all_stored_files()}

@router.post("/api/stop-poll")
def stop_poll():
    pause_poller()
    return {"polling": False, "message": "Polling paused"}

@router.post("/api/start-poll")
def start_poll():
    resume_poller()
    return {"polling": True, "message": "Polling resumed"}