"""
dropbox_crawler.py
Recursive Dropbox folder crawler + delta-based sync processor.

Key differences from Google Drive crawler:
  1. Uses /files/list_folder (recursive=False) + cursor for pagination
  2. Dropbox provides content_hash natively — no need to download just to hash
  3. Path is built-in — no need to walk up parent hierarchy
  4. Delta: /files/list_folder/continue with saved cursor gives exact changes
  5. No folder IDs for browsing — uses path strings ("/folder/subfolder")
"""
import asyncio
import hashlib
import httpx
import json
import os
from datetime import datetime, timezone

from dropbox_auth import load_dropbox_token
from dropbox_normalizer import build_dropbox_normalized, _guess_mime
from duplicate_check import (
    is_visited, mark_visited,
    is_content_seen, mark_content_seen, get_original_folder,
    get_visited_entry,
)
from storage import save_file_pair, update_normalized_json
from events import broadcast
from config import (
    MAX_FILE_SIZE_BYTES, DROPBOX_STORAGE_DIR,
    DROPBOX_ROOT_FOLDER_FILE, DROPBOX_CURSOR_FILE, STORAGE_DIR,
)

# ── Dropbox API base URLs ──────────────────────────────────────────────────────
DBX_API     = 'https://api.dropboxapi.com/2'
DBX_CONTENT = 'https://content.dropboxapi.com/2'

_is_crawling = False
_root_folder = {'path': None, 'name': None}


# ── Root folder helpers ────────────────────────────────────────────────────────

def set_dropbox_root(path: str, name: str):
    _root_folder['path'] = path
    _root_folder['name'] = name
    os.makedirs(DROPBOX_STORAGE_DIR, exist_ok=True)
    with open(DROPBOX_ROOT_FOLDER_FILE, 'w', encoding='utf-8') as f:
        json.dump({'path': path, 'name': name}, f, indent=2)
    print(f'[dropbox_crawler] Root folder set: {path!r} ({name})')


