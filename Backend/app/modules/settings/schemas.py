from __future__ import annotations
import uuid
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
