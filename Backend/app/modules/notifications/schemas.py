from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

# ── Preferences ────────────────────────────────────────────────────────────────


class NotificationPreferenceOut(BaseModel):
    id: uuid.UUID
    email_enabled: bool
    whatsapp_enabled: bool
    order_updates: bool
    marketing: bool
    model_config = {"from_attributes": True}


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: bool | None = None
    whatsapp_enabled: bool | None = None
    order_updates: bool | None = None
    marketing: bool | None = None


# ── Notification Rules (matrix) ───────────────────────────────────────────────


class NotificationRuleOut(BaseModel):
    id: uuid.UUID
    event_type: str
    display_name: str | None = None
    category: str | None = None
    description: str | None = None
    enabled: bool
    email_enabled: bool
    whatsapp_enabled: bool
    priority: str
    retry_policy: dict[str, Any] | None = None
    cooldown_seconds: int
    customer_visible: bool
    admin_visible: bool
    is_system: bool
    display_order: int
    last_triggered_at: datetime | None = None
    last_sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class NotificationRuleUpdate(BaseModel):
    display_name: str | None = None
    category: str | None = None
    description: str | None = None
    enabled: bool | None = None
    email_enabled: bool | None = None
    whatsapp_enabled: bool | None = None
    priority: str | None = None
    retry_policy: dict[str, Any] | None = None
    cooldown_seconds: int | None = None
    customer_visible: bool | None = None
    admin_visible: bool | None = None
    display_order: int | None = None


# ── Notification Templates ────────────────────────────────────────────────────


class NotificationTemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    channel: str
    event_type: str
    subject: str | None = None
    template_body: str
    variables: dict[str, Any] | None = None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class NotificationTemplateUpdate(BaseModel):
    subject: str | None = None
    template_body: str | None = None
    variables: dict[str, Any] | None = None
    is_active: bool | None = None


class NotificationTemplateVersionOut(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    version: int
    subject: str | None = None
    template_body: str
    variables: dict[str, Any] | None = None
    created_at: datetime
    created_by: uuid.UUID | None = None
    model_config = {"from_attributes": True}


# ── Notification Logs ─────────────────────────────────────────────────────────


class NotificationLogOut(BaseModel):
    id: uuid.UUID
    channel: str
    event_type: str
    recipient: str
    status: str
    provider: str | None = None
    provider_message_id: str | None = None
    error_message: str | None = None
    attempt_count: int
    rendered_subject: str | None = None
    rendered_body: str | None = None
    whatsapp_params: dict[str, Any] | None = None
    template_id: uuid.UUID | None = None
    template_version: int | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Analytics ─────────────────────────────────────────────────────────────────


class DailyTotalOut(BaseModel):
    date: str
    sent: int
    delivered: int
    failed: int


class TopTemplateOut(BaseModel):
    name: str
    event_type: str
    channel: str
    sent_count: int


class ProviderSuccessRateOut(BaseModel):
    sent: int
    failed: int
    success_rate: float


class NotificationAnalyticsOut(BaseModel):
    total_sent: int
    total_failed: int
    total_pending: int
    total_retrying: int
    total_delivered: int
    total_read: int
    total_retried: int
    email_sent: int
    email_failed: int
    whatsapp_sent: int
    whatsapp_failed: int
    avg_delivery_seconds: float | None = None
    provider_success_rate: dict[str, ProviderSuccessRateOut] = {}
    daily_totals: list[DailyTotalOut] = []
    top_templates: list[TopTemplateOut] = []
