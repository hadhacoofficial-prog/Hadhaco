from __future__ import annotations

from app.modules.notifications.dto import EmailPayload, WhatsAppPayload
from app.modules.notifications.providers.registry import registry


class NotificationDispatcher:
    """Single entry point business logic goes through to actually send.

    Resolves the concrete provider via the ProviderRegistry — NotificationService
    never imports ResendProvider/WhatsAppProvider directly.

    Providers receive immutable DTOs (EmailPayload / WhatsAppPayload) that
    contain every piece of data needed for delivery.  No provider may hold
    or receive an AsyncSession.
    """

    async def send_email(self, payload: EmailPayload) -> str:
        provider = registry.get_email_provider()
        return await provider.send_email(payload)

    async def send_whatsapp(self, payload: WhatsAppPayload) -> str:
        provider = registry.get_whatsapp_provider()
        return await provider.send_whatsapp(payload)


dispatcher = NotificationDispatcher()
