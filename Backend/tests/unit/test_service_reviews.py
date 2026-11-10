"""ReviewService mock-based tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.modules.reviews.repository import ReviewRepository
from app.modules.reviews.schemas import ReviewCreate, ReviewUpdate


class TestReviewServiceSubmit:
    def setup_method(self):
        from app.modules.reviews.service import ReviewService

        self.svc = ReviewService()

    async def _submit(self, *, blocked: bool = False, live: int = 0, calls=None):
        """Submit with every repo call mocked; returns (result|exc, mocks)."""
        calls = calls if calls is not None else []
        db = AsyncMock()
        mock_review = MagicMock()
        mocks = {
            "lock": AsyncMock(side_effect=lambda *a, **k: calls.append("lock")),
            "blocked": AsyncMock(
                side_effect=lambda *a, **k: calls.append("blocked") or blocked
            ),
            "count": AsyncMock(
                side_effect=lambda *a, **k: calls.append("count") or live
            ),
            "create": AsyncMock(
                side_effect=lambda *a, **k: calls.append("create") or mock_review
            ),
            "sync": AsyncMock(),
        }
        with (
            patch.object(ReviewRepository, "lock_product_user", mocks["lock"]),
            patch.object(ReviewRepository, "is_blocked", mocks["blocked"]),
            patch.object(
                ReviewRepository, "count_live_by_product_user", mocks["count"]
            ),
            patch.object(
                ReviewRepository,
                "has_delivered_order_item",
                AsyncMock(return_value=True),
            ),
            patch.object(ReviewRepository, "create", mocks["create"]),
            patch.object(self.svc, "_sync_product_rating", mocks["sync"]),
        ):
            try:
                result = await self.svc.submit_review(
                    db,
                    user_id=uuid.uuid4(),
                    customer_name=None,
                    data=ReviewCreate(
                        product_id=uuid.uuid4(), rating=5, title="Great", body="Loved"
                    ),
                )
            except HTTPException as exc:
                result = exc
        return db, mock_review, result, mocks

    async def test_submit_publishes_immediately(self):
        db, mock_review, result, mocks = await self._submit()
        assert result is mock_review
        kwargs = mocks["create"].await_args.kwargs
        assert kwargs["is_approved"] is True
        assert kwargs["is_rejected"] is False
        assert kwargs["approved_at"] is not None
        mocks["sync"].assert_awaited_once_with(db, mock_review.product_id)
        db.commit.assert_awaited_once()

    async def test_submit_locks_before_checking_block_and_cap(self):
        calls: list[str] = []
        await self._submit(calls=calls)
        assert calls == ["lock", "blocked", "count", "create"]

    async def test_submit_allows_another_review_of_same_product(self):
        _, mock_review, result, mocks = await self._submit(live=4)
        assert result is mock_review
        mocks["create"].assert_awaited_once()

    async def test_submit_409_at_per_product_cap(self):
        from app.core.config import settings

        db, _, result, mocks = await self._submit(live=settings.REVIEW_MAX_PER_PRODUCT)
        assert isinstance(result, HTTPException)
        assert result.status_code == 409
        assert str(settings.REVIEW_MAX_PER_PRODUCT) in result.detail
        mocks["create"].assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_submit_403_with_message_when_blocked(self):
        from app.modules.reviews.service import BLOCKED_MESSAGE

        db, _, result, mocks = await self._submit(blocked=True)
        assert isinstance(result, HTTPException)
        assert result.status_code == 403
        assert result.detail == BLOCKED_MESSAGE
        mocks["count"].assert_not_awaited()
        mocks["create"].assert_not_awaited()
        db.commit.assert_not_awaited()


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

    def _owned_review(self, user_id: uuid.UUID, *, approved: bool) -> MagicMock:
        review = MagicMock()
        review.user_id = user_id
        review.product_id = uuid.uuid4()
        review.is_approved = approved
        return review

    async def _edit(self, review: MagicMock, data: ReviewUpdate):
        db = AsyncMock()
        update = AsyncMock(return_value=review)
        sync = AsyncMock()
        with (
            patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=review)),
            patch.object(ReviewRepository, "update", update),
            patch.object(self.svc, "_sync_product_rating", sync),
        ):
            result = await self.svc.edit_review(
                db, review_id=uuid.uuid4(), user_id=review.user_id, data=data
            )
        return db, update, sync, result

    async def test_edit_rating_keeps_review_published_and_resyncs(self):
        review = self._owned_review(uuid.uuid4(), approved=True)
        review.is_rejected = False
        db, update, sync, (result, rating_changed) = await self._edit(
            review, ReviewUpdate(rating=2)
        )
        assert result is review
        assert rating_changed is True
        assert update.await_args.args[2] == {"rating": 2}
        sync.assert_awaited_once_with(db, review.product_id)
        db.commit.assert_awaited_once()

    async def test_edit_text_only_skips_resync(self):
        review = self._owned_review(uuid.uuid4(), approved=True)
        review.is_rejected = False
        _, update, sync, (_, rating_changed) = await self._edit(
            review, ReviewUpdate(body="Updated text")
        )
        assert rating_changed is False
        assert update.await_args.args[2] == {"body": "Updated text"}
        sync.assert_not_awaited()

    async def test_edit_publishes_legacy_pending_review(self):
        review = self._owned_review(uuid.uuid4(), approved=False)
        review.is_rejected = False
        db, update, sync, (_, rating_changed) = await self._edit(
            review, ReviewUpdate(body="Updated text")
        )
        updates = update.await_args.args[2]
        assert updates["is_approved"] is True
        assert updates["approved_at"] is not None
        assert rating_changed is True
        sync.assert_awaited_once_with(db, review.product_id)

    async def test_edit_keeps_legacy_rejected_review_hidden(self):
        review = self._owned_review(uuid.uuid4(), approved=False)
        review.is_rejected = True
        _, update, sync, (_, rating_changed) = await self._edit(
            review, ReviewUpdate(rating=5)
        )
        assert "is_approved" not in update.await_args.args[2]
        assert rating_changed is False
        sync.assert_not_awaited()

    async def test_edit_without_changes_skips_resync(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        review = self._owned_review(user_id, approved=True)
        update = AsyncMock()
        sync = AsyncMock()
        with (
            patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=review)),
            patch.object(ReviewRepository, "update", update),
            patch.object(self.svc, "_sync_product_rating", sync),
        ):
            _, rating_changed = await self.svc.edit_review(
                db, review_id=uuid.uuid4(), user_id=user_id, data=ReviewUpdate()
            )
        assert rating_changed is False
        update.assert_not_awaited()
        sync.assert_not_awaited()

    async def test_delete_approved_review_resyncs_product_rating(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        review = self._owned_review(user_id, approved=True)
        soft_delete = AsyncMock()
        sync = AsyncMock()
        with (
            patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=review)),
            patch.object(ReviewRepository, "soft_delete", soft_delete),
            patch.object(self.svc, "_sync_product_rating", sync),
        ):
            rating_changed = await self.svc.delete_review(
                db, review_id=uuid.uuid4(), user_id=user_id
            )
        assert rating_changed is True
        soft_delete.assert_awaited_once_with(db, review)
        sync.assert_awaited_once_with(db, review.product_id)
        db.commit.assert_awaited_once()

    async def test_delete_pending_review_skips_resync(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        review = self._owned_review(user_id, approved=False)
        sync = AsyncMock()
        with (
            patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=review)),
            patch.object(ReviewRepository, "soft_delete", AsyncMock()),
            patch.object(self.svc, "_sync_product_rating", sync),
        ):
            rating_changed = await self.svc.delete_review(
                db, review_id=uuid.uuid4(), user_id=user_id
            )
        assert rating_changed is False
        sync.assert_not_awaited()
        db.commit.assert_awaited_once()

    async def test_admin_delete_removes_images_and_blocks_author(self):
        db = AsyncMock()
        review = MagicMock()
        review.id = uuid.uuid4()
        review.product_id = uuid.uuid4()
        image = MagicMock()
        review.images = [image]
        calls: list[str] = []
        delete_image = AsyncMock(side_effect=lambda *a, **k: calls.append("image"))
        update = AsyncMock(side_effect=lambda *a, **k: calls.append("update"))
        hard_delete = AsyncMock()
        sync = AsyncMock()
        with (
            patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=review)),
            patch.object(ReviewRepository, "update", update),
            patch.object(ReviewRepository, "hard_delete", hard_delete),
            patch.object(self.svc._images, "delete", delete_image),
            patch.object(self.svc, "_sync_product_rating", sync),
        ):
            await self.svc.admin_delete(db, review_id=review.id)
        delete_image.assert_awaited_once_with(db, image=image)
        # Row kept as the block marker, not hard-deleted.
        hard_delete.assert_not_awaited()
        changes = update.await_args.args[2]
        assert changes["deleted_at"] is not None
        assert changes["admin_removed_at"] == changes["deleted_at"]
        assert changes["is_approved"] is False
        assert "is_rejected" not in changes
        assert calls == ["image", "update"]
        sync.assert_awaited_once_with(db, review.product_id)
        db.commit.assert_awaited_once()

    async def test_admin_unblock_purges_all_removed_reviews_of_customer(self):
        db = AsyncMock()
        removed = MagicMock()
        removed.id = uuid.uuid4()
        delete_removed = AsyncMock()
        with (
            patch.object(
                ReviewRepository, "get_removed_by_id", AsyncMock(return_value=removed)
            ),
            patch.object(ReviewRepository, "delete_admin_removed", delete_removed),
        ):
            await self.svc.admin_unblock(db, review_id=removed.id)
        delete_removed.assert_awaited_once_with(
            db, product_id=removed.product_id, user_id=removed.user_id
        )
        db.commit.assert_awaited_once()

    async def test_admin_unblock_404_when_not_removed(self):
        db = AsyncMock()
        with patch.object(
            ReviewRepository, "get_removed_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.admin_unblock(db, review_id=uuid.uuid4())
        assert exc.value.status_code == 404
        db.commit.assert_not_awaited()

    async def _my_status(self, *, latest, blocked: bool, live: int):
        with (
            patch.object(
                ReviewRepository,
                "get_latest_by_product_user",
                AsyncMock(return_value=latest),
            ),
            patch.object(
                ReviewRepository,
                "has_delivered_order_item",
                AsyncMock(return_value=True),
            ),
            patch.object(
                ReviewRepository, "is_blocked", AsyncMock(return_value=blocked)
            ),
            patch.object(
                ReviewRepository,
                "count_live_by_product_user",
                AsyncMock(return_value=live),
            ),
        ):
            return await self.svc.my_review_status(
                AsyncMock(), product_id=uuid.uuid4(), user_id=uuid.uuid4()
            )

    async def test_my_status_blocked_explains_and_allows_none(self):
        from app.modules.reviews.service import BLOCKED_MESSAGE

        status = await self._my_status(latest=None, blocked=True, live=0)
        assert status["is_blocked"] is True
        assert status["blocked_message"] == BLOCKED_MESSAGE
        assert status["reviews_remaining"] == 0

    async def test_my_status_reports_remaining_and_newest_review(self):
        from app.core.config import settings

        latest = MagicMock(rating=4)
        status = await self._my_status(latest=latest, blocked=False, live=2)
        assert status["has_reviewed"] is True
        assert status["review_id"] == latest.id
        assert status["rating"] == 4
        assert status["is_blocked"] is False
        assert status["blocked_message"] is None
        assert status["reviews_remaining"] == settings.REVIEW_MAX_PER_PRODUCT - 2

    async def test_my_status_zero_remaining_at_cap(self):
        from app.core.config import settings

        status = await self._my_status(
            latest=MagicMock(), blocked=False, live=settings.REVIEW_MAX_PER_PRODUCT
        )
        assert status["reviews_remaining"] == 0

    async def test_sync_product_rating_without_reviews_resets_product(self):
        db = AsyncMock()
        pid = uuid.uuid4()
        with patch.object(
            ReviewRepository, "rating_summary", AsyncMock(return_value=None)
        ):
            await self.svc._sync_product_rating(db, pid)
        params = db.execute.await_args_list[-1].args[1]
        assert params == {"avg": None, "cnt": 0, "pid": pid}

    async def test_sync_product_rating_locks_product_row_first(self):
        db = AsyncMock()
        agg = MagicMock()
        agg.fetchone.return_value = MagicMock(
            _mapping={"review_count": 1, "average_rating": 4.0}
        )
        db.execute = AsyncMock(side_effect=[MagicMock(), agg, MagicMock()])
        await self.svc._sync_product_rating(db, uuid.uuid4())
        statements = [str(c.args[0]) for c in db.execute.await_args_list]
        assert "FOR NO KEY UPDATE" in statements[0]
        assert "AVG(rating)" in statements[1]
        assert statements[2].strip().startswith("UPDATE products")

    async def test_list_product_reviews_returns_list(self):
        db = AsyncMock()
        with patch.object(
            ReviewRepository,
            "list_for_product",
            AsyncMock(return_value=([], 0)),
        ):
            reviews, total = await self.svc.list_product_reviews(
                db, product_id=uuid.uuid4()
            )
        assert reviews == []
        assert total == 0

    async def test_rating_summary_delegates_to_repo(self):
        db = AsyncMock()
        mock_summary = {"avg": 4.2, "count": 10}
        with patch.object(
            ReviewRepository, "rating_summary", AsyncMock(return_value=mock_summary)
        ):
            result = await self.svc.rating_summary(db, uuid.uuid4())
        assert result == mock_summary
