from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession


class EmailProvider(ABC):
    @abstractmethod
    async def send_email(
        self, db: AsyncSession, *, to: str, subject: str, html: str
    ) -> str:
        """Send an email. Returns provider message ID."""


class WhatsAppProvider(ABC):
    @abstractmethod
    async def send_whatsapp(
        self,
        db: AsyncSession,
        *,
        to: str,
        template_name: str,
        language: str,
        components: list[dict],
    ) -> str:
        """Send a pre-approved WhatsApp template message. Returns provider message ID."""
