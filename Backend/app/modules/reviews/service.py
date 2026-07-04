from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import ReviewRequestEvent, event_bus
from app.modules.media.service import MediaService
from app.modules.reviews.models import Review, ReviewVote
from app.modules.reviews.repository import ReviewRepository
from app.modules.reviews.schemas import AdminReviewOut, ReviewCreate, ReviewUpdate


class ReviewService:
    def __init__(self) -> None:
        self._repo = ReviewRepository()
        self._media = MediaService()

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
        existing = await self._repo.get_by_product_user(
            db, product_id=data.product_id, user_id=user_id
        )
        if existing and existing.deleted_at is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "You have already reviewed this product"
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
            is_approved=False,
            is_rejected=False,
        )

        if images:
            await self._attach_images(db, review_id=review.id, images=images)

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
    ) -> Review:
        review = await self._get_owned(db, review_id=review_id, user_id=user_id)
        updates = data.model_dump(exclude_unset=True)
        if updates:
            updates["is_approved"] = False
            updates["is_rejected"] = False
            review = await self._repo.update(db, review, updates)
        await db.commit()
        await db.refresh(review)
        return review

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_review(
        self, db: AsyncSession, *, review_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        review = await self._get_owned(db, review_id=review_id, user_id=user_id)
        await self._repo.soft_delete(db, review)
        await db.commit()

    # ── Listing ───────────────────────────────────────────────────────────────

    async def list_product_reviews(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        viewer_user_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Review]:
        return await self._repo.list_for_product(
            db,
            product_id=product_id,
            viewer_user_id=viewer_user_id,
            offset=offset,
            limit=limit,
        )

    async def rating_summary(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> dict[str, Any] | None:
        return await self._repo.rating_summary(db, product_id)

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
        """Recalculate and cache average_rating + review_count on the product."""
        from sqlalchemy import text as sql

        row = (
            await db.execute(
                sql("""
                    SELECT
                        COUNT(*) AS review_count,
                        ROUND(AVG(rating)::NUMERIC, 1) AS average_rating
                    FROM reviews
                    WHERE product_id = :pid
                      AND is_approved = true
                      AND deleted_at IS NULL
                """),
                {"pid": product_id},
            )
        ).fetchone()
        if row is None:
            return
        mapping = dict(row._mapping)
        await db.execute(
            sql("""
                UPDATE products
                SET average_rating = :avg, review_count = :cnt
                WHERE id = :pid
            """),
            {
                "avg": mapping.get("average_rating"),
                "cnt": int(mapping.get("review_count") or 0),
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
        review = await self._repo.get_by_id(db, review_id)
        if not review:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
        product_id = review.product_id
        await self._repo.hard_delete(db, review_id)
        await self._sync_product_rating(db, product_id)
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
        offset: int = 0,
        limit: int = 50,
    ) -> list[AdminReviewOut]:
        rows = await self._repo.list_all(db, status=status, offset=offset, limit=limit)
        result: list[AdminReviewOut] = []
        for review, product_name in rows:
            out = AdminReviewOut.model_validate(review)
            out.product_name = product_name
            result.append(out)
        return result

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

    async def _attach_images(
        self,
        db: AsyncSession,
        *,
        review_id: uuid.UUID,
        images: list[UploadFile],
    ) -> None:
        for i, upload in enumerate(images[:5]):  # max 5 images
            content = await upload.read()
            key = f"reviews/{review_id}/{i}_{upload.filename}"
            url = self._media.upload_bytes(
                content, key=key, content_type=upload.content_type or "image/jpeg"
            )
            await self._repo.add_image(
                db, review_id=review_id, url=url, r2_key=key, sort_order=i
            )
