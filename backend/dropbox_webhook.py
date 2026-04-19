"""
dropbox_webhook.py
Handles Dropbox push notifications.

How Dropbox webhooks differ from Google Drive:
  1. Webhook URL is registered in the Dropbox App Console (not via API).
     → No registration/expiry management needed — just expose the endpoint.
  2. Verification: Dropbox sends a GET with ?challenge=RANDOM → respond with that value.
  3. Notification: Dropbox sends a POST with {"list_folder": {"accounts": [...]}}
     The body tells you WHICH accounts changed, NOT what changed.
  4. To get the actual changes: call /files/list_folder/continue with your saved cursor.

Setup (one-time in Dropbox App Console):
  1. Go to https://www.dropbox.com/developers/apps → your app → Settings
  2. Scroll to "Webhooks" section
  3. Add webhook URL: https://your-domain.com/api/webhook/dropbox
  4. Dropbox will send a GET to verify — our endpoint handles it automatically.
"""
import asyncio
import hashlib
import hmac
import json
from fastapi import APIRouter, Request, Response, Query
from fastapi.responses import PlainTextResponse

from events import broadcast
from config import DROPBOX_APP_SECRET

router = APIRouter()

_processing = False

@router.get("")
async def dropbox_webhook_verify(challenge: str = Query(...)):
    """
    Dropbox webhook verification endpoint.
    Dropbox sends GET /api/webhook/dropbox?challenge=RANDOM_STRING
    We must respond with the challenge value as plain text.
    """
    print(f'[dropbox_webhook] Verification challenge received: {challenge[:20]}…')
    return PlainTextResponse(content=challenge)

@router.post("")
async def dropbox_webhook_notify(request: Request):
    """
    Receives Dropbox push notifications.
    """
    raw_body  = await request.body()
    signature = request.headers.get('X-Dropbox-Signature', '')

    try:
        payload     = json.loads(raw_body)
        account_ids = payload.get('list_folder', {}).get('accounts', [])
    except Exception:
        account_ids = []

    print(f'[dropbox_webhook] Notification received. accounts={account_ids}')

    asyncio.create_task(
        process_dropbox_notification(account_ids, raw_body, signature)
    )

    # Must return 200 quickly — Dropbox will retry if we don't
    return Response(status_code=200)


async def process_dropbox_notification(account_ids: list, raw_body: bytes, signature: str):
    """
    Called on every Dropbox push notification POST.
    Verifies the HMAC signature, then triggers delta sync.

    `account_ids` — list of Dropbox account IDs that had changes
    `raw_body`    — raw request body (for HMAC verification)
    `signature`   — value of X-Dropbox-Signature header
    """
    global _processing

    # ── Verify HMAC-SHA256 signature ───────────────────────
    if DROPBOX_APP_SECRET and signature:
        expected = hmac.new(
            DROPBOX_APP_SECRET.encode('utf-8'),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            print('[dropbox_webhook] SIGNATURE MISMATCH — ignoring notification')
            return
    else:
        print('[dropbox_webhook] WARNING: Signature verification skipped (no APP_SECRET or header)')

    if not account_ids:
        return

    if _processing:
        await broadcast({
            'type':    'webhook_received',
            'message': 'Dropbox change detected — delta already running, queued',
        })
        return

    _processing = True
    try:
        from dropbox_crawler import process_dropbox_delta, is_dropbox_crawling

        await broadcast({
            'type':    'webhook_received',
            'message': f'Dropbox change detected — fetching delta for {len(account_ids)} account(s)…',
        })

        if is_dropbox_crawling():
            await broadcast({
                'type':    'webhook_received',
                'message': 'Dropbox crawl already in progress — delta queued',
            })
            return

        await process_dropbox_delta()

    except Exception as e:
        await broadcast({'type': 'error', 'message': f'Dropbox delta error: {e}'})
    finally:
        _processing = False
