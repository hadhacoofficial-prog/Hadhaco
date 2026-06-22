from __future__ import annotations

import uuid

from pydantic import BaseModel


class NotificationPreferenceOut(BaseModel):
    id: uuid.UUID
    email_enabled: bool
    sms_enabled: bool
    order_updates: bool
    marketing: bool
    model_config = {"from_attributes": True}


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    order_updates: bool | None = None
    marketing: bool | None = None
