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
import logging

def notify_rag_pipeline(folder_number: int) -> None:
    """
    Notify the RAG pipeline to ingest a newly synced folder.
    This is fire-and-forget — connector never waits for RAG
    to complete. If RAG pipeline is down, connector continues normally.
    """
    rag_url = os.getenv("RAG_PIPELINE_URL", "http://localhost:8001")
    try:
        # Fire and forget in a separate thread to not block async context
        def _post():
            try:
                response = httpx.post(f"{rag_url}/ingest/{folder_number}", timeout=120)
                logging.info(f"[RAG] Ingestion triggered for folder {folder_number} — status: {response.status_code}")
            except Exception as e:
                logging.error(f"[RAG] Pipeline notification failed for folder {folder_number}: {e}")
        
        asyncio.create_task(asyncio.to_thread(_post))
    except Exception as e:
        logging.error(f"[RAG] Failed to schedule notification for folder {folder_number}: {e}")


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


_account_cache = {}

async def _get_email_for_account(account_id: str, token: str) -> str:
    if not account_id:
        return ""
    if account_id in _account_cache:
        return _account_cache[account_id]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                'https://api.dropboxapi.com/2/users/get_account',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                json={'account_id': account_id},
            )
            if resp.status_code == 200:
                email = resp.json().get('email', '')
                _account_cache[account_id] = email
                return email
    except Exception:
        pass
    _account_cache[account_id] = ""
    return ""

async def _get_folder_members(shared_folder_id: str, token: str) -> list:
    """
    Fetch all members of a shared Dropbox folder using
    /sharing/list_folder_members with full cursor-based pagination.

    Used when a file's sharing_info contains parent_shared_folder_id —
    members are inherited from the parent folder, not set on the file.

    Args:
        shared_folder_id: the parent_shared_folder_id value from
                          file's sharing_info (numeric string like
                          "84528192421")
        token: Dropbox OAuth access token

    Returns:
        list of dicts: [{"email", "name", "role", "account_id"}]
        Returns [] on any failure — but logs the full error details.
    """
    members: list = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # ── Initial request ──────────────────────────────────────
            resp = await client.post(
                f'{DBX_API}/sharing/list_folder_members',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                json={'shared_folder_id': shared_folder_id},
            )

            if resp.status_code != 200:
                logging.error(
                    f"[_get_folder_members] API returned {resp.status_code} "
                    f"for shared_folder_id={shared_folder_id}: {resp.text}"
                )
                return []

            def _parse_page(data: dict) -> None:
                """Parse users, invitees, and groups from one response page."""
                for u in data.get('users', []):
                    user_info = u.get('user', {})
                    members.append({
                        'email':      user_info.get('email', ''),
                        'name':       user_info.get('display_name', ''),
                        'role':       u.get('access_type', {}).get('.tag', ''),
                        'account_id': user_info.get('account_id', ''),
                    })
                for i in data.get('invitees', []):
                    inv = i.get('invitee', {})
                    members.append({
                        'email':      inv.get('email', ''),
                        'name':       '',
                        'role':       i.get('access_type', {}).get('.tag', ''),
                        'account_id': None,
                    })
                for g in data.get('groups', []):
                    grp = g.get('group', {})
                    members.append({
                        'email':      '',
                        'name':       grp.get('group_name', ''),
                        'role':       g.get('access_type', {}).get('.tag', ''),
                        'account_id': None,
                        'is_group':   True,
                    })

            data = resp.json()
            _parse_page(data)

            # ── Cursor-based pagination ──────────────────────────────
            cursor = data.get('cursor')
            while cursor:
                page_resp = await client.post(
                    f'{DBX_API}/sharing/list_folder_members/continue',
                    headers={
                        'Authorization': f'Bearer {token}',
                        'Content-Type':  'application/json',
                    },
                    json={'cursor': cursor},
                )
                if page_resp.status_code != 200:
                    logging.error(
                        f"[_get_folder_members] Pagination error "
                        f"{page_resp.status_code}: {page_resp.text}"
                    )
                    break  # stop pagination but return what we have so far

                page_data = page_resp.json()
                _parse_page(page_data)
                cursor = page_data.get('cursor')
                if not page_data.get('has_more') or not cursor:
                    break

    except Exception as e:
        logging.error(f"[_get_folder_members] Unexpected error: {e}")
        return []

    logging.info(
        f"[_get_folder_members] folder={shared_folder_id} → "
        f"{len(members)} member(s) found"
    )
    return members


