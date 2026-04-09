# 🚀 Drive Connector Pipeline

A high-performance, full-stack application that connects to Google Drive, recursively crawls folders, normalizes data, and maintains a real-time synchronized dataset using Google Push Notifications (Webhooks) and Byte-level Deduplication.

---

## 📌 Overview

This project provides a complete pipeline for ingesting and monitoring Google Drive content:

*   **Secure Authentication**: Google OAuth 2.0 integration.
*   **Deep Crawling**: Recursive traversal of complex folder hierarchies.
*   **Real-Time Synchronization**: Uses Google Drive Webhooks (Push Notifications) with delta-based change detection instead of inefficient polling.
*   **Smart Storage**: SHA-256 based content hashing to prevent duplicate file storage.
*   **Data Normalization**: Unified metadata format for all file types (Docs, Sheets, PDFs, etc.).
*   **Live Monitoring**: Server-Sent Events (SSE) for real-time activity tracking in the UI.

---

## 🏗️ Project Structure

```
Different-Connector-Pipeline/
│
├── backend/
│   ├── main.py              # FastAPI application & API layer
│   ├── auth.py              # Google OAuth 2.0 & Token management
│   ├── crawler.py           # Core recursion, Hashing & Delta sync logic
│   ├── webhook.py           # Google Drive Webhook handler & Registration
│   ├── normalizer.py        # Metadata extraction & Standardization
│   ├── storage.py           # Local persistence & Folder management
│   ├── duplicate_check.py   # SHA-256 Deduplication & Lock management
│   ├── events.py            # SSE (Server-Sent Events) broadcast system
│   ├── config.py            # Environment configurations
│   ├── requirements.txt     # Python dependencies
│   └── .env                 # Environment variables (create this yourself)
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── LoginPage.jsx    # OAuth flow entry
│   │   │   ├── FolderPicker.jsx # Google Drive directory browser
│   │   │   ├── Dashboard.jsx    # Real-time activity feeds & File explorer
│   │   ├── App.jsx
│   │   └── index.css            # Modern UI styling
│   ├── vite.config.js
│   └── package.json
│
├── docker-compose.yml       # Full system orchestration (optional)
└── storage/                 # Data persistence layer (auto-created at runtime)
    ├── visited.json         # Tracks all crawled Drive file IDs
    ├── content_hashes.json  # SHA-256 dedup registry
    ├── page_token.json      # Drive Changes API cursor
    └── <number>/            # One folder per stored file
        ├── normalized.json  # Normalized metadata
        └── raw.<ext>        # Raw file content
```

---

## ⚙️ Core Features

### 🔐 Multi-Layer Security
*   Google OAuth 2.0 protocol for secure delegated access.
*   Scope-limited permissions (`drive.readonly`).
*   Secure environment variable management.

### 📂 Intelligent Crawling & Deduplication
*   **Recursive Discovery**: Automatically finds every file in the selected root folder and all its subfolders.
*   **Google Native Export**: Automatically converts Google Docs/Sheets/Slides to standard formats (PDF, CSV, etc.) for local storage.
*   **SHA-256 Hashing**: Generates unique fingerprints for every file. If a duplicate file is found (even with a different name), the system skips redundant storage and references the original.

### 📡 Real-Time Delta Webhook Engine
*   **Push Notifications**: Registers a webhook channel with the Google Drive API.
*   **Delta-Based Sync**: Uses `GET /drive/v3/changes` with a saved `page_token` to fetch **only what changed** since the last check — not a full re-crawl.
*   **Change Handling**: Detects and handles file moves (path update), renames (name update), deletions (status → `deleted`), and new files.
*   **Auto-Renewal**: Built-in scheduler to automatically renew the webhook channel before it expires.

### 📊 Modern Dashboard
*   **SSE Activity Feed**: Watch files being found, processed, stored, and updated in real-time.
*   **File Exploration**: View all stored files with normalized metadata (Size, MimeType, Owner, Path, Status).
*   **Folder Navigation**: Browse your Google Drive directory structure directly within the app.

---

## 🧠 Tech Stack

### Backend
*   **FastAPI** — Modern, high-performance web framework.
*   **AsyncIO & Aiofiles** — Fully non-blocking I/O for high concurrency.
*   **Httpx** — Modern async HTTP client for Google API interactions.
*   **APScheduler** — Webhook renewal background jobs.
*   **Python-dotenv** — Environment variable management.

### Frontend
*   **React 18 (Vite)** — Lightning-fast frontend development.
*   **EventSource (SSE)** — Native browser support for real-time streams.
*   **Vanilla CSS** — Clean, responsive design.

---

## 🔑 Prerequisites

Before running locally, make sure you have:

*   **Python 3.11+**
*   **Node.js 18+** and **npm**
*   **ngrok** (free account) — to expose your local backend to the internet so Google can send webhook notifications

---

## ☁️ Google Cloud Console Setup

> You only need to do this once.

