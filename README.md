# ☁️ RAG One Space — Multi-Cloud Document Intelligence Platform

A full-stack platform that synchronizes documents from **Google Drive** and **Dropbox** in real time, ingests them into a **vector database**, and exposes a **RAG-powered chat API** for natural language document querying — with built-in accuracy evaluation using **RAGAS**.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [System Architecture](#-system-architecture)
- [Features](#-features)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Cloud Provider Setup](#-cloud-provider-setup)
- [Local Development](#-local-development)
- [Docker Deployment](#-docker-deployment)
- [Environment Variables](#-environment-variables)
- [API Reference](#-api-reference)
- [RAG Evaluation](#-rag-evaluation)
- [Known Limitations](#-known-limitations)
- [Troubleshooting](#-troubleshooting)

---

## 🌐 Overview

RAG One Space is a three-service platform:

| Service | Technology | Port | Role |
|---|---|---|---|
| **Frontend** | React + Vite | 5173 | Connector dashboard UI |
| **Backend (Connector Pipeline)** | FastAPI (Python 3.11+) | 8000 | Cloud sync, OAuth, webhook handling |
| **RAG Pipeline** | FastAPI (Python 3.11+) | 8001 | Document ingestion, vector search, chat API |

| Capability | Details |
|---|---|
| Cloud Providers | Google Drive, Dropbox |
| Auth | OAuth 2.0 (both providers) |
| Sync Strategy | Webhook-driven delta sync (cursor/token-based) |
| Deduplication | SHA-256 content hashing |
| Live Monitoring | Server-Sent Events (SSE) |
| Vector Database | Qdrant Cloud |
| Embedding Model | OpenAI `text-embedding-3-large` (3072 dims) |
| Answer Generation | OpenAI `gpt-4o` |
| Evaluation | RAGAS (Faithfulness, Answer Relevancy, Context Precision, Context Recall) |

---

## 🏗️ System Architecture

```
[Google Drive / Dropbox]
        │  webhook fires on file change
        ▼
[Backend — Connector Pipeline :8000]
        │  downloads raw file
        │  writes storage/{n}/raw.{ext}
        │  writes storage/{n}/normalized.json
        │  calls POST /ingest/{n} → RAG Pipeline
        ▼
[RAG Pipeline :8001]
        │  reads storage/{n}/raw.{ext}       (READ ONLY)
        │  reads storage/{n}/normalized.json (READ ONLY)
        │  extracts text (PyMuPDF + GPT-4o OCR fallback)
        │  chunks → embeds (text-embedding-3-large)
        │  upserts to Qdrant Cloud
        ▼
[Qdrant Cloud — "documents" collection]
        │  top-15 cosine similarity search
        ▼
[POST /query or /query-global]
        │  GPT-4o answers with retrieved context
        ▼
[{success, message, data: {answer, sources}}]
```

---

## ⚙️ Features

### 🔐 Unified Authentication
- **Google Drive** — OAuth 2.0 via Google Cloud Console
- **Dropbox** — OAuth 2.0 via Dropbox Developer Console with `sharing.read` scope for member resolution

### 📡 Real-Time Delta Sync Engines
- **Google Drive** — `watch()` subscription model for push notifications
- **Dropbox** — Challenge-response webhook with cursor-based delta sync
- **Auto-trigger** — Every successful file sync automatically notifies the RAG pipeline to re-ingest

### 📁 Intelligent Storage
- **Cross-cloud deduplication** — SHA-256 hashing prevents duplicate downloads
- **Unified metadata schema** — `normalized.json` written for every file regardless of source
- **Live path updates** — `normalized.json` updates automatically when files are renamed or moved in Drive/Dropbox
- **Content status tracking** — `accessible`, `too_large`, `deleted`, `inaccessible`, `error`

### 🔎 Dropbox Sharing Intelligence
- **Inherited member fetching** — Resolves folder-level sharing via `/sharing/list_folder_members` with full cursor-based pagination
- **Uploader resolution** — Three-level fallback: member list → `/users/get_account` → `/files/get_metadata`
- **`shared_with` population** — Lists all collaborators (users, invitees, groups) with name, email, and role
- **Scope verification** — Startup check confirms `sharing.read` scope with actionable error message if missing

### 🧠 RAG Pipeline
- **Multi-format support** — PDF (text + scanned), XLSX, CSV, TXT, PNG, JPG
- **Scanned PDF handling** — PyMuPDF extracts text; pages with < 150 chars fall back to GPT-4o Vision OCR
- **Smart chunking** — `RecursiveCharacterTextSplitter` (LangChain) for prose, row-per-chunk for tabular data
- **Metadata-rich chunks** — Every chunk stores `file_path`, `parent_folder`, `web_url`, `source_type`, `owner_email` for location queries
- **Re-ingestion safety** — Deletes old Qdrant points by `source_id` before upserting to prevent duplicates
- **Bulk re-ingestion** — `POST /ingest/all` re-indexes all storage folders in one call

### 📊 RAG Accuracy Evaluation
- **Synthetic test generation** — RAGAS `TestsetGenerator` creates Q&A pairs from HR/policy PDFs automatically
- **Four RAGAS metrics** — Faithfulness, Answer Relevancy, Context Precision, Context Recall
- **Reports** — CSV (per-question scores, sorted worst-first) + JSON summary with pass rates, failed queries, score distribution
- **Score threshold** — Queries scoring below 0.70 on any metric are flagged

### 🌐 Standardized API Responses
Every endpoint in both services returns the same envelope:
```json
{
    "success": true,
    "message": "Human-readable status",
    "data": { }
}
```

---

## 🗂️ Project Structure

```
RAG_One_Space/
│
├── docker-compose.yml              ← runs all 3 services together
├── .dockerignore
├── README.md
│
├── backend/                        ← Connector Pipeline (port 8000)
│   ├── main.py                     ← FastAPI app entry point
│   ├── auth.py                     ← Google OAuth logic
│   ├── crawler.py                  ← Google Drive recursive crawl + delta sync
│   ├── dropbox_auth.py             ← Dropbox OAuth logic
│   ├── dropbox_crawler.py          ← Dropbox recursive crawl + delta sync
│   ├── dropbox_normalizer.py       ← Dropbox metadata normalization
│   ├── dropbox_webhook.py          ← Dropbox webhook handler
│   ├── webhook.py                  ← Google Drive webhook handler
│   ├── normalizer.py               ← Google Drive metadata normalization
│   ├── storage.py                  ← File storage + deduplication logic
│   ├── duplicate_check.py          ← Content hash tracking
│   ├── events.py                   ← SSE broadcast
│   ├── config.py                   ← Environment config loader
│   ├── response.py                 ← Standardized response envelope
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env
│   └── storage/                    ← Local file store (shared with RAG pipeline)
│       ├── {folder_number}/
│       │   ├── raw.{ext}           ← downloaded file
│       │   └── normalized.json     ← metadata
│       └── dropbox/                ← internal Dropbox cursor/root files
│
├── rag_pipeline/                   ← RAG Pipeline (port 8001)
│   ├── main.py                     ← FastAPI app entry point
│   ├── api_routes.py               ← /ingest, /ingest/all, /query, /query-global
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env
│   │
│   ├── ingestion/
│   │   ├── ingestion_pipeline.py   ← orchestrator (read → chunk → embed → store)
│   │   ├── preprocessor/
│   │   │   ├── router.py           ← routes file type to correct parser
│   │   │   ├── pdf_parser.py       ← PyMuPDF + GPT-4o OCR fallback
│   │   │   ├── xlsx_parser.py      ← pandas sheet-wise row extraction
│   │   │   ├── csv_parser.py       ← pandas row extraction
│   │   │   ├── txt_parser.py       ← plain text reader
│   │   │   └── image_parser.py     ← GPT-4o vision OCR
│   │   └── chunker/
│   │       ├── text_chunker.py     ← LangChain RecursiveCharacterTextSplitter
│   │       └── table_chunker.py    ← custom row-per-chunk (no LangChain)
│   │
│   ├── store/
│   │   └── qdrant_store.py         ← embed + upsert + delete + collection init
│   │
│   ├── retrieval/
│   │   └── rag_query.py            ← embed → search Qdrant → GPT-4o answer
│   │
│   ├── utils/
│   │   ├── schema.py               ← ChunkPayload TypedDict (16 fields)
│   │   ├── ids.py                  ← uuid4 chunk IDs + uuid5 document IDs
│   │   ├── file_io.py              ← reads storage folder (READ ONLY)
│   │   └── response.py             ← standardized response envelope
│   │
│   └── evaluation/                 ← RAGAS accuracy evaluation
│       ├── config.py               ← evaluation settings
│       ├── create_dataset.py       ← generate synthetic Q&A from PDFs
│       ├── run_eval.py             ← run pipeline + RAGAS metrics
│       ├── report_generator.py     ← CSV + JSON reports
│       ├── hr_documents/           ← place HR PDFs here for evaluation
│       └── reports/                ← evaluation output CSVs and JSONs
│
└── frontend/                       ← React + Vite Dashboard (port 5173)
    ├── src/
    │   └── components/
    │       ├── LoginPage.jsx
    │       ├── FolderPicker.jsx
    │       ├── DropboxFolderPicker.jsx
    │       └── Dashboard.jsx
    ├── nginx.conf                  ← API proxy for Docker deployment
    ├── Dockerfile
    ├── vite.config.js
    └── package.json
```

---

## 🔑 Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Backend + RAG Pipeline |
| Node.js | 18+ | Frontend |
| ngrok | Latest | Public webhook URLs for local dev |
| Docker + Docker Compose | Latest | Containerized deployment |
| OpenAI API Key | — | Embeddings + GPT-4o (RAG + OCR) |
| Qdrant Cloud Account | — | Vector database |

> **Windows note:** If you get SSL errors locally, run `pip install python-certifi-win32`. This package is excluded from Docker builds automatically.

---

## ☁️ Cloud Provider Setup

### 1. Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **Google Drive API**
3. Configure the **OAuth consent screen**
4. Create **Web Application** credentials

**Authorized Redirect URI:**
```
http://localhost:8000/auth/callback
```

---

### 2. Dropbox Developer Console

1. Go to [Dropbox App Console](https://www.dropbox.com/developers/apps)
2. Create a new app (Full Dropbox, Scoped Access)
3. Add the following **Redirect URIs:**
```
http://localhost:8000/dropbox/callback
https://<your-ngrok-id>.ngrok-free.app/dropbox/callback
```
4. Add the following **Webhook URI:**
```
https://<your-ngrok-id>.ngrok-free.app/api/webhook/dropbox
```
5. Enable these **Permissions** (all are required):

| Permission | Purpose |
|---|---|
| `files.metadata.read` | List and read file metadata |
| `files.content.read` | Download file contents |
| `account_info.read` | Resolve uploader account emails |
| `sharing.read` | Fetch folder members + shared_with list |

> ⚠️ After enabling `sharing.read`, you must **re-authenticate** Dropbox in the dashboard. Existing tokens do not automatically receive new scopes.

### 3. Qdrant Cloud

1. Go to [cloud.qdrant.io](https://cloud.qdrant.io)
2. Create a free cluster
3. Copy the **Cluster URL** and generate an **API Key**
4. Add both to `rag_pipeline/.env`

The RAG pipeline creates the `documents` collection automatically on first startup.

---

## 🚀 Local Development

### Step 1 — Backend Setup

```bash
cd backend
python -m venv .venv

# Activate
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

### Step 2 — RAG Pipeline Setup

```bash
cd rag_pipeline
python -m venv .venv

# Activate
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

### Step 3 — Frontend Setup

```bash
cd frontend
npm install
```

### Step 4 — Start ngrok

```bash
ngrok http 8000
```

Copy your ngrok URL (e.g. `https://abc123.ngrok-free.app`) — needed in `.env` and the Dropbox console.

### Step 5 — Configure Environment Variables

**`backend/.env`:**
```env
# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# Dropbox OAuth
DROPBOX_APP_KEY=your_dropbox_app_key
DROPBOX_APP_SECRET=your_dropbox_app_secret
DROPBOX_REDIRECT_URI=https://<your-ngrok-id>.ngrok-free.app/dropbox/callback

# General
WEBHOOK_URL=https://<your-ngrok-id>.ngrok-free.app
FRONTEND_URL=http://localhost:5173
STORAGE_DIR=./storage
MAX_FILE_SIZE_MB=50

# RAG Pipeline URL (connector notifies RAG after each file sync)
RAG_PIPELINE_URL=http://localhost:8001
```

**`rag_pipeline/.env`:**
```env
OPENAI_API_KEY=your_openai_api_key
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key

# Absolute path to backend storage folder
STORAGE_BASE_PATH=C:\path\to\RAG_One_Space\backend\storage   # Windows
# STORAGE_BASE_PATH=/path/to/RAG_One_Space/backend/storage   # macOS/Linux
```

### Step 6 — Run All Three Services

Open three separate terminals:

**Terminal 1 — Backend (Connector Pipeline):**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 2 — RAG Pipeline:**
```bash
cd rag_pipeline
uvicorn main:app --reload --port 8001
```

**Terminal 3 — Frontend:**
```bash
cd frontend
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## 🐳 Docker Deployment

Run all three services with a single command from the project root:

```bash
# First time — build all images
docker compose build

# Start all services
docker compose up

# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop all services
docker compose down
```

**Port mapping in Docker:**

| Service | Browser URL | Container Port |
|---|---|---|
| Frontend | http://localhost:5173 | 80 (nginx) |
| Backend | http://localhost:8000 | 8000 |
| RAG Pipeline | http://localhost:8001 | 8001 |

> **ngrok note:** When running in Docker, ngrok must still run on your host machine (`ngrok http 8000`). Docker maps host port 8000 to the backend container — the ngrok tunnel continues to work the same way.

> **Windows path note:** The `STORAGE_BASE_PATH` in `rag_pipeline/.env` uses a Windows absolute path for local dev. Docker overrides this automatically with `/app/storage` via the `docker-compose.yml` environment block — no manual change needed.

---

## 🔧 Environment Variables

### `backend/.env`

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | OAuth callback (local: `http://localhost:8000/auth/callback`) |
| `DROPBOX_APP_KEY` | Dropbox app key |
| `DROPBOX_APP_SECRET` | Dropbox app secret |
| `DROPBOX_REDIRECT_URI` | Dropbox OAuth callback URL |
| `WEBHOOK_URL` | Your public ngrok URL (e.g. `https://abc.ngrok-free.app`) |
| `FRONTEND_URL` | Frontend origin (default: `http://localhost:5173`) |
| `STORAGE_DIR` | Local storage path (default: `./storage`) |
| `MAX_FILE_SIZE_MB` | Max file size to download (default: `50`) |
| `RAG_PIPELINE_URL` | RAG pipeline URL (default: `http://localhost:8001`) |

### `rag_pipeline/.env`

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key (used for embeddings + GPT-4o) |
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key |
| `STORAGE_BASE_PATH` | Absolute path to `backend/storage/` folder |

---

## 📡 API Reference

All endpoints return the standardized envelope:
```json
{
    "success": true,
    "message": "Human-readable status",
    "data": { }
}
```

### Backend — Connector Pipeline (port 8000)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/auth/login` | Start Google Drive OAuth flow |
| `GET` | `/auth/callback` | Google OAuth callback |
| `GET` | `/auth/status` | Check Google Drive auth status |
| `GET` | `/auth/logout` | Revoke Google Drive session |
| `GET` | `/dropbox/login` | Start Dropbox OAuth flow |
| `GET` | `/dropbox/callback` | Dropbox OAuth callback |
| `GET` | `/dropbox/status` | Check Dropbox auth status |
| `GET` | `/dropbox/logout` | Revoke Dropbox session |
| `GET` | `/api/files` | List all synced files with metadata |
| `GET` | `/api/folders` | List available Google Drive folders |
| `GET` | `/api/dropbox/folders` | List available Dropbox folders |
| `POST` | `/api/crawl` | Start Google Drive folder crawl |
| `POST` | `/api/dropbox/crawl` | Start Dropbox folder crawl |
| `GET` | `/api/webhook/dropbox` | Dropbox webhook challenge verification |
| `POST` | `/api/webhook/dropbox` | Receive Dropbox webhook events |
| `GET` | `/api/events` | SSE stream for live sync monitoring *(not wrapped — streaming)* |

### RAG Pipeline (port 8001)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/ingest/{folder_number}` | Ingest a single storage folder into Qdrant |
| `POST` | `/ingest/all` | Re-ingest all accessible storage folders |
| `POST` | `/query` | Ask a question (simple request body) |
| `POST` | `/query-global` | Ask a question with user context (extended request body) |

#### POST /query

```json
{
  "question": "Who can nominate an employee for recognition?"
}
```

#### POST /query-global

```json
{
  "user_id": "",
  "session_id": "",
  "question": "Who is eligible to work from home under the policy?",
  "user_details": {
    "user_name": "",
    "user_role": "",
    "user_email": ""
  }
}
```
> All fields except `question` are optional and reserved for future personalization. Both `/query` and `/query-global` use identical RAG logic underneath.

#### Query Response Example

```json
{
  "success": true,
  "message": "Query answered successfully",
  "data": {
    "answer": "Employees in eligible roles may work from home with manager approval...",
    "sources": [
      {
        "chunk_id": "e138d364-c0e3-4be2-9817-dbf5c37bc7a9",
        "filename": "14.pdf",
        "page_or_sheet": "page 3",
        "file_path": "Connector Folder/14.pdf",
        "web_url": "https://drive.google.com/file/d/..."
      }
    ],
    "retrieved_contexts": ["...chunk text 1...", "...chunk text 2..."]
  }
}
```

---

## 🧪 RAG Evaluation

The RAG pipeline includes a RAGAS-based accuracy evaluation system.

### Setup

Place HR or policy PDF documents in:
```
rag_pipeline/evaluation/hr_documents/
```

Make sure the RAG pipeline is running and documents are ingested into Qdrant first.

### Run Evaluation (4 steps)

```bash
cd rag_pipeline

# Step 1 — Generate synthetic test questions from PDFs
python evaluation/create_dataset.py
# Output: evaluation/testset.json

# Step 2 — Run test questions through the RAG pipeline
python evaluation/run_eval.py
# Output: evaluation/pipeline_results.json + terminal score table

# Step 3 — Generate reports
python evaluation/report_generator.py
# Output: evaluation/reports/evaluation_YYYY-MM-DD_HH-MM.csv
#         evaluation/reports/evaluation_YYYY-MM-DD_HH-MM.json
```

### Metrics

| Metric | What It Measures | Fix If Low |
|---|---|---|
| **Faithfulness** | Answer is grounded in retrieved context only (no hallucination) | Tighten system prompt |
| **Answer Relevancy** | Answer directly addresses the question | Improve system prompt, reduce temperature |
| **Context Precision** | Retrieved chunks are relevant (retrieval noise) | Reduce `SEARCH_TOP_K` (currently 15) |
| **Context Recall** | Retrieval finds all needed information | Reduce `chunk_size` or increase `SEARCH_TOP_K` |

Scores below **0.70** are flagged in the report. The CSV is sorted worst-first for easy review.

---

## ⚠️ Known Limitations

| Area | Limitation |
|---|---|
| Webhooks | Fail if ngrok session disconnects (free tier URLs change on restart) |
| OAuth | Token refresh not fully automated — manual re-auth may be required |
| Dropbox Sharing | `uploader_email` stays empty when `modified_by` is absent from file metadata (Dropbox API limitation for owner-uploaded files) |
| RAG — Large Files | Files marked `too_large` or `deleted` in `content_status` are skipped during ingestion |
| RAG — Video/Audio | `.mp4`, `.mp3`, `.bin` file types are not supported by the preprocessor |
| Qdrant | Re-ingesting the same file deletes and re-creates all its chunks — expected behavior |
| RAGAS Evaluation | `TestsetGenerator` may produce fewer questions than requested if source PDFs are too short |
| Docker + Windows | `STORAGE_BASE_PATH` in `rag_pipeline/.env` must use the absolute Windows path for local dev; Docker overrides this automatically |

---

## 🛠️ Troubleshooting

### SSL Certificate Errors (Windows only)

```bash
pip install python-certifi-win32
```
Restart your terminal after installation. This package is excluded from Docker builds automatically.

---

### Dropbox `shared_with` Is Always Empty

The `sharing.read` scope is missing from your Dropbox OAuth token.

1. Go to [Dropbox App Console](https://www.dropbox.com/developers/apps)
2. Open your app → **Permissions** tab
3. Enable `sharing.read` → Save
4. **Re-authenticate** Dropbox in the dashboard (existing tokens do not get new scopes automatically)

Watch the backend logs for confirmation:
```
[DROPBOX] sharing.read scope confirmed — shared_with population enabled
```

---

### `uploader_email` Is Empty

Dropbox does not expose a native "uploaded by" field. The connector resolves it via `modified_by` in `sharing_info`. This field is absent when:
- The file was uploaded by the folder owner
- The file has not been modified by a collaborator since upload

This is a Dropbox API limitation. The field will populate correctly when a non-owner collaborator modifies the file.

---

### RAG Pipeline Not Receiving Files

1. Confirm `RAG_PIPELINE_URL=http://localhost:8001` is set in `backend/.env`
2. Confirm the RAG pipeline is running on port 8001
3. Check backend logs for `[RAG] Ingestion triggered for folder N`
4. If running in Docker, the URL must be `http://rag-pipeline:8001` (set automatically in `docker-compose.yml`)

---

### Qdrant Chunks Have `null` `file_path` / `web_url`

These files were ingested before the full `ChunkPayload` schema was in place. Re-ingest all folders:

```bash
curl -X POST http://localhost:8001/ingest/all
```

---

### Invalid Redirect URI (Dropbox)

Ensure your ngrok URL matches exactly in all three places:
- `backend/.env` → `DROPBOX_REDIRECT_URI`
- Dropbox Developer Console → Redirect URIs
- Dropbox Developer Console → Webhook URI

Even a trailing slash mismatch will cause auth failures.

---

### Webhook Not Receiving Events

1. Confirm ngrok is running and the tunnel is active
2. Verify the webhook URL in the Dropbox console matches your current ngrok URL
3. Check that `/api/webhook/dropbox` challenge-response returned `200` during initial verification
4. Note: ngrok free tier URLs change on every restart — update the Dropbox console and `.env` each time

---

## 📄 License

This project is for internal/development use.