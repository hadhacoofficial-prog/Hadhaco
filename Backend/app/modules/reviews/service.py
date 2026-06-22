from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import ReviewRequestEvent, event_bus
from app.modules.media.service import MediaService
from app.modules.reviews.models import Review, ReviewVote
from app.modules.reviews.repository import ReviewRepository
from app.modules.reviews.schemas import ReviewCreate, ReviewUpdate


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
        data: ReviewCreate,
        images: list[UploadFile] | None = None,
    ) -> Review:
        # one review per product per user
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
            rating=data.rating,
            title=data.title,
            body=data.body,
            is_verified_purchase=is_verified,
            is_approved=False,  # requires admin approval
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
            # re-queue for approval on edit
            updates["is_approved"] = False
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
        offset: int = 0,
        limit: int = 20,
    ) -> list[Review]:
        return await self._repo.list_for_product(
            db, product_id=product_id, approved_only=True, offset=offset, limit=limit
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

    async def admin_action(
        self, db: AsyncSession, *, review_id: uuid.UUID, action: str
    ) -> Review:
        review = await self._repo.get_by_id(db, review_id)
        if not review:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
        if action == "approve":
            review = await self._repo.update(
                db, review, {"is_approved": True, "is_flagged": False}
            )
        elif action == "reject":
            await self._repo.soft_delete(db, review)
        elif action == "flag":
            review = await self._repo.update(db, review, {"is_flagged": True})
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Unknown action: {action}"
            )
        await db.commit()
        await db.refresh(review)
        return review

    async def list_pending(
        self, db: AsyncSession, *, offset: int = 0, limit: int = 50
    ) -> list[Review]:
        return await self._repo.list_pending(db, offset=offset, limit=limit)

    # ── ReviewRequest event listener ──────────────────────────────────────────

    @staticmethod
    def register_review_request_listener() -> None:
        """Subscribe to ReviewRequestEvent (fired after order delivery)."""

        # ReviewRequestEvent is informational — could trigger email/push.
        # Implementation here is a no-op hook; notification module handles delivery.
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
            url = await self._media.upload_bytes(
                content, key=key, content_type=upload.content_type or "image/jpeg"
            )
            await self._repo.add_image(
                db, review_id=review_id, url=url, r2_key=key, sort_order=i
            )
