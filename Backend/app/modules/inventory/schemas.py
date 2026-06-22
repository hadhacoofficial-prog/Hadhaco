import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class InventoryMovementResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    movement_type: str
    delta: int
    quantity_before: int
    quantity_after: int
    reference_type: str | None
    reference_id: str | None
    notes: str | None
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InventoryMovementListResponse(BaseModel):
    items: list[InventoryMovementResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ManualAdjustmentRequest(BaseModel):
    delta: int = Field(..., description="Positive to add stock, negative to remove")
    notes: str | None = Field(None, max_length=500)
    variant_id: uuid.UUID | None = None


class LowStockItem(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    stock_quantity: int
    low_stock_threshold: int
    status: str
    category_id: uuid.UUID | None
