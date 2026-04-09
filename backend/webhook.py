import asyncio
import json
import os
import uuid
import httpx
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from auth import load_credentials
from config import STORAGE_DIR, WEBHOOK_URL

CHANNEL_FILE = os.path.join(STORAGE_DIR, 'webhook_channel.json')
PAGE_TOKEN_FILE = os.path.join(STORAGE_DIR, 'page_token.json')

_renewal_scheduler = AsyncIOScheduler()
_processing = False


# ── Persistence helpers ────────────────────────────────────────────────────────

def _save_channel(channel_id: str, resource_id: str, expiration_ms: int):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(CHANNEL_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'channel_id': channel_id,
            'resource_id': resource_id,
            'expiration_ms': expiration_ms,
        }, f, indent=2)


def load_channel() -> dict:
    if not os.path.exists(CHANNEL_FILE):
        return {}
    try:
        with open(CHANNEL_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_page_token(token: str):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(PAGE_TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump({'token': token}, f)


def load_page_token() -> str | None:
    if not os.path.exists(PAGE_TOKEN_FILE):
        return None
    try:
        with open(PAGE_TOKEN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('token')
    except Exception:
        return None


# ── Core webhook registration ──────────────────────────────────────────────────

async def _get_start_page_token(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            'https://www.googleapis.com/drive/v3/changes/startPageToken',
            headers={'Authorization': f'Bearer {access_token}'},
            params={'supportsAllDrives': 'true'},
        )
        resp.raise_for_status()
        return resp.json()['startPageToken']


async def register_webhook() -> dict:
    """Register a Drive push notification channel. Returns a status dict."""
    if not WEBHOOK_URL:
        return {
            'success': False,
            'error': (
                'WEBHOOK_URL not set in .env. '
                'For local dev, use ngrok: ngrok http 8000 '
                'then set WEBHOOK_URL=https://<your-id>.ngrok.io'
            ),
        }

    creds = load_credentials()
    if not creds or not creds.token:
        return {'success': False, 'error': 'Not authenticated'}

    # Tear down any existing channel first
    await stop_webhook(quiet=True)

    # Fresh start-page-token so we only see changes from now onwards
    try:
        start_token = await _get_start_page_token(creds.token)
    except Exception as e:
        return {'success': False, 'error': f'Could not get page token: {e}'}

    save_page_token(start_token)

    channel_id = str(uuid.uuid4())
    callback_url = WEBHOOK_URL.rstrip('/') + '/api/webhook/drive'

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            'https://www.googleapis.com/drive/v3/changes/watch',
            headers={
                'Authorization': f'Bearer {creds.token}',
                'Content-Type': 'application/json',
            },
            params={
                'pageToken': start_token,
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true',
            },
            json={
                'id': channel_id,
                'type': 'web_hook',
                'address': callback_url,
            },
        )

    if resp.status_code not in (200, 201):
        return {
            'success': False,
            'error': f'Google API returned {resp.status_code}: {resp.text}',
        }

    data = resp.json()
    expiration_ms = int(data.get('expiration', 0))
    _save_channel(channel_id, data.get('resourceId', ''), expiration_ms)

    # Schedule auto-renewal 1 hour before expiry (Google max TTL = 7 days)
    _schedule_renewal(expiration_ms)

    exp_iso = (
        datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc).isoformat()
        if expiration_ms else 'unknown'
    )
    return {
        'success': True,
        'channel_id': channel_id,
        'callback_url': callback_url,
        'expires_at': exp_iso,
    }


async def stop_webhook(quiet: bool = False):
    """Deregister the current webhook channel from Google."""
    channel = load_channel()
    if not channel.get('channel_id'):
        return

    creds = load_credentials()
    if creds and creds.token:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    'https://www.googleapis.com/drive/v3/channels/stop',
                    headers={
                        'Authorization': f'Bearer {creds.token}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'id': channel['channel_id'],
                        'resourceId': channel['resource_id'],
                    },
                )
        except Exception:
            pass

    if os.path.exists(CHANNEL_FILE):
        os.remove(CHANNEL_FILE)

    if not quiet:
        from events import broadcast
        await broadcast({'type': 'webhook_stopped', 'message': 'Webhook channel stopped'})


# ── Auto-renewal scheduler ─────────────────────────────────────────────────────

