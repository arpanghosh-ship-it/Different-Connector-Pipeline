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
_pending_states: dict = {}

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
            creds.refresh(GoogleRequest())
            _save_credentials(creds)
        return creds
    except Exception:
        return None


def _save_credentials(creds: Credentials):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'expiry': creds.expiry.isoformat() if creds.expiry else None,
        }, f)


@router.get('/auth/login')
def login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail='GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env')
    flow = _make_flow()
    state = secrets.token_urlsafe(16)
    _pending_states[state] = True

    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=state,
    )
    return RedirectResponse(auth_url)


@router.get('/auth/callback')
def callback(code: str = None, state: str = None, error: str = None):
    if error:
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&reason={error}')

    if not state or state not in _pending_states:
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&reason=invalid_state')

    del _pending_states[state]

    try:
        flow = _make_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        _save_credentials(creds)
    except Exception:
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&reason=token_exchange_failed')

    return RedirectResponse(f'{FRONTEND_URL}?auth=success')


@router.get('/auth/logout')
def logout():
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)
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
