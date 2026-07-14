from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import ok
from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_whatsapp_webhook_signature
from app.middleware.rate_limit import rate_limit_webhook
from app.modules.notifications.repository import NotificationRepository

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/notifications/webhooks", tags=["notifications"])
_repo = NotificationRepository()


@router.get("/whatsapp", include_in_schema=False)
async def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    """Meta's webhook subscription verification handshake."""
    if hub_mode != "subscribe" or hub_verify_token != settings.WHATSAPP_VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    return PlainTextResponse(hub_challenge)


@router.post(
    "/whatsapp",
    include_in_schema=False,
    dependencies=[Depends(rate_limit_webhook)],
)
async def whatsapp_status_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_whatsapp_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    updated = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status_update in value.get("statuses", []):
                wamid = status_update.get("id")
                status = status_update.get("status")
                if not wamid or not status:
                    continue
                log_entry = await _repo.get_log_by_provider_message_id(db, wamid)
                if not log_entry:
                    continue
                if status == "delivered":
                    await _repo.mark_delivered(db, log_entry)
                elif status == "read":
                    await _repo.mark_read(db, log_entry)
                elif status == "failed":
                    errors = status_update.get("errors", [])
                    reason = (
                        errors[0].get("title", "delivery failed")
                        if errors
                        else ("delivery failed")
                    )
                    await _repo.mark_failed(db, log_entry, reason)
                updated += 1
                log.info("whatsapp_status_update", wamid=wamid, status=status)

    return ok(
        {"updated": updated},
        ResponseCode.WEBHOOK_PROCESSED,
        "WhatsApp webhook processed successfully",
    )
