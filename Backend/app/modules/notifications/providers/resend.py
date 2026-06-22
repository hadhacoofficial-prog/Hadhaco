from __future__ import annotations

import httpx
import structlog

from app.core.config import settings
from app.modules.notifications.providers.base import NotificationProvider

log = structlog.get_logger(__name__)

_BASE = "https://api.resend.com"


class ResendAuthError(RuntimeError):
    """401 from Resend — API key is missing, revoked, or wrong."""


class ResendDomainError(RuntimeError):
    """403 from Resend — sender domain is not verified."""


class ResendProvider(NotificationProvider):
    async def send_email(self, *, to: str, subject: str, html: str) -> str:
        payload = {
            "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>",
            "reply_to": settings.EMAIL_REPLY_TO,
            "to": [to],
            "subject": subject,
            "html": html,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(
                f"{_BASE}/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json=payload,
            )

        if resp.status_code == 401:
            # Do not retry on auth failures — the key will not change between
            # attempts.  The caller should mark the log as permanently failed.
            raise ResendAuthError(
                "Resend API returned 401 Unauthorized. "
                "The RESEND_API_KEY is missing, revoked, or incorrect. "
                "Generate a new key at resend.com/api-keys."
            )

        if resp.status_code == 403:
            raise ResendDomainError(
                f"Resend API returned 403 Forbidden. "
                f"The sender domain for '{settings.EMAIL_FROM}' is not verified. "
                f"Add and verify the domain at resend.com/domains."
            )

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error(
                "resend_http_error",
                status_code=exc.response.status_code,
                response_body=exc.response.text[:500],
                to=to,
                subject=subject,
            )
            raise

        message_id: str = resp.json().get("id", "")
        log.info("resend_email_sent", to=to, subject=subject, message_id=message_id)
        return message_id

    async def send_sms(self, *, to: str, body: str) -> str:
        raise NotImplementedError("Resend does not support SMS")
