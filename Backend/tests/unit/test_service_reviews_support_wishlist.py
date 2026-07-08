"""Tests for ReviewService, SupportService, WishlistService and related repos."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks

import app.modules.addresses.models  # noqa: F401
import app.modules.cart.models  # noqa: F401

# Force mapper init
import app.modules.catalog.models  # noqa: F401
import app.modules.categories.models  # noqa: F401
import app.modules.collections.models  # noqa: F401
import app.modules.coupons.models  # noqa: F401
import app.modules.inventory.models  # noqa: F401
import app.modules.orders.models  # noqa: F401
import app.modules.payments.models  # noqa: F401
import app.modules.profiles.models  # noqa: F401
import app.modules.returns.models  # noqa: F401
import app.modules.reviews.models  # noqa: F401
import app.modules.shipping.models  # noqa: F401
import app.modules.support.models  # noqa: F401
import app.modules.wishlist.models  # noqa: F401


def _sone(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _sall(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _scalar_one(value):
    r = MagicMock()
    r.scalar_one.return_value = value
    return r


def _scalar(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _db(*results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


# ─── ReviewRepository (missing lines) ────────────────────────────────────────


class TestReviewRepositoryVotes:
    def setup_method(self):
        from app.modules.reviews.repository import ReviewRepository

        self.repo = ReviewRepository()

    # add_image/delete_images were removed from ReviewRepository in the
    # Phase 3 cutover — review images now go through
    # UniversalImageService.upload(preset_id="review_photo"), covered by
    # tests/unit/test_media_universal_service.py.

    async def test_get_vote_returns_none(self):
        db = _db(_sone(None))
        result = await self.repo.get_vote(
            db, review_id=uuid.uuid4(), user_id=uuid.uuid4()
        )
        assert result is None

    async def test_get_vote_returns_vote(self):
        mock_vote = MagicMock()
        db = _db(_sone(mock_vote))
        result = await self.repo.get_vote(
            db, review_id=uuid.uuid4(), user_id=uuid.uuid4()
        )
        assert result is mock_vote

    async def test_upsert_vote_creates_new(self):
        # First call: get_vote (returns None) → two executes: get_vote select, _sync_helpful_count select+update
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        none_result = MagicMock()
        none_result.scalar_one_or_none.return_value = None
        count_result = MagicMock()
        count_result.scalar.return_value = 3
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[none_result, count_result, update_result])

        await self.repo.upsert_vote(
            db, review_id=uuid.uuid4(), user_id=uuid.uuid4(), is_helpful=True
        )
        db.add.assert_called_once()

    async def test_upsert_vote_updates_existing(self):
        mock_vote = MagicMock()
        mock_vote.is_helpful = False
        db = AsyncMock()
        db.flush = AsyncMock()

        vote_result = MagicMock()
        vote_result.scalar_one_or_none.return_value = mock_vote
        count_result = MagicMock()
        count_result.scalar.return_value = 5
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[vote_result, count_result, update_result])

        await self.repo.upsert_vote(
            db, review_id=uuid.uuid4(), user_id=uuid.uuid4(), is_helpful=True
        )
        assert mock_vote.is_helpful is True

    async def test_sync_helpful_count_executes_update(self):
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 7
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[count_result, update_result])
        await self.repo._sync_helpful_count(db, uuid.uuid4())
        assert db.execute.await_count == 2


# ─── ReviewService ────────────────────────────────────────────────────────────


class TestReviewService:
    def setup_method(self):
        from app.modules.reviews.repository import ReviewRepository
        from app.modules.reviews.service import ReviewService

        self.svc = ReviewService()
        self.repo_cls = ReviewRepository

    async def test_edit_review_success(self):
        from app.modules.reviews.schemas import ReviewUpdate

        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        user_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.user_id = user_id
        mock_updated = MagicMock()
        with (
            patch.object(
                self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(self.repo_cls, "update", AsyncMock(return_value=mock_updated)),
        ):
            result = await self.svc.edit_review(
                db,
                review_id=uuid.uuid4(),
                user_id=user_id,
                data=ReviewUpdate(rating=5, title="Great!"),
            )
        assert result is mock_updated

    async def test_edit_review_no_changes_skips_update(self):
        from app.modules.reviews.schemas import ReviewUpdate

        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        user_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.user_id = user_id
        with (
            patch.object(
                self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(self.repo_cls, "update", AsyncMock()) as mock_upd,
        ):
            await self.svc.edit_review(
                db,
                review_id=uuid.uuid4(),
                user_id=user_id,
                data=ReviewUpdate(),  # no fields set
            )
        mock_upd.assert_not_awaited()

    async def test_delete_review_calls_soft_delete(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        user_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.user_id = user_id
        with (
            patch.object(
                self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(self.repo_cls, "soft_delete", AsyncMock()) as mock_del,
        ):
            await self.svc.delete_review(db, review_id=uuid.uuid4(), user_id=user_id)
        mock_del.assert_awaited_once()

    async def test_list_product_reviews(self):
        db = AsyncMock()
        mock_review = MagicMock()
        with patch.object(
            self.repo_cls, "list_for_product", AsyncMock(return_value=[mock_review])
        ):
            result = await self.svc.list_product_reviews(db, product_id=uuid.uuid4())
        assert result == [mock_review]

    async def test_rating_summary(self):
        db = AsyncMock()
        with patch.object(
            self.repo_cls,
            "rating_summary",
            AsyncMock(return_value={"avg": 4.5, "count": 10}),
        ):
            result = await self.svc.rating_summary(db, uuid.uuid4())
        assert result["avg"] == 4.5

    async def test_vote_raises_404_when_review_not_found(self):
        from fastapi import HTTPException

        db = AsyncMock()
        with patch.object(self.repo_cls, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.vote(
                    db, review_id=uuid.uuid4(), user_id=uuid.uuid4(), is_helpful=True
                )
        assert exc.value.status_code == 404

    async def test_vote_raises_400_when_own_review(self):
        from fastapi import HTTPException

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.is_approved = True
        mock_review.user_id = user_id  # same user
        with patch.object(
            self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.vote(
                    db, review_id=uuid.uuid4(), user_id=user_id, is_helpful=True
                )
        assert exc.value.status_code == 400

    async def test_vote_success(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        reviewer_id = uuid.uuid4()
        voter_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.is_approved = True
        mock_review.user_id = reviewer_id
        mock_vote = MagicMock()
        with (
            patch.object(
                self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(
                self.repo_cls, "upsert_vote", AsyncMock(return_value=mock_vote)
            ),
        ):
            result = await self.svc.vote(
                db, review_id=uuid.uuid4(), user_id=voter_id, is_helpful=True
            )
        assert result is mock_vote

    async def test_admin_action_approve(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        mock_review = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(
                self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(self.repo_cls, "update", AsyncMock(return_value=mock_updated)),
            patch.object(self.svc, "_sync_product_rating", AsyncMock()),
        ):
            result = await self.svc.admin_action(
                db, review_id=uuid.uuid4(), action="approve"
            )
        assert result is mock_updated

    async def test_admin_action_reject_calls_update(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        mock_review = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(
                self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(
                self.repo_cls, "update", AsyncMock(return_value=mock_updated)
            ) as mock_upd,
            patch.object(self.svc, "_sync_product_rating", AsyncMock()),
        ):
            await self.svc.admin_action(db, review_id=uuid.uuid4(), action="reject")
        mock_upd.assert_awaited_once()

    async def test_admin_action_flag(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        mock_review = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(
                self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
            ),
            patch.object(self.repo_cls, "update", AsyncMock(return_value=mock_updated)),
            patch.object(self.svc, "_sync_product_rating", AsyncMock()),
        ):
            await self.svc.admin_action(db, review_id=uuid.uuid4(), action="flag")

    async def test_admin_action_raises_400_on_unknown(self):
        from fastapi import HTTPException

        db = AsyncMock()
        mock_review = MagicMock()
        with patch.object(
            self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.admin_action(db, review_id=uuid.uuid4(), action="ban")
        assert exc.value.status_code == 400

    async def test_list_pending(self):
        db = AsyncMock()
        mock_review = MagicMock()
        with patch.object(
            self.repo_cls, "list_pending", AsyncMock(return_value=[mock_review])
        ):
            result = await self.svc.list_pending(db)
        assert result == [mock_review]

    async def test_get_owned_raises_403_when_wrong_user(self):
        from fastapi import HTTPException

        db = AsyncMock()
        mock_review = MagicMock()
        mock_review.user_id = uuid.uuid4()  # different user
        with patch.object(
            self.repo_cls, "get_by_id", AsyncMock(return_value=mock_review)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc._get_owned(
                    db, review_id=uuid.uuid4(), user_id=uuid.uuid4()
                )
        assert exc.value.status_code == 403


# ─── SupportService ───────────────────────────────────────────────────────────


class TestSupportService:
    def setup_method(self):
        from app.modules.support.repository import SupportRepository
        from app.modules.support.service import SupportService

        self.svc = SupportService()
        self.repo_cls = SupportRepository

    async def test_create_ticket_success(self):
        from app.modules.support.schemas import TicketCreate

        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        mock_ticket = MagicMock()
        mock_ticket.id = uuid.uuid4()
        with (
            patch.object(
                self.repo_cls,
                "next_ticket_number",
                AsyncMock(return_value="SUP-2026-0001"),
            ),
            patch.object(
                self.repo_cls, "create_ticket", AsyncMock(return_value=mock_ticket)
            ),
            patch.object(self.repo_cls, "add_message", AsyncMock()),
        ):
            result = await self.svc.create_ticket(
                db,
                customer_id=uuid.uuid4(),
                data=TicketCreate(
                    subject="My order is late", category="order", body="Please help"
                ),
            )
        assert result is mock_ticket

    async def test_reply_raises_404_when_ticket_not_found(self):
        from fastapi import HTTPException

        from app.modules.support.schemas import MessageCreate

        db = AsyncMock()
        with patch.object(self.repo_cls, "get_ticket", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.reply(
                    db,
                    ticket_id=uuid.uuid4(),
                    sender_id=uuid.uuid4(),
                    data=MessageCreate(body="Hello"),
                )
        assert exc.value.status_code == 404

    async def test_reply_raises_403_when_wrong_user(self):
        from fastapi import HTTPException

        from app.modules.support.schemas import MessageCreate

        db = AsyncMock()
        mock_ticket = MagicMock()
        mock_ticket.customer_id = uuid.uuid4()
        with patch.object(
            self.repo_cls, "get_ticket", AsyncMock(return_value=mock_ticket)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.reply(
                    db,
                    ticket_id=uuid.uuid4(),
                    sender_id=uuid.uuid4(),
                    data=MessageCreate(body="Hello"),
                )
        assert exc.value.status_code == 403

    async def test_reply_success_reopens_resolved_ticket(self):
        from app.modules.support.schemas import MessageCreate

        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        sender_id = uuid.uuid4()
        mock_ticket = MagicMock()
        mock_ticket.customer_id = sender_id
        mock_ticket.status = "resolved"
        mock_msg = MagicMock()
        with (
            patch.object(
                self.repo_cls, "get_ticket", AsyncMock(return_value=mock_ticket)
            ),
            patch.object(
                self.repo_cls, "add_message", AsyncMock(return_value=mock_msg)
            ),
            patch.object(self.repo_cls, "update_ticket", AsyncMock()) as mock_upd,
        ):
            await self.svc.reply(
                db,
                ticket_id=uuid.uuid4(),
                sender_id=sender_id,
                data=MessageCreate(body="Still waiting"),
            )
        mock_upd.assert_awaited_once()

    async def test_get_ticket_raises_404_when_not_found(self):
        from fastapi import HTTPException

        db = AsyncMock()
        with patch.object(self.repo_cls, "get_ticket", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.get_ticket(
                    db, uuid.uuid4(), viewer_id=uuid.uuid4(), is_admin=False
                )
        assert exc.value.status_code == 404

    async def test_get_ticket_raises_403_when_not_owner(self):
        from fastapi import HTTPException

        db = AsyncMock()
        mock_ticket = MagicMock()
        mock_ticket.customer_id = uuid.uuid4()
        with patch.object(
            self.repo_cls, "get_ticket", AsyncMock(return_value=mock_ticket)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.get_ticket(
                    db, uuid.uuid4(), viewer_id=uuid.uuid4(), is_admin=False
                )
        assert exc.value.status_code == 403

    async def test_get_ticket_admin_bypasses_ownership(self):
        db = AsyncMock()
        mock_ticket = MagicMock()
        mock_ticket.customer_id = uuid.uuid4()
        with patch.object(
            self.repo_cls, "get_ticket", AsyncMock(return_value=mock_ticket)
        ):
            result = await self.svc.get_ticket(
                db, uuid.uuid4(), viewer_id=uuid.uuid4(), is_admin=True
            )
        assert result is mock_ticket

    async def test_admin_list(self):
        db = AsyncMock()
        with patch.object(self.repo_cls, "list_all", AsyncMock(return_value=[])):
            result = await self.svc.admin_list(
                db, status_filter="open", offset=0, limit=20
            )
        assert result == []

    async def test_admin_update_raises_404(self):
        from fastapi import HTTPException

        from app.modules.support.schemas import AdminTicketUpdate

        db = AsyncMock()
        with patch.object(self.repo_cls, "get_ticket", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.admin_update(
                    db,
                    ticket_id=uuid.uuid4(),
                    data=AdminTicketUpdate(status="resolved"),
                )
        assert exc.value.status_code == 404

    async def test_admin_update_success(self):
        from app.modules.support.schemas import AdminTicketUpdate

        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        mock_ticket = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(
                self.repo_cls, "get_ticket", AsyncMock(return_value=mock_ticket)
            ),
            patch.object(
                self.repo_cls, "update_ticket", AsyncMock(return_value=mock_updated)
            ),
        ):
            result = await self.svc.admin_update(
                db, ticket_id=uuid.uuid4(), data=AdminTicketUpdate(status="closed")
            )
        assert result is mock_updated


# ─── WishlistService ──────────────────────────────────────────────────────────


class TestWishlistService:
    def setup_method(self):
        from app.modules.wishlist.service import WishlistService

        self.svc = WishlistService()

    async def test_get_returns_response(self):
        db = AsyncMock()
        mock_wishlist = MagicMock()
        mock_wishlist.id = uuid.uuid4()
        mock_wishlist.items = []
        with patch(
            "app.modules.wishlist.service._repo.get_or_create",
            AsyncMock(return_value=mock_wishlist),
        ):
            result = await self.svc.get(db, uuid.uuid4())
        assert result.total == 0

    async def test_add_calls_add_item(self):
        from app.modules.wishlist.schemas import AddToWishlistRequest

        db = AsyncMock()
        product_id = uuid.uuid4()
        mock_wishlist = MagicMock()
        mock_wishlist.id = uuid.uuid4()
        mock_wishlist.items = []
        with (
            patch(
                "app.modules.wishlist.service._repo.get_or_create",
                AsyncMock(return_value=mock_wishlist),
            ),
            patch(
                "app.modules.wishlist.service._repo.add_item", AsyncMock()
            ) as mock_add,
        ):
            await self.svc.add(
                db, uuid.uuid4(), AddToWishlistRequest(product_id=product_id)
            )
        mock_add.assert_awaited_once()

    async def test_remove_calls_remove_item(self):
        db = AsyncMock()
        product_id = uuid.uuid4()
        mock_wishlist = MagicMock()
        mock_wishlist.id = uuid.uuid4()
        mock_wishlist.items = []
        with (
            patch(
                "app.modules.wishlist.service._repo.get_or_create",
                AsyncMock(return_value=mock_wishlist),
            ),
            patch(
                "app.modules.wishlist.service._repo.remove_item", AsyncMock()
            ) as mock_rm,
        ):
            await self.svc.remove(db, uuid.uuid4(), product_id, None)
        mock_rm.assert_awaited_once()

    async def test_toggle_adds_when_not_in_wishlist(self):
        from app.modules.wishlist.schemas import AddToWishlistRequest

        db = AsyncMock()
        mock_wishlist = MagicMock()
        mock_wishlist.id = uuid.uuid4()
        with (
            patch(
                "app.modules.wishlist.service._repo.get_or_create",
                AsyncMock(return_value=mock_wishlist),
            ),
            patch(
                "app.modules.wishlist.service._repo.is_in_wishlist",
                AsyncMock(return_value=False),
            ),
            patch("app.modules.wishlist.service._repo.add_item", AsyncMock()),
        ):
            result = await self.svc.toggle(
                db, uuid.uuid4(), AddToWishlistRequest(product_id=uuid.uuid4())
            )
        assert result["action"] == "added"

    async def test_toggle_removes_when_already_in_wishlist(self):
        from app.modules.wishlist.schemas import AddToWishlistRequest

        db = AsyncMock()
        mock_wishlist = MagicMock()
        mock_wishlist.id = uuid.uuid4()
        with (
            patch(
                "app.modules.wishlist.service._repo.get_or_create",
                AsyncMock(return_value=mock_wishlist),
            ),
            patch(
                "app.modules.wishlist.service._repo.is_in_wishlist",
                AsyncMock(return_value=True),
            ),
            patch("app.modules.wishlist.service._repo.remove_item", AsyncMock()),
        ):
            result = await self.svc.toggle(
                db, uuid.uuid4(), AddToWishlistRequest(product_id=uuid.uuid4())
            )
        assert result["action"] == "removed"


# ─── CouponRepository (missing lines) ────────────────────────────────────────


class TestCouponRepositoryExtra:
    def setup_method(self):
        from app.modules.coupons.repository import CouponRepository

        self.repo = CouponRepository()

    async def test_update_returns_updated(self):
        mock_coupon = MagicMock()
        update_result = MagicMock()
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = mock_coupon
        db = _db(update_result, select_result)
        result = await self.repo.update(db, uuid.uuid4(), {"is_active": False})
        assert result is mock_coupon

    async def test_increment_usage(self):
        db = _db(MagicMock())
        await self.repo.increment_usage(db, uuid.uuid4())
        db.execute.assert_awaited_once()

    async def test_record_usage(self):
        db = _db()
        await self.repo.record_usage(
            db, uuid.uuid4(), uuid.uuid4(), 50.0, order_id=uuid.uuid4()
        )
        db.add.assert_called_once()

    async def test_update_usage_order_id(self):
        db = _db(MagicMock())
        await self.repo.update_usage_order_id(
            db, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        )
        db.execute.assert_awaited_once()

    async def test_delete_when_found(self):
        mock_coupon = MagicMock()
        db = _db(_sone(mock_coupon))
        await self.repo.delete(db, uuid.uuid4())
        db.delete.assert_awaited_once_with(mock_coupon)

    async def test_delete_when_not_found(self):
        db = _db(_sone(None))
        await self.repo.delete(db, uuid.uuid4())
        db.delete.assert_not_awaited()


# ─── ReviewService — images and event listener (remaining lines) ──────────────


class TestReviewServiceImages:
    def setup_method(self):
        from app.modules.reviews.repository import ReviewRepository
        from app.modules.reviews.service import ReviewService

        self.svc = ReviewService()
        self.repo_cls = ReviewRepository

    async def test_attach_images_calls_upload_and_reorder(self):
        db = AsyncMock()
        review_id = uuid.uuid4()
        mock_upload = AsyncMock()
        mock_upload.read = AsyncMock(return_value=b"imgdata")
        mock_upload.filename = "test.jpg"
        mock_upload.content_type = "image/jpeg"

        mock_image = MagicMock()
        mock_image.id = uuid.uuid4()
        self.svc._images = MagicMock()
        self.svc._images.upload = AsyncMock(return_value=mock_image)
        self.svc._images.reorder = AsyncMock()

        await self.svc._attach_images(
            db,
            review_id=review_id,
            images=[mock_upload],
            background_tasks=BackgroundTasks(),
        )

        self.svc._images.upload.assert_awaited_once()
        self.svc._images.reorder.assert_awaited_once_with(db, [(mock_image.id, 0)])

    async def test_attach_images_caps_at_five(self):
        db = AsyncMock()
        review_id = uuid.uuid4()

        def _make_upload(name: str):
            u = AsyncMock()
            u.read = AsyncMock(return_value=b"data")
            u.filename = name
            u.content_type = "image/jpeg"
            return u

        uploads = [_make_upload(f"{i}.jpg") for i in range(8)]
        self.svc._images = MagicMock()
        self.svc._images.upload = AsyncMock(
            side_effect=lambda *args, **kwargs: MagicMock(id=uuid.uuid4())
        )
        self.svc._images.reorder = AsyncMock()

        await self.svc._attach_images(
            db, review_id=review_id, images=uploads, background_tasks=BackgroundTasks()
        )

        assert self.svc._images.upload.await_count == 5  # max 5

    async def test_submit_review_with_images_calls_attach(self):
        from app.modules.reviews.schemas import ReviewCreate

        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        user_id = uuid.uuid4()
        product_id = uuid.uuid4()
        mock_review = MagicMock()
        mock_review.id = uuid.uuid4()
        mock_upload = AsyncMock()
        mock_upload.read = AsyncMock(return_value=b"img")
        mock_upload.filename = "photo.jpg"
        mock_upload.content_type = "image/jpeg"

        mock_image = MagicMock()
        mock_image.id = uuid.uuid4()
        self.svc._images = MagicMock()
        self.svc._images.upload = AsyncMock(return_value=mock_image)
        self.svc._images.reorder = AsyncMock()
        with (
            patch.object(
                self.repo_cls, "get_by_product_user", AsyncMock(return_value=None)
            ),
            patch.object(
                self.repo_cls, "has_delivered_order_item", AsyncMock(return_value=True)
            ),
            patch.object(self.repo_cls, "create", AsyncMock(return_value=mock_review)),
        ):
            result = await self.svc.submit_review(
                db,
                user_id=user_id,
                customer_name=None,
                data=ReviewCreate(
                    product_id=product_id,
                    rating=5,
                    title="Lovely",
                    body="Beautiful piece",
                ),
                images=[mock_upload],
            )

        self.svc._images.upload.assert_awaited_once()
        assert result is mock_review

    async def test_register_review_request_listener(self):
        from app.core.events import ReviewRequestEvent, event_bus
        from app.modules.reviews.service import ReviewService

        initial = len(event_bus._listeners.get(ReviewRequestEvent, []))
        ReviewService.register_review_request_listener()
        after = len(event_bus._listeners.get(ReviewRequestEvent, []))
        assert after == initial + 1
