# ☁️ Multi-Cloud Connector Pipeline

A high-performance full-stack application that synchronizes data from **Google Drive** and **Dropbox** in real time. It recursively crawls cloud directories, normalizes metadata, and maintains a synchronized local dataset using **webhooks** and **SHA-256 byte-level deduplication**.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Cloud Provider Setup](#-cloud-provider-setup)
- [Local Development](#-local-development)
- [Environment Variables](#-environment-variables)
- [API Reference](#-api-reference)
- [Known Limitations](#-known-limitations)
- [Troubleshooting](#-troubleshooting)

---

## 🌐 Overview

This project provides a unified pipeline for ingesting and monitoring content across multiple cloud providers:

| Capability | Details |
|---|---|
| Cloud Providers | Google Drive, Dropbox |
| Auth | OAuth 2.0 (both providers) |
| Sync Strategy | Webhook-driven delta sync (cursor/token-based) |
| Deduplication | SHA-256 content hashing |
| Live Monitoring | Server-Sent Events (SSE) |
| Frontend | React + Vite + TypeScript |
| Backend | FastAPI (Python 3.11+) |

---

## ⚙️ Features

### 🔐 Unified Authentication
- **Google Drive** — OAuth via Google Cloud Console
- **Dropbox** — OAuth via Dropbox Developer Console

**Required Dropbox Scopes:**
- `files.content.read`
- `files.metadata.read`

### 📡 Real-Time Delta Engines
- **Google Drive** — `watch()` subscription model for push notifications
- **Dropbox** — Challenge-response webhook verification
- **Delta Sync** — Cursor/token-based syncing avoids full re-scans, reducing API cost and latency

### 📁 Intelligent Storage
- **Cross-cloud deduplication** — SHA-256 hashing prevents duplicate downloads across providers
- **Robust sorting** — Tuple-based type-safe sorting handles mixed `int`/`str` values and prevents Python `TypeError`
- **Unified metadata normalization** — Consistent schema regardless of provider

---

## 🗂️ Project Structure

```
Cloud-Connector-Pipeline/
│
├── backend/
│   ├── main.py               # FastAPI app entry point
│   ├── auth.py               # Google OAuth logic
│   ├── dropbox_auth.py       # Dropbox OAuth logic
│   ├── crawler.py            # Recursive directory traversal
│   ├── webhook.py            # Webhook handlers (Google + Dropbox)
│   ├── storage.py            # Deduplication & local storage
│   ├── config.py             # Environment config loader
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   └── components/
│   │       ├── LoginPage.jsx
│   │       ├── FolderPicker.jsx
│   │       └── Dashboard.jsx
│   ├── vite.config.js
│   └── package.json
│
└── storage/
    └── <file_hash>/          # Deduplicated file store (Google Drive)
    └── dropbox/              # Deduplicated file store (Dropbox)
```

---

## 🔑 Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| ngrok | Latest |
| (Windows only) `python-certifi-win32` | Latest |

> **Note:** ngrok is required to expose your local server for webhook testing. Your ngrok URL must remain active during development.

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
2. Create a new app (Full Dropbox or App Folder scope)
3. Add the following under **Redirect URIs:**

```
http://localhost:8000/dropbox/callback
https://<your-ngrok-id>.ngrok-free.app/dropbox/callback
```

4. Add the following under **Webhook URI:**

```
https://<your-ngrok-id>.ngrok-free.app/api/webhook/dropbox
```

5. Enable these **Permissions:**
   - `files.metadata.read`
   - `files.content.read`

---

## 🚀 Local Development

### Step 1 — Backend Setup

```bash
cd backend
python -m venv venv

# Activate virtual environment
source venv/bin/activate          # macOS/Linux
venv\Scripts\activate             # Windows

pip install -r requirements.txt
```

### Step 2 — Start ngrok

```bash
ngrok http 8000
```

Copy your ngrok forwarding URL (e.g., `https://abc123.ngrok-free.app`) — you'll need it in `.env` and your Dropbox console.

### Step 3 — Configure Environment Variables

Create a `.env` file inside `backend/`:

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
```

### Step 4 — Configure Vite Proxy

Update `frontend/vite.config.js` to proxy API requests:

```js
export default defineConfig({
  server: {
    proxy: {
      '/api':      'http://localhost:8000',
      '/auth':     'http://localhost:8000',
      '/dropbox':  'http://localhost:8000',
    }
  }
})
```

### Step 5 — Run the Application

**Backend:**
```bash
uvicorn main:app --reload --port 8000
```

**Frontend** (in a separate terminal):
```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`.

---

## 🧪 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/auth/login` | Start Google Drive OAuth flow |
| `GET` | `/auth/callback` | Google OAuth callback |
| `GET` | `/dropbox/login` | Start Dropbox OAuth flow |
| `GET` | `/dropbox/callback` | Dropbox OAuth callback |
| `GET` | `/api/webhook/dropbox` | Dropbox webhook challenge verification |
| `POST` | `/api/webhook/dropbox` | Receive Dropbox webhook events |
| `GET` | `/api/events` | SSE stream for live sync monitoring |

---

## ⚠️ Known Limitations

| Area | Limitation |
|---|---|
| Webhooks | Fail if ngrok session disconnects |
| OAuth | Token refresh not implemented — manual re-auth required |
| Rate Limits | Large sync jobs may hit provider API rate limits |
| Deduplication | Hash-based only — renamed files with identical content are treated as duplicates |
| Production | OAuth redirect URIs must be updated for deployed environments |

---

## 🛠️ Troubleshooting

### SSL Certificate Errors (Windows only)

```bash
pip install python-certifi-win32
```

Restart your terminal after installation.

---

### Invalid Redirect URI

Ensure your ngrok URL matches **exactly** in all three places:

- `backend/.env` → `DROPBOX_REDIRECT_URI`
- Dropbox Developer Console → Redirect URIs
- Dropbox Developer Console → Webhook URI

Even a trailing slash mismatch will cause auth failures.

---

### Sorting Crash (`TypeError`)

Mixed-type sorting (e.g., `int` vs `str` keys) is handled via tuple-based comparison:

```python
items.sort(key=lambda x: (0, int(x)) if isinstance(x, int) else (1, str(x)))
```

---

### Webhook Not Receiving Events

1. Confirm ngrok is running and the tunnel is active
2. Verify the webhook URL in the Dropbox console matches your current ngrok URL (ngrok URLs change on free tier restarts)
3. Check that the `/api/webhook/dropbox` challenge-response endpoint returned `200` during initial verification

---

## 📄 License

This project is for internal/development use. Add your license here.