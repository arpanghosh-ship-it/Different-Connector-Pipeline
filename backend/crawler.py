import asyncio
import httpx
import json
import os
import hashlib  # <-- NEW: Required for generating content hashes
from auth import load_credentials
from normalizer import build_normalized_document, is_google_native, get_export_mime
from storage import save_file_pair

# <-- UPDATED: Added new content-checking functions
from duplicate_check import is_visited, mark_visited, is_content_seen, mark_content_seen, get_original_folder 
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

    # 1. Check if we've seen this exact Drive File ID before
    if await is_visited(source_id):
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
        
        # --- NEW HASHING LOGIC START ---
        if raw_bytes:
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            
            if await is_content_seen(content_hash):
                # We already have a file with this exact content
                await broadcast({
                    'type': 'skipped', 
                    'path': full_path, 
                    'file_name': file['name'], 
                    'reason': 'Duplicate content'
                })
                
                # Still mark this Drive ID as visited, pointing to the original folder
                original_folder = await get_original_folder(content_hash)
                await mark_visited(source_id, original_folder, file['name'], full_path)
                return
        else:
            content_hash = None
        # --- NEW HASHING LOGIC END ---

    except ValueError:
        raw_bytes = b''
        raw_mime = 'application/octet-stream'
        content_status = 'too_large'
        content_hash = None
    except PermissionError:
        raw_bytes = b''
        raw_mime = 'application/octet-stream'
        content_status = 'inaccessible'
        content_hash = None
    except FileNotFoundError:
        raw_bytes = b''
        raw_mime = 'application/octet-stream'
        content_status = 'deleted'
        content_hash = None
    except Exception:
        raw_bytes = b''
        raw_mime = 'application/octet-stream'
        content_status = 'error'
        content_hash = None

    normalized = build_normalized_document(file, full_path, content_status, owner_email)

    folder_number = await save_file_pair(source_id, normalized, raw_bytes, raw_mime)
    
    # --- UPDATED: Mark both the ID and the Hash as visited ---
    await mark_visited(source_id, folder_number, file['name'], full_path)
    if content_hash:
        await mark_content_seen(content_hash, folder_number)

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


