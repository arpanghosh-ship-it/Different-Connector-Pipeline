import os
from datetime import datetime, timezone

GOOGLE_NATIVE_EXPORT_MAP = {
    'application/vnd.google-apps.document': ('text/plain', '.txt'),
    'application/vnd.google-apps.spreadsheet': ('text/csv', '.csv'),
    'application/vnd.google-apps.presentation': ('text/plain', '.txt'),
    'application/vnd.google-apps.drawing': ('image/png', '.png'),
}

GOOGLE_NATIVE_TYPE_LABELS = {
    'application/vnd.google-apps.document': 'gdoc',
    'application/vnd.google-apps.spreadsheet': 'gsheet',
    'application/vnd.google-apps.presentation': 'gslides',
    'application/vnd.google-apps.drawing': 'gdrawing',
    'application/vnd.google-apps.folder': 'folder',
    'application/vnd.google-apps.form': 'gform',
    'application/vnd.google-apps.script': 'gscript',
}


def get_export_mime(mime_type: str):
    entry = GOOGLE_NATIVE_EXPORT_MAP.get(mime_type)
    if entry:
        return entry
    return None, None


def is_google_native(mime_type: str) -> bool:
    return mime_type in GOOGLE_NATIVE_EXPORT_MAP


def get_file_extension(file_name: str, mime_type: str) -> str:
    _, export_ext = get_export_mime(mime_type)
    if export_ext:
        return export_ext
    _, ext = os.path.splitext(file_name)
    return ext.lower() if ext else ''


def get_file_type_label(file_name: str, mime_type: str) -> str:
    if mime_type in GOOGLE_NATIVE_TYPE_LABELS:
        return GOOGLE_NATIVE_TYPE_LABELS[mime_type]
    ext = get_file_extension(file_name, mime_type)
    return ext.lstrip('.') if ext else mime_type.split('/')[-1][:10]


def format_size(size_bytes) -> str:
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


def build_normalized_document(file: dict, path: str, content_status: str, owner_email: str = None) -> dict:
    export_mime, _ = get_export_mime(file.get('mimeType', ''))
    file_name = file.get('name', '')
    mime_type = file.get('mimeType', '')
    size_bytes = int(file.get('size', 0)) if file.get('size') else None

    return {
        'source_id': file['id'],
        'source_type': 'drive',
        'file_name': file_name,
        'mime_type': mime_type,
        'export_mime_type': export_mime,
        'file_extension': get_file_extension(file_name, mime_type),
        'file_type': get_file_type_label(file_name, mime_type),
        'size_bytes': size_bytes,
        'size_human': format_size(size_bytes),
        'path': path,
        'parent_folder_id': (file.get('parents') or [None])[0],
        'owner_email': owner_email or (
            file.get('owners', [{}])[0].get('emailAddress') if file.get('owners') else None
        ),
        'web_url': file.get('webViewLink'),
        'shared': file.get('shared', False),
        'modified_at': file.get('modifiedTime'),
        'content_status': content_status,
        'raw_file_path': None,
        'folder_number': None,
        'connector_synced_at': datetime.now(timezone.utc).isoformat(),
    }
