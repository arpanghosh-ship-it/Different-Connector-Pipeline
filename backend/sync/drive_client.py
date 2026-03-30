import httpx
from config.settings import MAX_FILE_SIZE_BYTES
from normalize.mime import is_google_native, get_export_mime

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_EXPORT_URL = "https://www.googleapis.com/drive/v3/files/{id}/export"
DRIVE_DOWNLOAD_URL = "https://www.googleapis.com/drive/v3/files/{id}?alt=media&supportsAllDrives=true"

async def list_items(folder_id: str, token: str) -> list:
    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
        "fields": "files(id,name,mimeType,parents,modifiedTime,owners,shared,size,webViewLink,driveId),nextPageToken",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
        "pageSize": "1000",
    }
    headers = {"Authorization": f"Bearer {token}"}
    all_items = []

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.get(DRIVE_FILES_URL, params=params, headers=headers)
            if resp.status_code == 401:
                raise Exception("Token expired")
            resp.raise_for_status()
            data = resp.json()
            all_items.extend(data.get("files", []))
            next_token = data.get("nextPageToken")
            if not next_token:
                break
            params["pageToken"] = next_token

    return all_items

async def fetch_content(file: dict, token: str) -> tuple[bytes, str]:
    headers = {"Authorization": f"Bearer {token}"}
    mime = file.get("mimeType", "")

    size = int(file.get("size", 0)) if file.get("size") else 0
    if size > MAX_FILE_SIZE_BYTES and not is_google_native(mime):
        raise ValueError(f"File too large: {size} bytes")

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        if is_google_native(mime):
            export_mime, _ = get_export_mime(mime)
            url = DRIVE_EXPORT_URL.format(id=file["id"])
            resp = await client.get(url, params={"mimeType": export_mime}, headers=headers)
        else:
            url = DRIVE_DOWNLOAD_URL.format(id=file["id"])
            resp = await client.get(url, headers=headers)

        if resp.status_code == 403:
            raise PermissionError("403 Forbidden")
        if resp.status_code == 404:
            raise FileNotFoundError("404 Not Found")
        resp.raise_for_status()

        actual_mime = export_mime if is_google_native(mime) else mime
        return resp.content, actual_mime

async def list_drive_folders(token: str, parent_id: str = "root") -> list:
    params = {
        "q": f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        "fields": "files(id,name,parents)",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
        "orderBy": "name",
        "pageSize": "100",
    }
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(DRIVE_FILES_URL, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json().get("files", [])