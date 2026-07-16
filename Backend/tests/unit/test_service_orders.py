"""OrderService mock-based tests — no real DB needed."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.orders.schemas import (
    CancelOrderRequest,
    SetComplimentaryGiftRequest,
    UpdateOrderStatusRequest,
)


class TestOrderServiceReviewEnrichment:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_enrich_review_states_marks_reviewed_and_unreviewed_items(self):
        """Delivered-order items get product_slug + review state attached, one
        bulk slug query and one bulk review query regardless of item count."""
        user_id = uuid.uuid4()
        pid_reviewed = uuid.uuid4()
        pid_unreviewed = uuid.uuid4()
        review_id = uuid.uuid4()

        item_reviewed = MagicMock(product_id=pid_reviewed)
        item_unreviewed = MagicMock(product_id=pid_unreviewed)
        item_no_product = MagicMock(product_id=None)
        response = MagicMock(items=[item_reviewed, item_unreviewed, item_no_product])

        slug_row_1 = MagicMock(id=pid_reviewed, slug="reviewed-product")
        slug_row_2 = MagicMock(id=pid_unreviewed, slug="unreviewed-product")
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                fetchall=MagicMock(return_value=[slug_row_1, slug_row_2])
            )
        )

        review = MagicMock(product_id=pid_reviewed, id=review_id, rating=5)
        with patch(
            "app.modules.reviews.repository.ReviewRepository.list_by_products_user",
            AsyncMock(return_value=[review]),
        ):
            await self.svc._enrich_review_states(db, response, user_id)

        assert item_reviewed.product_slug == "reviewed-product"
        assert item_reviewed.is_reviewed is True
        assert item_reviewed.review_id == review_id
        assert item_reviewed.review_rating == 5

        assert item_unreviewed.product_slug == "unreviewed-product"
        assert item_unreviewed.is_reviewed is False
        assert item_unreviewed.review_id is None
        assert item_unreviewed.review_rating is None

        # Skipped item (no product_id) is left untouched — never assigned.
        assert isinstance(item_no_product.product_slug, MagicMock)

    async def test_get_order_enriches_only_for_delivered_customer_view(self):
        """Enrichment only runs when a user_id is passed AND the order is
        delivered — admin views (no user_id) and non-delivered orders skip it."""
        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock(user_id=user_id, status="shipped")
        with patch(
            "app.modules.orders.service._repo.get_by_id",
            AsyncMock(return_value=mock_order),
        ):
            with patch(
                "app.modules.orders.schemas.OrderResponse.model_validate",
                return_value=MagicMock(status="shipped"),
            ):
                with patch.object(
                    self.svc, "_enrich_review_states", AsyncMock()
                ) as enrich:
                    await self.svc.get_order(db, mock_order.id, user_id=user_id)
        enrich.assert_not_called()


class TestOrderServiceGetOrder:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_get_order_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_order(db, uuid.uuid4())

    async def test_get_order_raises_404_for_wrong_owner(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()
        with patch(
            "app.modules.orders.service._repo.get_by_id",
            AsyncMock(return_value=mock_order),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_order(db, uuid.uuid4(), user_id=uuid.uuid4())

    async def test_get_order_no_user_check_for_admin(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.id = uuid.uuid4()
        with patch(
            "app.modules.orders.service._repo.get_by_id",
            AsyncMock(return_value=mock_order),
        ):
            with patch(
                "app.modules.orders.schemas.OrderResponse.model_validate",
                return_value=MagicMock(),
            ):
                result = await self.svc.get_order(db, mock_order.id)
        assert result is not None


class TestOrderServiceList:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_list_my_orders_empty(self):
        db = AsyncMock()
        with patch(
            "app.modules.orders.service._repo.list_for_user",
            AsyncMock(return_value=([], 0)),
        ):
            result = await self.svc.list_my_orders(db, uuid.uuid4())
        assert result.total == 0
        assert result.total_pages == 0
        assert result.items == []

    async def test_list_my_orders_with_results(self):
        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.order_number = "ORD-001"
        mock_order.status = "pending"
        mock_order.payment_status = "pending"
        mock_order.fulfillment_status = "pending"
        mock_order.total = Decimal("1500.00")
        mock_order.created_at = datetime.now(UTC)
        mock_order.items = []
        mock_order.complimentary_gift = None
        with patch(
            "app.modules.orders.service._repo.list_for_user",
            AsyncMock(return_value=([mock_order], 1)),
        ):
            result = await self.svc.list_my_orders(
                db, uuid.uuid4(), page=1, page_size=10
            )
        assert result.total == 1
        assert len(result.items) == 1
        assert result.total_pages == 1

    async def test_list_my_orders_pagination(self):
        db = AsyncMock()
        with patch(
            "app.modules.orders.service._repo.list_for_user",
            AsyncMock(return_value=([], 25)),
        ):
            result = await self.svc.list_my_orders(
                db, uuid.uuid4(), page=2, page_size=10
            )
        assert result.page == 2
        assert result.page_size == 10
        assert result.total == 25
        assert result.total_pages == 3

    async def test_admin_list_orders_empty(self):
        db = AsyncMock()
        with patch(
            "app.modules.orders.service._repo.list_all", AsyncMock(return_value=([], 0))
        ):
            result = await self.svc.admin_list_orders(db)
        assert result.total == 0

    async def test_admin_list_orders_with_results(self):
        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.order_number = "ORD-002"
        mock_order.status = "confirmed"
        mock_order.payment_status = "paid"
        mock_order.fulfillment_status = "pending"
        mock_order.total = Decimal("500.00")
        mock_order.created_at = datetime.now(UTC)
        mock_order.complimentary_gift = None
        with patch(
            "app.modules.orders.service._repo.list_all",
            AsyncMock(return_value=([mock_order], 1)),
        ):
            result = await self.svc.admin_list_orders(db)
        assert result.total == 1


class TestOrderServiceCancel:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_cancel_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.cancel_order(
                    db,
                    uuid.uuid4(),
                    uuid.uuid4(),
                    CancelOrderRequest(reason="changed mind"),
                )

    async def test_cancel_raises_404_for_wrong_user(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        owner = uuid.uuid4()
        caller = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = owner
        with patch(
            "app.modules.orders.service._repo.get_by_id",
            AsyncMock(return_value=mock_order),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.cancel_order(
                    db, uuid.uuid4(), caller, CancelOrderRequest(reason="x")
                )

    async def test_cancel_raises_validation_for_shipped_status(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.status = "shipped"
        with patch(
            "app.modules.orders.service._repo.get_by_id",
            AsyncMock(return_value=mock_order),
        ):
            with pytest.raises(ValidationError):
                await self.svc.cancel_order(
                    db, uuid.uuid4(), user_id, CancelOrderRequest(reason="x")
                )

    async def test_cancel_raises_validation_for_delivered_status(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.status = "delivered"
        with patch(
            "app.modules.orders.service._repo.get_by_id",
            AsyncMock(return_value=mock_order),
        ):
            with pytest.raises(ValidationError):
                await self.svc.cancel_order(
                    db, uuid.uuid4(), user_id, CancelOrderRequest(reason="x")
                )


class TestOrderServiceUpdateStatus:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_update_status_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.update_status(
                    db, uuid.uuid4(), UpdateOrderStatusRequest(status="confirmed")
                )

    async def test_update_status_success(self):
        db = AsyncMock()
        order_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.user_id = uuid.uuid4()
        mock_order.status = "pending"
        mock_updated = MagicMock()
        with (
            patch(
                "app.modules.orders.service._repo.get_by_id",
                AsyncMock(return_value=mock_order),
            ),
            patch(
                "app.modules.orders.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            patch("app.modules.orders.service.event_bus.publish", AsyncMock()),
            patch(
                "app.modules.orders.schemas.OrderResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.update_status(
                db, order_id, UpdateOrderStatusRequest(status="confirmed")
            )
        assert result is not None

    async def test_update_status_to_cancelled_sets_cancelled_at(self):
        db = AsyncMock()
        order_id = uuid.uuid4()
        captured_data = {}
        mock_order = MagicMock()
        mock_order.status = "confirmed"
        mock_order.user_id = uuid.uuid4()
        mock_order.coupon_id = None  # no coupon → skip coupon revert

        async def capture_update(db, oid, data):
            captured_data.update(data)
            return MagicMock()

        with (
            patch(
                "app.modules.orders.service._repo.get_by_id",
                AsyncMock(return_value=mock_order),
            ),
            patch("app.modules.orders.service._repo.update", capture_update),
            patch("app.modules.orders.service.event_bus.publish", AsyncMock()),
            patch(
                "app.modules.orders.schemas.OrderResponse.model_validate",
                return_value=MagicMock(),
            ),
            patch(
                "app.modules.orders.service._reservation_svc.release_order_reservations",
                AsyncMock(),
            ),
        ):
            await self.svc.update_status(
                db, order_id, UpdateOrderStatusRequest(status="cancelled")
            )
        assert "cancelled_at" in captured_data
        assert captured_data["status"] == "cancelled"


class TestOrderServiceComplimentaryGift:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_rejects_when_feature_flag_disabled(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        user_id = uuid.uuid4()
        with patch(
            "app.modules.orders.service.SettingsService.is_feature_enabled",
            AsyncMock(return_value=False),
        ):
            with pytest.raises(ValidationError, match="currently unavailable"):
                await self.svc.set_complimentary_gift(
                    db,
                    uuid.uuid4(),
                    user_id,
                    SetComplimentaryGiftRequest(gift="Traditional Sweet"),
                )

    async def test_allows_when_feature_flag_enabled_and_eligible(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        order_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.payment_status = "paid"
        mock_order.total = Decimal("2500.00")
        mock_order.complimentary_gift = None

        with (
            patch(
                "app.modules.orders.service.SettingsService.is_feature_enabled",
                AsyncMock(return_value=True),
            ),
            patch(
                "app.modules.orders.service._repo.get_by_id",
                AsyncMock(return_value=mock_order),
            ),
            patch(
                "app.modules.orders.service._repo.update",
                AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "app.modules.orders.schemas.OrderResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            await self.svc.set_complimentary_gift(
                db,
                order_id,
                user_id,
                SetComplimentaryGiftRequest(gift="Traditional Sweet"),
            )


class TestHandleExpiredOrderSideEffects:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_empty_order_ids_noop(self):
        """Empty list → no DB calls at all."""
        db = AsyncMock()
        with patch(
            "app.modules.orders.service._repo.get_by_ids",
            AsyncMock(return_value=[]),
        ) as mock_get:
            await self.svc.handle_expired_order_side_effects(db, [])
            mock_get.assert_not_called()

    async def test_coupon_reverted_for_each_order_with_coupon(self):
        """Orders with coupon_id get coupon reverted."""
        db = AsyncMock()
        oid1, oid2 = uuid.uuid4(), uuid.uuid4()
        uid1, uid2 = uuid.uuid4(), uuid.uuid4()
        cid1, cid2 = uuid.uuid4(), uuid.uuid4()

        order1 = MagicMock()
        order1.id = oid1
        order1.user_id = uid1
        order1.coupon_id = cid1

        order2 = MagicMock()
        order2.id = oid2
        order2.user_id = uid2
        order2.coupon_id = cid2

        with patch(
            "app.modules.orders.service._repo.get_by_ids",
            AsyncMock(return_value=[order1, order2]),
        ):
            mock_coupon_svc = MagicMock()
            mock_coupon_svc.revert_usage = AsyncMock()
            with patch(
                "app.modules.coupons.service.CouponService",
                return_value=mock_coupon_svc,
            ):
                await self.svc.handle_expired_order_side_effects(db, [oid1, oid2])

        assert mock_coupon_svc.revert_usage.call_count == 2
        calls = mock_coupon_svc.revert_usage.call_args_list
        assert calls[0].args == (db, cid1, uid1, oid1)
        assert calls[1].args == (db, cid2, uid2, oid2)

    async def test_orders_without_coupon_skipped(self):
        """Orders without coupon_id are silently skipped."""
        db = AsyncMock()
        oid = uuid.uuid4()

        order = MagicMock()
        order.id = oid
        order.user_id = uuid.uuid4()
        order.coupon_id = None  # no coupon

        with patch(
            "app.modules.orders.service._repo.get_by_ids",
            AsyncMock(return_value=[order]),
        ):
            mock_coupon_svc = MagicMock()
            mock_coupon_svc.revert_usage = AsyncMock()
            with patch(
                "app.modules.coupons.service.CouponService",
                return_value=mock_coupon_svc,
            ):
                await self.svc.handle_expired_order_side_effects(db, [oid])

        mock_coupon_svc.revert_usage.assert_not_called()

    async def test_missing_order_id_skipped(self):
        """Order IDs not found in DB are silently skipped."""
        db = AsyncMock()
        oid = uuid.uuid4()

        with patch(
            "app.modules.orders.service._repo.get_by_ids",
            AsyncMock(return_value=[]),  # order not found
        ):
            mock_coupon_svc = MagicMock()
            mock_coupon_svc.revert_usage = AsyncMock()
            with patch(
                "app.modules.coupons.service.CouponService",
                return_value=mock_coupon_svc,
            ):
                await self.svc.handle_expired_order_side_effects(db, [oid])

        mock_coupon_svc.revert_usage.assert_not_called()

    async def test_coupon_revert_failure_does_not_propagate(self):
        """If revert_usage raises, the error is caught and logged."""
        db = AsyncMock()
        oid = uuid.uuid4()

        order = MagicMock()
        order.id = oid
        order.user_id = uuid.uuid4()
        order.coupon_id = uuid.uuid4()

        with patch(
            "app.modules.orders.service._repo.get_by_ids",
            AsyncMock(return_value=[order]),
        ):
            mock_coupon_svc = MagicMock()
            mock_coupon_svc.revert_usage = AsyncMock(
                side_effect=RuntimeError("DB error")
            )
            with patch(
                "app.modules.coupons.service.CouponService",
                return_value=mock_coupon_svc,
            ):
                # Should NOT raise
                await self.svc.handle_expired_order_side_effects(db, [oid])

    async def test_partial_failure_continues_remaining(self):
        """If one coupon revert fails, the others still proceed."""
        db = AsyncMock()
        oid1, oid2 = uuid.uuid4(), uuid.uuid4()
        uid1, uid2 = uuid.uuid4(), uuid.uuid4()
        cid1, cid2 = uuid.uuid4(), uuid.uuid4()

        order1 = MagicMock()
        order1.id = oid1
        order1.user_id = uid1
        order1.coupon_id = cid1

        order2 = MagicMock()
        order2.id = oid2
        order2.user_id = uid2
        order2.coupon_id = cid2

        with patch(
            "app.modules.orders.service._repo.get_by_ids",
            AsyncMock(return_value=[order1, order2]),
        ):
            call_count = 0

            async def _revert_side_effect(db, coupon_id, user_id, order_id):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("DB error on first")

            mock_coupon_svc = MagicMock()
            mock_coupon_svc.revert_usage = AsyncMock(side_effect=_revert_side_effect)
            with patch(
                "app.modules.coupons.service.CouponService",
                return_value=mock_coupon_svc,
            ):
                await self.svc.handle_expired_order_side_effects(db, [oid1, oid2])

        # Both were attempted despite first failure
        assert mock_coupon_svc.revert_usage.call_count == 2
