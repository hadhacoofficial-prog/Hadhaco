from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.models import Review, ReviewImage, ReviewVote


class ReviewRepository:
    # ── Existence / gate checks ───────────────────────────────────────────────

    async def has_delivered_order_item(
        self, db: AsyncSession, *, user_id: uuid.UUID, product_id: uuid.UUID
    ) -> bool:
        """Return True if user has a delivered order containing this product."""
        result = await db.execute(
            text(
                """
                SELECT 1
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.user_id = :user_id
                  AND oi.product_id = :product_id
                  AND o.status = 'delivered'
                  AND o.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"user_id": user_id, "product_id": product_id},
        )
        return result.fetchone() is not None

    async def get_by_id(self, db: AsyncSession, review_id: uuid.UUID) -> Review | None:
        result = await db.execute(
            select(Review).where(Review.id == review_id, Review.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def has_any_review(self, db: AsyncSession, *, order_id: uuid.UUID) -> bool:
        """Return True if any review exists for the given order."""
        result = await db.execute(
            select(Review.id)
            .where(
                Review.order_id == order_id,
                Review.deleted_at.is_(None),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_by_product_user(
        self, db: AsyncSession, *, product_id: uuid.UUID, user_id: uuid.UUID
    ) -> Review | None:
        result = await db.execute(
            select(Review).where(
                Review.product_id == product_id,
                Review.user_id == user_id,
                Review.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create(self, db: AsyncSession, **kwargs: Any) -> Review:
        review = Review(**kwargs)
        db.add(review)
        await db.flush()
        await db.refresh(review)
        return review

    async def update(self, db: AsyncSession, review: Review, data: dict[str, Any]) -> Review:
        for k, v in data.items():
            setattr(review, k, v)
        db.add(review)
        await db.flush()
        await db.refresh(review)
        return review

    async def soft_delete(self, db: AsyncSession, review: Review) -> None:
        from datetime import UTC, datetime

        review.deleted_at = datetime.now(UTC)
        db.add(review)
        await db.flush()

    # ── Listing ───────────────────────────────────────────────────────────────

    async def list_for_product(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        approved_only: bool = True,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Review]:
        q = select(Review).where(
            Review.product_id == product_id,
            Review.deleted_at.is_(None),
        )
        if approved_only:
            q = q.where(Review.is_approved.is_(True))
        q = q.order_by(Review.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    async def list_pending(
        self, db: AsyncSession, *, offset: int = 0, limit: int = 50
    ) -> list[Review]:
        result = await db.execute(
            select(Review)
            .where(Review.is_approved.is_(False), Review.deleted_at.is_(None))
            .order_by(Review.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    # ── Rating summary ────────────────────────────────────────────────────────

    async def rating_summary(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> dict[str, Any] | None:
        row = await db.execute(
            text(
                """
                SELECT
                    product_id,
                    COUNT(*)                                    AS review_count,
                    ROUND(AVG(rating)::NUMERIC, 1)              AS average_rating,
                    COUNT(*) FILTER (WHERE rating = 5)          AS five_star,
                    COUNT(*) FILTER (WHERE rating = 4)          AS four_star,
                    COUNT(*) FILTER (WHERE rating = 3)          AS three_star,
                    COUNT(*) FILTER (WHERE rating = 2)          AS two_star,
                    COUNT(*) FILTER (WHERE rating = 1)          AS one_star
                FROM reviews
                WHERE product_id = :product_id
                  AND is_approved = true
                  AND deleted_at IS NULL
                GROUP BY product_id
                """
            ),
            {"product_id": product_id},
        )
        r = row.fetchone()
        if r is None:
            return None
        return dict(r._mapping)

    # ── Images ────────────────────────────────────────────────────────────────

    async def add_image(
        self,
        db: AsyncSession,
        *,
        review_id: uuid.UUID,
        url: str,
        r2_key: str | None,
        sort_order: int = 0,
    ) -> ReviewImage:
        img = ReviewImage(review_id=review_id, url=url, r2_key=r2_key, sort_order=sort_order)
        db.add(img)
        await db.flush()
        return img

    async def delete_images(self, db: AsyncSession, review_id: uuid.UUID) -> None:
        await db.execute(delete(ReviewImage).where(ReviewImage.review_id == review_id))

    # ── Votes ─────────────────────────────────────────────────────────────────

    async def get_vote(
        self, db: AsyncSession, *, review_id: uuid.UUID, user_id: uuid.UUID
    ) -> ReviewVote | None:
        result = await db.execute(
            select(ReviewVote).where(
                ReviewVote.review_id == review_id, ReviewVote.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert_vote(
        self, db: AsyncSession, *, review_id: uuid.UUID, user_id: uuid.UUID, is_helpful: bool
    ) -> ReviewVote:
        vote = await self.get_vote(db, review_id=review_id, user_id=user_id)
        if vote:
            vote.is_helpful = is_helpful
        else:
            vote = ReviewVote(review_id=review_id, user_id=user_id, is_helpful=is_helpful)
            db.add(vote)
        await db.flush()
        await self._sync_helpful_count(db, review_id)
        return vote

    async def _sync_helpful_count(self, db: AsyncSession, review_id: uuid.UUID) -> None:
        result = await db.execute(
            select(func.count()).where(
                ReviewVote.review_id == review_id, ReviewVote.is_helpful.is_(True)
            )
        )
        count = result.scalar() or 0
        await db.execute(update(Review).where(Review.id == review_id).values(helpful_count=count))
