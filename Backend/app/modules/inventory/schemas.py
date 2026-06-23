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


# ── Reservation schemas ───────────────────────────────────────────────────────


class ReservationResponse(BaseModel):
    id: uuid.UUID
    reservation_number: str
    user_id: uuid.UUID
    order_id: uuid.UUID | None
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    quantity: int
    status: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReservationListResponse(BaseModel):
    items: list[ReservationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Inventory transaction schemas ─────────────────────────────────────────────


class InventoryTransactionResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    reservation_id: uuid.UUID | None
    order_id: uuid.UUID | None
    transaction_type: str
    quantity: int
    before_available: int
    after_available: int
    before_reserved: int
    after_reserved: int
    before_sold: int
    after_sold: int
    reference: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InventoryTransactionListResponse(BaseModel):
    items: list[InventoryTransactionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Stock summary (admin dashboard) ──────────────────────────────────────────


class ProductStockSummary(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    total_stock: int
    reserved_quantity: int
    sold_quantity: int
    available_quantity: int
    active_reservations: int
