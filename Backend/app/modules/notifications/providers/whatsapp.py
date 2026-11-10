from __future__ import annotations

import httpx
import structlog

from app.modules.notifications.dto import WhatsAppPayload
from app.modules.notifications.providers.base import (
    WhatsAppProvider as _WhatsAppProviderABC,
)

log = structlog.get_logger(__name__)


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

    async def send_whatsapp(self, payload: WhatsAppPayload) -> str:
        phone_id = payload.phone_number_id
        if not phone_id:
            raise WhatsAppAuthError(
                "WhatsApp phone_number_id is not configured. "
                "Set it via the admin notification-provider settings or "
                "WHATSAPP_PHONE_NUMBER_ID."
            )

        recipient = payload.to.strip().replace(" ", "").replace("-", "").lstrip("+")

        body: dict = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": payload.template_name,
                "language": {"code": payload.language},
                "components": payload.components,
            },
        }

        log.info("whatsapp_send_attempt", to=recipient, template=payload.template_name)

        base_url = f"https://graph.facebook.com/{payload.api_version}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{base_url}/{phone_id}/messages",
                headers={
                    "Authorization": f"Bearer {payload.access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
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
                to=recipient,
            )
            raise

        data: dict = resp.json()
        messages = data.get("messages", [])
        message_id = messages[0].get("id", "") if messages else ""

        log.info("whatsapp_sent", to=recipient, message_id=message_id)
        return message_id

    async def send_whatsapp_text(self, payload: WhatsAppPayload) -> str:
        """Free-form message — only valid within Meta's 24h customer-service
        window (e.g. a live support reply). Not used for business-initiated
        notifications; callers must ensure the window applies."""
        phone_id = payload.phone_number_id
        if not phone_id:
            raise WhatsAppAuthError("WhatsApp phone_number_id is not configured.")

        recipient = payload.to.strip().replace(" ", "").replace("-", "").lstrip("+")
        body: dict = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": (
                {"body": payload.components[0].get("text", "")}
                if payload.components
                else {"body": ""}
            ),
        }

        base_url = f"https://graph.facebook.com/{payload.api_version}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{base_url}/{phone_id}/messages",
                headers={
                    "Authorization": f"Bearer {payload.access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )

        if resp.status_code in (401, 403):
            raise WhatsAppAuthError(
                f"WhatsApp API returned {resp.status_code}. Access token invalid."
            )
        resp.raise_for_status()

        data: dict = resp.json()
        messages = data.get("messages", [])
        return messages[0].get("id", "") if messages else ""
