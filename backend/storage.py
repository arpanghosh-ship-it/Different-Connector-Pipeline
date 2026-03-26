import json
import os
import mimetypes
import aiofiles
from config import STORAGE_DIR, COUNTER_FILE

os.makedirs(STORAGE_DIR, exist_ok=True)


def _get_next_number() -> int:
    if not os.path.exists(COUNTER_FILE):
        data = {'next': 1}
    else:
        with open(COUNTER_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

    current = int(data['next'])
    data['next'] = current + 1
    with open(COUNTER_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return current


def _ext_from_mime(mime_type: str) -> str:
    ext_map = {
        'text/plain': '.txt',
        'text/csv': '.csv',
        'application/pdf': '.pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/webp': '.webp',
        'application/zip': '.zip',
        'application/json': '.json',
        'text/html': '.html',
        'text/markdown': '.md',
    }
    if mime_type in ext_map:
        return ext_map[mime_type]
    ext = mimetypes.guess_extension(mime_type)
    return ext if ext else '.bin'


async def save_file_pair(source_id: str, normalized: dict, raw_content: bytes, raw_mime: str) -> int:
    folder_number = _get_next_number()
    folder_path = os.path.join(STORAGE_DIR, str(folder_number))
    os.makedirs(folder_path, exist_ok=True)

    ext = _ext_from_mime(raw_mime)
    raw_file_name = f'raw{ext}'
    raw_file_path = os.path.join(folder_path, raw_file_name)

    async with aiofiles.open(raw_file_path, 'wb') as f:
        await f.write(raw_content)

    normalized['raw_file_path'] = raw_file_path
    normalized['folder_number'] = folder_number

    json_path = os.path.join(folder_path, 'normalized.json')
    async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(normalized, indent=2))

    return folder_number


def _folder_sort_key(entry):
    try:
        return int(entry.name)
    except ValueError:
        return entry.name


def get_all_stored_files() -> list:
    results = []
    if not os.path.exists(STORAGE_DIR):
        return results

    entries = [e for e in os.scandir(STORAGE_DIR) if e.is_dir()]
    entries.sort(key=_folder_sort_key)

    for entry in entries:
        json_path = os.path.join(entry.path, 'normalized.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    results.append(json.load(f))
            except Exception:
                pass

    results.sort(key=lambda item: (int(item.get('folder_number') or 10**12), item.get('file_name') or ''))
    return results
