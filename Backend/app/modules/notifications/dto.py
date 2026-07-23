"""Immutable delivery payloads for the notification pipeline.

Design rule: *no provider may hold an AsyncSession*. Every piece of
data a provider needs to deliver a message (recipient address, rendered
subject/body, API keys, phone_number_id, …) must live inside a plain
dataclass that is built **while** a DB session is open and then passed
into the provider *after* the session is closed.

This module defines the DTOs that decouple the DB-read phase from the
HTTP-delivery phase of every notification.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EmailPayload:
    """Everything the Resend provider needs — no DB session required."""

    to: str
    subject: str
    html: str
    api_key: str
    from_name: str
    from_email: str
    reply_to: str


@dataclass(frozen=True)
class WhatsAppPayload:
    """Everything the Meta WhatsApp provider needs — no DB session required."""

    to: str
    template_name: str
    language: str
    components: list[dict[str, Any]] = field(default_factory=list)
    access_token: str = ""
    phone_number_id: str = ""
    api_version: str = ""


@dataclass(frozen=True)
class ProviderConfig:
    """Resolved provider configuration from DB settings + env fallbacks.

    Built once per dispatch while a DB session is open, then reused
    for all subsequent HTTP calls without touching the database again.
    """

    # Email (Resend)
    email_api_key: str = ""
    email_from_name: str = ""
    email_from_email: str = ""
    email_reply_to: str = ""
    email_enabled: bool = True

    # WhatsApp (Meta)
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = ""
    whatsapp_enabled: bool = True


@dataclass(frozen=True)
class RetryContext:
    """Pre-loaded data for retrying a single notification log entry.

    Built during the DB-read phase so that the actual HTTP delivery
    can happen without any open database connection.
    """

    log_id: uuid.UUID
    channel: str
    event_type: str
    recipient: str
    rendered_subject: str | None = None
    rendered_body: str | None = None
    whatsapp_params: dict[str, Any] | None = None
    template_id: uuid.UUID | None = None
    provider_config: ProviderConfig | None = None
