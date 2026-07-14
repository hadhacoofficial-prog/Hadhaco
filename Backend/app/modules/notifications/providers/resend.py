from __future__ import annotations

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.notifications.providers.base import EmailProvider
from app.modules.settings.repository import SettingsRepository

log = structlog.get_logger(__name__)

_BASE = "https://api.resend.com"
_settings_repo = SettingsRepository()


class ResendAuthError(RuntimeError):
    """401 from Resend — API key is missing, revoked, or wrong."""


class ResendDomainError(RuntimeError):
    """403 from Resend — sender domain is not verified."""


class ResendProvider(EmailProvider):
    async def _config(self, db: AsyncSession) -> dict[str, str]:
        db_config = await _settings_repo.get_provider_config(db, provider="email")
        return {
            "api_key": db_config.get("api_key") or settings.RESEND_API_KEY,
            "from_name": db_config.get("from_name") or settings.EMAIL_FROM_NAME,
            "from_email": db_config.get("from_email") or settings.EMAIL_FROM,
            "reply_to": db_config.get("reply_to") or settings.EMAIL_REPLY_TO,
        }

    async def send_email(
        self, db: AsyncSession, *, to: str, subject: str, html: str
    ) -> str:
        cfg = await self._config(db)
        payload = {
            "from": f"{cfg['from_name']} <{cfg['from_email']}>",
            "reply_to": cfg["reply_to"],
            "to": [to],
            "subject": subject,
            "html": html,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(
                f"{_BASE}/emails",
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
                json=payload,
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
                f"The sender domain for '{cfg['from_email']}' is not verified. "
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
