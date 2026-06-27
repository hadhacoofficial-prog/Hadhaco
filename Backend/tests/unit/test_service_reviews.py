"""ReviewService mock-based tests."""

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.modules.reviews.repository import ReviewRepository
from app.modules.reviews.schemas import ReviewCreate, ReviewUpdate


class TestReviewServiceSubmit:
    def setup_method(self):
        from app.modules.reviews.service import ReviewService

        self.svc = ReviewService()

    async def test_submit_raises_409_for_duplicate_review(self):
        db = AsyncMock()
        existing_review = MagicMock()
        existing_review.deleted_at = None
        with patch.object(
            ReviewRepository,
            "get_by_product_user",
            AsyncMock(return_value=existing_review),
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.submit_review(
                    db,
                    user_id=uuid.uuid4(),
                    customer_name=None,
                    data=ReviewCreate(
                        product_id=uuid.uuid4(),
                        rating=5,
                        title="Great",
                        body="Loved it",
                    ),
                )
        assert exc.value.status_code == 409

    async def test_submit_succeeds_for_new_review(self):
        db = AsyncMock()
        mock_review = MagicMock()
        mock_review.id = uuid.uuid4()
        with (
            patch.object(
                ReviewRepository, "get_by_product_user", AsyncMock(return_value=None)
            ),
            patch.object(
                ReviewRepository,
                "has_delivered_order_item",
                AsyncMock(return_value=True),
            ),
            patch.object(
                ReviewRepository, "create", AsyncMock(return_value=mock_review)
            ),
        ):
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            result = await self.svc.submit_review(
                db,
                user_id=uuid.uuid4(),
                customer_name=None,
                data=ReviewCreate(
                    product_id=uuid.uuid4(), rating=5, title="Great", body="Loved it"
                ),
            )
        assert result is mock_review

    async def test_submit_succeeds_when_prior_review_was_deleted(self):
        db = AsyncMock()
        from datetime import datetime

        existing_review = MagicMock()
        existing_review.deleted_at = datetime.now(UTC)  # soft-deleted
        mock_review = MagicMock()
        with (
            patch.object(
                ReviewRepository,
                "get_by_product_user",
                AsyncMock(return_value=existing_review),
            ),
            patch.object(
                ReviewRepository,
                "has_delivered_order_item",
                AsyncMock(return_value=False),
            ),
            patch.object(
                ReviewRepository, "create", AsyncMock(return_value=mock_review)
            ),
        ):
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            result = await self.svc.submit_review(
                db,
                user_id=uuid.uuid4(),
                customer_name=None,
                data=ReviewCreate(
                    product_id=uuid.uuid4(), rating=3, title="OK", body="Meh"
                ),
            )
        assert result is mock_review


class TestReviewServiceVote:
    def setup_method(self):
        from app.modules.reviews.service import ReviewService

        self.svc = ReviewService()

    async def test_vote_raises_404_when_review_not_found(self):
        db = AsyncMock()
        with patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.vote(
                    db, review_id=uuid.uuid4(), user_id=uuid.uuid4(), is_helpful=True
                )
        assert exc.value.status_code == 404

    async def test_vote_raises_404_when_review_not_approved(self):
        db = AsyncMock()
        mock_review = MagicMock()
        mock_review.is_approved = False
        with patch.object(
            ReviewRepository, "get_by_id", AsyncMock(return_value=mock_review)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.vote(
                    db, review_id=uuid.uuid4(), user_id=uuid.uuid4(), is_helpful=True
                )
        assert exc.value.status_code == 404

    async def test_vote_raises_400_when_voting_own_review(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.is_approved = True
        mock_review.user_id = user_id
        with patch.object(
            ReviewRepository, "get_by_id", AsyncMock(return_value=mock_review)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.vote(
                    db, review_id=uuid.uuid4(), user_id=user_id, is_helpful=True
                )
        assert exc.value.status_code == 400

    async def test_vote_success(self):
        db = AsyncMock()
        review_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.is_approved = True
        mock_review.user_id = uuid.uuid4()  # different from voter
        mock_vote = MagicMock()
        with (
            patch.object(
                ReviewRepository, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(
                ReviewRepository, "upsert_vote", AsyncMock(return_value=mock_vote)
            ),
        ):
            db.commit = AsyncMock()
            result = await self.svc.vote(
                db, review_id=review_id, user_id=user_id, is_helpful=True
            )
        assert result is mock_vote


class TestReviewServiceAdmin:
    def setup_method(self):
        from app.modules.reviews.service import ReviewService

        self.svc = ReviewService()

    async def test_admin_action_raises_404_when_not_found(self):
        db = AsyncMock()
        with patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.admin_action(
                    db, review_id=uuid.uuid4(), action="approve"
                )
        assert exc.value.status_code == 404

    async def test_admin_action_approve(self):
        db = AsyncMock()
        mock_review = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(
                ReviewRepository, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(
                ReviewRepository, "update", AsyncMock(return_value=mock_updated)
            ),
            patch.object(self.svc, "_sync_product_rating", AsyncMock()),
        ):
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            result = await self.svc.admin_action(
                db, review_id=uuid.uuid4(), action="approve"
            )
        assert result is mock_updated

    async def test_admin_action_reject_calls_update(self):
        db = AsyncMock()
        mock_review = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(
                ReviewRepository, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(
                ReviewRepository, "update", AsyncMock(return_value=mock_updated)
            ),
            patch.object(self.svc, "_sync_product_rating", AsyncMock()),
        ):
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            await self.svc.admin_action(db, review_id=uuid.uuid4(), action="reject")

    async def test_admin_action_invalid_action_raises_400(self):
        db = AsyncMock()
        mock_review = MagicMock()
        with patch.object(
            ReviewRepository, "get_by_id", AsyncMock(return_value=mock_review)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.admin_action(db, review_id=uuid.uuid4(), action="nuke")
        assert exc.value.status_code == 400

    async def test_list_pending_returns_empty(self):
        db = AsyncMock()
        with patch.object(ReviewRepository, "list_pending", AsyncMock(return_value=[])):
            result = await self.svc.list_pending(db)
        assert result == []


class TestReviewServiceOwned:
    def setup_method(self):
        from app.modules.reviews.service import ReviewService

        self.svc = ReviewService()

    async def test_edit_raises_404_when_not_found(self):
        db = AsyncMock()
        with patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.edit_review(
                    db,
                    review_id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                    data=ReviewUpdate(rating=4),
                )
        assert exc.value.status_code == 404

    async def test_edit_raises_403_when_not_owner(self):
        db = AsyncMock()
        owner_id = uuid.uuid4()
        caller_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.user_id = owner_id
        with patch.object(
            ReviewRepository, "get_by_id", AsyncMock(return_value=mock_review)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.edit_review(
                    db,
                    review_id=uuid.uuid4(),
                    user_id=caller_id,
                    data=ReviewUpdate(rating=4),
                )
        assert exc.value.status_code == 403

    async def test_delete_raises_403_when_not_owner(self):
        db = AsyncMock()
        owner_id = uuid.uuid4()
        caller_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.user_id = owner_id
        with patch.object(
            ReviewRepository, "get_by_id", AsyncMock(return_value=mock_review)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.delete_review(
                    db, review_id=uuid.uuid4(), user_id=caller_id
                )
        assert exc.value.status_code == 403

    async def test_list_product_reviews_returns_list(self):
        db = AsyncMock()
        with patch.object(
            ReviewRepository, "list_for_product", AsyncMock(return_value=[])
        ):
            result = await self.svc.list_product_reviews(db, product_id=uuid.uuid4())
        assert result == []

    async def test_rating_summary_delegates_to_repo(self):
        db = AsyncMock()
        mock_summary = {"avg": 4.2, "count": 10}
        with patch.object(
            ReviewRepository, "rating_summary", AsyncMock(return_value=mock_summary)
        ):
            result = await self.svc.rating_summary(db, uuid.uuid4())
        assert result == mock_summary
