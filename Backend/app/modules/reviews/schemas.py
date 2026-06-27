from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ── Images ────────────────────────────────────────────────────────────────────


class ReviewImageOut(BaseModel):
    id: uuid.UUID
    url: str
    sort_order: int

    model_config = {"from_attributes": True}


# ── Submit / Edit ─────────────────────────────────────────────────────────────


class ReviewCreate(BaseModel):
    product_id: uuid.UUID
    order_id: uuid.UUID | None = None
    rating: int = Field(..., ge=1, le=5)
    title: str | None = Field(None, max_length=255)
    body: str | None = None


class ReviewUpdate(BaseModel):
    rating: int | None = Field(None, ge=1, le=5)
    title: str | None = Field(None, max_length=255)
    body: str | None = None


# ── Response ──────────────────────────────────────────────────────────────────

ReviewStatus = Literal["pending", "approved", "rejected"]


class ReviewOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    user_id: uuid.UUID
    order_id: uuid.UUID | None
    customer_name: str | None
    rating: int
    title: str | None
    body: str | None
    is_verified_purchase: bool
    is_approved: bool
    is_rejected: bool
    is_flagged: bool
    helpful_count: int
    approved_at: datetime | None = None
    approved_by: str | None = None
    created_at: datetime
    updated_at: datetime
    images: list[ReviewImageOut] = []

    @property
    def status(self) -> ReviewStatus:
        if self.is_approved:
            return "approved"
        if self.is_rejected:
            return "rejected"
        return "pending"

    model_config = {"from_attributes": True}


class AdminReviewOut(ReviewOut):
    """Extended review DTO for admin endpoints — includes product name."""

    product_name: str | None = None


# ── Rating summary ────────────────────────────────────────────────────────────


class ProductRatingSummary(BaseModel):
    product_id: uuid.UUID
    review_count: int
    average_rating: float
    five_star: int
    four_star: int
    three_star: int
    two_star: int
    one_star: int


# ── Vote ──────────────────────────────────────────────────────────────────────


class ReviewVoteIn(BaseModel):
    is_helpful: bool


class ReviewVoteOut(BaseModel):
    id: uuid.UUID
    review_id: uuid.UUID
    is_helpful: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Admin ─────────────────────────────────────────────────────────────────────


class AdminReviewAction(BaseModel):
    action: str  # "approve" | "reject" | "flag"
