from __future__ import annotations
from abc import ABC, abstractmethod


class NotificationProvider(ABC):
    @abstractmethod
    async def send_email(self, *, to: str, subject: str, html: str) -> str:
        """Returns provider message ID."""

    @abstractmethod
    async def send_sms(self, *, to: str, body: str) -> str:
        """Returns provider message ID."""
