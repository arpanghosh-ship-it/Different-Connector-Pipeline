"""
dropbox_auth.py
Dropbox OAuth 2.0 authentication — PKCE-less, offline access (refresh token).

Flow:
  1. GET /dropbox/login           → redirect to Dropbox consent screen
  2. GET /dropbox/callback?code=  → exchange code for tokens, save credentials
  3. GET /dropbox/me              → return current account info
  4. GET /dropbox/logout          → delete saved credentials
"""
import json
import logging
import os
import secrets
import httpx
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from config import (
    DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REDIRECT_URI,
    FRONTEND_URL, DROPBOX_CREDENTIALS_FILE, DROPBOX_STATES_FILE,
    DROPBOX_STORAGE_DIR,
)
from response import success_response, error_response

router = APIRouter()
logger = logging.getLogger(__name__)

DROPBOX_AUTH_URL  = 'https://www.dropbox.com/oauth2/authorize'
DROPBOX_TOKEN_URL = 'https://api.dropboxapi.com/oauth2/token'
DROPBOX_USER_URL  = 'https://api.dropboxapi.com/2/users/get_current_account'


# ── State helpers (CSRF protection) ───────────────────────────────────────────

def _load_states() -> dict:
    os.makedirs(DROPBOX_STORAGE_DIR, exist_ok=True)
    if not os.path.exists(DROPBOX_STATES_FILE):
        return {}
    try:
        with open(DROPBOX_STATES_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_states(states: dict):
    os.makedirs(DROPBOX_STORAGE_DIR, exist_ok=True)
    with open(DROPBOX_STATES_FILE, 'w') as f:
        json.dump(states, f)


# ── Credential helpers ─────────────────────────────────────────────────────────

def _save_credentials(access_token: str, refresh_token: str, account_id: str):
    os.makedirs(DROPBOX_STORAGE_DIR, exist_ok=True)
    with open(DROPBOX_CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'access_token':  access_token,
            'refresh_token': refresh_token,
            'account_id':    account_id,
        }, f, indent=2)
    logger.info('[dropbox_auth] Credentials saved.')


def _load_raw_credentials() -> dict | None:
    if not os.path.exists(DROPBOX_CREDENTIALS_FILE):
        return None
    try:
        with open(DROPBOX_CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


async def _refresh_access_token(refresh_token: str) -> str | None:
    """Exchange a refresh token for a new short-lived access token."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                DROPBOX_TOKEN_URL,
                data={
                    'grant_type':    'refresh_token',
                    'refresh_token': refresh_token,
                    'client_id':     DROPBOX_APP_KEY,
                    'client_secret': DROPBOX_APP_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            new_token = data.get('access_token')
            if new_token:
                # Update the saved credentials with the new access token
                creds = _load_raw_credentials() or {}
                creds['access_token'] = new_token
                with open(DROPBOX_CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(creds, f, indent=2)
                logger.info('[dropbox_auth] Access token refreshed.')
            return new_token
    except Exception as e:
        logger.error(f'[dropbox_auth] Token refresh failed: {e}')
        return None


async def load_dropbox_token() -> str | None:
    """
    Returns a valid Dropbox access token, refreshing if needed.
    Returns None if not authenticated.
    """
    creds = _load_raw_credentials()
    if not creds:
        return None

    access_token  = creds.get('access_token')
    refresh_token = creds.get('refresh_token')

    # Verify the current token works
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                DROPBOX_USER_URL,
                headers={
                    'Authorization':  f'Bearer {access_token}',
                    'Content-Type':   'application/json',
                },
                content=b'null',
            )
            if resp.status_code == 200:
                return access_token  # Token is fine
    except Exception:
        pass

    # Token expired or invalid — try to refresh
    if refresh_token:
        new_token = await _refresh_access_token(refresh_token)
        return new_token

    return None


def is_dropbox_authenticated() -> bool:
    """Quick synchronous check — just verifies credentials file exists."""
    return os.path.exists(DROPBOX_CREDENTIALS_FILE)


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get('/dropbox/login')
def dropbox_login():
    if not DROPBOX_APP_KEY or not DROPBOX_APP_SECRET:
        return error_response(
            message='DROPBOX_APP_KEY and DROPBOX_APP_SECRET must be set in .env',
            status_code=500,
        )

    state = secrets.token_urlsafe(16)
    states = _load_states()
    states[state] = True
    _save_states(states)

    # token_access_type=offline → gives us a refresh token
    params = (
        f'?client_id={DROPBOX_APP_KEY}'
        f'&redirect_uri={DROPBOX_REDIRECT_URI}'
        f'&response_type=code'
        f'&state={state}'
        f'&token_access_type=offline'
    )
    logger.info(f'[dropbox_auth] Login initiated. State saved: {state[:8]}...')
    return RedirectResponse(DROPBOX_AUTH_URL + params)


@router.get('/dropbox/callback')
async def dropbox_callback(code: str = None, state: str = None, error: str = None, error_description: str = None):
    logger.info(f'[dropbox_auth] Callback. state={state[:8] if state else None} error={error}')

    if error:
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&connector=dropbox&reason={error}')

    states = _load_states()
    if not state or state not in states:
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&connector=dropbox&reason=invalid_state')

    del states[state]
    _save_states(states)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                DROPBOX_TOKEN_URL,
                data={
                    'code':          code,
                    'grant_type':    'authorization_code',
                    'client_id':     DROPBOX_APP_KEY,
                    'client_secret': DROPBOX_APP_SECRET,
                    'redirect_uri':  DROPBOX_REDIRECT_URI,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        access_token  = data.get('access_token', '')
        refresh_token = data.get('refresh_token', '')
        account_id    = data.get('account_id', '')

        if not access_token:
            return RedirectResponse(f'{FRONTEND_URL}?auth=error&connector=dropbox&reason=no_access_token')

        _save_credentials(access_token, refresh_token, account_id)
        logger.info('[dropbox_auth] Token exchange OK -- redirecting to frontend.')

    except Exception as e:
        logger.error(f'[dropbox_auth] Token exchange failed: {e}')
        return RedirectResponse(f'{FRONTEND_URL}?auth=error&connector=dropbox&reason=token_exchange_failed')

    return RedirectResponse(f'{FRONTEND_URL}?auth=success&connector=dropbox')


@router.get('/dropbox/logout')
def dropbox_logout():
    if os.path.exists(DROPBOX_CREDENTIALS_FILE):
        os.remove(DROPBOX_CREDENTIALS_FILE)
    if os.path.exists(DROPBOX_STATES_FILE):
        os.remove(DROPBOX_STATES_FILE)
    logger.info('[dropbox_auth] Logged out.')
    return success_response(
        message='Dropbox logout completed'
    )


@router.get('/dropbox/me')
async def dropbox_me():
    token = await load_dropbox_token()
    if not token:
        return error_response(
            message='Dropbox is not authenticated',
            status_code=401
        )

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            DROPBOX_USER_URL,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type':  'application/json',
            },
            content=b'null',
        )
        if resp.status_code != 200:
            return error_response(
                message='Dropbox token is invalid',
                status_code=401
            )

        data = resp.json()
        return success_response(
            message='Dropbox user profile retrieved successfully',
            data={
            'name':     data.get('name', {}).get('display_name', ''),
            'email':    data.get('email', ''),
            'picture':  None,
            'provider': 'dropbox',
            }
        )
