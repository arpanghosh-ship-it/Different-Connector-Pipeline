# 🚀 Drive Connector Pipeline

A high-performance, full-stack application that connects to Google Drive, recursively crawls folders, normalizes data, and maintains a real-time synchronized dataset using Google Push Notifications (Webhooks) and Byte-level Deduplication.

---

## 📌 Overview

This project provides a complete pipeline for ingesting and monitoring Google Drive content:

*   **Secure Authentication**: Google OAuth 2.0 integration.
*   **Deep Crawling**: Recursive traversal of complex folder hierarchies.
*   **Real-Time Synchronization**: Uses Google Drive Webhooks (Push Notifications) instead of inefficient polling.
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
│   ├── crawler.py           # Core recursion & Hashing logic
│   ├── webhook.py           # Google Drive Webhook handler & Registration
│   ├── normalizer.py        # Metadata extraction & Standardization
│   ├── storage.py           # Local persistence & Folder management
│   ├── duplicate_check.py   # SHA-256 Deduplication & Lock management
│   ├── events.py            # SSE (Server-Sent Events) broadcast system
│   ├── config.py            # Environment configurations
│   ├── Dockerfile           # Backend containerization
│   └── requirements.txt     # Python dependencies
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── LoginPage.jsx    # OAuth flow entry
│   │   │   ├── FolderPicker.jsx # Google Drive directory browser
│   │   │   ├── Dashboard.jsx    # Real-time activity feeds & File explorer
│   │   ├── App.jsx
│   │   └── index.css            # Modern UI styling
│   └── vite.config.js
│
├── docker-compose.yml       # Full system orchestration
└── storage/                 # Data persistence layer (Local)
```

---

## ⚙️ Core Features

### 🔐 Multi-Layer Security
*   Google OAuth 2.0 protocol for secure delegated access.
*   Scope-limited permissions (`drive.readonly`).
*   Secure environment variable management.

### 📂 Intelligent Crawling & Deduplication
*   **Recursive Discovery**: Automatically finds every file in the selected root and its subfolders.
*   **Google Native Export**: Automatically converts Google Docs/Sheets/Slides to standard formats (PDF, CSV, etc.) for local storage.
*   **SHA-256 Hashing**: Generates unique fingerprints for every file. If a duplicate file is found (even with a different name), the system skips redundant storage and references the original.

### 📡 Real-Time Webhook Engine
*   **Push Notifications**: Registers a webhook channel with Google Drive API.
*   **Background Processing**: Immediately acknowledges Google's ping and triggers a scan in a background task to keep the API responsive.
*   **Auto-Renewal**: Built-in scheduler to automatically renew the webhook channel before it expires.

### 📊 Modern Dashboard
*   **SSE Activity Feed**: Watch files being found, processed, and stored in real-time.
*   **File Exploration**: View all stored files with normalized metadata (Size, MimeType, Owner, Path).
*   **Folder Navigation**: Browse your Google Drive directory structure directly within the app.

---

## 🧠 Tech Stack

### Backend
*   **FastAPI**: Modern, high-performance web framework.
*   **AsyncIO & Aiofiles**: Fully non-blocking I/O for high concurrency.
*   **Httpx**: Modern HTTP client for Google API interactions.
*   **APScheduler**: For webhook renewal background jobs.

### Frontend
*   **React (Vite)**: Lightning-fast frontend development.
*   **EventSource (SSE)**: Native browser support for real-time streams.
*   **Tailwind-like Vanilla CSS**: Clean, responsive design.

---

## 🔑 Environment Setup

### 1. Google Cloud Console
*   Enable **Google Drive API**.
*   Configure **OAuth Consent Screen**.
*   Create **OAuth 2.0 Client IDs** (Web application).
*   Add `http://localhost:8000/auth/callback` to Authorized Redirect URIs.

### 2. Backend Config
Create `backend/.env`:
```env
GOOGLE_CLIENT_ID=your_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
FRONTEND_URL=http://localhost:5173
STORAGE_DIR=./storage
MAX_FILE_SIZE_MB=50

# PUBLIC URL for Webhooks (Required for Google to reach you)
# Use ngrok for local dev: ngrok http 8000
WEBHOOK_URL=https://<your-id>.ngrok.io
```

---

## ▶️ Getting Started

### 🐳 Using Docker (Recommended)
```bash
docker-compose up --build
```

### 🔧 Manual Setup

#### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## 🧪 API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| **GET** | `/api/status` | Current authentication and webhook status |
| **GET** | `/api/folders` | Browse Google Drive folders |
| **POST** | `/api/start-crawl` | Initialize root folder and start sync |
| **GET** | `/api/files` | Retrieve all normalized stored files |
| **GET** | `/api/events` | **SSE Stream** for real-time activity |
| **POST** | `/api/webhook/drive`| Google Push Notification Receiver |
| **POST** | `/api/webhook/register`| Manually re-register the webhook |

---

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

---


