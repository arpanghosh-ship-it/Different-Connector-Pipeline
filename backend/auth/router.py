import os
import secrets
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from config.settings import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, FRONTEND_URL, CREDENTIALS_FILE
from auth.state_store import load_states, save_states, STATES_FILE
from auth.flow import make_flow
from auth.credentials import load_credentials, save_credentials

router = APIRouter()

@router.get("/auth/login")
def login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env"
        )
    flow = make_flow()
    state = secrets.token_urlsafe(16)

    states = load_states()
    states[state] = True
    save_states(states)
    print(f"[auth] Login initiated. State saved: {state[:8]}...")

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",
        prompt="consent",
        state=state,
    )
    return RedirectResponse(auth_url)


@router.get("/auth/callback")
def callback(code: str = None, state: str = None, error: str = None):
    print(f"[auth] Callback received. state={state[:8] if state else None}... error={error}")

    if error:
        print(f"[auth] OAuth error: {error}")
        return RedirectResponse(f"{FRONTEND_URL}?auth=error&reason={error}")

    states = load_states()
    if not state or state not in states:
        print(f"[auth] Invalid state! Known states: {list(states.keys())[:3]}")
        return RedirectResponse(f"{FRONTEND_URL}?auth=error&reason=invalid_state")

    del states[state]
    save_states(states)

    try:
        flow = make_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        save_credentials(creds)
        print("[auth] Token exchange successful. Redirecting to frontend.")
    except Exception as e:
        print(f"[auth] Token exchange failed: {e}")
        return RedirectResponse(f"{FRONTEND_URL}?auth=error&reason=token_exchange_failed")

    return RedirectResponse(f"{FRONTEND_URL}?auth=success")


@router.get("/auth/logout")
def logout():
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)
    if os.path.exists(STATES_FILE):
        os.remove(STATES_FILE)
    print("[auth] Logged out — credentials deleted.")
    return {"message": "Logged out"}


@router.get("/auth/me")
async def me():
    creds = load_credentials()
    if not creds or not creds.token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Token invalid")
        return resp.json()