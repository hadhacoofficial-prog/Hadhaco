from __future__ import annotations

from abc import ABC, abstractmethod

from app.modules.notifications.dto import EmailPayload, WhatsAppPayload


class EmailProvider(ABC):
    @abstractmethod
    async def send_email(self, payload: EmailPayload) -> str:
        """Send an email. Returns provider message ID."""


class WhatsAppProvider(ABC):
    @abstractmethod
    async def send_whatsapp(self, payload: WhatsAppPayload) -> str:
        """Send a pre-approved WhatsApp template message. Returns provider message ID."""
