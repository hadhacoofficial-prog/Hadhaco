from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FeatureFlagOut(BaseModel):
    key: str
    value: bool
    description: str | None
    updated_at: datetime
    model_config = {"from_attributes": True}


class FeatureFlagUpdate(BaseModel):
    value: bool
    description: str | None = None


# ── Notification provider settings ──────────────────────────────────────────


class ProviderSettingsUpdate(BaseModel):
    """Arbitrary key -> value map for a provider's config fields.

    Keys are provider-specific (e.g. "api_key", "from_email" for email;
    "access_token", "phone_number_id" for whatsapp). Omitted/empty values are
    left unchanged.
    """

    values: dict[str, str]


class ProviderSettingsOut(BaseModel):
    provider: str
    settings: dict[str, str | None]


class ProviderTestResult(BaseModel):
    success: bool
    message: str
    message_id: str | None = None


class ProviderHealthOut(BaseModel):
    provider: str
    connection_status: str  # "connected" | "error" | "not_configured"
    connection_detail: str | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_failure_message: str | None = None
    last_webhook_at: datetime | None = None
    webhook_url: str | None = None
    webhook_verification_configured: bool = False


class WhatsAppMessageTemplateOut(BaseModel):
    name: str
    language: str
    status: str  # Meta's APPROVED | PENDING | REJECTED | DISABLED
    category: str
