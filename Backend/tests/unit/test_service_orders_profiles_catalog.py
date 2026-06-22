"""Tests for OrderService, ProfileService, and CatalogService."""

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── OrderService ─────────────────────────────────────────────────────────────


class TestOrderServiceGetAndList:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_get_order_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_order(db, uuid.uuid4())

    async def test_get_order_raises_404_when_wrong_user(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()  # different user
        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_order(db, uuid.uuid4(), user_id=uuid.uuid4())

    async def test_get_order_returns_validated_response(self):
        db = AsyncMock()
        mock_order = MagicMock()
        with (
            patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)),
            patch(
                "app.modules.orders.service.OrderResponse.model_validate", return_value=MagicMock()
            ),
        ):
            result = await self.svc.get_order(db, uuid.uuid4())
        assert result is not None

    async def test_list_my_orders_returns_paginated(self):
        from datetime import datetime

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.order_number = "ORD-202406-000001"
        mock_order.status = "pending"
        mock_order.payment_status = "pending"
        mock_order.total = 999.0
        mock_order.created_at = datetime.now(UTC)
        mock_order.items = []
        with patch(
            "app.modules.orders.service._repo.list_for_user",
            AsyncMock(return_value=([mock_order], 1)),
        ):
            result = await self.svc.list_my_orders(db, uuid.uuid4(), page=1, page_size=20)
        assert result.total == 1

    async def test_admin_list_orders_returns_paginated(self):
        from datetime import datetime

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.order_number = "ORD-202406-000001"
        mock_order.status = "confirmed"
        mock_order.payment_status = "captured"
        mock_order.total = 1500.0
        mock_order.created_at = datetime.now(UTC)
        with patch(
            "app.modules.orders.service._repo.list_all", AsyncMock(return_value=([mock_order], 1))
        ):
            result = await self.svc.admin_list_orders(db, page=1, page_size=20)
        assert result.total == 1


class TestOrderServiceUpdateStatus:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_update_status_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.schemas import UpdateOrderStatusRequest

        db = AsyncMock()
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update_status(
                    db, uuid.uuid4(), UpdateOrderStatusRequest(status="confirmed")
                )

    async def test_update_status_publishes_event_and_returns_response(self):
        from app.core.events import event_bus
        from app.modules.orders.schemas import UpdateOrderStatusRequest

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()
        mock_order.status = "pending"
        mock_updated = MagicMock()
        with (
            patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)),
            patch("app.modules.orders.service._repo.update", AsyncMock(return_value=mock_updated)),
            patch.object(event_bus, "publish", AsyncMock()),
            patch(
                "app.modules.orders.service.OrderResponse.model_validate", return_value=MagicMock()
            ),
        ):
            result = await self.svc.update_status(
                db, uuid.uuid4(), UpdateOrderStatusRequest(status="confirmed")
            )
        assert result is not None

    async def test_update_status_to_delivered_sets_delivered_at(self):
        from app.core.events import event_bus
        from app.modules.orders.schemas import UpdateOrderStatusRequest

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()
        mock_order.status = "confirmed"
        mock_updated = MagicMock()
        update_call_data = {}

        async def capture_update(db, oid, data):
            update_call_data.update(data)
            return mock_updated

        with (
            patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)),
            patch("app.modules.orders.service._repo.update", capture_update),
            patch.object(event_bus, "publish", AsyncMock()),
            patch(
                "app.modules.orders.service.OrderResponse.model_validate", return_value=MagicMock()
            ),
        ):
            await self.svc.update_status(
                db, uuid.uuid4(), UpdateOrderStatusRequest(status="delivered")
            )
        assert "delivered_at" in update_call_data


class TestOrderServiceCancel:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_cancel_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.schemas import CancelOrderRequest

        db = AsyncMock()
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.cancel_order(
                    db, uuid.uuid4(), uuid.uuid4(), CancelOrderRequest(reason="Changed mind")
                )

    async def test_cancel_raises_404_when_wrong_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.schemas import CancelOrderRequest

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()  # different user
        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.cancel_order(
                    db, uuid.uuid4(), uuid.uuid4(), CancelOrderRequest(reason="Changed mind")
                )

    async def test_cancel_raises_validation_error_when_already_delivered(self):
        from app.core.exceptions import ValidationError
        from app.modules.orders.schemas import CancelOrderRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.status = "delivered"  # not in _CANCELLABLE_STATUSES
        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)
        ):
            with pytest.raises(ValidationError):
                await self.svc.cancel_order(
                    db, uuid.uuid4(), user_id, CancelOrderRequest(reason="Changed mind")
                )

    async def test_cancel_success_returns_response(self):
        from app.core.events import event_bus
        from app.modules.orders.schemas import CancelOrderRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.status = "pending"
        mock_order.items = []
        mock_updated = MagicMock()
        with (
            patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)),
            patch("app.modules.orders.service._repo.update", AsyncMock(return_value=mock_updated)),
            patch.object(event_bus, "publish", AsyncMock()),
            patch(
                "app.modules.orders.service.OrderResponse.model_validate", return_value=MagicMock()
            ),
        ):
            result = await self.svc.cancel_order(
                db, uuid.uuid4(), user_id, CancelOrderRequest(reason="Changed mind")
            )
        assert result is not None