def _schedule_renewal(expiration_ms: int):
    """Schedule a renewal job 1 hour before the channel expires."""
    if _renewal_scheduler.get_job('webhook_renew'):
        _renewal_scheduler.remove_job('webhook_renew')

    if not expiration_ms:
        return

    # Renew 1 hour before expiry
    renew_at_ms = expiration_ms - (60 * 60 * 1000)
    renew_dt = datetime.fromtimestamp(renew_at_ms / 1000, tz=timezone.utc)

    # If expiry is very soon, renew in 5 minutes instead
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    if renew_at_ms <= now_ms:
        # IMPORTANT: set next_run_time explicitly so the interval job does NOT
        # fire immediately. Without this, APScheduler fires the job as soon as
        # it is added, which causes _renewal_job → register_webhook →
        # _schedule_renewal → new interval job → fires immediately → infinite loop.
        next_run = datetime.now(timezone.utc) + timedelta(minutes=5)
        _renewal_scheduler.add_job(
            _renewal_job,
            'interval',
            minutes=5,
            id='webhook_renew',
            replace_existing=True,
            next_run_time=next_run,
        )
        print(f'[webhook] Expiry imminent — renewal scheduled in 5 min ({next_run.isoformat()})')
    else:
        _renewal_scheduler.add_job(
            _renewal_job,
            'date',
            run_date=renew_dt,
            id='webhook_renew',
            replace_existing=True,
        )
        print(f'[webhook] Renewal scheduled at {renew_dt.isoformat()}')

    if not _renewal_scheduler.running:
        _renewal_scheduler.start()


async def _renewal_job():
    from events import broadcast
    await broadcast({'type': 'webhook_renewing', 'message': 'Renewing webhook channel…'})
    result = await register_webhook()
    if result['success']:
        await broadcast({'type': 'webhook_renewed', 'message': 'Webhook channel renewed', 'expires_at': result.get('expires_at')})
    else:
        await broadcast({'type': 'error', 'message': f'Webhook renewal failed: {result["error"]}'})


def stop_renewal_scheduler():
    if _renewal_scheduler.running:
        _renewal_scheduler.shutdown(wait=False)


# ── Notification handler ───────────────────────────────────────────────────────

async def process_drive_notification(resource_state: str, channel_id: str, message_number: str):
    """
    Called by the FastAPI webhook endpoint on every Google push.

    resource_state values:
      'sync'   — initial handshake after registration (no-op)
      'change' — something in Drive changed
    """
    global _processing

    from events import broadcast

    print(f'[webhook] ► Notification received: state={resource_state!r}  channel={channel_id!r}  msg={message_number}')

    # Handshake — just acknowledge, nothing to do
    if resource_state == 'sync':
        print('[webhook]   Handshake — acknowledged, no action needed')
        return

    # Verify it\'s our channel
    channel = load_channel()
    stored_id = channel.get('channel_id')
    if stored_id != channel_id:
        print(f'[webhook]   Channel ID MISMATCH — stored={stored_id!r}, received={channel_id!r} — ignoring')
        return

    print(f'[webhook]   Channel ID matched — proceeding with delta sync')

    if _processing:
        await broadcast({'type': 'webhook_received', 'message': 'Change detected — crawl already running, queued'})
        return

    _processing = True
    try:
        from crawler import process_delta_changes, get_root_folder, is_crawling

        root = get_root_folder()
        if not root.get('id'):
            print('[webhook]   No root folder set — ignoring')
            return

        await broadcast({
            'type': 'webhook_received',
            'message': f'Drive change detected (msg #{message_number}) — fetching delta…',
        })

        if is_crawling():
            await broadcast({'type': 'webhook_received', 'message': 'Crawl already in progress — delta queued'})
            return

        await process_delta_changes()

    finally:
        _processing = False


# ── Status helper ──────────────────────────────────────────────────────────────

def webhook_status() -> dict:
    channel = load_channel()
    if not channel.get('channel_id'):
        return {'active': False, 'channel_id': None, 'expires_at': None}

    expiration_ms = channel.get('expiration_ms', 0)
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    still_valid = expiration_ms == 0 or now_ms < expiration_ms

    exp_iso = (
        datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc).isoformat()
        if expiration_ms else None
    )
    return {
        'active': still_valid,
        'channel_id': channel['channel_id'],
        'expires_at': exp_iso,
        'callback_url': WEBHOOK_URL.rstrip('/') + '/api/webhook/drive' if WEBHOOK_URL else None,
    }