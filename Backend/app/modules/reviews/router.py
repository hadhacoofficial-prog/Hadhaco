from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_admin,
)
from app.modules.reviews.schemas import (
    AdminReviewAction,
    AdminReviewOut,
    MyProductReviewStatus,
    ProductRatingSummary,
    ReviewCreate,
    ReviewOut,
    ReviewUpdate,
    ReviewVoteIn,
    ReviewVoteOut,
)
from app.modules.reviews.service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])
_svc = ReviewService()


# ── Public ────────────────────────────────────────────────────────────────────


@router.get(
    "/products/{product_id}", response_model=BaseSuccessResponse[list[ReviewOut]]
)
async def list_product_reviews(
    product_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    viewer_user_id = user.id if user else None
    result = await _svc.list_product_reviews(
        db,
        product_id=product_id,
        viewer_user_id=viewer_user_id,
        offset=offset,
        limit=limit,
    )
    return ok(result, ResponseCode.REVIEW_LISTED, "Reviews listed successfully")


@router.get(
    "/products/{product_id}/summary",
    response_model=BaseSuccessResponse[ProductRatingSummary],
)
async def product_rating_summary(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    data = await _svc.rating_summary(db, product_id)
    if data is None:
        summary = ProductRatingSummary(
            product_id=product_id,
            review_count=0,
            average_rating=0.0,
            five_star=0,
            four_star=0,
            three_star=0,
            two_star=0,
            one_star=0,
        )
    else:
        summary = ProductRatingSummary(**data)
    return ok(
        summary,
        ResponseCode.REVIEW_SUMMARY_FETCHED,
        "Rating summary fetched successfully",
    )


# ── Customer (auth required) ──────────────────────────────────────────────────


@router.get(
    "/products/{product_id}/my-status",
    response_model=BaseSuccessResponse[MyProductReviewStatus],
)
async def my_review_status(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Read-only reminder state for the product-page review banner — does not
    change who may review (see MyProductReviewStatus)."""
    data = await _svc.my_review_status(db, product_id=product_id, user_id=user.id)
    return ok(
        MyProductReviewStatus(**data),
        ResponseCode.REVIEW_STATUS_FETCHED,
        "Review status fetched successfully",
    )


@router.post("", response_model=BaseSuccessResponse[ReviewOut], status_code=201)
async def submit_review(
    product_id: uuid.UUID = Form(...),
    rating: int = Form(..., ge=1, le=5),
    body: str | None = Form(None),
    title: str | None = Form(None),
    order_id: uuid.UUID | None = Form(None),
    images: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.common.responses import created

    data = ReviewCreate(
        product_id=product_id,
        rating=rating,
        body=body,
        title=title,
        order_id=order_id,
    )
    result = await _svc.submit_review(
        db,
        user_id=user.id,
        customer_name=getattr(user, "full_name", None),
        data=data,
        images=images or None,
    )
    return created(
        result, ResponseCode.REVIEW_SUBMITTED, "Review submitted successfully"
    )


@router.patch("/{review_id}", response_model=BaseSuccessResponse[ReviewOut])
async def edit_review(
    review_id: uuid.UUID,
    data: ReviewUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    result = await _svc.edit_review(db, review_id=review_id, user_id=user.id, data=data)
    return ok(result, ResponseCode.REVIEW_UPDATED, "Review updated successfully")


@router.delete(
    "/{review_id}", response_model=BaseSuccessResponse[None], status_code=200
)
async def delete_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await _svc.delete_review(db, review_id=review_id, user_id=user.id)
    return deleted(ResponseCode.REVIEW_DELETED, "Review deleted successfully")


@router.post("/{review_id}/vote", response_model=BaseSuccessResponse[ReviewVoteOut])
async def vote_review(
    review_id: uuid.UUID,
    body: ReviewVoteIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    result = await _svc.vote(
        db, review_id=review_id, user_id=user.id, is_helpful=body.is_helpful
    )
    return ok(result, ResponseCode.REVIEW_VOTED, "Vote recorded successfully")


# ── Admin ─────────────────────────────────────────────────────────────────────


@router.get("/admin/reviews", response_model=BaseSuccessResponse[list[AdminReviewOut]])
async def list_all_reviews(
    status: str | None = Query(None, description="pending | approved | rejected"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.list_all_reviews(db, status=status, offset=offset, limit=limit)
    return ok(result, ResponseCode.REVIEW_ALL_LISTED, "Reviews listed successfully")


@router.get("/admin/pending", response_model=BaseSuccessResponse[list[ReviewOut]])
async def list_pending_reviews(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.list_pending(db, offset=offset, limit=limit)
    return ok(
        result,
        ResponseCode.REVIEW_PENDING_LISTED,
        "Pending reviews listed successfully",
    )


@router.post("/admin/send-reminders", response_model=BaseSuccessResponse[dict])
async def send_review_reminders(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.core.config import settings
    from app.core.events import ReviewRequestEvent, event_bus
    from app.modules.orders.models import Order
    from app.modules.profiles.models import Profile
    from app.modules.reviews.repository import ReviewRepository

    now = datetime.now(UTC)
    deadline = now - timedelta(hours=settings.REVIEW_REMINDER_DELAY_HOURS)
    oldest = now - timedelta(days=30)

    result = await db.execute(
        select(Order, Profile.email)
        .join(Profile, Profile.id == Order.user_id)
        .where(
            Order.status == "delivered",
            Order.delivered_at <= deadline,
            Order.delivered_at >= oldest,
        )
    )
    rows = result.all()

    candidate_ids = [order.id for order, email in rows if email]
    reviewed_ids = await ReviewRepository().get_reviewed_order_ids(db, candidate_ids)

    # Commit is a no-op here (read-only query), but ensures listeners
    # see a clean transaction boundary before the publish loop.
    await db.commit()

    sent = 0
    skipped = 0
    for order, email in rows:
        if not email or order.id in reviewed_ids:
            skipped += 1
            continue
        await event_bus.publish(
            ReviewRequestEvent(
                order_id=str(order.id),
                user_id=str(order.user_id),
                customer_email=email,
                order_number=order.order_number,
            )
        )
        sent += 1

    return ok(
        {"sent": sent, "skipped": skipped, "candidates": len(rows)},
        ResponseCode.REVIEW_REMINDERS_SENT,
        f"Sent {sent} review reminder(s)",
    )


@router.post("/admin/{review_id}/action", response_model=BaseSuccessResponse[ReviewOut])
async def admin_review_action(
    review_id: uuid.UUID,
    body: AdminReviewAction,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    admin_id = str(getattr(admin, "id", "")) if admin else None
    result = await _svc.admin_action(
        db, review_id=review_id, action=body.action, admin_identifier=admin_id
    )
    return ok(
        result, ResponseCode.REVIEW_ACTION_APPLIED, "Review action applied successfully"
    )


@router.delete(
    "/admin/{review_id}", response_model=BaseSuccessResponse[None], status_code=200
)
async def admin_delete_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    await _svc.admin_delete(db, review_id=review_id)
    return deleted(ResponseCode.REVIEW_DELETED, "Review deleted successfully")
