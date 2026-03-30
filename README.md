# Google Drive Connector

A highly resilient, modular monolith ingestion service built with FastAPI. This connector fetches files from Google Drive and transforms them into a standardized, source-agnostic `NormalizedDocument` schema, making it ideal for feeding downstream chunking pipelines, RAG chatbots, and vector databases.

## 🌟 Core Architecture

The connector is designed around a **7-Layer Normalize Adapter** pattern. A failure in any layer produces a deterministic, storable outcome rather than a crash, ensuring the pipeline remains resilient and retryable.

1. **OAuth Token Check:** Proactively verifies and refreshes tokens before they expire.
2. **Drive Type Router:** Automatically handles API parameter adjustments for My Drive vs. Shared Drives.
3. **Folder Access & Path Cache:** Resolves full file paths locally to avoid expensive recursive API calls.
4. **Metadata Fetch:** Pulls all necessary non-content fields using optimized field masks.
5. **Content Fetch:** Routes Google-native formats (Docs, Sheets) to `.export()` and binary files to `.get(alt=media)`.
6. **Error Classifier:** Deterministically classifies API responses (200 Accessible, 403 Inaccessible, 404 Deleted).
7. **Normalize Adapter:** Maps the data into the universal `NormalizedDocument` schema and persists it.

## 📁 Project Structure

```text
backend/
├── main.py                 # FastAPI application and SSE event stream
├── requirements.txt        # Python dependencies
├── config/
│   └── settings.py         # Environment variables and constants
├── auth/
│   ├── router.py           # OAuth2 login, callback, and user info routes
│   ├── flow.py             # Google Auth flow configuration
│   ├── credentials.py      # Token storage and proactive refresh logic
│   └── state_store.py      # OAuth state validation
├── sync/
│   ├── crawler.py          # Recursive folder crawling and file processing
│   ├── drive_client.py     # HTTPX client for Google Drive API interactions
│   └── poller.py           # APScheduler background sync jobs
├── normalize/
│   ├── document.py         # NormalizedDocument schema builder
│   ├── mime.py             # MIME type detection and Google Workspace export mapping
│   └── formatters.py       # Human-readable byte formatting
├── storage/
│   ├── file_store.py       # Local persistence for raw files and normalized JSON
│   ├── visited.py          # Duplicate tracking via source_id
│   └── root_folder.py      # State management for the current sync target
└── events/
    └── bus.py              # Async queue for real-time Server-Sent Events (SSE)
```

## 🚀 Getting Started

### Prerequisites

- Python 3.12+
- A Google Cloud Project with the Google Drive API enabled.
- OAuth 2.0 Client IDs configured in your Google Cloud Console.

### 1. Environment Setup

Create a `.env` file in the root `backend/` directory:

```env
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
FRONTEND_URL=http://localhost:5173
STORAGE_DIR=./storage
MAX_FILE_SIZE_MB=50
POLL_INTERVAL_SECONDS=30
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Server

```bash
uvicorn main:app --reload --port 8000
```

## 📡 API Reference

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/auth/login` | Initiates the Google OAuth2 flow. |
| `GET` | `/auth/callback` | Handles the OAuth callback and exchanges the code for tokens. |
| `GET` | `/auth/me` | Returns the authenticated user's profile information. |
| `GET` | `/auth/logout` | Clears local credentials. |

### Crawling & Sync

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/start-crawl` | Triggers a recursive sync of a specific Drive folder. Body: `{"folder_id": "string", "folder_name": "string"}` |
| `GET` | `/api/status` | Returns current auth status, active root folder, and total files stored. |
| `GET` | `/api/folders?parent_id=root` | Lists subfolders for a given parent ID. |
| `GET` | `/api/files` | Returns a consolidated list of all successfully normalized files in local storage. |

### Background Poller

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/start-poll` | Resumes the background scheduler (runs every 30s). |
| `POST` | `/api/stop-poll` | Pauses the background scheduler. |

### Real-time Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/events` | An SSE endpoint that streams real-time updates about the crawler's progress (e.g., `scan_start`, `file_found`, `stored`, `skipped`, `error`). |

## 📄 Output Schema (`NormalizedDocument`)

Every file successfully processed by the connector will be saved alongside its raw binary/text counterpart as a `normalized.json` file. This schema acts as a universal contract for your downstream AI ingestion pipelines.

```json
{
  "source_id": "1A2B3C4D5E...",
  "source_type": "drive",
  "file_name": "Q1 Architecture Roadmap",
  "mime_type": "application/vnd.google-apps.document",
  "export_mime_type": "text/plain",
  "file_extension": ".txt",
  "file_type": "gdoc",
  "size_bytes": 10245,
  "size_human": "10.0 KB",
  "path": "/Engineering/Q1 Architecture Roadmap",
  "parent_folder_id": "xyz123...",
  "owner_email": "engineer@intglobal.com",
  "web_url": "https://docs.google.com/document/d/...",
  "shared": true,
  "modified_at": "2026-03-31T10:00:00.000Z",
  "content_status": "accessible",
  "raw_file_path": "./storage/1/raw.txt",
  "folder_number": 1,
  "connector_synced_at": "2026-03-31T14:30:00.000Z"
}
```