async def _get_file_members(file_id: str, token: str) -> list:
    """
    Fetch members explicitly shared on a specific Dropbox file using
    /sharing/list_file_members with cursor-based pagination.

    Used only when has_explicit_shared_members is True on the file
    entry AND there is no parent_shared_folder_id.

    Args:
        file_id: the Dropbox file ID (entry["id"], starts with "id:")
        token: Dropbox OAuth access token

    Returns:
        list of dicts: [{"email", "name", "role", "account_id"}]
        Returns [] on any failure — but logs the full error details.
    """
    members: list = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # ── Initial request ──────────────────────────────────────
            resp = await client.post(
                f'{DBX_API}/sharing/list_file_members',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                json={'file': file_id},
            )

            if resp.status_code != 200:
                logging.error(
                    f"[_get_file_members] API returned {resp.status_code} "
                    f"for file_id={file_id}: {resp.text}"
                )
                return []

            def _parse_page(data: dict) -> None:
                """Parse users and invitees from one response page."""
                for u in data.get('users', []):
                    user_info = u.get('user', {})
                    members.append({
                        'email':      user_info.get('email', ''),
                        'name':       user_info.get('display_name', ''),
                        'role':       u.get('access_type', {}).get('.tag', ''),
                        'account_id': user_info.get('account_id', ''),
                    })
                for i in data.get('invitees', []):
                    inv = i.get('invitee', {})
                    members.append({
                        'email':      inv.get('email', ''),
                        'name':       '',
                        'role':       i.get('access_type', {}).get('.tag', ''),
                        'account_id': None,
                    })

            data = resp.json()
            _parse_page(data)

            # ── Cursor-based pagination ──────────────────────────────
            cursor = data.get('cursor')
            while cursor:
                page_resp = await client.post(
                    f'{DBX_API}/sharing/list_file_members/continue',
                    headers={
                        'Authorization': f'Bearer {token}',
                        'Content-Type':  'application/json',
                    },
                    json={'cursor': cursor},
                )
                if page_resp.status_code != 200:
                    logging.error(
                        f"[_get_file_members] Pagination error "
                        f"{page_resp.status_code}: {page_resp.text}"
                    )
                    break  # stop pagination but return what we have so far

                page_data = page_resp.json()
                _parse_page(page_data)
                cursor = page_data.get('cursor')
                if not page_data.get('has_more') or not cursor:
                    break

    except Exception as e:
        logging.error(f"[_get_file_members] Unexpected error: {e}")
        return []

    logging.info(
        f"[_get_file_members] file={file_id} → {len(members)} member(s) found"
    )
    return members