async def _get_full_path(folder_id: str, token: str, root_folder_id: str) -> str:
    """
    Walks up the Drive folder hierarchy from folder_id to root_folder_id
    and builds the full path string, e.g. "Root Folder/training/subfolder".
    """
    parts = []
    current_id = folder_id
    visited_ids: set = set()

    async with httpx.AsyncClient(timeout=15) as client:
        while current_id and current_id != root_folder_id:
            if current_id in visited_ids:
                break
            visited_ids.add(current_id)

            resp = await client.get(
                f'{DRIVE_FILES_URL}/{current_id}',
                params={'fields': 'id,name,parents', 'supportsAllDrives': 'true'},
                headers={'Authorization': f'Bearer {token}'},
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            parts.append(data.get('name', ''))
            parents = data.get('parents', [])
            current_id = parents[0] if parents else None

    root = get_root_folder()
    root_name = root.get('name', 'Root')
    parts.append(root_name)
    parts.reverse()
    return '/'.join(parts)


async def process_delta_changes():
    """
    Fetches only the files that changed in Drive since the last saved page token.
    Handles three cases:
      - Deleted / trashed   → sets content_status = 'deleted' in normalized.json
      - Known file changed  → updates path, parent, name, etc. in normalized.json
      - New file            → triggers a targeted start_crawl() (dedup skips existing)
    Saves the new page_token when done.
    """
    from datetime import datetime, timezone
    from duplicate_check import get_visited_entry, mark_visited
    from storage import update_normalized_json
    from webhook import load_page_token, save_page_token

    creds = load_credentials()
    if not creds or not creds.token:
        await broadcast({'type': 'error', 'message': 'Delta sync: not authenticated'})
        return

    token = creds.token
    root = get_root_folder()
    root_id = root.get('id')

    page_token = load_page_token()
    if not page_token:
        await broadcast({
            'type': 'error',
            'message': 'Delta sync: no page token — re-select folder to reset',
        })
        return

    changes_url = 'https://www.googleapis.com/drive/v3/changes'
    all_changes = []
    next_token = None

    print(f'[delta] Starting delta sync. page_token={page_token!r}  root_id={root_id!r}')

    # ── Fetch all change pages ─────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=30) as client:
        current_page_token = page_token
        while True:
            params = {
                'pageToken': current_page_token,
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true',
                # Explicitly list file subfields so Drive always returns them,
                # even for shared-drive files where bare 'file' can be sparse.
                'fields': (
                    'nextPageToken,newStartPageToken,'
                    'changes(type,removed,fileId,'
                    'file(id,name,mimeType,parents,modifiedTime,'
                    'owners(emailAddress),shared,size,webViewLink,trashed))'
                ),
            }
            resp = await client.get(
                changes_url,
                params=params,
                headers={'Authorization': f'Bearer {token}'},
            )
            if resp.status_code == 401:
                await broadcast({'type': 'error', 'message': 'Delta sync: token expired'})
                return

            resp.raise_for_status()
            data = resp.json()
            all_changes.extend(data.get('changes', []))

            # Capture the final new page token
            next_token = data.get('newStartPageToken') or data.get('nextPageToken')

            if 'nextPageToken' in data:
                current_page_token = data['nextPageToken']
            else:
                break

    print(f'[delta] API returned {len(all_changes)} change(s). next_token={next_token!r}')

    # Save updated token so next delta starts from here
    if next_token:
        save_page_token(next_token)

    if not all_changes:
        print('[delta] No changes — silent success.')
        return  # nothing changed — silent success

    await broadcast({
        'type': 'webhook_received',
        'message': f'Delta sync: {len(all_changes)} change(s) detected — processing…',
    })

    new_files_to_crawl = []

    for change in all_changes:
        if change.get('type') != 'file':
            continue

        file_id = change.get('fileId')
        removed = change.get('removed', False)
        file_obj = change.get('file') or {}
        trashed = file_obj.get('trashed', False)

        print(f'[delta]   Change: file_id={file_id!r}  removed={removed}  trashed={trashed}  name={file_obj.get("name")!r}  parents={file_obj.get("parents")}')

        # ── Case 1: File deleted / trashed ─────────────────────────────────────
        if removed or trashed:
            entry = await get_visited_entry(file_id)
            if entry:
                folder_num = entry['folder_number']
                print(f'[delta]     → DELETED: folder #{folder_num}  path={entry.get("path")!r}')
                await update_normalized_json(folder_num, {
                    'content_status': 'deleted',
                    'connector_synced_at': datetime.now(timezone.utc).isoformat(),
                })
                await broadcast({
                    'type': 'stored',
                    'path': entry.get('path', ''),
                    'file_name': entry.get('file_name', ''),
                    'folder_number': folder_num,
                    'content_status': 'deleted',
                    'mime_type': '',
                })
            else:
                print(f'[delta]     → DELETED but not in visited — skipping')
            continue

        # ── Case 2: Already known file — update its metadata ───────────────────
        entry = await get_visited_entry(file_id)
        if entry:
            print(f'[delta]     → KNOWN FILE: folder #{entry["folder_number"]}  rebuilding path…')
            folder_num = entry['folder_number']
            parent_id = (file_obj.get('parents') or [None])[0]
            owner_email = None
            if file_obj.get('owners'):
                owner_email = file_obj['owners'][0].get('emailAddress')

            # Rebuild full path from the new parent hierarchy
            try:
                if parent_id and root_id:
                    parent_path = await _get_full_path(parent_id, token, root_id)
                    full_path = f"{parent_path}/{file_obj.get('name', '')}"
                else:
                    full_path = entry.get('path', '')
            except Exception:
                full_path = entry.get('path', '')  # fallback to old path

            updated_fields = {
                'file_name': file_obj.get('name', ''),
                'path': full_path,
                'parent_folder_id': parent_id,
                'modified_at': file_obj.get('modifiedTime'),
                'shared': file_obj.get('shared', False),
                'web_url': file_obj.get('webViewLink'),
                'connector_synced_at': datetime.now(timezone.utc).isoformat(),
            }
            if owner_email:
                updated_fields['owner_email'] = owner_email

            ok = await update_normalized_json(folder_num, updated_fields)
            if ok:
                # Also sync visited.json with the new name/path
                await mark_visited(file_id, folder_num, file_obj.get('name', ''), full_path)
                await broadcast({
                    'type': 'stored',
                    'path': full_path,
                    'file_name': file_obj.get('name', ''),
                    'folder_number': folder_num,
                    'content_status': 'updated',
                    'mime_type': file_obj.get('mimeType', ''),
                })
            continue

        # ── Case 3: New file — queue it for a targeted crawl ──────────────────
        print(f'[delta]     → NEW FILE (not in visited): {file_obj.get("name")!r}')
        if file_id:
            new_files_to_crawl.append(file_obj)

    # ── Process any genuinely new files ───────────────────────────────────────
    if new_files_to_crawl and root_id:
        await broadcast({
            'type': 'webhook_received',
            'message': f'{len(new_files_to_crawl)} new file(s) detected — scanning root folder…',
        })
        # Full crawl, but dedup (is_visited) ensures only truly new files are stored
        await start_crawl(root_id, root.get('name', ''))

    await broadcast({'type': 'crawl_complete'})


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