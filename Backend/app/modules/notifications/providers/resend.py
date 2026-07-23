from __future__ import annotations

import httpx
import structlog

from app.modules.notifications.dto import EmailPayload
from app.modules.notifications.providers.base import EmailProvider

log = structlog.get_logger(__name__)

_BASE = "https://api.resend.com"


class ResendAuthError(RuntimeError):
    """401 from Resend — API key is missing, revoked, or wrong."""


class ResendDomainError(RuntimeError):
    """403 from Resend — sender domain is not verified."""


class ResendProvider(EmailProvider):
    async def send_email(self, payload: EmailPayload) -> str:
        http_payload = {
            "from": f"{payload.from_name} <{payload.from_email}>",
            "reply_to": payload.reply_to,
            "to": [payload.to],
            "subject": payload.subject,
            "html": payload.html,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(
                f"{_BASE}/emails",
                headers={"Authorization": f"Bearer {payload.api_key}"},
                json=http_payload,
            )

        if resp.status_code == 401:
            raise ResendAuthError(
                "Resend API returned 401 Unauthorized. "
                "The Resend API key is missing, revoked, or incorrect. "
                "Generate a new key at resend.com/api-keys."
            )

        if resp.status_code == 403:
            raise ResendDomainError(
                f"Resend API returned 403 Forbidden. "
                f"The sender domain for '{payload.from_email}' is not verified. "
                f"Add and verify the domain at resend.com/domains."
            )

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error(
                "resend_http_error",
                status_code=exc.response.status_code,
                to=payload.to,
                subject=payload.subject,
            )
            raise

        message_id: str = resp.json().get("id", "")
        log.info(
            "resend_email_sent",
            to=payload.to,
            subject=payload.subject,
            message_id=message_id,
        )
        return message_id
