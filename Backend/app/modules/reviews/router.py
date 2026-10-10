from __future__ import annotations

import math
import uuid
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.cache import (
    PREFIX_REVIEW_LIST,
    PREFIX_REVIEW_SUMMARY,
    TTL_REVIEW_LIST,
    TTL_REVIEW_SUMMARY,
    add_cache_headers,
    bust_review_cache,
    cache_swr,
)
from app.core.database import AsyncSessionLocal, get_db
from app.core.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_admin,
)
from app.core.redis import get_redis
from app.modules.reviews.schemas import (
    AdminReviewAction,
    MyProductReviewStatus,
    ProductRatingSummary,
    ReviewCreate,
    ReviewListResponse,
    ReviewOut,
    ReviewUpdate,
    ReviewVoteIn,
    ReviewVoteOut,
)
from app.modules.reviews.service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])
_svc = ReviewService()

# Seconds past the TTL that an idle entry is still served (stale) while one
# background refresh runs. bust_review_cache hard-deletes on any review change,
# so this only ever bridges idle expiry, never a stale review after an edit.
_REVIEW_SWR_WINDOW = 3600


# ── Public ────────────────────────────────────────────────────────────────────


@router.get(
    "/products/{product_id}",
    response_model=BaseSuccessResponse[list[ReviewOut]],
)
async def list_product_reviews(
    product_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("newest", pattern="^(newest|oldest|highest|lowest|helpful)$"),
    rating: int | None = Query(None, ge=1, le=5, description="Exact star rating"),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    user=Depends(get_current_user_optional),
):
    viewer_user_id = user.id if user else None

    from fastapi.responses import JSONResponse

    # Backward-compatible: data is the reviews array (unchanged shape).
    # Total count for pagination is returned in the X-Total-Count header.
    if viewer_user_id is not None:
        # Per-viewer fields (e.g. "my vote") — never cached.
        reviews, total = await _svc.list_product_reviews(
            db,
            product_id=product_id,
            viewer_user_id=viewer_user_id,
            offset=offset,
            limit=limit,
            sort=sort,
            rating=rating,
        )
        body = ok(
            [ReviewOut.model_validate(r) for r in reviews],
            ResponseCode.REVIEW_LISTED,
            "Reviews listed successfully",
        ).model_dump(mode="json")
        return JSONResponse(content=body, headers={"X-Total-Count": str(total)})

    # All variants share the `{prefix}:{product_id}:` namespace so
    # bust_review_cache can sweep them with one pattern.
    cache_key = f"{PREFIX_REVIEW_LIST}:{product_id}:{offset}:{limit}:{sort}:{rating}"

    # Fresh session: cache_swr may re-run this from a detached background
    # refresh after the request session is gone.
    async def _fetch() -> dict:
        async with AsyncSessionLocal() as s:
            reviews, total = await _svc.list_product_reviews(
                s,
                product_id=product_id,
                viewer_user_id=None,
                offset=offset,
                limit=limit,
                sort=sort,
                rating=rating,
            )
            body = ok(
                [ReviewOut.model_validate(r) for r in reviews],
                ResponseCode.REVIEW_LISTED,
                "Reviews listed successfully",
            ).model_dump(mode="json")
            return {"body": body, "total": total}

    # SWR: an idle product's reviews still serve instantly (stale) and refresh
    # once in the background, instead of a ~1.3s cold fetch for the visitor.
    cached = await cache_swr(
        redis,
        cache_key,
        ttl=TTL_REVIEW_LIST,
        swr_window=_REVIEW_SWR_WINDOW,
        fetch_fn=_fetch,
    )
    response = JSONResponse(
        content=cached["body"], headers={"X-Total-Count": str(cached["total"])}
    )
    add_cache_headers(response, TTL_REVIEW_LIST, private=True)
    return response


@router.get(
    "/products/{product_id}/summary",
    response_model=BaseSuccessResponse[ProductRatingSummary],
)
async def product_rating_summary(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = f"{PREFIX_REVIEW_SUMMARY}:{product_id}"

    async def _fetch() -> dict:
        async with AsyncSessionLocal() as s:
            data = await _svc.rating_summary(s, product_id)
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
        ).model_dump(mode="json")

    from fastapi.responses import JSONResponse

    content = await cache_swr(
        redis,
        cache_key,
        ttl=TTL_REVIEW_SUMMARY,
        swr_window=_REVIEW_SWR_WINDOW,
        fetch_fn=_fetch,
    )
    response = JSONResponse(content=content)
    add_cache_headers(response, TTL_REVIEW_SUMMARY)
    return response


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
    from app.core.redis import get_redis_pool

    redis = get_redis_pool()
    await bust_review_cache(redis, str(data.product_id))
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
    from app.core.redis import get_redis_pool

    redis = get_redis_pool()
    await bust_review_cache(redis, str(result.product_id))
    return ok(result, ResponseCode.REVIEW_UPDATED, "Review updated successfully")


@router.delete(
    "/{review_id}", response_model=BaseSuccessResponse[None], status_code=200
)
async def delete_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    review = await _svc._repo.get_by_id(db, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    product_id = str(review.product_id)
    await _svc.delete_review(db, review_id=review_id, user_id=user.id)
    from app.core.redis import get_redis_pool

    redis = get_redis_pool()
    await bust_review_cache(redis, product_id)
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


@router.get("/admin/reviews", response_model=BaseSuccessResponse[ReviewListResponse])
async def list_all_reviews(
    status: str | None = Query(None, description="pending | approved | rejected"),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=200),
    rating: int | None = Query(None, ge=1, le=5),
    verified: bool | None = None,
    search: str | None = Query(None, max_length=200),
    date_from: datetime | None = Query(None, description="Inclusive (ISO 8601)"),
    date_to: datetime | None = Query(None, description="Exclusive (ISO 8601)"),
    sort_by: str = Query(
        "created_at", pattern="^(created_at|rating|helpful_count|product_name)$"
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    items, total = await _svc.list_all_reviews(
        db,
        status=status,
        page=page,
        page_size=page_size,
        rating=rating,
        verified=verified,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total_pages = math.ceil(total / page_size) if total else 1
    data = ReviewListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
    return ok(data, ResponseCode.REVIEW_ALL_LISTED, "Reviews listed successfully")


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
    from app.core.redis import get_redis_pool

    redis = get_redis_pool()
    await bust_review_cache(redis, str(result.product_id))
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
    review = await _svc._repo.get_by_id(db, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    product_id = str(review.product_id)
    await _svc.admin_delete(db, review_id=review_id)
    from app.core.redis import get_redis_pool

    redis = get_redis_pool()
    await bust_review_cache(redis, product_id)
    return deleted(ResponseCode.REVIEW_DELETED, "Review deleted successfully")