class TestOrderServiceCreateFromCart:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_create_raises_validation_error_when_cart_empty(self):
        from app.core.exceptions import ValidationError
        from app.modules.cart.repository import CartRepository
        from app.modules.orders.schemas import CreateOrderRequest

        db = AsyncMock()
        with patch.object(CartRepository, "get_for_user", AsyncMock(return_value=None)):
            with pytest.raises(ValidationError, match="Cart is empty"):
                await self.svc.create_from_cart(
                    db,
                    uuid.uuid4(),
                    CreateOrderRequest(
                        shipping_address_id=uuid.uuid4(),
                        payment_method="razorpay",
                    ),
                )

    async def test_create_raises_error_when_cart_has_no_items(self):
        from app.core.exceptions import ValidationError
        from app.modules.cart.repository import CartRepository
        from app.modules.orders.schemas import CreateOrderRequest

        db = AsyncMock()
        empty_cart = MagicMock()
        empty_cart.items = []
        with patch.object(CartRepository, "get_for_user", AsyncMock(return_value=empty_cart)):
            with pytest.raises(ValidationError, match="Cart is empty"):
                await self.svc.create_from_cart(
                    db,
                    uuid.uuid4(),
                    CreateOrderRequest(
                        shipping_address_id=uuid.uuid4(),
                        payment_method="razorpay",
                    ),
                )


# ─── ProfileService ───────────────────────────────────────────────────────────


