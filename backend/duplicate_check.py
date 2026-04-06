import json
import os
import asyncio
from config import VISITED_FILE, STORAGE_DIR

_lock = asyncio.Lock()

# Define the new file path for storing content hashes
CONTENT_HASHES_FILE = os.path.join(STORAGE_DIR, 'content_hashes.json')

def _load() -> dict:
    os.makedirs(STORAGE_DIR, exist_ok=True)
    if not os.path.exists(VISITED_FILE):
        return {}
    try:
        with open(VISITED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict):
    with open(VISITED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def is_visited(source_id: str) -> bool:
    return source_id in _load()


def mark_visited(source_id: str, folder_number: int, file_name: str, path: str):
    visited = _load()
    visited[source_id] = {
        'folder_number': folder_number,
        'file_name': file_name,
        'path': path,
    }
    _save(visited)


def get_all_visited() -> dict:
    return _load()


def total_visited() -> int:
    return len(_load())


# --- NEW CONTENT HASHING LOGIC ---

def _load_hashes() -> dict:
    if not os.path.exists(CONTENT_HASHES_FILE):
        return {}
    try:
        with open(CONTENT_HASHES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_hashes(data: dict):
    with open(CONTENT_HASHES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def is_content_seen(content_hash: str) -> bool:
    """Checks if a file with this exact content hash has already been stored."""
    if not content_hash: 
        return False
    return content_hash in _load_hashes()


def mark_content_seen(content_hash: str, original_folder_number: int):
    """Saves the hash pointing to the original folder number to prevent future duplicates."""
    if not content_hash:
        return
    hashes = _load_hashes()
    hashes[content_hash] = {
        'folder_number': original_folder_number
    }
    _save_hashes(hashes)


def get_original_folder(content_hash: str) -> int:
    """Retrieves the folder number where the original identical content is stored."""
    return _load_hashes().get(content_hash, {}).get('folder_number')