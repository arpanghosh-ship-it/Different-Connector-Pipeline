from datetime import datetime, timezone
from normalize.mime import get_export_mime, get_file_extension, get_file_type_label
from normalize.formatters import format_size

def build_normalized_document(file: dict, path: str, content_status: str, owner_email: str = None) -> dict:
    export_mime, _ = get_export_mime(file.get("mimeType", ""))
    file_name = file.get("name", "")
    mime_type = file.get("mimeType", "")
    size_bytes = int(file.get("size", 0)) if file.get("size") else None

    return {
        "source_id": file["id"],
        "source_type": "drive",
        "file_name": file_name,
        "mime_type": mime_type,
        "export_mime_type": export_mime,
        "file_extension": get_file_extension(file_name, mime_type),
        "file_type": get_file_type_label(file_name, mime_type),
        "size_bytes": size_bytes,
        "size_human": format_size(size_bytes),
        "path": path,
        "parent_folder_id": (file.get("parents") or [None])[0],
        "owner_email": owner_email or (
            file.get("owners", [{}])[0].get("emailAddress") if file.get("owners") else None
        ),
        "web_url": file.get("webViewLink"),
        "shared": file.get("shared", False),
        "modified_at": file.get("modifiedTime"),
        "content_status": content_status,
        "raw_file_path": None,
        "folder_number": None,
        "connector_synced_at": datetime.now(timezone.utc).isoformat(),
    }