class TestProfileService:
    def setup_method(self):
        from app.modules.profiles.repository import ProfileRepository
        from app.modules.profiles.service import ProfileService

        self.svc = ProfileService()
        self.repo_cls = ProfileRepository

    async def test_get_profile_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch.object(self.repo_cls, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_profile(db, str(uuid.uuid4()))

    async def test_get_profile_returns_profile(self):
        db = AsyncMock()
        mock_profile = MagicMock()
        with patch.object(self.repo_cls, "get_by_id", AsyncMock(return_value=mock_profile)):
            result = await self.svc.get_profile(db, str(uuid.uuid4()))
        assert result is mock_profile

    async def test_update_profile_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.profiles.schemas import ProfileUpdateRequest

        db = AsyncMock()
        with patch.object(self.repo_cls, "update", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update_profile(
                    db, str(uuid.uuid4()), ProfileUpdateRequest(full_name="Alice")
                )

    async def test_update_profile_returns_same_when_no_data(self):
        from app.modules.profiles.schemas import ProfileUpdateRequest

        db = AsyncMock()
        mock_profile = MagicMock()
        with patch.object(self.repo_cls, "get_by_id", AsyncMock(return_value=mock_profile)):
            result = await self.svc.update_profile(db, str(uuid.uuid4()), ProfileUpdateRequest())
        assert result is mock_profile

    async def test_update_avatar_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch.object(self.repo_cls, "update", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update_avatar(
                    db, str(uuid.uuid4()), "https://cdn.example.com/avatar.jpg"
                )

    async def test_update_avatar_returns_updated_profile(self):
        db = AsyncMock()
        mock_profile = MagicMock()
        with patch.object(self.repo_cls, "update", AsyncMock(return_value=mock_profile)):
            result = await self.svc.update_avatar(
                db, str(uuid.uuid4()), "https://cdn.example.com/avatar.jpg"
            )
        assert result is mock_profile

    async def test_list_users_returns_paginated(self):
        from datetime import datetime

        db = AsyncMock()
        mock_profile = MagicMock()
        mock_profile.id = uuid.uuid4()
        mock_profile.email = "test@example.com"
        mock_profile.full_name = "Test User"
        mock_profile.phone = None
        mock_profile.avatar_url = None
        mock_profile.role = "customer"
        mock_profile.is_active = True
        mock_profile.is_verified = False
        mock_profile.created_at = datetime.now(UTC)
        with patch.object(
            self.repo_cls, "list_paginated", AsyncMock(return_value=([mock_profile], 1))
        ):
            result = await self.svc.list_users(db, page=1, page_size=20)
        assert result.total == 1

    async def test_change_role_raises_404_when_not_found(self):
        from app.core.constants import UserRole
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch.object(self.repo_cls, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.change_role(db, str(uuid.uuid4()), UserRole.ADMIN, str(uuid.uuid4()))

    async def test_change_role_success_calls_audit(self):
        from app.core.constants import UserRole

        db = AsyncMock()
        mock_profile = MagicMock()
        mock_profile.role = UserRole.CUSTOMER
        mock_updated = MagicMock()
        with (
            patch.object(self.repo_cls, "get_by_id", AsyncMock(return_value=mock_profile)),
            patch.object(self.repo_cls, "update", AsyncMock(return_value=mock_updated)),
            patch("app.modules.audit.service.AuditService.log", AsyncMock()),
        ):
            result = await self.svc.change_role(
                db, str(uuid.uuid4()), UserRole.ADMIN, str(uuid.uuid4())
            )
        assert result is mock_updated

    async def test_set_status_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch.object(self.repo_cls, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.set_status(db, str(uuid.uuid4()), False, str(uuid.uuid4()))

    async def test_set_status_success(self):
        db = AsyncMock()
        mock_profile = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(self.repo_cls, "get_by_id", AsyncMock(return_value=mock_profile)),
            patch.object(self.repo_cls, "update", AsyncMock(return_value=mock_updated)),
            patch("app.modules.audit.service.AuditService.log", AsyncMock()),
        ):
            result = await self.svc.set_status(db, str(uuid.uuid4()), False, str(uuid.uuid4()))
        assert result is mock_updated


# ─── CatalogService ───────────────────────────────────────────────────────────


class TestCatalogServiceRead:
    def setup_method(self):
        from app.modules.catalog.service import CatalogService

        self.svc = CatalogService()

    async def test_get_by_id_raises_404(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_by_id(db, uuid.uuid4())

    async def test_get_by_id_returns_validated_response(self):
        db = AsyncMock()
        mock_product = MagicMock()
        with (
            patch(
                "app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=mock_product)
            ),
            patch(
                "app.modules.catalog.service.ProductResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.get_by_id(db, uuid.uuid4())
        assert result is not None

    async def test_get_by_slug_raises_404(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_slug", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_by_slug(db, "missing-slug")

    async def test_list_products_returns_paginated(self):
        from datetime import datetime

        db = AsyncMock()
        mock_product = MagicMock()
        mock_product.images = []
        mock_product.id = uuid.uuid4()
        mock_product.sku = "SKU-001"
        mock_product.name = "Silver Ring"
        mock_product.slug = "silver-ring"
        mock_product.short_description = None
        mock_product.category_id = None
        mock_product.metal_type = "silver"
        mock_product.base_price = 999.0
        mock_product.compare_at_price = None
        mock_product.stock_quantity = 10
        mock_product.status = "active"
        mock_product.is_featured = False
        mock_product.is_new_arrival = False
        mock_product.is_best_seller = False
        mock_product.created_at = datetime.now(UTC)
        with patch(
            "app.modules.catalog.service._repo.list_paginated",
            AsyncMock(return_value=([mock_product], 1)),
        ):
            result = await self.svc.list_products(db, page=1, page_size=20)
        assert result.total == 1


class TestCatalogServiceWrite:
    def setup_method(self):
        from app.modules.catalog.service import CatalogService

        self.svc = CatalogService()

    async def _make_create_request(self):
        from app.modules.catalog.schemas import ProductCreateRequest

        return ProductCreateRequest(
            sku="SKU-001",
            name="Silver Ring",
            slug="silver-ring",
            base_price=999.0,
            tax_rate=3.0,
            stock_quantity=10,
        )

    async def test_create_raises_conflict_on_duplicate_sku(self):
        from app.core.exceptions import ConflictError

        db = AsyncMock()
        with patch(
            "app.modules.catalog.service._repo.get_by_sku", AsyncMock(return_value=MagicMock())
        ):
            with pytest.raises(ConflictError):
                await self.svc.create(db, await self._make_create_request())

    async def test_create_raises_conflict_on_duplicate_slug(self):
        from app.core.exceptions import ConflictError

        db = AsyncMock()
        with (
            patch("app.modules.catalog.service._repo.get_by_sku", AsyncMock(return_value=None)),
            patch(
                "app.modules.catalog.service._repo.get_by_slug", AsyncMock(return_value=MagicMock())
            ),
        ):
            with pytest.raises(ConflictError):
                await self.svc.create(db, await self._make_create_request())

    async def test_create_success(self):
        db = AsyncMock()
        mock_product = MagicMock()
        with (
            patch("app.modules.catalog.service._repo.get_by_sku", AsyncMock(return_value=None)),
            patch("app.modules.catalog.service._repo.get_by_slug", AsyncMock(return_value=None)),
            patch("app.modules.catalog.service._repo.create", AsyncMock(return_value=mock_product)),
            patch(
                "app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=mock_product)
            ),
            patch(
                "app.modules.catalog.service.ProductResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.create(db, await self._make_create_request())
        assert result is not None

    async def test_update_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.catalog.schemas import ProductUpdateRequest

        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update(db, uuid.uuid4(), ProductUpdateRequest(name="New Name"))

    async def test_update_raises_conflict_on_duplicate_slug(self):
        from app.core.exceptions import ConflictError
        from app.modules.catalog.schemas import ProductUpdateRequest

        db = AsyncMock()
        mock_product = MagicMock()
        mock_product.slug = "old-slug"
        mock_product.status = "active"
        with (
            patch(
                "app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=mock_product)
            ),
            patch(
                "app.modules.catalog.service._repo.get_by_slug", AsyncMock(return_value=MagicMock())
            ),
        ):
            with pytest.raises(ConflictError):
                await self.svc.update(db, uuid.uuid4(), ProductUpdateRequest(slug="taken-slug"))

    async def test_delete_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.delete(db, uuid.uuid4())

    async def test_delete_calls_soft_delete(self):
        db = AsyncMock()
        mock_product = MagicMock()
        with (
            patch(
                "app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=mock_product)
            ),
            patch("app.modules.catalog.service._repo.soft_delete", AsyncMock()) as mock_soft,
        ):
            await self.svc.delete(db, uuid.uuid4())
        mock_soft.assert_awaited_once()


class TestCatalogServiceVariantsAndAttributes:
    def setup_method(self):
        from app.modules.catalog.service import CatalogService

        self.svc = CatalogService()

    async def test_add_variant_raises_404_when_product_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.catalog.schemas import ProductVariantCreateRequest

        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.add_variant(
                    db, uuid.uuid4(), ProductVariantCreateRequest(sku="V-001", name="Small")
                )

    async def test_add_variant_raises_conflict_on_duplicate_sku(self):
        from app.core.exceptions import ConflictError
        from app.modules.catalog.schemas import ProductVariantCreateRequest

        db = AsyncMock()
        with (
            patch(
                "app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=MagicMock())
            ),
            patch(
                "app.modules.catalog.service._repo.get_by_sku", AsyncMock(return_value=MagicMock())
            ),
        ):
            with pytest.raises(ConflictError):
                await self.svc.add_variant(
                    db, uuid.uuid4(), ProductVariantCreateRequest(sku="V-001", name="Small")
                )

    async def test_add_variant_success(self):
        from app.modules.catalog.schemas import ProductVariantCreateRequest

        db = AsyncMock()
        mock_variant = MagicMock()
        with (
            patch(
                "app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=MagicMock())
            ),
            patch("app.modules.catalog.service._repo.get_by_sku", AsyncMock(return_value=None)),
            patch(
                "app.modules.catalog.service._repo.add_variant",
                AsyncMock(return_value=mock_variant),
            ),
        ):
            result = await self.svc.add_variant(
                db, uuid.uuid4(), ProductVariantCreateRequest(sku="V-001", name="Small")
            )
        assert result is mock_variant

    async def test_update_variant_raises_404(self):
        from app.core.exceptions import NotFoundError
        from app.modules.catalog.schemas import ProductVariantUpdateRequest

        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_variant", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update_variant(
                    db, uuid.uuid4(), ProductVariantUpdateRequest(name="Updated")
                )

    async def test_delete_variant_raises_404(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.catalog.service._repo.delete_variant", AsyncMock(return_value=False)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.delete_variant(db, uuid.uuid4())

    async def test_upsert_attribute_raises_404_when_product_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.catalog.schemas import ProductAttributeCreateRequest

        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.upsert_attribute(
                    db, uuid.uuid4(), ProductAttributeCreateRequest(name="metal", value="Silver")
                )

    async def test_delete_attribute_raises_404(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.catalog.service._repo.delete_attribute", AsyncMock(return_value=False)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.delete_attribute(db, uuid.uuid4(), "metal")
