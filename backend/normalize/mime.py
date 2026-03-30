import os

GOOGLE_NATIVE_EXPORT_MAP = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}

GOOGLE_NATIVE_TYPE_LABELS = {
    "application/vnd.google-apps.document": "gdoc",
    "application/vnd.google-apps.spreadsheet": "gsheet",
    "application/vnd.google-apps.presentation": "gslides",
    "application/vnd.google-apps.drawing": "gdrawing",
    "application/vnd.google-apps.folder": "folder",
    "application/vnd.google-apps.form": "gform",
    "application/vnd.google-apps.script": "gscript",
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
    return ext.lower() if ext else ""

def get_file_type_label(file_name: str, mime_type: str) -> str:
    if mime_type in GOOGLE_NATIVE_TYPE_LABELS:
        return GOOGLE_NATIVE_TYPE_LABELS[mime_type]
    ext = get_file_extension(file_name, mime_type)
    return ext.lstrip(".") if ext else mime_type.split("/")[-1][:10]