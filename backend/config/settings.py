import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
STORAGE_DIR = os.getenv("STORAGE_DIR", "./storage")
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

CREDENTIALS_FILE = os.path.join(STORAGE_DIR, "credentials.json")
VISITED_FILE = os.path.join(STORAGE_DIR, "visited.json")
COUNTER_FILE = os.path.join(STORAGE_DIR, "counter.json")
ROOT_FOLDER_FILE = os.path.join(STORAGE_DIR, "root_folder.json")