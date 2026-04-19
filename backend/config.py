import os
from dotenv import load_dotenv

load_dotenv()

# ── Google Drive ───────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID     = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI  = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8000/auth/callback')
FRONTEND_URL         = os.getenv('FRONTEND_URL', 'http://localhost:5173')
STORAGE_DIR          = os.getenv('STORAGE_DIR', './storage')
MAX_FILE_SIZE_BYTES  = int(os.getenv('MAX_FILE_SIZE_MB', '50')) * 1024 * 1024
POLL_INTERVAL_SECONDS = int(os.getenv('POLL_INTERVAL_SECONDS', '30'))

# Webhook — must be a publicly reachable HTTPS URL pointing at this server.
# For local dev: run `ngrok http 8000` and set this to the https:// URL.
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

CREDENTIALS_FILE  = os.path.join(STORAGE_DIR, 'credentials.json')
VISITED_FILE      = os.path.join(STORAGE_DIR, 'visited.json')
COUNTER_FILE      = os.path.join(STORAGE_DIR, 'counter.json')
ROOT_FOLDER_FILE  = os.path.join(STORAGE_DIR, 'root_folder.json')

# ── Dropbox ────────────────────────────────────────────────────────────────────
# Get from: https://www.dropbox.com/developers/apps
# Create an app → Scoped Access → Full Dropbox
# Permissions: files.content.read, files.metadata.read, account_info.read
DROPBOX_APP_KEY      = os.getenv('DROPBOX_APP_KEY', '')
DROPBOX_APP_SECRET   = os.getenv('DROPBOX_APP_SECRET', '')
DROPBOX_REDIRECT_URI = os.getenv('DROPBOX_REDIRECT_URI', 'http://localhost:8000/dropbox/callback')

# Dropbox storage files — kept separate from Google Drive storage
DROPBOX_STORAGE_DIR      = os.path.join(STORAGE_DIR, 'dropbox')
DROPBOX_CREDENTIALS_FILE = os.path.join(DROPBOX_STORAGE_DIR, 'dropbox_credentials.json')
DROPBOX_ROOT_FOLDER_FILE = os.path.join(DROPBOX_STORAGE_DIR, 'dropbox_root_folder.json')
DROPBOX_CURSOR_FILE      = os.path.join(DROPBOX_STORAGE_DIR, 'dropbox_cursor.json')
DROPBOX_STATES_FILE      = os.path.join(DROPBOX_STORAGE_DIR, 'dropbox_pending_states.json')