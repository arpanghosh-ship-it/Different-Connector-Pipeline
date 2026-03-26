import asyncio
import httpx
import json
import os
from auth import load_credentials
from normalizer import build_normalized_document, is_google_native, get_export_mime
from storage import save_file_pair
from duplicate_check import is_visited, mark_visited
from events import broadcast
from config import MAX_FILE_SIZE_BYTES, STORAGE_DIR, ROOT_FOLDER_FILE

_is_crawling = False
_root_folder = {'id': None, 'name': None}

DRIVE_FILES_URL = 'https://www.googleapis.com/drive/v3/files'
DRIVE_EXPORT_URL = 'https://www.googleapis.com/drive/v3/files/{id}/export'
DRIVE_DOWNLOAD_URL = 'https://www.googleapis.com/drive/v3/files/{id}?alt=media&supportsAllDrives=true'


def set_root_folder(folder_id: str, folder_name: str):
    _root_folder['id'] = folder_id
    _root_folder['name'] = folder_name
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(ROOT_FOLDER_FILE, 'w', encoding='utf-8') as f:
        json.dump({'id': folder_id, 'name': folder_name}, f)


def get_root_folder() -> dict:
    if _root_folder['id']:
        return _root_folder
    if os.path.exists(ROOT_FOLDER_FILE):
        with open(ROOT_FOLDER_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _root_folder.update(data)
    return _root_folder


def is_crawling() -> bool:
    return _is_crawling


async def _list_items(folder_id: str, token: str) -> list:
    params = {
        'q': f"'{folder_id}' in parents and trashed=false",
        'fields': 'files(id,name,mimeType,parents,modifiedTime,owners,shared,size,webViewLink,driveId),nextPageToken',
        'supportsAllDrives': 'true',
        'includeItemsFromAllDrives': 'true',
        'pageSize': '1000',
    }
    headers = {'Authorization': f'Bearer {token}'}
    all_items = []

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.get(DRIVE_FILES_URL, params=params, headers=headers)
            if resp.status_code == 401:
                raise Exception('Token expired')
            resp.raise_for_status()
            data = resp.json()
            all_items.extend(data.get('files', []))
            next_token = data.get('nextPageToken')
            if not next_token:
                break
            params['pageToken'] = next_token

    return all_items


async def _fetch_content(file: dict, token: str) -> tuple[bytes, str]:
    headers = {'Authorization': f'Bearer {token}'}
    mime = file.get('mimeType', '')

    size = int(file.get('size', 0)) if file.get('size') else 0
    if size > MAX_FILE_SIZE_BYTES and not is_google_native(mime):
        raise ValueError(f'File too large: {size} bytes')

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        if is_google_native(mime):
            export_mime, _ = get_export_mime(mime)
            url = DRIVE_EXPORT_URL.format(id=file['id'])
            resp = await client.get(url, params={'mimeType': export_mime}, headers=headers)
        else:
            url = DRIVE_DOWNLOAD_URL.format(id=file['id'])
            resp = await client.get(url, headers=headers)

        if resp.status_code == 403:
            raise PermissionError('403 Forbidden')
        if resp.status_code == 404:
            raise FileNotFoundError('404 Not Found')
        resp.raise_for_status()

        actual_mime = export_mime if is_google_native(mime) else mime
        return resp.content, actual_mime


async def _process_file(file: dict, full_path: str, token: str):
    source_id = file['id']

    if is_visited(source_id):
        await broadcast({'type': 'skipped', 'path': full_path, 'file_name': file['name']})
        return

    await broadcast({'type': 'file_found', 'path': full_path, 'file_name': file['name']})
    await broadcast({'type': 'processing', 'path': full_path, 'file_name': file['name']})

    owner_email = None
    if file.get('owners'):
        owner_email = file['owners'][0].get('emailAddress')

    try:
        raw_bytes, raw_mime = await _fetch_content(file, token)
        content_status = 'accessible'
    except ValueError:
        raw_bytes = b''
        raw_mime = 'application/octet-stream'
        content_status = 'too_large'
    except PermissionError:
        raw_bytes = b''
        raw_mime = 'application/octet-stream'
        content_status = 'inaccessible'
    except FileNotFoundError:
        raw_bytes = b''
        raw_mime = 'application/octet-stream'
        content_status = 'deleted'
    except Exception:
        raw_bytes = b''
        raw_mime = 'application/octet-stream'
        content_status = 'error'

    normalized = build_normalized_document(file, full_path, content_status, owner_email)

    folder_number = await save_file_pair(source_id, normalized, raw_bytes, raw_mime)
    mark_visited(source_id, folder_number, file['name'], full_path)

    await broadcast({
        'type': 'stored',
        'path': full_path,
        'file_name': file['name'],
        'folder_number': folder_number,
        'content_status': content_status,
        'mime_type': file.get('mimeType', ''),
    })


async def _crawl_folder(folder_id: str, folder_name: str, parent_path: str, token: str):
    current_path = f'{parent_path}/{folder_name}' if folder_name else parent_path

    await broadcast({'type': 'scan_start', 'path': current_path})

    try:
        items = await _list_items(folder_id, token)
    except Exception as e:
        await broadcast({'type': 'error', 'path': current_path, 'message': str(e)})
        return

    for item in items:
        mime = item.get('mimeType', '')
        if mime == 'application/vnd.google-apps.folder':
            await _crawl_folder(item['id'], item['name'], current_path, token)
        else:
            file_path = f"{current_path}/{item['name']}"
            await _process_file(item, file_path, token)
            await asyncio.sleep(0.1)


async def start_crawl(folder_id: str, folder_name: str = ''):
    global _is_crawling
    if _is_crawling:
        return

    _is_crawling = True
    await broadcast({'type': 'crawl_start', 'folder_id': folder_id})

    try:
        creds = load_credentials()
        if not creds or not creds.token:
            await broadcast({'type': 'error', 'message': 'Not authenticated'})
            return

        root = get_root_folder()
        name = root.get('name') or folder_name or 'Root'

        await _crawl_folder(folder_id, '', name, creds.token)
        await broadcast({'type': 'crawl_complete'})

    except Exception as e:
        await broadcast({'type': 'error', 'message': str(e)})
    finally:
        _is_crawling = False


async def list_drive_folders(parent_id: str = 'root') -> list:
    creds = load_credentials()
    if not creds or not creds.token:
        return []

    params = {
        'q': f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        'fields': 'files(id,name,parents)',
        'supportsAllDrives': 'true',
        'includeItemsFromAllDrives': 'true',
        'orderBy': 'name',
        'pageSize': '100',
    }
    headers = {'Authorization': f'Bearer {creds.token}'}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(DRIVE_FILES_URL, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json().get('files', [])
