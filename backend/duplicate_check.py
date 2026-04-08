import json
import os
import asyncio
from config import VISITED_FILE, STORAGE_DIR

_lock = asyncio.Lock()

# Define the new file path for storing content hashes
CONTENT_HASHES_FILE = os.path.join(STORAGE_DIR, 'content_hashes.json')

async def _load() -> dict:
    os.makedirs(STORAGE_DIR, exist_ok=True)
    if not os.path.exists(VISITED_FILE):
        return {}
    async with _lock:
        try:
            with open(VISITED_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}


async def _save(data: dict):
    async with _lock:
        with open(VISITED_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)


async def is_visited(source_id: str) -> bool:
    data = await _load()
    return source_id in data


async def mark_visited(source_id: str, folder_number: int, file_name: str, path: str):
    visited = await _load()
    visited[source_id] = {
        'folder_number': folder_number,
        'file_name': file_name,
        'path': path,
    }
    await _save(visited)


async def get_all_visited() -> dict:
    return await _load()


async def total_visited() -> int:
    data = await _load()
    return len(data)


# --- NEW CONTENT HASHING LOGIC ---

async def _load_hashes() -> dict:
    if not os.path.exists(CONTENT_HASHES_FILE):
        return {}
    async with _lock:
        try:
            with open(CONTENT_HASHES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}


async def _save_hashes(data: dict):
    async with _lock:
        with open(CONTENT_HASHES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)


async def is_content_seen(content_hash: str) -> bool:
    """Checks if a file with this exact content hash has already been stored."""
    if not content_hash: 
        return False
    data = await _load_hashes()
    return content_hash in data


async def mark_content_seen(content_hash: str, original_folder_number: int):
    """Saves the hash pointing to the original folder number to prevent future duplicates."""
    if not content_hash:
        return
    hashes = await _load_hashes()
    hashes[content_hash] = {
        'folder_number': original_folder_number
    }
    await _save_hashes(hashes)


async def get_original_folder(content_hash: str) -> int:
    """Retrieves the folder number where the original identical content is stored."""
    data = await _load_hashes()
    return data.get(content_hash, {}).get('folder_number')