1.  Go to [https://console.cloud.google.com](https://console.cloud.google.com) and create a new project (or use an existing one).
2.  Enable the **Google Drive API**:
    -   Navigate to **APIs & Services → Library**
    -   Search for "Google Drive API" → Click **Enable**
3.  Configure the **OAuth Consent Screen**:
    -   Go to **APIs & Services → OAuth consent screen**
    -   Choose **External**, fill in App name & support email
    -   Add scope: `https://www.googleapis.com/auth/drive.readonly`
    -   Add your Google account as a **Test user**
4.  Create **OAuth 2.0 Credentials**:
    -   Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
    -   Application type: **Web application**
    -   Add Authorized Redirect URI: `http://localhost:8000/auth/callback`
    -   Download or copy the **Client ID** and **Client Secret**

---

## ▶️ Running Locally (Without Docker)

### Step 1 — Clone the repository

```bash
git clone https://github.com/arpanghosh-ship-it/Different-Connector-Pipeline.git
cd Different-Connector-Pipeline
```

---

### Step 2 — Set up the Backend

#### 2a. Create a virtual environment

```bash
cd backend

# Create venv
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

#### 2b. Install Python dependencies

```bash
pip install -r requirements.txt
```

#### 2c. Create the `.env` file

Create a file called `.env` inside the `backend/` folder with the following content:

```env
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
FRONTEND_URL=http://localhost:5173
STORAGE_DIR=./storage
MAX_FILE_SIZE_MB=50
WEBHOOK_URL=https://<your-ngrok-id>.ngrok-free.app
```

> The `WEBHOOK_URL` must be a publicly reachable HTTPS URL. See Step 3 below.

#### 2d. Start the backend server

```bash
uvicorn main:app --reload --port 8000
```

The backend API will be available at: `http://localhost:8000`

---

### Step 3 — Set up ngrok (Required for Webhooks)

Google Drive needs to send push notifications to a **publicly accessible HTTPS URL**. ngrok creates a secure tunnel from the internet to your local machine.

#### 3a. Install ngrok

Download from [https://ngrok.com/download](https://ngrok.com/download) or install via:

```bash
# Windows (via chocolatey)
choco install ngrok

# macOS
brew install ngrok/ngrok/ngrok
```

#### 3b. Authenticate ngrok (free account required)

```bash
ngrok config add-authtoken <your_ngrok_authtoken>
```

Get your auth token from: [https://dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken)

#### 3c. Start the tunnel

```bash
ngrok http 8000
```

You will see output like:

```
Forwarding   https://abc123.ngrok-free.app -> http://localhost:8000
```

#### 3d. Update your `.env`

Copy the `https://` URL and set it in `backend/.env`:

```env
WEBHOOK_URL=https://abc123.ngrok-free.app
```

Then **restart the backend** so it picks up the new URL.

> ⚠️ **Important**: ngrok free URLs change every time you restart ngrok. Whenever you restart ngrok, update `WEBHOOK_URL` in `.env`, restart the backend, and re-select your folder in the UI.

---

### Step 4 — Set up the Frontend

Open a **new terminal** (keep the backend running):

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at: `http://localhost:5173`

> The Vite dev server automatically proxies `/api` and `/auth` requests to `http://localhost:8000`, so no CORS issues during development.

---

### Step 5 — Using the Application

1.  Open `http://localhost:5173` in your browser.
2.  Click **Sign in with Google** and authorize the app.
3.  Browse your Google Drive folders and **select a root folder** to sync.
4.  The crawl starts immediately. Watch the **Activity Feed** on the left for real-time updates.
5.  Once the initial crawl is complete, the webhook is registered automatically.
6.  Any changes you make in that Google Drive folder (add, move, rename, delete files) will be reflected in the **Synced Files** panel within ~10 seconds — **no need to re-select the folder**.

---

## 🧪 API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| **GET** | `/api/status` | Current authentication and webhook status |
| **GET** | `/api/folders` | Browse Google Drive folders |
| **POST** | `/api/start-crawl` | Initialize root folder and start sync |
| **GET** | `/api/files` | Retrieve all normalized stored files |
| **GET** | `/api/events` | **SSE Stream** for real-time activity |
| **POST** | `/api/webhook/drive` | Google Push Notification Receiver |
| **POST** | `/api/webhook/register` | Manually re-register the webhook |
| **GET** | `/api/webhook/status` | Current webhook channel status |
| **POST** | `/api/webhook/stop` | Deregister the webhook channel |

---

## 🔁 How the Delta Webhook Works

```
Google Drive (change event)
        │
        ▼
  POST /api/webhook/drive
        │
        ▼
  process_drive_notification()
  [verifies channel ID matches]
        │
        ▼
  process_delta_changes()
  [GET /drive/v3/changes?pageToken=<saved_token>]
        │
        ├── File deleted/trashed  → update content_status = "deleted"
        ├── Known file changed    → rebuild path, update normalized.json
        └── New file              → trigger crawl (dedup skips existing)
        │
        ▼
  Save new page_token for next event
```

---

## 🐳 Using Docker (Alternative)

If you prefer Docker:

```bash
docker-compose up --build
```

This starts both the backend and frontend in containers with all environment already configured.

---

## 📄 License

This project is licensed under the MIT License — see the LICENSE file for details.
