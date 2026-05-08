import json
import logging
import os
import secrets
import httpx
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    FRONTEND_URL, SCOPES, CREDENTIALS_FILE, STORAGE_DIR
)
from response import success_response, error_response

router = APIRouter()
logger = logging.getLogger(__name__)

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
        logger.info(f"[auth] No credentials file found at: {CREDENTIALS_FILE}")
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
            logger.info("[auth] Token expired -- refreshing...")
            creds.refresh(GoogleRequest())
            _save_credentials(creds)
        logger.info(f"[auth] Credentials loaded OK. Token valid: {not creds.expired}")
        return creds
    except Exception as e:
        logger.error(f"[auth] ERROR loading credentials: {e}")
        return None


def _save_credentials(creds: Credentials):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'expiry': creds.expiry.isoformat() if creds.expiry else None,
        }, f)
    logger.info(f"[auth] Credentials saved to {CREDENTIALS_FILE}")


@router.get('/auth/login')
def login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return error_response(
            message='GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env',
            status_code=500,
        )
    flow = _make_flow()
    state = secrets.token_urlsafe(16)

    # Save state to FILE (not memory)
    states = _load_states()
    states[state] = True
    _save_states(states)
    logger.info(f"[auth] Login initiated. State saved: {state[:8]}...")

    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='false',   # ← changed to false (removes calendar scope)
        prompt='consent',
        state=state,
    )
    return RedirectResponse(auth_url)


@router.get('/auth/callback')
def callback(code: str = None, state: str = None, error: str = None):
    logger.info(f"[auth] Callback received. state={state[:8] if state else None}... error={error}")

    if error:
        logger.error(f"[auth] OAuth error: {error}")
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&reason={error}')

    states = _load_states()
    if not state or state not in states:
        logger.warning(f"[auth] Invalid state! Known states: {list(states.keys())[:3]}")
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&reason=invalid_state')

    del states[state]
    _save_states(states)

    try:
        flow = _make_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        _save_credentials(creds)
        logger.info("[auth] Token exchange successful. Redirecting to frontend.")
    except Exception as e:
        logger.error(f"[auth] Token exchange failed: {e}")
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&reason=token_exchange_failed')

    return RedirectResponse(f'{FRONTEND_URL}?auth=success')


@router.get('/auth/logout')
def logout():
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)
    if os.path.exists(STATES_FILE):
        os.remove(STATES_FILE)
    logger.info("[auth] Logged out -- credentials deleted.")
    return success_response(
        message='Google Drive logout completed'
    )


@router.get('/auth/me')
async def me():
    creds = load_credentials()
    if not creds or not creds.token:
        return error_response(
            message='Google Drive is not authenticated',
            status_code=401
        )

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {creds.token}'},
        )
        if resp.status_code != 200:
            return error_response(
                message='Google Drive token is invalid',
                status_code=401
            )
        return success_response(
            message='Google Drive user profile retrieved successfully',
            data=resp.json()
        )
