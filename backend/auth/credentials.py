import json
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from config.settings import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SCOPES, CREDENTIALS_FILE, STORAGE_DIR

def load_credentials() -> Credentials | None:
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"[auth] No credentials file found at: {CREDENTIALS_FILE}")
        return None
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=SCOPES,
        )
        if creds.expired and creds.refresh_token:
            print("[auth] Token expired — refreshing...")
            creds.refresh(GoogleRequest())
            save_credentials(creds)
        print(f"[auth] Credentials loaded OK. Token valid: {not creds.expired}")
        return creds
    except Exception as e:
        print(f"[auth] ERROR loading credentials: {e}")
        return None

def save_credentials(creds: Credentials):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }, f)
    print(f"[auth] Credentials saved to {CREDENTIALS_FILE}")