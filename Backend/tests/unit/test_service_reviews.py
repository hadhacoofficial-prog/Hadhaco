"""ReviewService mock-based tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

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
                ReviewRepository,
                "get_soft_deleted_by_product_user",
                AsyncMock(return_value=None),
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

    async def test_submit_purges_soft_deleted_review_before_create(self):
        # get_by_product_user ignores soft-deleted rows, but the unique
        # (product_id, user_id) constraint does not — the stale row and its
        # photos must be purged before insert or resubmitting raises a 500.
        db = AsyncMock()
        product_id = uuid.uuid4()
        user_id = uuid.uuid4()
        stale = MagicMock()
        stale.id = uuid.uuid4()
        stale_image = MagicMock()
        stale.images = [stale_image]
        mock_review = MagicMock()
        calls: list[str] = []
        delete_image = AsyncMock(side_effect=lambda *a, **k: calls.append("image"))
        hard_delete = AsyncMock(side_effect=lambda *a, **k: calls.append("purge"))
        create = AsyncMock(
            side_effect=lambda *a, **k: calls.append("create") or mock_review
        )
        with (
            patch.object(
                ReviewRepository, "get_by_product_user", AsyncMock(return_value=None)
            ),
            patch.object(
                ReviewRepository,
                "get_soft_deleted_by_product_user",
                AsyncMock(return_value=stale),
            ),
            patch.object(
                ReviewRepository,
                "has_delivered_order_item",
                AsyncMock(return_value=False),
            ),
            patch.object(ReviewRepository, "hard_delete", hard_delete),
            patch.object(ReviewRepository, "create", create),
            patch.object(self.svc._images, "delete", delete_image),
        ):
            result = await self.svc.submit_review(
                db,
                user_id=user_id,
                customer_name=None,
                data=ReviewCreate(
                    product_id=product_id, rating=3, title="OK", body="Meh"
                ),
            )
        assert result is mock_review
        delete_image.assert_awaited_once_with(db, image=stale_image)
        hard_delete.assert_awaited_once_with(db, stale.id)
        assert calls == ["image", "purge", "create"]

    async def test_submit_409_does_not_purge(self):
        db = AsyncMock()
        lookup = AsyncMock()
        with (
            patch.object(
                ReviewRepository,
                "get_by_product_user",
                AsyncMock(return_value=MagicMock()),
            ),
            patch.object(ReviewRepository, "get_soft_deleted_by_product_user", lookup),
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.submit_review(
                    db,
                    user_id=uuid.uuid4(),
                    customer_name=None,
                    data=ReviewCreate(product_id=uuid.uuid4(), rating=5, body="x"),
                )
        assert exc.value.status_code == 409
        lookup.assert_not_awaited()

    async def _submit_with_create_error(self, exc: Exception):
        db = AsyncMock()
        with (
            patch.object(
                ReviewRepository, "get_by_product_user", AsyncMock(return_value=None)
            ),
            patch.object(
                ReviewRepository,
                "get_soft_deleted_by_product_user",
                AsyncMock(return_value=None),
            ),
            patch.object(
                ReviewRepository,
                "has_delivered_order_item",
                AsyncMock(return_value=False),
            ),
            patch.object(ReviewRepository, "create", AsyncMock(side_effect=exc)),
        ):
            await self.svc.submit_review(
                db,
                user_id=uuid.uuid4(),
                customer_name=None,
                data=ReviewCreate(product_id=uuid.uuid4(), rating=5, body="x"),
            )

    async def test_submit_concurrent_duplicate_maps_to_409(self):
        err = IntegrityError(
            "INSERT", {}, Exception('violates "uq_reviews_product_user"')
        )
        with pytest.raises(HTTPException) as exc:
            await self._submit_with_create_error(err)
        assert exc.value.status_code == 409

    async def test_submit_other_integrity_error_is_reraised(self):
        err = IntegrityError("INSERT", {}, Exception('violates "reviews_product_fk"'))
        with pytest.raises(IntegrityError):
            await self._submit_with_create_error(err)


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

    async def test_edit_approved_review_resyncs_product_rating(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        review = self._owned_review(user_id, approved=True)
        update = AsyncMock(return_value=review)
        sync = AsyncMock()
        with (
            patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=review)),
            patch.object(ReviewRepository, "update", update),
            patch.object(self.svc, "_sync_product_rating", sync),
        ):
            result, rating_changed = await self.svc.edit_review(
                db, review_id=uuid.uuid4(), user_id=user_id, data=ReviewUpdate(rating=2)
            )
        assert result is review
        assert rating_changed is True
        updates = update.await_args.args[2]
        assert updates["is_approved"] is False
        sync.assert_awaited_once_with(db, review.product_id)
        db.commit.assert_awaited_once()

    async def test_edit_pending_review_skips_resync(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        review = self._owned_review(user_id, approved=False)
        sync = AsyncMock()
        with (
            patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=review)),
            patch.object(ReviewRepository, "update", AsyncMock(return_value=review)),
            patch.object(self.svc, "_sync_product_rating", sync),
        ):
            _, rating_changed = await self.svc.edit_review(
                db, review_id=uuid.uuid4(), user_id=user_id, data=ReviewUpdate(rating=2)
            )
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

    async def test_admin_delete_removes_images_then_row(self):
        db = AsyncMock()
        review = MagicMock()
        review.id = uuid.uuid4()
        review.product_id = uuid.uuid4()
        image = MagicMock()
        review.images = [image]
        calls: list[str] = []
        delete_image = AsyncMock(side_effect=lambda *a, **k: calls.append("image"))
        hard_delete = AsyncMock(side_effect=lambda *a, **k: calls.append("row"))
        with (
            patch.object(ReviewRepository, "get_by_id", AsyncMock(return_value=review)),
            patch.object(ReviewRepository, "hard_delete", hard_delete),
            patch.object(self.svc._images, "delete", delete_image),
            patch.object(self.svc, "_sync_product_rating", AsyncMock()),
        ):
            await self.svc.admin_delete(db, review_id=review.id)
        delete_image.assert_awaited_once_with(db, image=image)
        hard_delete.assert_awaited_once_with(db, review.id)
        assert calls == ["image", "row"]

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
