import uuid
from datetime import datetime

from pydantic import BaseModel


class WishlistItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    added_at: datetime

    model_config = {"from_attributes": True}


class WishlistResponse(BaseModel):
    id: uuid.UUID
    items: list[WishlistItemResponse]
    total: int

    model_config = {"from_attributes": True}


class AddToWishlistRequest(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
