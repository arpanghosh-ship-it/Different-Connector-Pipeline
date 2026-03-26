import json
import os
import asyncio
from config import VISITED_FILE, STORAGE_DIR

_lock = asyncio.Lock()


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
