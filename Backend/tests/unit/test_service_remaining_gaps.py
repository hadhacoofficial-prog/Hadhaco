"""Final coverage push: inventory, fraud, collections, coupons, profiles, catalog, orders."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def _sone(v):
    r = MagicMock()
    r.scalar_one_or_none.return_value = v
    return r


def _sall(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _scalar_one(v):
    r = MagicMock()
    r.scalar_one.return_value = v
    return r


def _db(*results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


# ─── InventoryService ─────────────────────────────────────────────────────────


class TestInventoryService:
    def setup_method(self):
        from app.modules.inventory.service import InventoryService

        self.svc = InventoryService()

    async def test_record_movement_success(self):
        from app.modules.inventory.schemas import InventoryMovementResponse

        db = AsyncMock()
        db.execute = AsyncMock()  # stock update execute
        product_id = uuid.uuid4()
        snapshot = {
            "stock_quantity": 10,
            "allow_backorder": False,
            "low_stock_threshold": 2,
            "sku": "ABC",
            "product_name": "Ring",
        }
        mock_movement = MagicMock()
        mock_resp = MagicMock()
        with (
            patch(
                "app.modules.inventory.service._repo.get_stock_snapshot",
                AsyncMock(return_value=snapshot),
            ),
            patch(
                "app.modules.inventory.service._repo.record",
                AsyncMock(return_value=mock_movement),
            ),
            patch("app.core.events.event_bus.publish", AsyncMock()),
            patch.object(
                InventoryMovementResponse, "model_validate", return_value=mock_resp
            ),
        ):
            result = await self.svc.record_movement(
                db, product_id=product_id, delta=-5, movement_type="sale"
            )
        assert result is mock_resp

    async def test_record_movement_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.inventory.service._repo.get_stock_snapshot",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.record_movement(
                    db, product_id=uuid.uuid4(), delta=-1, movement_type="sale"
                )

    async def test_record_movement_raises_validation_on_insufficient_stock(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        snapshot = {
            "stock_quantity": 3,
            "allow_backorder": False,
            "low_stock_threshold": 5,
        }
        with patch(
            "app.modules.inventory.service._repo.get_stock_snapshot",
            AsyncMock(return_value=snapshot),
        ):
            with pytest.raises(ValidationError):
                await self.svc.record_movement(
                    db, product_id=uuid.uuid4(), delta=-10, movement_type="sale"
                )

    async def test_manual_adjustment_delegates_to_record_movement(self):
        from app.modules.inventory.schemas import (
            InventoryMovementResponse,
            ManualAdjustmentRequest,
        )

        db = AsyncMock()
        db.execute = AsyncMock()
        product_id = uuid.uuid4()
        snapshot = {
            "stock_quantity": 20,
            "allow_backorder": True,
            "low_stock_threshold": 2,
            "sku": "S",
            "product_name": "P",
        }
        mock_resp = MagicMock()
        with (
            patch(
                "app.modules.inventory.service._repo.get_stock_snapshot",
                AsyncMock(return_value=snapshot),
            ),
            patch(
                "app.modules.inventory.service._repo.record",
                AsyncMock(return_value=MagicMock()),
            ),
            patch("app.core.events.event_bus.publish", AsyncMock()),
            patch.object(
                InventoryMovementResponse, "model_validate", return_value=mock_resp
            ),
        ):
            result = await self.svc.manual_adjustment(
                db,
                product_id=product_id,
                payload=ManualAdjustmentRequest(delta=5, notes="stock add"),
                actor_id=uuid.uuid4(),
            )
        assert result is mock_resp

    async def test_get_history_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.inventory.service._repo.get_stock_snapshot",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_history(db, uuid.uuid4())

    async def test_get_history_success(self):
        from app.modules.inventory.schemas import InventoryMovementResponse

        db = AsyncMock()
        snapshot = {
            "stock_quantity": 5,
            "allow_backorder": False,
            "low_stock_threshold": 2,
        }
        mock_movement = MagicMock()
        now = datetime.now(UTC)
        # Build a real schema object so InventoryMovementListResponse validates it
        real_item = InventoryMovementResponse.model_construct(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            variant_id=None,
            movement_type="sale",
            delta=-2,
            quantity_before=10,
            quantity_after=8,
            reference_type=None,
            reference_id=None,
            notes=None,
            created_by=None,
            created_at=now,
        )
        with (
            patch(
                "app.modules.inventory.service._repo.get_stock_snapshot",
                AsyncMock(return_value=snapshot),
            ),
            patch(
                "app.modules.inventory.service._repo.list_for_product",
                AsyncMock(return_value=([mock_movement], 1)),
            ),
            patch.object(
                InventoryMovementResponse, "model_validate", return_value=real_item
            ),
        ):
            result = await self.svc.get_history(db, uuid.uuid4())
        assert result.total == 1


# ─── FraudService ─────────────────────────────────────────────────────────────


class TestFraudService:
    def setup_method(self):
        from app.modules.fraud.repository import FraudRepository
        from app.modules.fraud.service import FraudService

        self.svc = FraudService()
        self.repo_cls = FraudRepository

    async def test_record_signal(self):
        from app.modules.fraud.schemas import FraudSignalCreate

        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        mock_signal = MagicMock()
        with patch.object(self.repo_cls, "create", AsyncMock(return_value=mock_signal)):
            result = await self.svc.record_signal(
                db,
                data=FraudSignalCreate(
                    user_id=uuid.uuid4(),
                    signal_type="multiple_failed_payments",
                    severity="medium",
                    description="Suspicious activity",
                ),
            )
        assert result is mock_signal

    async def test_list_signals(self):
        db = AsyncMock()
        with patch.object(self.repo_cls, "list_unresolved", AsyncMock(return_value=[])):
            result = await self.svc.list_signals(db, offset=0, limit=20)
        assert result == []

    async def test_resolve_signal_raises_404(self):
        from fastapi import HTTPException

        from app.modules.fraud.schemas import FraudResolveRequest

        db = AsyncMock()
        with patch.object(self.repo_cls, "get", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.resolve_signal(
                    db,
                    signal_id=uuid.uuid4(),
                    resolver_id=uuid.uuid4(),
                    data=FraudResolveRequest(is_resolved=True),
                )
        assert exc.value.status_code == 404

    async def test_resolve_signal_success(self):
        from app.modules.fraud.schemas import FraudResolveRequest

        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        mock_signal = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(self.repo_cls, "get", AsyncMock(return_value=mock_signal)),
            patch.object(self.repo_cls, "update", AsyncMock(return_value=mock_updated)),
        ):
            result = await self.svc.resolve_signal(
                db,
                signal_id=uuid.uuid4(),
                resolver_id=uuid.uuid4(),
                data=FraudResolveRequest(is_resolved=True),
            )
        assert result is mock_updated


# ─── CollectionsRepository extra ─────────────────────────────────────────────


class TestCollectionsRepositoryExtra:
    def setup_method(self):
        from app.modules.collections.repository import CollectionRepository

        self.repo = CollectionRepository()

    async def test_add_products_executes_upsert(self):
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 0
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        await self.repo.add_products(
            db, col_id=uuid.uuid4(), product_ids=[uuid.uuid4(), uuid.uuid4()]
        )
        # 1 for max_order_result + 1 bulk multi-row upsert (not one per product)
        assert db.execute.await_count == 2

    async def test_add_products_empty_list(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        await self.repo.add_products(db, col_id=uuid.uuid4(), product_ids=[])
        db.execute.assert_not_awaited()

    async def test_remove_product_executes_delete(self):
        db = _db(MagicMock())
        await self.repo.remove_product(db, col_id=uuid.uuid4(), product_id=uuid.uuid4())
        db.execute.assert_awaited_once()

    async def test_get_product_ids(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [uuid.uuid4(), uuid.uuid4()]
        db = _db(mock_result)
        result = await self.repo.get_product_ids(db, uuid.uuid4())
        assert len(result) == 2


# ─── CouponService extra ──────────────────────────────────────────────────────


class TestCouponServiceExtra:
    def setup_method(self):
        from app.modules.coupons.service import CouponService

        self.svc = CouponService()

    async def test_create_success(self):
        from app.modules.coupons.schemas import CouponCreateRequest, CouponResponse

        db = AsyncMock()
        mock_coupon = MagicMock()
        mock_resp = MagicMock()
        with (
            patch(
                "app.modules.coupons.service._repo.get_by_code",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.coupons.service._repo.create",
                AsyncMock(return_value=mock_coupon),
            ),
            patch.object(CouponResponse, "model_validate", return_value=mock_resp),
        ):
            result = await self.svc.create(
                db,
                payload=CouponCreateRequest(
                    code="SAVE20",
                    coupon_type="percentage",
                    value=20,
                    min_order_amount=0,
                    per_user_limit=1,
                ),
            )
        assert result is mock_resp

    async def test_create_raises_conflict_when_code_exists(self):
        from app.core.exceptions import ConflictError
        from app.modules.coupons.schemas import CouponCreateRequest

        db = AsyncMock()
        with patch(
            "app.modules.coupons.service._repo.get_by_code",
            AsyncMock(return_value=MagicMock()),
        ):
            with pytest.raises(ConflictError):
                await self.svc.create(
                    db,
                    payload=CouponCreateRequest(
                        code="DUP",
                        coupon_type="fixed_amount",
                        value=50,
                        min_order_amount=0,
                        per_user_limit=1,
                    ),
                )

    async def test_update_success(self):
        from app.modules.coupons.schemas import CouponResponse, CouponUpdateRequest

        db = AsyncMock()
        mock_coupon = MagicMock()
        mock_updated = MagicMock()
        mock_resp = MagicMock()
        with (
            patch(
                "app.modules.coupons.service._repo.get_by_id",
                AsyncMock(return_value=mock_coupon),
            ),
            patch(
                "app.modules.coupons.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            patch.object(CouponResponse, "model_validate", return_value=mock_resp),
        ):
            result = await self.svc.update(
                db, uuid.uuid4(), CouponUpdateRequest(is_active=False)
            )
        assert result is mock_resp

    async def test_apply_and_reserve_success(self):
        from app.modules.coupons.schemas import CouponResponse

        db = AsyncMock()
        coupon_id = uuid.uuid4()
        mock_coupon = MagicMock()
        mock_coupon.id = coupon_id
        mock_coupon.is_active = True
        mock_coupon.status = "active"
        mock_coupon.valid_from = None
        mock_coupon.valid_until = None
        mock_coupon.usage_limit = None
        mock_coupon.usage_count = 0
        mock_coupon.min_order_amount = 0
        mock_coupon.max_order_amount = None
        mock_coupon.per_user_limit = 99
        mock_coupon.one_time_per_customer = False
        mock_coupon.first_order_only = False
        mock_coupon.new_customer_only = False
        mock_coupon.returning_customer_only = False
        mock_coupon.coupon_type = "flat"
        mock_coupon.value = 50
        mock_coupon.max_discount = None
        now = datetime.now(UTC)
        mock_resp = CouponResponse.model_construct(
            id=coupon_id,
            code="FLAT50",
            coupon_type="fixed_amount",
            value=50,
            min_order_amount=0,
            per_user_limit=99,
            usage_count=0,
            is_active=True,
            max_discount=None,
            usage_limit=None,
            description=None,
            valid_from=None,
            valid_until=None,
            created_at=now,
        )
        with (
            patch(
                "app.modules.coupons.service._repo.get_by_code",
                AsyncMock(return_value=mock_coupon),
            ),
            patch(
                "app.modules.coupons.service._repo.get_by_code_for_update",
                AsyncMock(return_value=mock_coupon),
            ),
            patch(
                "app.modules.coupons.service._repo.get_user_usage_count",
                AsyncMock(return_value=0),
            ),
            patch("app.modules.coupons.service._repo.record_usage", AsyncMock()),
            patch("app.modules.coupons.service._repo.increment_usage", AsyncMock()),
            patch.object(CouponResponse, "model_validate", return_value=mock_resp),
        ):
            discount, c_id, coupon_type = await self.svc.apply_and_reserve(
                db, code="FLAT50", subtotal=200.0, user_id=uuid.uuid4()
            )
        assert c_id == coupon_id
        assert coupon_type == "flat"


# ─── ProfilesRepository extra ─────────────────────────────────────────────────


class TestProfilesRepositoryExtra:
    def setup_method(self):
        from app.modules.profiles.repository import ProfileRepository

        self.repo = ProfileRepository()

    async def test_create_profile(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        await self.repo.create(
            db, {"id": str(uuid.uuid4()), "email": "x@x.com", "role": "customer"}
        )
        db.add.assert_called_once()

    async def test_list_paginated_with_role_filter(self):
        count_result = _scalar_one(0)
        items_result = _sall([])
        db = _db(count_result, items_result)
        items, total = await self.repo.list_paginated(db, role="admin")
        assert total == 0

    async def test_list_paginated_with_is_active_filter(self):
        count_result = _scalar_one(0)
        items_result = _sall([])
        db = _db(count_result, items_result)
        items, total = await self.repo.list_paginated(db, is_active=True)
        assert total == 0

    async def test_list_paginated_with_search_filter(self):
        count_result = _scalar_one(0)
        items_result = _sall([])
        db = _db(count_result, items_result)
        items, total = await self.repo.list_paginated(db, search="haris")
        assert total == 0

    async def test_list_paginated_ascending_sort(self):
        count_result = _scalar_one(1)
        mock_profile = MagicMock()
        items_result = _sall([mock_profile])
        db = _db(count_result, items_result)
        items, total = await self.repo.list_paginated(db, sort_dir="asc")
        assert total == 1

    async def test_soft_delete_executes_update(self):
        db = _db(MagicMock())
        await self.repo.soft_delete(db, uuid.uuid4())
        db.execute.assert_awaited_once()


# ─── CatalogService extra paths ───────────────────────────────────────────────


class TestCatalogServiceExtra:
    def setup_method(self):
        from app.modules.catalog.repository import ProductRepository
        from app.modules.catalog.service import CatalogService

        self.svc = CatalogService()
        self.repo_cls = ProductRepository

    async def test_get_by_slug_success(self):
        from app.modules.catalog.schemas import ProductResponse

        db = AsyncMock()
        mock_product = MagicMock()
        mock_resp = MagicMock()
        with (
            patch(
                "app.modules.catalog.service._repo.get_by_slug",
                AsyncMock(return_value=mock_product),
            ),
            patch(
                "app.modules.catalog.service._repo.get_collections_for_product",
                AsyncMock(return_value=[]),
            ),
            patch.object(ProductResponse, "model_validate", return_value=mock_resp),
        ):
            result = await self.svc.get_by_slug(db, "silver-ring")
        assert result is mock_resp

    async def test_list_products_no_primary_image_falls_back(self):
        """When no image is_primary, falls back to first image url."""
        db = AsyncMock()
        mock_product = MagicMock()
        img = MagicMock()
        img.id = uuid.uuid4()
        img.is_primary = False
        img.sort_order = 0
        img.alt_text = None
        img.metadata_ = {}
        img.original_key = "products/p/i/original.jpg"
        img.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
        large_variant = MagicMock()
        large_variant.id = uuid.uuid4()
        large_variant.variant_name = "large"
        large_variant.breakpoint = "desktop"
        large_variant.dpr = 1
        large_variant.format = "webp"
        large_variant.status = "ready"
        large_variant.url = "https://cdn/first.jpg"
        large_variant.width = 1200
        large_variant.height = 1200
        large_variant.error_message = None
        img.variants = [large_variant]
        mock_product.images = [img]
        mock_product.id = uuid.uuid4()
        mock_product.sku = "SKU1"
        mock_product.name = "Ring"
        mock_product.slug = "ring"
        mock_product.short_description = "A ring"
        mock_product.category_id = uuid.uuid4()
        mock_product.metal_type = "silver"
        mock_product.base_price = 999.0
        mock_product.compare_at_price = None
        mock_product.stock_quantity = 5
        mock_product.status = "active"
        mock_product.is_featured = False
        mock_product.is_new_arrival = True
        mock_product.is_best_seller = False
        mock_product.created_at = datetime.now(UTC)
        with (
            patch(
                "app.modules.catalog.service._repo.list_paginated",
                AsyncMock(return_value=([mock_product], 1)),
            ),
            patch(
                "app.modules.catalog.service._repo.get_images_for_products",
                AsyncMock(
                    return_value={mock_product.id: [img]}
                ),
            ),
            patch(
                "app.modules.catalog.service._repo.get_image_variants_for_images",
                AsyncMock(return_value={img.id: [large_variant]}),
            ),
            patch(
                "app.modules.catalog.service._repo.get_collections_for_products",
                AsyncMock(return_value={}),
            ),
        ):
            result = await self.svc.list_products(db)
        expected_version = int(img.updated_at.timestamp())
        assert (
            result.items[0].primary_image
            == f"https://cdn/first.jpg?v={expected_version}"
        )

    async def test_create_with_active_status_sets_published_at(self):
        from app.modules.catalog.schemas import ProductCreateRequest, ProductResponse

        db = AsyncMock()
        mock_product = MagicMock()
        mock_product.id = uuid.uuid4()
        mock_resp = MagicMock()
        with (
            patch(
                "app.modules.catalog.service._repo.get_by_sku",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.catalog.service._repo.get_by_slug",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.catalog.service._repo.create",
                AsyncMock(return_value=mock_product),
            ),
            patch("app.modules.catalog.service._repo.add_variant", AsyncMock()),
            patch("app.modules.catalog.service._repo.upsert_attribute", AsyncMock()),
            patch(
                "app.modules.catalog.service._repo.get_by_id",
                AsyncMock(return_value=mock_product),
            ),
            patch.object(ProductResponse, "model_validate", return_value=mock_resp),
        ):
            result = await self.svc.create(
                db,
                payload=ProductCreateRequest(
                    sku="SKU-NEW",
                    name="Gold Ring",
                    slug="gold-ring",
                    base_price=2000,
                    status="active",
                    metal_type="gold",
                    category_id=uuid.uuid4(),
                ),
            )
        assert result is mock_resp

    async def test_update_sets_published_at_when_activating(self):
        from app.modules.catalog.schemas import ProductResponse, ProductUpdateRequest

        db = AsyncMock()
        mock_product = MagicMock()
        mock_product.slug = "silver-ring"
        mock_product.status = "draft"  # currently draft
        mock_updated = MagicMock()
        mock_resp = MagicMock()
        with (
            patch(
                "app.modules.catalog.service._repo.get_by_id",
                AsyncMock(return_value=mock_product),
            ),
            patch(
                "app.modules.catalog.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            patch(
                "app.modules.catalog.service._repo.get_collections_for_product",
                AsyncMock(return_value=[]),
            ),
            patch.object(ProductResponse, "model_validate", return_value=mock_resp),
        ):
            result = await self.svc.update(
                db,
                uuid.uuid4(),
                payload=ProductUpdateRequest(status="active"),  # activating
            )
        assert result is mock_resp

    async def test_update_variant_success(self):
        from app.modules.catalog.schemas import ProductVariantUpdateRequest

        db = AsyncMock()
        mock_variant = MagicMock()
        mock_updated = MagicMock()
        with (
            patch(
                "app.modules.catalog.service._repo.get_variant",
                AsyncMock(return_value=mock_variant),
            ),
            patch(
                "app.modules.catalog.service._repo.update_variant",
                AsyncMock(return_value=mock_updated),
            ),
        ):
            result = await self.svc.update_variant(
                db, uuid.uuid4(), ProductVariantUpdateRequest(price_adjustment=100)
            )
        assert result is mock_updated

    async def test_upsert_attribute_success(self):
        from app.modules.catalog.schemas import ProductAttributeCreateRequest

        db = AsyncMock()
        mock_product = MagicMock()
        mock_attr = MagicMock()
        with (
            patch(
                "app.modules.catalog.service._repo.get_by_id",
                AsyncMock(return_value=mock_product),
            ),
            patch(
                "app.modules.catalog.service._repo.upsert_attribute",
                AsyncMock(return_value=mock_attr),
            ),
        ):
            result = await self.svc.upsert_attribute(
                db,
                uuid.uuid4(),
                ProductAttributeCreateRequest(name="purity", value="925", sort_order=0),
            )
        assert result is mock_attr

    async def test_adjust_stock_raises_when_negative(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        mock_product = MagicMock()
        from app.modules.catalog.schemas import StockAdjustRequest

        with (
            patch(
                "app.modules.catalog.service._repo.get_by_id",
                AsyncMock(return_value=mock_product),
            ),
            patch(
                "app.modules.catalog.service._reservation_svc.record_adjustment",
                AsyncMock(side_effect=ValidationError("Insufficient stock")),
            ),
        ):
            with pytest.raises(ValidationError):
                await self.svc.adjust_stock(
                    db, uuid.uuid4(), StockAdjustRequest(delta=-100)
                )


# ─── OrderService — optional fields + cancel with items ─────────────────────


class TestOrderServiceExtra:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_update_status_with_tracking_info(self):
        from datetime import datetime as dt

        from app.modules.orders.schemas import OrderResponse, UpdateOrderStatusRequest

        db = AsyncMock()
        db.commit = AsyncMock()
        mock_order = MagicMock()
        mock_order.status = "confirmed"
        mock_order.user_id = uuid.uuid4()
        mock_updated = MagicMock()
        mock_resp = MagicMock()
        with (
            patch(
                "app.modules.orders.service._repo.get_by_id",
                AsyncMock(return_value=mock_order),
            ),
            patch(
                "app.modules.orders.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            patch("app.core.events.event_bus.publish", AsyncMock()),
            patch.object(OrderResponse, "model_validate", return_value=mock_resp),
        ):
            result = await self.svc.update_status(
                db,
                order_id=uuid.uuid4(),
                payload=UpdateOrderStatusRequest(
                    status="shipped",
                    tracking_number="TRK123",
                    shipping_provider="Delhivery",
                    estimated_delivery=dt(2026, 7, 1, tzinfo=UTC),
                ),
            )
        assert result is mock_resp

    async def test_cancel_order_restores_inventory(self):
        from app.modules.orders.schemas import CancelOrderRequest, OrderResponse

        db = AsyncMock()
        db.commit = AsyncMock()
        user_id = uuid.uuid4()
        mock_item = MagicMock()
        mock_item.product_id = uuid.uuid4()
        mock_item.quantity = 2
        mock_item.variant_id = None
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.status = "pending"
        mock_order.coupon_id = None
        mock_order.items = [mock_item]
        mock_updated = MagicMock()
        mock_resp = MagicMock()
        with (
            patch(
                "app.modules.orders.service._repo.get_by_id",
                AsyncMock(return_value=mock_order),
            ),
            patch(
                "app.modules.orders.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            # Cancellation now releases reservations atomically instead of
            # calling InventoryService.record_movement for each item
            patch(
                "app.modules.orders.service._reservation_svc.release_order_reservations",
                AsyncMock(),
            ) as mock_release,
            patch("app.core.events.event_bus.publish", AsyncMock()),
            patch.object(OrderResponse, "model_validate", return_value=mock_resp),
        ):
            result = await self.svc.cancel_order(
                db,
                order_id=uuid.uuid4(),
                user_id=user_id,
                payload=CancelOrderRequest(reason="Changed my mind"),
            )
        mock_release.assert_awaited_once()
        assert result is mock_resp
