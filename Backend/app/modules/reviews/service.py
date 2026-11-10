from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import ReviewRequestEvent, event_bus
from app.core.exceptions import HTTP_422
from app.modules.media.universal_service import UniversalImageService
from app.modules.reviews.models import Review, ReviewVote
from app.modules.reviews.repository import ReviewRepository
from app.modules.reviews.schemas import AdminReviewOut, ReviewCreate, ReviewUpdate

# Shown to a customer an admin blocked from reviewing a product (submit 403
# and the product page), so both read the same.
BLOCKED_MESSAGE = (
    "Our team removed one of your reviews of this product, so you can't post "
    "new reviews for it."
)


class ReviewService:
    def __init__(self) -> None:
        self._repo = ReviewRepository()
        self._images = UniversalImageService()

    # ── Submit ────────────────────────────────────────────────────────────────

    async def submit_review(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        customer_name: str | None,
        data: ReviewCreate,
        images: list[UploadFile] | None = None,
    ) -> Review:
        # Held to commit: concurrent submits by this customer for this product
        # run one at a time, so the cap below can't be raced past.
        await self._repo.lock_product_user(
            db, product_id=data.product_id, user_id=user_id
        )
        if await self._repo.is_blocked(db, product_id=data.product_id, user_id=user_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, BLOCKED_MESSAGE)
        max_reviews = settings.REVIEW_MAX_PER_PRODUCT
        live = await self._repo.count_live_by_product_user(
            db, product_id=data.product_id, user_id=user_id
        )
        if live >= max_reviews:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"You can have up to {max_reviews} reviews of this product. "
                "Delete one to post another.",
            )

        is_verified = await self._repo.has_delivered_order_item(
            db, user_id=user_id, product_id=data.product_id
        )

        review = await self._repo.create(
            db,
            product_id=data.product_id,
            user_id=user_id,
            order_id=data.order_id,
            customer_name=customer_name,
            rating=data.rating,
            title=data.title,
            body=data.body,
            is_verified_purchase=is_verified,
            # Published immediately; admins can only remove afterwards.
            is_approved=True,
            is_rejected=False,
            approved_at=datetime.now(UTC),
        )

        if images:
            from app.modules.media.universal_service import UniversalImageServiceError

            try:
                await self._attach_images(
                    db,
                    review_id=review.id,
                    images=images,
                )
            except UniversalImageServiceError as exc:
                raise HTTPException(HTTP_422, str(exc)) from exc

        await self._sync_product_rating(db, review.product_id)
        await db.commit()
        await db.refresh(review)
        return review

    # ── Edit ──────────────────────────────────────────────────────────────────

    async def edit_review(
        self,
        db: AsyncSession,
        *,
        review_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ReviewUpdate,
    ) -> tuple[Review, bool]:
        """Edit in place; the review stays published. Returns
        (review, rating_changed): rating_changed is True when the product's
        average_rating / review_count moved, so callers know to bust product
        caches.

        A legacy review still pending from the old moderation flow is
        published by its first edit; a legacy rejected one stays hidden.
        """
        review = await self._get_owned(db, review_id=review_id, user_id=user_id)
        updates = data.model_dump(exclude_unset=True)
        publishes = bool(updates) and not review.is_approved and not review.is_rejected
        rating_changed = publishes or ("rating" in updates and review.is_approved)
        if publishes:
            updates["is_approved"] = True
            updates["approved_at"] = datetime.now(UTC)
        if updates:
            review = await self._repo.update(db, review, updates)
        if rating_changed:
            await self._sync_product_rating(db, review.product_id)
        await db.commit()
        await db.refresh(review)
        return review, rating_changed

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_review(
        self, db: AsyncSession, *, review_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Soft-delete. Returns True when the review was approved, i.e. the
        product's average_rating / review_count changed."""
        review = await self._get_owned(db, review_id=review_id, user_id=user_id)
        rating_changed = review.is_approved
        await self._repo.soft_delete(db, review)
        if rating_changed:
            await self._sync_product_rating(db, review.product_id)
        await db.commit()
        return rating_changed

    # ── Listing ───────────────────────────────────────────────────────────────

    async def list_product_reviews(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        viewer_user_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
        sort: str = "newest",
        rating: int | None = None,
    ) -> tuple[list[Review], int]:
        return await self._repo.list_for_product(
            db,
            product_id=product_id,
            viewer_user_id=viewer_user_id,
            offset=offset,
            limit=limit,
            sort=sort,
            rating=rating,
        )

    async def rating_summary(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> dict[str, Any] | None:
        return await self._repo.rating_summary(db, product_id)

    async def my_review_status(
        self, db: AsyncSession, *, product_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, Any]:
        """Product-page review state for the viewer. Read-only: mirrors the
        submit rules (block, per-product cap) so the page can explain them
        instead of failing on submit; review_id/rating are the newest review."""
        review = await self._repo.get_latest_by_product_user(
            db, product_id=product_id, user_id=user_id
        )
        has_purchased = await self._repo.has_delivered_order_item(
            db, user_id=user_id, product_id=product_id
        )
        is_blocked = await self._repo.is_blocked(
            db, product_id=product_id, user_id=user_id
        )
        live = await self._repo.count_live_by_product_user(
            db, product_id=product_id, user_id=user_id
        )
        return {
            "product_id": product_id,
            "has_purchased_delivered": has_purchased,
            "has_reviewed": review is not None,
            "review_id": review.id if review else None,
            "rating": review.rating if review else None,
            "is_blocked": is_blocked,
            "blocked_message": BLOCKED_MESSAGE if is_blocked else None,
            "reviews_remaining": (
                0 if is_blocked else max(0, settings.REVIEW_MAX_PER_PRODUCT - live)
            ),
        }

    # ── Votes ─────────────────────────────────────────────────────────────────

    async def vote(
        self,
        db: AsyncSession,
        *,
        review_id: uuid.UUID,
        user_id: uuid.UUID,
        is_helpful: bool,
    ) -> ReviewVote:
        review = await self._repo.get_by_id(db, review_id)
        if not review or not review.is_approved:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
        if review.user_id == user_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Cannot vote on your own review"
            )
        vote = await self._repo.upsert_vote(
            db, review_id=review_id, user_id=user_id, is_helpful=is_helpful
        )
        await db.commit()
        return vote

    # ── Admin ─────────────────────────────────────────────────────────────────

    async def _sync_product_rating(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> None:
        """Recalculate and cache average_rating + review_count on the product
        (newest published review per customer — see repository.rating_summary)."""
        from sqlalchemy import text as sql

        # Serialize concurrent syncs for this product (e.g. two simultaneous
        # submits): without the lock each aggregate misses the other's
        # uncommitted review and the last UPDATE leaves a stale count. The
        # lock waits for the other transaction, then the aggregate below (a
        # new READ COMMITTED snapshot) sees its row. NO KEY UPDATE, not
        # UPDATE: a review insert already holds FOR KEY SHARE on the product
        # via the FK, which FOR UPDATE would conflict with (deadlock).
        await db.execute(
            sql("SELECT 1 FROM products WHERE id = :pid FOR NO KEY UPDATE"),
            {"pid": product_id},
        )
        summary = await self._repo.rating_summary(db, product_id)
        await db.execute(
            sql("""
                UPDATE products
                SET average_rating = :avg, review_count = :cnt
                WHERE id = :pid
            """),
            {
                "avg": summary["average_rating"] if summary else None,
                "cnt": int(summary["review_count"]) if summary else 0,
                "pid": product_id,
            },
        )

    async def admin_action(
        self,
        db: AsyncSession,
        *,
        review_id: uuid.UUID,
        action: str,
        admin_identifier: str | None = None,
    ) -> Review:
        review = await self._repo.get_by_id(db, review_id)
        if not review:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
        if action == "approve":
            review = await self._repo.update(
                db,
                review,
                {
                    "is_approved": True,
                    "is_rejected": False,
                    "is_flagged": False,
                    "approved_at": datetime.now(UTC),
                    "approved_by": admin_identifier,
                },
            )
        elif action == "reject":
            review = await self._repo.update(
                db,
                review,
                {
                    "is_approved": False,
                    "is_rejected": True,
                    "is_flagged": False,
                },
            )
        elif action == "flag":
            review = await self._repo.update(db, review, {"is_flagged": True})
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Unknown action: {action}"
            )
        product_id = review.product_id
        await self._sync_product_rating(db, product_id)
        await db.commit()
        await db.refresh(review)
        return review

    async def admin_delete(self, db: AsyncSession, *, review_id: uuid.UUID) -> None:
        """Remove a review and block its author from reviewing the product
        again. The row is kept (soft-deleted + admin_removed_at) as the block
        marker; its photos are deleted. Undo with admin_unblock."""
        review = await self._repo.get_by_id(db, review_id)
        if not review:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
        product_id = review.product_id
        now = datetime.now(UTC)
        await self._delete_images(db, review)
        await self._repo.update(
            db,
            review,
            {
                "deleted_at": now,
                "admin_removed_at": now,
                "is_approved": False,
                "is_flagged": False,
            },
        )
        await self._sync_product_rating(db, product_id)
        await db.commit()

    async def admin_unblock(self, db: AsyncSession, *, review_id: uuid.UUID) -> None:
        """Lift the block left by admin_delete so the customer may post new
        reviews of that product. Every review an admin removed from this
        customer on the product is purged (not restored) — any one of them
        would keep the block."""
        review = await self._repo.get_removed_by_id(db, review_id)
        if not review:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Removed review not found")
        await self._repo.delete_admin_removed(
            db, product_id=review.product_id, user_id=review.user_id
        )
        await db.commit()

    async def list_pending(
        self, db: AsyncSession, *, offset: int = 0, limit: int = 50
    ) -> list[Review]:
        return await self._repo.list_pending(db, offset=offset, limit=limit)

    async def list_all_reviews(
        self,
        db: AsyncSession,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 15,
        rating: int | None = None,
        verified: bool | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> tuple[list[AdminReviewOut], int]:
        rows, total = await self._repo.list_all_paginated(
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
        result: list[AdminReviewOut] = []
        for review, product_name in rows:
            out = AdminReviewOut.model_validate(review)
            out.product_name = product_name
            result.append(out)
        return result, total

    # ── ReviewRequest event listener ──────────────────────────────────────────

    @staticmethod
    def register_review_request_listener() -> None:
        async def _on_review_request(event: ReviewRequestEvent) -> None:
            pass  # notification module will pick this up

        event_bus.on(ReviewRequestEvent, _on_review_request)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_owned(
        self, db: AsyncSession, *, review_id: uuid.UUID, user_id: uuid.UUID
    ) -> Review:
        review = await self._repo.get_by_id(db, review_id)
        if not review:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
        if review.user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your review")
        return review

    async def _delete_images(self, db: AsyncSession, review: Review) -> None:
        """Remove a review's photos (storage + image rows) before the review
        row is hard-deleted; images reference it polymorphically, without FK."""
        for image in list(review.images):
            await self._images.delete(db, image=image)

    async def _attach_images(
        self,
        db: AsyncSession,
        *,
        review_id: uuid.UUID,
        images: list[UploadFile],
    ) -> None:
        for i, upload in enumerate(images[:5]):  # max 5 images
            content = await upload.read()
            image = await self._images.upload(
                db,
                preset_id="review_photo",
                file_bytes=content,
                filename=upload.filename or "review.jpg",
                content_type=upload.content_type or "image/jpeg",
                owner_type="review",
                owner_id=review_id,
                uploaded_by=None,
            )
            await self._images.reorder(db, [(image.id, i)])