def get_dropbox_root() -> dict:
    if _root_folder['path'] is not None:
        return _root_folder
    if os.path.exists(DROPBOX_ROOT_FOLDER_FILE):
        with open(DROPBOX_ROOT_FOLDER_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _root_folder.update(data)
    return _root_folder


def is_dropbox_crawling() -> bool:
    return _is_crawling


# ── Cursor helpers ─────────────────────────────────────────────────────────────

def save_dropbox_cursor(cursor: str):
    os.makedirs(DROPBOX_STORAGE_DIR, exist_ok=True)
    with open(DROPBOX_CURSOR_FILE, 'w', encoding='utf-8') as f:
        json.dump({'cursor': cursor}, f)


def load_dropbox_cursor() -> str | None:
    if not os.path.exists(DROPBOX_CURSOR_FILE):
        return None
    try:
        with open(DROPBOX_CURSOR_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('cursor')
    except Exception:
        return None


# ── Dropbox dedup key ──────────────────────────────────────────────────────────
# Dropbox source IDs start with "id:" — we use them directly as unique keys.
# Dropbox also provides a content_hash natively (no download needed for dedup).

def _dropbox_dedup_key(content_hash: str) -> str:
    """Prefix Dropbox content hashes to avoid collision with Drive SHA256s."""
    return f'dbx:{content_hash}'


# ── File download ──────────────────────────────────────────────────────────────

async def _download_file(path: str, token: str) -> bytes:
    """Download raw file bytes from Dropbox."""
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.post(
            f'{DBX_CONTENT}/files/download',
            headers={
                'Authorization':   f'Bearer {token}',
                'Dropbox-API-Arg': json.dumps({'path': path}),
            },
        )
        if resp.status_code == 409:
            raise PermissionError(f'Dropbox 409 (conflict/restricted): {path}')
        resp.raise_for_status()
        return resp.content


# ── Process a single file entry ────────────────────────────────────────────────

async def _process_dropbox_file(entry: dict, token: str, owner_email: str):
    """
    Process one Dropbox file entry:
      1. Skip if already visited (same Dropbox file ID)
      2. Skip if content already stored (same content_hash)
      3. Download + save
    """
    source_id    = entry.get('id', '')
    file_name    = entry.get('name', '')
    path_display = entry.get('path_display', '')
    size_bytes   = entry.get('size', 0) or 0
    dbx_hash     = entry.get('content_hash')    # Dropbox-native SHA256-like hash

    # ── 1. Skip already-visited Dropbox file ID ───────────
    if await is_visited(source_id):
        await broadcast({'type': 'skipped', 'path': path_display, 'file_name': file_name})
        return

    await broadcast({'type': 'file_found',  'path': path_display, 'file_name': file_name})
    await broadcast({'type': 'processing',  'path': path_display, 'file_name': file_name})

    # ── 2. Content-hash dedup (no download needed!) ───────
    if dbx_hash:
        dedup_key = _dropbox_dedup_key(dbx_hash)
        if await is_content_seen(dedup_key):
            original_folder = await get_original_folder(dedup_key)
            await mark_visited(source_id, original_folder, file_name, path_display)
            await broadcast({
                'type':      'skipped',
                'path':      path_display,
                'file_name': file_name,
                'reason':    'Duplicate content',
            })
            return

    # ── 3. Download raw content ────────────────────────────
    try:
        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise ValueError(f'Too large: {size_bytes} bytes')

        raw_bytes      = await _download_file(path_display, token)
        content_status = 'accessible'

        # If Dropbox didn't provide a hash (rare), compute our own
        if not dbx_hash and raw_bytes:
            dbx_hash  = hashlib.sha256(raw_bytes).hexdigest()
            dedup_key = _dropbox_dedup_key(dbx_hash)
            if await is_content_seen(dedup_key):
                original_folder = await get_original_folder(dedup_key)
                await mark_visited(source_id, original_folder, file_name, path_display)
                await broadcast({
                    'type':      'skipped',
                    'path':      path_display,
                    'file_name': file_name,
                    'reason':    'Duplicate content',
                })
                return

    except ValueError:
        raw_bytes      = b''
        content_status = 'too_large'
        dbx_hash       = None
    except PermissionError:
        raw_bytes      = b''
        content_status = 'inaccessible'
        dbx_hash       = None
    except Exception as e:
        print(f'[dropbox_crawler] Download error for {path_display!r}: {e}')
        raw_bytes      = b''
        content_status = 'error'
        dbx_hash       = None

    # ── 4. Build normalized doc + save ────────────────────
    normalized    = build_dropbox_normalized(entry, content_status, owner_email)
    mime_type     = normalized.get('mime_type', 'application/octet-stream')
    folder_number = await save_file_pair(source_id, normalized, raw_bytes, mime_type)

    await mark_visited(source_id, folder_number, file_name, path_display)
    if dbx_hash:
        await mark_content_seen(_dropbox_dedup_key(dbx_hash), folder_number)

    await broadcast({
        'type':           'stored',
        'path':           path_display,
        'file_name':      file_name,
        'folder_number':  folder_number,
        'content_status': content_status,
        'mime_type':      mime_type,
    })


# ── List a folder (one level, non-recursive) ──────────────────────────────────

async def _list_folder(path: str, token: str) -> tuple[list, str | None]:
    """
    Returns (entries, cursor).
    Handles pagination with has_more.
    """
    entries = []
    cursor  = None

    async with httpx.AsyncClient(timeout=30) as client:
        # Initial request
        resp = await client.post(
            f'{DBX_API}/files/list_folder',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type':  'application/json',
            },
            json={
                'path':                                path,
                'recursive':                           False,
                'include_media_info':                  False,
                'include_deleted':                     False,
                'include_has_explicit_shared_members': False,
                'limit':                               2000,
            },
        )
        resp.raise_for_status()
        data     = resp.json()
        entries.extend(data.get('entries', []))
        cursor   = data.get('cursor')
        has_more = data.get('has_more', False)

        # Paginate
        while has_more and cursor:
            resp = await client.post(
                f'{DBX_API}/files/list_folder/continue',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                json={'cursor': cursor},
            )
            resp.raise_for_status()
            data     = resp.json()
            entries.extend(data.get('entries', []))
            cursor   = data.get('cursor')
            has_more = data.get('has_more', False)

    return entries, cursor


# ── Recursive folder crawl ─────────────────────────────────────────────────────

async def _crawl_dropbox_folder(path: str, token: str, owner_email: str):
    await broadcast({'type': 'scan_start', 'path': path})

    try:
        entries, _ = await _list_folder(path, token)
    except Exception as e:
        await broadcast({'type': 'error', 'path': path, 'message': str(e)})
        return

    for entry in entries:
        tag = entry.get('.tag', '')
        if tag == 'folder':
            await _crawl_dropbox_folder(entry['path_display'], token, owner_email)
        elif tag == 'file':
            await _process_dropbox_file(entry, token, owner_email)
            await asyncio.sleep(0.05)


# ── Public: start full crawl ───────────────────────────────────────────────────

async def start_dropbox_crawl(path: str, name: str = ''):
    """
    Entry point: crawl `path` recursively.
    Also saves the latest cursor so delta sync knows where to start from.
    """
    global _is_crawling
    if _is_crawling:
        return

    _is_crawling = True
    await broadcast({'type': 'crawl_start', 'folder_id': path})

    try:
        token = await load_dropbox_token()
        if not token:
            await broadcast({'type': 'error', 'message': 'Dropbox: not authenticated'})
            return

        # Get owner email once
        owner_email = ''
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    'https://api.dropboxapi.com/2/users/get_current_account',
                    headers={
                        'Authorization': f'Bearer {token}',
                        'Content-Type':  'application/json',
                    },
                    content=b'null',
                )
                if resp.status_code == 200:
                    owner_email = resp.json().get('email', '')
        except Exception:
            pass

        await _crawl_dropbox_folder(path, token, owner_email)

        # Save latest cursor AFTER initial crawl — so delta starts from now
        await _save_latest_cursor(path, token)

        await broadcast({'type': 'crawl_complete'})

    except Exception as e:
        await broadcast({'type': 'error', 'message': str(e)})
    finally:
        _is_crawling = False


