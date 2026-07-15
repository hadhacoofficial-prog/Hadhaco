import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.common.validators import IpAddressStr


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    actor_role: str | None
    action: str
    resource_type: str
    resource_id: uuid.UUID | None
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    meta: dict[str, Any] | None
    ip_address: IpAddressStr | None
    user_agent: str | None
    request_id: str | None
    source: str
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
