# 🚀 Drive Connector Pipeline

A full-stack application that connects to Google Drive, recursively crawls folders, normalizes files, and maintains a continuously updating dataset with real-time activity tracking.

---

## 📌 Overview

This project allows you to:

* Authenticate with Google Drive
* Select a folder to crawl
* Recursively scan all nested files and folders
* Normalize file metadata (type, size, extension, etc.)
* Store processed files locally
* Continuously monitor updates using polling (every 30 seconds)
* View real-time updates via Server-Sent Events (SSE)

---

## 🏗️ Project Structure

```
Different-Connector-Pipeline/
│
├── backend/
│   ├── main.py              # FastAPI app (APIs + SSE)
│   ├── auth.py              # Google OAuth logic
│   ├── crawler.py           # Recursive Drive crawler
│   ├── poller.py            # Polling scheduler (30 sec)
│   ├── normalizer.py        # File normalization logic
│   ├── storage.py           # Local file storage
│   ├── events.py            # SSE event system
│   ├── duplicate_check.py   # Duplicate tracking
│   ├── config.py            # Configurations
│   ├── requirements.txt     # Backend dependencies
│   └── .env.example         # Environment variables template
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── LoginPage.jsx
│   │   │   ├── FolderPicker.jsx
│   │   │   ├── Dashboard.jsx
│   │   ├── index.css
│   │   └── main.jsx
│   │
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── storage/                 # Ignored (generated files)
├── README.md
└── .gitignore
```

---

## ⚙️ Features

### 🔐 Authentication

* Google OAuth 2.0 login
* Secure token handling

### 📂 Folder Crawling

* Recursive traversal of nested folders
* Handles Google native files (Docs, Sheets, etc.)

### 🔄 Polling System

* Runs every **30 seconds**
* Detects new or updated files
* Can be **paused/resumed**

### 📡 Real-Time Updates

* Server-Sent Events (SSE)
* Live activity feed in frontend

### 📊 File Normalization

Each file includes:

* File name
* File type (pdf, csv, gdoc, etc.)
* File extension
* Size (KB / MB / GB)
* Owner email
* Path
* Last modified time

---

## 🧠 Tech Stack

### Backend

* FastAPI
* AsyncIO
* APScheduler
* Google Drive API

### Frontend

* React (Vite)
* Fetch API
* SSE (EventSource)

---

## 🔑 Environment Setup

### 1. Backend `.env`

Create file:

```
backend/.env
```

Add:

```
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
REDIRECT_URI=http://localhost:8000/auth/callback
FRONTEND_URL=http://localhost:5173
```

---

## ▶️ Running the Project

---

### 🔧 Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate
# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn main:app --reload --port 8000
```

Backend runs on:

```
http://localhost:8000
```

---

### 💻 Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run frontend
npm run dev
```

Frontend runs on:

```
http://localhost:5173
```

---

## 🔄 Application Flow

1. Open frontend
2. Login using Google
3. Select a folder
4. Start crawling
5. View files and activity updates
6. Polling runs every 30 seconds
7. New files automatically appear

---

## 🧪 API Endpoints

| Method | Endpoint           | Description        |
| ------ | ------------------ | ------------------ |
| GET    | `/api/health`      | Health check       |
| GET    | `/api/status`      | App status         |
| GET    | `/api/folders`     | List Drive folders |
| POST   | `/api/start-crawl` | Start crawling     |
| GET    | `/api/files`       | Get stored files   |
| POST   | `/api/start-poll`  | Resume polling     |
| POST   | `/api/stop-poll`   | Pause polling      |
| GET    | `/api/events`      | SSE stream         |

---

## ⚠️ Notes

* `storage/` folder is ignored in Git
* `.env` file should never be committed
* Ensure Google OAuth redirect URI matches backend

---

## 🤝 Collaboration Workflow

* `main` branch → stable production code
* Each developer works in separate branch:

  ```
  git checkout -b username/feature-name
  ```
* Push branch:

  ```
  git push -u origin username/feature-name
  ```
* Create Pull Request → Merge after testing

---

## 🛠️ Future Improvements

* Search and filter files
* Pagination for large datasets
* File preview support
* Multi-user support
* Cloud storage integration (S3, GCS)

---

## 📄 License

This project is for learning and development purposes.

---

## 👨‍💻 Author

**Arpan Ghosh**