async def _save_latest_cursor(path: str, token: str):
    """Fetch and save the latest cursor for the root path (delta start point)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f'{DBX_API}/files/list_folder/get_latest_cursor',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                json={
                    'path':      path,
                    'recursive': True,
                },
            )
            resp.raise_for_status()
            cursor = resp.json().get('cursor')
            if cursor:
                save_dropbox_cursor(cursor)
                print(f'[dropbox_crawler] Latest cursor saved: {cursor[:20]}…')
    except Exception as e:
        print(f'[dropbox_crawler] Could not save latest cursor: {e}')


# ── Delta processor (called by webhook handler) ────────────────────────────────

async def process_dropbox_delta():
    """
    Calls /files/list_folder/continue with the saved cursor.
    Handles:
      - deleted entry (.tag == 'deleted')  → update content_status = 'deleted'
      - known file changed                 → update normalized.json (path, name, modified_at)
      - new file                           → download + store as new
    Saves the new cursor when done.
    """
    token = await load_dropbox_token()
    if not token:
        await broadcast({'type': 'error', 'message': 'Dropbox delta: not authenticated'})
        return

    cursor = load_dropbox_cursor()
    if not cursor:
        await broadcast({
            'type':    'error',
            'message': 'Dropbox delta: no cursor — run initial crawl first',
        })
        return

    root      = get_dropbox_root()
    root_path = root.get('path', '')

    all_entries = []
    new_cursor  = cursor

    print(f'[dropbox_delta] Fetching changes from cursor: {cursor[:20]}…')

    # ── Fetch all delta pages ──────────────────────────────
    async with httpx.AsyncClient(timeout=30) as client:
        current_cursor = cursor
        while True:
            resp = await client.post(
                f'{DBX_API}/files/list_folder/continue',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                json={'cursor': current_cursor},
            )

            if resp.status_code == 401:
                await broadcast({'type': 'error', 'message': 'Dropbox delta: token expired'})
                return

            if resp.status_code == 409:
                # Cursor expired — need to reset
                print('[dropbox_delta] Cursor expired — resetting with latest cursor')
                await _save_latest_cursor(root_path, token)
                await broadcast({
                    'type':    'error',
                    'message': 'Dropbox delta: cursor expired, reset. Next change will sync correctly.',
                })
                return

            resp.raise_for_status()
            data = resp.json()
            all_entries.extend(data.get('entries', []))
            new_cursor = data.get('cursor', current_cursor)
            has_more   = data.get('has_more', False)

            if has_more:
                current_cursor = new_cursor
            else:
                break

    print(f'[dropbox_delta] Got {len(all_entries)} change entry/entries.')

    # Save new cursor immediately so next delta starts from here
    if new_cursor != cursor:
        save_dropbox_cursor(new_cursor)

    if not all_entries:
        print('[dropbox_delta] No changes — silent success.')
        return

    await broadcast({
        'type':    'webhook_received',
        'message': f'Dropbox delta: {len(all_entries)} change(s) — processing…',
    })

    # Get owner email once
    owner_email = ''
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                'https://api.dropboxapi.com/2/users/get_current_account',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                content=b'null',
            )
            if resp.status_code == 200:
                owner_email = resp.json().get('email', '')
    except Exception:
        pass

    new_files = []

    for entry in all_entries:
        tag          = entry.get('.tag', '')
        path_display = entry.get('path_display', '')
        source_id    = entry.get('id', '')
        file_name    = entry.get('name', '')

        # Only process entries inside our watched root path
        if root_path and not path_display.lower().startswith(root_path.lower()):
            print(f'[dropbox_delta] Skipping out-of-scope entry: {path_display!r}')
            continue

        print(f'[dropbox_delta] Entry: tag={tag!r}  path={path_display!r}  id={source_id!r}')

        # ── Case 1: Deleted ────────────────────────────────
        if tag == 'deleted':
            # Dropbox deleted entries don't have an id — look up by path
            visited_entry = await get_visited_entry(source_id) if source_id else None
            if not visited_entry:
                # Try to find by path in visited.json
                from duplicate_check import get_all_visited
                all_visited = await get_all_visited()
                for vid, vdata in all_visited.items():
                    if vdata.get('path', '').lower() == path_display.lower():
                        visited_entry = vdata
                        visited_entry['source_id'] = vid
                        break

            if visited_entry:
                folder_num = visited_entry['folder_number']
                await update_normalized_json(folder_num, {
                    'content_status':      'deleted',
                    'connector_synced_at': datetime.now(timezone.utc).isoformat(),
                })
                await broadcast({
                    'type':           'stored',
                    'path':           path_display,
                    'file_name':      visited_entry.get('file_name', file_name),
                    'folder_number':  folder_num,
                    'content_status': 'deleted',
                    'mime_type':      '',
                })
            continue

        # ── Case 2: Folder change — ignore ────────────────
        if tag == 'folder':
            continue

        # ── Case 3: File change ────────────────────────────
        if tag == 'file':
            visited_entry = await get_visited_entry(source_id)

            if visited_entry:
                # Known file — update metadata (re-download only if content changed)
                folder_num = visited_entry['folder_number']
                dbx_hash   = entry.get('content_hash')
                dedup_key  = _dropbox_dedup_key(dbx_hash) if dbx_hash else None

                updated_fields = {
                    'file_name':           file_name,
                    'path':                path_display,
                    'parent_folder_id':    path_display.rsplit('/', 1)[0] if '/' in path_display else '',
                    'modified_at':         entry.get('client_modified') or entry.get('server_modified'),
                    'web_url':             f'https://www.dropbox.com/home{path_display}',
                    'connector_synced_at': datetime.now(timezone.utc).isoformat(),
                }

                # If content changed (different hash) → re-download
                if dbx_hash and dedup_key and not await is_content_seen(dedup_key):
                    try:
                        import aiofiles
                        raw_bytes = await _download_file(path_display, token)
                        mime_type = _guess_mime(file_name)
                        ext       = os.path.splitext(file_name)[1].lower() or '.bin'
                        raw_path  = os.path.join(STORAGE_DIR, str(folder_num), f'raw{ext}')
                        async with aiofiles.open(raw_path, 'wb') as fh:
                            await fh.write(raw_bytes)
                        updated_fields['content_status']         = 'accessible'
                        updated_fields['raw_file_path']          = raw_path
                        updated_fields['dropbox_content_hash']   = dbx_hash
                        await mark_content_seen(dedup_key, folder_num)
                    except Exception as dl_err:
                        print(f'[dropbox_delta] Re-download failed: {dl_err}')

                ok = await update_normalized_json(folder_num, updated_fields)
                if ok:
                    await mark_visited(source_id, folder_num, file_name, path_display)
                    await broadcast({
                        'type':           'stored',
                        'path':           path_display,
                        'file_name':      file_name,
                        'folder_number':  folder_num,
                        'content_status': 'updated',
                        'mime_type':      '',
                    })

            else:
                # New file — queue for processing
                new_files.append(entry)

    # ── Process new files ──────────────────────────────────
    if new_files:
        await broadcast({
            'type':    'webhook_received',
            'message': f'{len(new_files)} new Dropbox file(s) — downloading…',
        })
        for entry in new_files:
            await _process_dropbox_file(entry, token, owner_email)
            await asyncio.sleep(0.05)

    await broadcast({'type': 'crawl_complete'})


# ── Public: list Dropbox folders ───────────────────────────────────────────────

async def list_dropbox_folders(path: str = '') -> list:
    """List immediate subfolders of `path`. Empty string = account root."""
    token = await load_dropbox_token()
    if not token:
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f'{DBX_API}/files/list_folder',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                json={
                    'path':      path,
                    'recursive': False,
                },
            )
            resp.raise_for_status()
            entries = resp.json().get('entries', [])
            return [
                {
                    'id':   e['path_lower'],
                    'name': e['name'],
                    'path': e['path_display'],
                }
                for e in entries
                if e.get('.tag') == 'folder'
            ]
    except Exception as e:
        print(f'[dropbox_crawler] list_dropbox_folders error: {e}')
        return []
