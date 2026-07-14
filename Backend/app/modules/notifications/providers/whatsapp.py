from __future__ import annotations

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.notifications.providers.base import (
    WhatsAppProvider as _WhatsAppProviderABC,
)
from app.modules.settings.repository import SettingsRepository

log = structlog.get_logger(__name__)

_settings_repo = SettingsRepository()


class WhatsAppAuthError(RuntimeError):
    """401/403 from Meta — access token is invalid or expired."""


class WhatsAppTemplateError(RuntimeError):
    """Template message rejected (e.g. template not approved, missing parameters)."""


class WhatsAppProvider(_WhatsAppProviderABC):
    """Meta WhatsApp Business Cloud API provider.

    Sends pre-approved template messages via the Cloud API's /messages endpoint
    with type=template — required for business-initiated (transactional) sends.
    A free-form type=text fallback is available separately for replies made
    within Meta's 24-hour customer-service window, but is never used for
    business-initiated notifications.
    """

    async def _config(self, db: AsyncSession) -> dict[str, str]:
        db_config = await _settings_repo.get_provider_config(db, provider="whatsapp")
        return {
            "access_token": db_config.get("access_token")
            or settings.WHATSAPP_ACCESS_TOKEN,
            "phone_number_id": db_config.get("phone_number_id")
            or settings.WHATSAPP_PHONE_NUMBER_ID,
            "api_version": db_config.get("api_version")
            or settings.WHATSAPP_API_VERSION,
        }

    async def send_whatsapp(
        self,
        db: AsyncSession,
        *,
        to: str,
        template_name: str,
        language: str,
        components: list[dict],
    ) -> str:
        cfg = await self._config(db)
        phone_id = cfg["phone_number_id"]
        if not phone_id:
            raise WhatsAppAuthError(
                "WhatsApp phone_number_id is not configured. "
                "Set it via the admin notification-provider settings or "
                "WHATSAPP_PHONE_NUMBER_ID."
            )

        recipient = to.strip().replace(" ", "").replace("-", "").lstrip("+")

        payload: dict = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components,
            },
        }

        log.info("whatsapp_send_attempt", to=recipient, template=template_name)

        base_url = f"https://graph.facebook.com/{cfg['api_version']}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{base_url}/{phone_id}/messages",
                headers={
                    "Authorization": f"Bearer {cfg['access_token']}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if resp.status_code in (401, 403):
            raise WhatsAppAuthError(
                f"WhatsApp API returned {resp.status_code}. "
                "The access token may be expired or invalid. "
                "Regenerate it in the Meta Business Suite."
            )

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error(
                "whatsapp_http_error",
                status_code=exc.response.status_code,
                response_body=exc.response.text[:500],
                to=recipient,
            )
            raise

        data: dict = resp.json()
        messages = data.get("messages", [])
        message_id = messages[0].get("id", "") if messages else ""

        log.info("whatsapp_sent", to=recipient, message_id=message_id)
        return message_id

    async def send_whatsapp_text(self, db: AsyncSession, *, to: str, body: str) -> str:
        """Free-form message — only valid within Meta's 24h customer-service
        window (e.g. a live support reply). Not used for business-initiated
        notifications; callers must ensure the window applies."""
        cfg = await self._config(db)
        phone_id = cfg["phone_number_id"]
        if not phone_id:
            raise WhatsAppAuthError("WhatsApp phone_number_id is not configured.")

        recipient = to.strip().replace(" ", "").replace("-", "").lstrip("+")
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": body},
        }

        base_url = f"https://graph.facebook.com/{cfg['api_version']}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{base_url}/{phone_id}/messages",
                headers={
                    "Authorization": f"Bearer {cfg['access_token']}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if resp.status_code in (401, 403):
            raise WhatsAppAuthError(
                f"WhatsApp API returned {resp.status_code}. Access token invalid."
            )
        resp.raise_for_status()

        data: dict = resp.json()
        messages = data.get("messages", [])
        return messages[0].get("id", "") if messages else ""
