from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class FraudSignalCreate(BaseModel):
    user_id: uuid.UUID | None = None
    ip_address: str | None = None
    signal_type: str
    severity: str = "medium"
    description: str
    metadata: dict = {}


class FraudSignalOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    signal_type: str
    severity: str
    description: str
    is_resolved: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class FraudResolveRequest(BaseModel):
    is_resolved: bool = True