async def _verify_dropbox_scopes(token: str) -> None:
    """
    Verify the Dropbox token has the sharing.read scope by probing
    /sharing/list_mountable_folders (requires sharing.read).

    Logs a clear, actionable warning if the scope is missing so the
    developer knows exactly why shared_with is always empty.

    Args:
        token: Dropbox OAuth access token
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            test_resp = await client.post(
                f'{DBX_API}/sharing/list_mountable_folders',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                json={'limit': 1},
            )
            if test_resp.status_code in (401, 403):
                logging.warning(
                    "═══════════════════════════════════════════════════\n"
                    "[DROPBOX] MISSING SCOPE: sharing.read\n"
                    "shared_with will be empty for ALL files.\n"
                    "Fix:\n"
                    "  1. Go to console.dropbox.com → Your App → Permissions\n"
                    "  2. Enable: sharing.read\n"
                    "  3. Click Save\n"
                    "  4. Re-authenticate Dropbox in the connector UI\n"
                    "═══════════════════════════════════════════════════"
                )
            else:
                logging.info(
                    "[DROPBOX] sharing.read scope confirmed — "
                    "shared_with population enabled"
                )
    except Exception as e:
        logging.error(f"[_verify_dropbox_scopes] Could not verify: {e}")


async def _get_modifier_from_metadata(
    path_display: str,
    token: str,
) -> str:
    """
    Fallback: fetch detailed file metadata from Dropbox to find
    the modifier account_id when sharing_info.modified_by is absent
    in the list_folder entry.

    Calls /files/get_metadata with include_sharing_info=true.
    Sometimes returns more detailed sharing_info than list_folder.

    Args:
        path_display: full Dropbox path of the file (e.g.
                      "/Team Folder/Report.pdf")
        token: Dropbox OAuth access token

    Returns:
        account_id string if found, empty string if not.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f'{DBX_API}/files/get_metadata',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type':  'application/json',
                },
                json={
                    'path':                               path_display,
                    'include_media_info':                 False,
                    'include_deleted':                    False,
                    'include_has_explicit_shared_members': True,
                    'include_sharing_info':               True,
                },
            )
            if resp.status_code == 200:
                data         = resp.json()
                sharing_info = data.get('sharing_info', {})
                modifier_id  = sharing_info.get('modified_by', '')
                if modifier_id:
                    logging.info(
                        f"[_get_modifier_from_metadata] Found "
                        f"modified_by={modifier_id} for "
                        f"{path_display!r} via get_metadata fallback"
                    )
                return modifier_id or ''
            else:
                logging.warning(
                    f"[_get_modifier_from_metadata] {resp.status_code} "
                    f"for {path_display!r}: {resp.text[:200]}"
                )
                return ''
    except Exception as e:
        logging.error(
            f"[_get_modifier_from_metadata] Error for "
            f"{path_display!r}: {e}"
        )
        return ''


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

    # ── SHARING & UPLOADER RESOLUTION ──────────────────────────
    sharing_info     = entry.get('sharing_info', {})
    parent_shared_id = sharing_info.get('parent_shared_folder_id')
    modified_by_id   = sharing_info.get('modified_by')
    uploader_email   = ""
    shared_with      = []

    # Step 1: Fetch shared members
    if parent_shared_id:
        # File is inside a shared folder — inherit folder members
        logging.info(
            f"[_process_dropbox_file] Fetching folder members for "
            f"parent_shared_folder_id={parent_shared_id} "
            f"file={path_display!r}"
        )
        shared_with = await _get_folder_members(parent_shared_id, token)
    elif entry.get('has_explicit_shared_members'):
        # File has its own direct sharing
        logging.info(
            f"[_process_dropbox_file] Fetching file members for "
            f"source_id={source_id} file={path_display!r}"
        )
        shared_with = await _get_file_members(source_id, token)

    logging.info(
        f"[_process_dropbox_file] {path_display!r} → "
        f"{len(shared_with)} shared member(s), "
        f"modified_by_id={modified_by_id!r}"
    )

    # Step 2: Resolve uploader email — three-level fallback chain
    if not modified_by_id:
        # modified_by absent in list_folder entry — try get_metadata
        logging.info(
            f"[uploader_resolution] modified_by absent in list_folder "
            f"for {path_display!r} — trying get_metadata fallback"
        )
        modified_by_id = await _get_modifier_from_metadata(path_display, token)

    if modified_by_id:
        # Level 1: Check if already in shared_with member list
        match = next(
            (m['email'] for m in shared_with
             if m.get('account_id') == modified_by_id
             and m.get('email')),
            None
        )
        if match:
            uploader_email = match
            logging.info(
                f"[uploader_resolution] {path_display!r} → "
                f"resolved from member list: {uploader_email}"
            )
        else:
            # Level 2: Direct account lookup
            uploader_email = await _get_email_for_account(modified_by_id, token)
            if uploader_email:
                logging.info(
                    f"[uploader_resolution] {path_display!r} → "
                    f"resolved via get_account: {uploader_email}"
                )
            else:
                # Level 3: Genuinely unresolvable
                logging.warning(
                    f"[uploader_resolution] {path_display!r} → "
                    f"could not resolve account_id={modified_by_id} "
                    f"— uploader_email stays empty"
                )
    else:
        logging.info(
            f"[uploader_resolution] {path_display!r} → "
            f"modified_by not found in list_folder or get_metadata "
            f"— uploader_email stays empty"
        )

    # IMPORTANT: Do NOT fall back to owner_email here.
    # Pass uploader_email as-is (empty string if not resolved).
    # The normalizer must also NOT overwrite it with owner_email.
    # This preserves the distinction between:
    #   ""                   → resolution failed or not available
    #   owner_email value    → genuinely confirmed as owner
    # ── END SHARING & UPLOADER RESOLUTION ──────────────────────

    normalized    = build_dropbox_normalized(entry, content_status, owner_email, uploader_email, shared_with)
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
    
    # Notify RAG pipeline for the newly stored file
    if content_status == 'accessible':
        notify_rag_pipeline(folder_number)


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
                'include_has_explicit_shared_members': True,
                'include_sharing_info':                True,
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

        await _verify_dropbox_scopes(token)

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
                    'include_has_explicit_shared_members': True,
                    'include_sharing_info':                True,
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

                sharing_info     = entry.get('sharing_info', {})
                parent_shared_id = sharing_info.get('parent_shared_folder_id')
                modified_by_id   = sharing_info.get('modified_by')
                uploader_email   = ""
                shared_with      = []

                # Fetch members (same logic as _process_dropbox_file)
                if parent_shared_id:
                    logging.info(
                        f"[process_dropbox_delta] Fetching folder members "
                        f"parent_shared_folder_id={parent_shared_id} "
                        f"file={path_display!r}"
                    )
                    shared_with = await _get_folder_members(parent_shared_id, token)
                elif entry.get('has_explicit_shared_members'):
                    logging.info(
                        f"[process_dropbox_delta] Fetching file members "
                        f"source_id={source_id} file={path_display!r}"
                    )
                    shared_with = await _get_file_members(source_id, token)

                logging.info(
                    f"[process_dropbox_delta] {path_display!r} → "
                    f"{len(shared_with)} member(s), "
                    f"modified_by_id={modified_by_id!r}"
                )

                # Resolve uploader email — three-level fallback chain
                if not modified_by_id:
                    # modified_by absent in list_folder entry — try get_metadata
                    logging.info(
                        f"[uploader_resolution] modified_by absent in list_folder "
                        f"for {path_display!r} — trying get_metadata fallback"
                    )
                    modified_by_id = await _get_modifier_from_metadata(
                        path_display, token
                    )

                if modified_by_id:
                    # Level 1: Check if already in shared_with member list
                    match = next(
                        (m['email'] for m in shared_with
                         if m.get('account_id') == modified_by_id
                         and m.get('email')),
                        None
                    )
                    if match:
                        uploader_email = match
                        logging.info(
                            f"[uploader_resolution] {path_display!r} → "
                            f"resolved from member list: {uploader_email}"
                        )
                    else:
                        # Level 2: Direct account lookup
                        uploader_email = await _get_email_for_account(
                            modified_by_id, token
                        )
                        if uploader_email:
                            logging.info(
                                f"[uploader_resolution] {path_display!r} → "
                                f"resolved via get_account: {uploader_email}"
                            )
                        else:
                            # Level 3: Genuinely unresolvable
                            logging.warning(
                                f"[uploader_resolution] {path_display!r} → "
                                f"could not resolve account_id={modified_by_id} "
                                f"— uploader_email stays empty"
                            )
                else:
                    logging.info(
                        f"[uploader_resolution] {path_display!r} → "
                        f"modified_by not found in list_folder or get_metadata "
                        f"— uploader_email stays empty"
                    )

                # IMPORTANT: Do NOT fallback to owner_email here.
                # Empty string means "not resolved" — caller must handle that.
                updated_fields['uploader_email'] = uploader_email
                updated_fields['shared_with']    = shared_with
                updated_fields['shared']         = (
                    bool(shared_with) or bool(parent_shared_id)
                )

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
                    
                    # Notify RAG pipeline of the metadata update (or content re-download)
                    notify_rag_pipeline(folder_num)

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
