from __future__ import annotations

from app.modules.notifications.providers.base import EmailProvider, WhatsAppProvider
from app.modules.notifications.providers.resend import ResendProvider
from app.modules.notifications.providers.whatsapp import (
    WhatsAppProvider as MetaWhatsAppProvider,
)

_EMAIL_PROVIDERS: dict[str, EmailProvider] = {"resend": ResendProvider()}
_WHATSAPP_PROVIDERS: dict[str, WhatsAppProvider] = {"meta": MetaWhatsAppProvider()}


class ProviderRegistry:
    """Resolves a channel to its configured concrete provider.

    Adding a new provider requires only: implement it against EmailProvider or
    WhatsAppProvider, register it here. NotificationService and business
    services never need to change.
    """

    def get_email_provider(self, name: str = "resend") -> EmailProvider:
        try:
            return _EMAIL_PROVIDERS[name]
        except KeyError:
            raise ValueError(f"Unknown email provider: {name}") from None

    def get_whatsapp_provider(self, name: str = "meta") -> WhatsAppProvider:
        try:
            return _WHATSAPP_PROVIDERS[name]
        except KeyError:
            raise ValueError(f"Unknown whatsapp provider: {name}") from None


registry = ProviderRegistry()
