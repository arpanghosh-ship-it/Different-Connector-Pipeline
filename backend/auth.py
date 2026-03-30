import json
import os
import secrets
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    FRONTEND_URL, SCOPES, CREDENTIALS_FILE, STORAGE_DIR
)

router = APIRouter()

# ── File-based state store (survives reloads & multiple processes) ──
STATES_FILE = os.path.join(STORAGE_DIR, 'pending_states.json')


def _load_states() -> dict:
    if not os.path.exists(STATES_FILE):
        return {}
    try:
        with open(STATES_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_states(states: dict):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(STATES_FILE, 'w') as f:
        json.dump(states, f)


CLIENT_CONFIG = {
    'web': {
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uris': [GOOGLE_REDIRECT_URI],
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': 'https://oauth2.googleapis.com/token',
    }
}


def _make_flow() -> Flow:
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    return flow


def load_credentials() -> Credentials | None:
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"[auth] No credentials file found at: {CREDENTIALS_FILE}")
        return None
    try:
        with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        creds = Credentials(
            token=data.get('token'),
            refresh_token=data.get('refresh_token'),
            token_uri='https://oauth2.googleapis.com/token',
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=SCOPES,
        )
        if creds.expired and creds.refresh_token:
            print("[auth] Token expired — refreshing...")
            creds.refresh(GoogleRequest())
            _save_credentials(creds)
        print(f"[auth] Credentials loaded OK. Token valid: {not creds.expired}")
        return creds
    except Exception as e:
        print(f"[auth] ERROR loading credentials: {e}")
        return None


def _save_credentials(creds: Credentials):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'expiry': creds.expiry.isoformat() if creds.expiry else None,
        }, f)
    print(f"[auth] Credentials saved to {CREDENTIALS_FILE}")


@router.get('/auth/login')
def login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail='GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env'
        )
    flow = _make_flow()
    state = secrets.token_urlsafe(16)

    # Save state to FILE (not memory)
    states = _load_states()
    states[state] = True
    _save_states(states)
    print(f"[auth] Login initiated. State saved: {state[:8]}...")

    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='false',   # ← changed to false (removes calendar scope)
        prompt='consent',
        state=state,
    )
    return RedirectResponse(auth_url)


@router.get('/auth/callback')
def callback(code: str = None, state: str = None, error: str = None):
    print(f"[auth] Callback received. state={state[:8] if state else None}... error={error}")

    if error:
        print(f"[auth] OAuth error: {error}")
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&reason={error}')

    states = _load_states()
    if not state or state not in states:
        print(f"[auth] Invalid state! Known states: {list(states.keys())[:3]}")
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&reason=invalid_state')

    del states[state]
    _save_states(states)

    try:
        flow = _make_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        _save_credentials(creds)
        print("[auth] Token exchange successful. Redirecting to frontend.")
    except Exception as e:
        print(f"[auth] Token exchange failed: {e}")
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&reason=token_exchange_failed')

    return RedirectResponse(f'{FRONTEND_URL}?auth=success')


@router.get('/auth/logout')
def logout():
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)
    if os.path.exists(STATES_FILE):
        os.remove(STATES_FILE)
    print("[auth] Logged out — credentials deleted.")
    return {'message': 'Logged out'}


@router.get('/auth/me')
async def me():
    creds = load_credentials()
    if not creds or not creds.token:
        raise HTTPException(status_code=401, detail='Not authenticated')

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {creds.token}'},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail='Token invalid')
        return resp.json()
