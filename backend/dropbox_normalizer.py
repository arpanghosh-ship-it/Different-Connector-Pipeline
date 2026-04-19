"""
dropbox_normalizer.py
Builds the same normalized.json schema used by the Google Drive connector,
but populated from Dropbox file metadata.

Normalized schema (identical to Drive for pipeline compatibility):
  source_id, source_type, file_name, mime_type, export_mime_type,
  file_extension, file_type, size_bytes, size_human, path,
  parent_folder_id, owner_email, web_url, shared, modified_at,
  content_status, raw_file_path, folder_number, connector_synced_at
"""
import mimetypes
import os
from datetime import datetime, timezone

# ── MIME guessing ──────────────────────────────────────────────────────────────

_EXT_TO_MIME = {
    '.pdf':  'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.txt':  'text/plain',
    '.csv':  'text/csv',
    '.md':   'text/markdown',
    '.html': 'text/html',
    '.jpg':  'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png':  'image/png',
    '.gif':  'image/gif',
    '.webp': 'image/webp',
    '.mp4':  'video/mp4',
    '.mp3':  'audio/mpeg',
    '.zip':  'application/zip',
    '.json': 'application/json',
}


def _guess_mime(file_name: str) -> str:
    ext = os.path.splitext(file_name)[1].lower()
    if ext in _EXT_TO_MIME:
        return _EXT_TO_MIME[ext]
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or 'application/octet-stream'


def _file_type_label(file_name: str, mime_type: str) -> str:
    ext = os.path.splitext(file_name)[1].lower().lstrip('.')
    return ext if ext else mime_type.split('/')[-1][:10]


def _format_size(size_bytes) -> str | None:
    if size_bytes is None:
        return None
    size_bytes = int(size_bytes)
    if size_bytes == 0:
        return '0 B'
    if size_bytes < 1024:
        return f'{size_bytes} B'
    if size_bytes < 1024 ** 2:
        return f'{size_bytes / 1024:.1f} KB'
    if size_bytes < 1024 ** 3:
        return f'{size_bytes / (1024 ** 2):.1f} MB'
    return f'{size_bytes / (1024 ** 3):.2f} GB'


def build_dropbox_normalized(
    entry: dict,
    content_status: str,
    owner_email: str = '',
) -> dict:
    """
    Build normalized.json from a Dropbox files/list_folder entry.

    `entry` shape (from Dropbox API):
    {
      ".tag":            "file",
      "name":            "Report.pdf",
      "path_display":    "/Folder/Subfolder/Report.pdf",
      "id":              "id:abc123...",
      "client_modified": "2024-01-15T10:30:00Z",
      "server_modified": "2024-01-15T10:35:00Z",
      "size":            102400,
      "content_hash":    "abc123..."  <- Dropbox native hash
    }
    """
    file_name  = entry.get('name', '')
    path       = entry.get('path_display', '')
    source_id  = entry.get('id', '')
    size_bytes = entry.get('size')

    # Dropbox uses client_modified as the user-visible modification time
    modified_at = entry.get('client_modified') or entry.get('server_modified')

    mime_type = _guess_mime(file_name)
    ext       = os.path.splitext(file_name)[1].lower()

    # Parent folder path = everything before the last "/" in path_display
    parent_path = path.rsplit('/', 1)[0] if '/' in path else ''

    # Build a web URL from the path (opens Dropbox web UI)
    web_url = f'https://www.dropbox.com/home{path}' if path else None

    return {
        'source_id':             source_id,
        'source_type':           'dropbox',
        'file_name':             file_name,
        'mime_type':             mime_type,
        'export_mime_type':      None,          # Dropbox has no native-format conversion
        'file_extension':        ext,
        'file_type':             _file_type_label(file_name, mime_type),
        'size_bytes':            size_bytes,
        'size_human':            _format_size(size_bytes),
        'path':                  path,
        'parent_folder_id':      parent_path,
        'owner_email':           owner_email,
        'web_url':               web_url,
        'shared':                False,          # Sharing info requires a separate API call
        'modified_at':           modified_at,
        'content_status':        content_status,
        'raw_file_path':         None,           # filled in by storage.save_file_pair
        'folder_number':         None,           # filled in by storage.save_file_pair
        'connector_synced_at':   datetime.now(timezone.utc).isoformat(),
        # Dropbox extras (stored alongside standard fields for pipeline use)
        'dropbox_content_hash':  entry.get('content_hash'),
        'dropbox_rev':           entry.get('rev'),
    }
