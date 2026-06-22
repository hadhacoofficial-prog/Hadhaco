"""Repository unit tests — mocked AsyncSession, no real DB required."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import app.modules.addresses.models  # noqa: F401
import app.modules.cart.models  # noqa: F401

# Force all SQLAlchemy mappers to configure before tests run.
# Product has relationship("Category", ...) so both must be imported together.
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

# ─── Mock helpers ─────────────────────────────────────────────────────────────


def _scalars_result(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _scalar_one(value):
    r = MagicMock()
    r.scalar_one.return_value = value
    return r


def _scalar_one_or_none(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _fetchone(value):
    r = MagicMock()
    r.fetchone.return_value = value
    return r


def _all_result(rows):
    """For queries that return tuple rows, e.g. select(Model, subquery).
    rows should be a list of tuples: [(obj, extra_col), ...]
    """
    r = MagicMock()
    r.all.return_value = rows
    return r


def _first(value):
    """Mock result.first() → value"""
    r = MagicMock()
    r.first.return_value = value
    return r


def _db(*results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


# ─── AddressRepository ────────────────────────────────────────────────────────


class TestAddressRepository:
    def setup_method(self):
        from app.modules.addresses.repository import AddressRepository

        self.repo = AddressRepository()

    async def test_list_for_user_returns_list(self):
        mock_addr = MagicMock()
        db = _db(_scalars_result([mock_addr]))
        result = await self.repo.list_for_user(db, uuid.uuid4())
        assert result == [mock_addr]

    async def test_list_for_user_returns_empty(self):
        db = _db(_scalars_result([]))
        result = await self.repo.list_for_user(db, uuid.uuid4())
        assert result == []

    async def test_get_returns_address(self):
        mock_addr = MagicMock()
        db = _db(_scalar_one_or_none(mock_addr))
        result = await self.repo.get(db, uuid.uuid4(), uuid.uuid4())
        assert result is mock_addr

    async def test_get_returns_none_when_not_found(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get(db, uuid.uuid4(), uuid.uuid4())
        assert result is None

    async def test_count_for_user_returns_count(self):
        db = _db(_scalar_one(3))
        result = await self.repo.count_for_user(db, uuid.uuid4())
        assert result == 3

    async def test_create_adds_flushes_and_refreshes(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.repo.create(
            db,
            {
                "id": uuid.uuid4(),
                "user_id": uuid.uuid4(),
                "type": "shipping",
                "full_name": "Alice",
                "line1": "123 Main",
                "city": "Mumbai",
                "state": "MH",
                "postal_code": "400001",
                "country": "IN",
            },
        )
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_update_calls_execute_twice(self):
        mock_addr = MagicMock()
        db = _db(MagicMock(), _scalar_one_or_none(mock_addr))
        await self.repo.update(db, uuid.uuid4(), {"full_name": "Bob"})
        assert db.execute.await_count == 2

    async def test_clear_default_executes_update(self):
        db = _db(MagicMock())
        await self.repo.clear_default(db, uuid.uuid4(), "shipping")
        db.execute.assert_awaited_once()

    async def test_soft_delete_executes_update(self):
        db = _db(MagicMock())
        await self.repo.soft_delete(db, uuid.uuid4())
        db.execute.assert_awaited_once()


# ─── ProductRepository (CatalogRepository) ───────────────────────────────────


class TestProductRepository:
    def setup_method(self):
        from app.modules.catalog.repository import ProductRepository

        self.repo = ProductRepository()

    async def test_get_by_id_returns_product(self):
        mock_prod = MagicMock()
        db = _db(_scalar_one_or_none(mock_prod))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_prod

    async def test_get_by_id_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is None

    async def test_get_by_slug_returns_product(self):
        mock_prod = MagicMock()
        db = _db(_scalar_one_or_none(mock_prod))
        result = await self.repo.get_by_slug(db, "silver-ring")
        assert result is mock_prod

    async def test_get_by_sku_returns_product(self):
        mock_prod = MagicMock()
        db = _db(_scalar_one_or_none(mock_prod))
        result = await self.repo.get_by_sku(db, "SR-001")
        assert result is mock_prod

    async def test_list_paginated_returns_items_and_total(self):
        mock_prod = MagicMock()
        db = _db(_scalar_one(5), _scalars_result([mock_prod]))
        items, total = await self.repo.list_paginated(db)
        assert total == 5
        assert items == [mock_prod]

    async def test_list_paginated_with_all_filters(self):
        db = _db(_scalar_one(0), _scalars_result([]))
        items, total = await self.repo.list_paginated(
            db,
            status="active",
            category_id=uuid.uuid4(),
            metal_type="silver",
            gender="female",
            is_featured=True,
            is_new_arrival=True,
            is_best_seller=False,
            min_price=100,
            max_price=5000,
            search="ring",
            sort_by="base_price",
            sort_dir="asc",
        )
        assert total == 0
        assert items == []

    async def test_create_adds_and_refreshes(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.repo.create(
            db,
            {
                "id": uuid.uuid4(),
                "name": "Silver Ring",
                "slug": "silver-ring",
                "sku": "SR-001",
                "base_price": 999.0,
                "tax_rate": 3.0,
            },
        )
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once()

    async def test_update_executes_and_refetches(self):
        mock_prod = MagicMock()
        db = _db(MagicMock(), _scalar_one_or_none(mock_prod))
        result = await self.repo.update(db, uuid.uuid4(), {"name": "Updated Ring"})
        assert result is mock_prod

    async def test_soft_delete_executes_update(self):
        db = _db(MagicMock())
        await self.repo.soft_delete(db, uuid.uuid4())
        db.execute.assert_awaited_once()

    async def test_add_image_adds_and_refreshes(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.repo.add_image(
            db,
            {
                "id": uuid.uuid4(),
                "product_id": uuid.uuid4(),
                "url": "https://cdn/img.jpg",
                "sort_order": 0,
            },
        )
        db.add.assert_called_once()

    async def test_delete_image_returns_false_when_not_found(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.delete_image(db, uuid.uuid4())
        assert result is False

    async def test_delete_image_returns_true_when_found(self):
        mock_img = MagicMock()
        db = _db(_scalar_one_or_none(mock_img))
        db.delete = AsyncMock()
        result = await self.repo.delete_image(db, uuid.uuid4())
        assert result is True
        db.delete.assert_awaited_once_with(mock_img)

    async def test_set_primary_image_executes_twice(self):
        db = _db(MagicMock(), MagicMock())
        await self.repo.set_primary_image(db, uuid.uuid4(), uuid.uuid4())
        assert db.execute.await_count == 2

    async def test_add_variant_adds_and_refreshes(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.repo.add_variant(
            db,
            {
                "id": uuid.uuid4(),
                "product_id": uuid.uuid4(),
                "name": "Large",
                "sku": "SR-001-L",
            },
        )
        db.add.assert_called_once()

    async def test_get_variant_returns_variant(self):
        mock_var = MagicMock()
        db = _db(_scalar_one_or_none(mock_var))
        result = await self.repo.get_variant(db, uuid.uuid4())
        assert result is mock_var

    async def test_update_variant_executes_and_refetches(self):
        mock_var = MagicMock()
        db = _db(MagicMock(), _scalar_one_or_none(mock_var))
        result = await self.repo.update_variant(db, uuid.uuid4(), {"name": "XL"})
        assert result is mock_var

    async def test_delete_variant_returns_false_when_not_found(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.delete_variant(db, uuid.uuid4())
        assert result is False

    async def test_delete_variant_returns_true_when_found(self):
        mock_var = MagicMock()
        db = _db(_scalar_one_or_none(mock_var))
        db.delete = AsyncMock()
        result = await self.repo.delete_variant(db, uuid.uuid4())
        assert result is True

    async def test_upsert_attribute_updates_existing(self):
        mock_attr = MagicMock()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(mock_attr))
        db.flush = AsyncMock()
        result = await self.repo.upsert_attribute(db, uuid.uuid4(), "Color", "Silver")
        assert result is mock_attr
        assert mock_attr.value == "Silver"

    async def test_upsert_attribute_creates_new(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        db.add = MagicMock()
        db.flush = AsyncMock()
        await self.repo.upsert_attribute(db, uuid.uuid4(), "Color", "Gold")
        db.add.assert_called_once()

    async def test_delete_attribute_returns_false_when_not_found(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.delete_attribute(db, uuid.uuid4(), "Color")
        assert result is False

    async def test_delete_attribute_returns_true_when_found(self):
        mock_attr = MagicMock()
        db = _db(_scalar_one_or_none(mock_attr))
        db.delete = AsyncMock()
        result = await self.repo.delete_attribute(db, uuid.uuid4(), "Color")
        assert result is True

    async def test_adjust_stock_returns_new_quantity(self):
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: 15
        db = _db(_fetchone(mock_row))
        result = await self.repo.adjust_stock(db, uuid.uuid4(), 5)
        assert result == 15

    async def test_adjust_stock_returns_zero_when_no_row(self):
        db = _db(_fetchone(None))
        result = await self.repo.adjust_stock(db, uuid.uuid4(), 5)
        assert result == 0


# ─── OrderRepository ──────────────────────────────────────────────────────────


class TestOrderRepository:
    def setup_method(self):
        from app.modules.orders.repository import OrderRepository

        self.repo = OrderRepository()

    async def test_get_by_id_returns_order(self):
        mock_order = MagicMock()
        db = _db(_scalar_one_or_none(mock_order))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_order

    async def test_get_by_order_number_returns_order(self):
        mock_order = MagicMock()
        db = _db(_scalar_one_or_none(mock_order))
        result = await self.repo.get_by_order_number(db, "HDH-202601-000001")
        assert result is mock_order

    async def test_list_for_user_with_pagination(self):
        mock_order = MagicMock()
        # list_for_user selects (Order, item_count_subquery), so result.all()
        # returns rows of (order_obj, item_count) tuples — not scalars
        db = _db(_scalar_one(3), _all_result([(mock_order, 2)]))
        items, total = await self.repo.list_for_user(db, uuid.uuid4())
        assert total == 3
        assert items == [mock_order]

    async def test_list_for_user_with_status_filter(self):
        db = _db(_scalar_one(0), _scalars_result([]))
        items, total = await self.repo.list_for_user(db, uuid.uuid4(), status="confirmed")
        assert total == 0

    async def test_list_all_with_no_filters(self):
        db = _db(_scalar_one(10), _scalars_result([]))
        items, total = await self.repo.list_all(db)
        assert total == 10

    async def test_list_all_with_all_filters(self):
        db = _db(_scalar_one(0), _scalars_result([]))
        items, total = await self.repo.list_all(
            db,
            status="confirmed",
            payment_status="paid",
            user_id=uuid.uuid4(),
            search="HDH-2026",
        )
        assert total == 0

    async def test_create_returns_order(self):
        db = AsyncMock()
        db.add = MagicMock()
        result = await self.repo.create(db, {"id": uuid.uuid4(), "user_id": uuid.uuid4()})
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_add_item_returns_item(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.repo.add_item(
            db,
            {
                "id": uuid.uuid4(),
                "order_id": uuid.uuid4(),
                "product_id": uuid.uuid4(),
                "quantity": 2,
                "unit_price": 999.0,
                "product_name": "Ring",
                "product_sku": "SR-001",
                "tax_rate": 3.0,
                "tax_amount": 30.0,
                "line_total": 1029.0,
            },
        )
        db.add.assert_called_once()

    async def test_update_executes_and_refetches(self):
        mock_order = MagicMock()
        db = _db(MagicMock(), _scalar_one_or_none(mock_order))
        result = await self.repo.update(db, uuid.uuid4(), {"status": "confirmed"})
        assert result is mock_order

    async def test_generate_order_number_format(self):
        db = _db(_scalar_one(0))
        result = await self.repo.generate_order_number(db)
        assert result.startswith("HDH-")
        assert len(result) > 10


# ─── ReviewRepository ─────────────────────────────────────────────────────────


class TestReviewRepository:
    def setup_method(self):
        from app.modules.reviews.repository import ReviewRepository

        self.repo = ReviewRepository()

    async def test_get_by_id_returns_review(self):
        mock_rev = MagicMock()
        db = _db(_scalar_one_or_none(mock_rev))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_rev

    async def test_get_by_id_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is None

    async def test_has_delivered_order_item_returns_true(self):
        db = _db(_fetchone(MagicMock()))
        result = await self.repo.has_delivered_order_item(
            db, user_id=uuid.uuid4(), product_id=uuid.uuid4()
        )
        assert result is True

    async def test_has_delivered_order_item_returns_false(self):
        db = _db(_fetchone(None))
        result = await self.repo.has_delivered_order_item(
            db, user_id=uuid.uuid4(), product_id=uuid.uuid4()
        )
        assert result is False

    async def test_has_any_review_returns_true(self):
        mock_rev = MagicMock()
        db = _db(_scalar_one_or_none(mock_rev))
        result = await self.repo.has_any_review(db, order_id=uuid.uuid4())
        assert result is True

    async def test_has_any_review_returns_false(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.has_any_review(db, order_id=uuid.uuid4())
        assert result is False

    async def test_get_by_product_user_returns_review(self):
        mock_rev = MagicMock()
        db = _db(_scalar_one_or_none(mock_rev))
        result = await self.repo.get_by_product_user(
            db, product_id=uuid.uuid4(), user_id=uuid.uuid4()
        )
        assert result is mock_rev

    async def test_create_review_adds_and_refreshes(self):
        db = AsyncMock()
        db.add = MagicMock()
        result = await self.repo.create(
            db,
            id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            rating=5,
            is_approved=False,
        )
        db.add.assert_called_once()

    async def test_update_review_modifies_in_place(self):
        db = AsyncMock()
        db.add = MagicMock()
        mock_review = MagicMock()
        await self.repo.update(db, mock_review, {"rating": 4, "body": "Great!"})
        assert mock_review.rating == 4
        db.add.assert_called_once_with(mock_review)

    async def test_soft_delete_sets_deleted_at(self):
        db = AsyncMock()
        db.add = MagicMock()
        mock_review = MagicMock()
        mock_review.deleted_at = None
        await self.repo.soft_delete(db, mock_review)
        assert mock_review.deleted_at is not None

    async def test_list_for_product_returns_reviews(self):
        mock_rev = MagicMock()
        db = _db(_scalars_result([mock_rev]))
        result = await self.repo.list_for_product(db, product_id=uuid.uuid4())
        assert result == [mock_rev]

    async def test_list_pending_returns_reviews(self):
        mock_rev = MagicMock()
        db = _db(_scalars_result([mock_rev]))
        result = await self.repo.list_pending(db)
        assert result == [mock_rev]

    async def test_rating_summary_returns_none_when_no_data(self):
        db = _db(_fetchone(None))
        result = await self.repo.rating_summary(db, uuid.uuid4())
        assert result is None

    async def test_rating_summary_returns_dict_when_found(self):
        mock_row = MagicMock()
        mock_row._mapping = {"product_id": uuid.uuid4(), "review_count": 5, "average_rating": 4.2}
        db = _db(_fetchone(mock_row))
        result = await self.repo.rating_summary(db, uuid.uuid4())
        assert result is not None
        assert result["review_count"] == 5


# ─── InventoryRepository ──────────────────────────────────────────────────────


class TestInventoryRepository:
    def setup_method(self):
        from app.modules.inventory.repository import InventoryRepository

        self.repo = InventoryRepository()

    async def test_get_stock_snapshot_returns_dict(self):
        mock_row = MagicMock()
        mock_row._mapping = {"stock_quantity": 10, "low_stock_threshold": 5}
        db = _db(_fetchone(mock_row))
        result = await self.repo.get_stock_snapshot(db, uuid.uuid4())
        assert result is not None
        assert result["stock_quantity"] == 10

    async def test_get_stock_snapshot_returns_none_when_not_found(self):
        db = _db(_fetchone(None))
        result = await self.repo.get_stock_snapshot(db, uuid.uuid4())
        assert result is None

    async def test_record_movement_adds(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.repo.record(
            db,
            {
                "id": uuid.uuid4(),
                "product_id": uuid.uuid4(),
                "movement_type": "sale",
                "delta": -1,
                "quantity_before": 10,
                "quantity_after": 9,
            },
        )
        db.add.assert_called_once()

    async def test_list_for_product_returns_paginated(self):
        mock_mov = MagicMock()
        db = _db(_scalar_one(5), _scalars_result([mock_mov]))
        items, total = await self.repo.list_for_product(db, uuid.uuid4())
        assert total == 5
        assert items == [mock_mov]

    async def test_list_for_product_with_type_filter(self):
        db = _db(_scalar_one(0), _scalars_result([]))
        items, total = await self.repo.list_for_product(db, uuid.uuid4(), movement_type="sale")
        assert total == 0


# ─── CollectionRepository ────────────────────────────────────────────────────


class TestCollectionRepository:
    def setup_method(self):
        from app.modules.collections.repository import CollectionRepository

        self.repo = CollectionRepository()

    async def test_list_active_returns_list(self):
        mock_col = MagicMock()
        db = _db(_scalars_result([mock_col]))
        result = await self.repo.list_active(db)
        assert result == [mock_col]

    async def test_get_by_slug_returns_collection(self):
        mock_col = MagicMock()
        db = _db(_scalar_one_or_none(mock_col))
        result = await self.repo.get_by_slug(db, "silver-rings")
        assert result is mock_col

    async def test_get_by_id_returns_collection(self):
        mock_col = MagicMock()
        db = _db(_scalar_one_or_none(mock_col))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_col

    async def test_create_adds_and_refreshes(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.repo.create(db, {"id": uuid.uuid4(), "name": "Silver", "slug": "silver"})
        db.add.assert_called_once()

    async def test_update_executes_and_refetches(self):
        mock_col = MagicMock()
        db = _db(MagicMock(), _scalar_one_or_none(mock_col))
        result = await self.repo.update(db, uuid.uuid4(), {"name": "Gold"})
        assert result is mock_col

    async def test_soft_delete_executes_update(self):
        db = _db(MagicMock())
        await self.repo.soft_delete(db, uuid.uuid4())
        db.execute.assert_awaited_once()


# ─── CouponRepository ─────────────────────────────────────────────────────────


class TestCouponRepository:
    def setup_method(self):
        from app.modules.coupons.repository import CouponRepository

        self.repo = CouponRepository()

    async def test_get_by_code_returns_coupon(self):
        mock_coupon = MagicMock()
        db = _db(_scalar_one_or_none(mock_coupon))
        result = await self.repo.get_by_code(db, "SAVE10")
        assert result is mock_coupon

    async def test_get_by_id_returns_coupon(self):
        mock_coupon = MagicMock()
        db = _db(_scalar_one_or_none(mock_coupon))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_coupon

    async def test_list_all_returns_coupons(self):
        mock_coupon = MagicMock()
        db = _db(_scalars_result([mock_coupon]))
        result = await self.repo.list_all(db)
        assert result == [mock_coupon]

    async def test_list_all_with_active_filter(self):
        db = _db(_scalars_result([]))
        result = await self.repo.list_all(db, is_active=True)
        assert result == []

    async def test_create_adds_and_refreshes(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.repo.create(
            db,
            {
                "id": uuid.uuid4(),
                "code": "SAVE10",
                "coupon_type": "percentage",
                "value": 10,
                "min_order_amount": 0,
                "per_user_limit": 5,
                "is_active": True,
            },
        )
        db.add.assert_called_once()

    async def test_get_user_usage_count_returns_count(self):
        db = _db(_scalar_one(2))
        result = await self.repo.get_user_usage_count(db, uuid.uuid4(), uuid.uuid4())
        assert result == 2


# ─── ProfileRepository ────────────────────────────────────────────────────────


class TestProfileRepository:
    def setup_method(self):
        from app.modules.profiles.repository import ProfileRepository

        self.repo = ProfileRepository()

    async def test_get_by_id_returns_profile(self):
        mock_profile = MagicMock()
        db = _db(_scalar_one_or_none(mock_profile))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_profile

    async def test_get_by_email_returns_profile(self):
        mock_profile = MagicMock()
        db = _db(_scalar_one_or_none(mock_profile))
        result = await self.repo.get_by_email(db, "test@example.com")
        assert result is mock_profile

    async def test_list_paginated_returns_users(self):
        mock_profile = MagicMock()
        db = _db(_scalar_one(10), _scalars_result([mock_profile]))
        items, total = await self.repo.list_paginated(db)
        assert total == 10
        assert items == [mock_profile]

    async def test_update_returns_profile(self):
        mock_profile = MagicMock()
        db = _db(MagicMock(), _scalar_one_or_none(mock_profile))
        result = await self.repo.update(db, uuid.uuid4(), {"full_name": "Alice"})
        assert result is mock_profile


# ─── CategoryRepository ───────────────────────────────────────────────────────


class TestCategoryRepository:
    def setup_method(self):
        from app.modules.categories.repository import CategoryRepository

        self.repo = CategoryRepository()

    async def test_list_all_active_returns_categories(self):
        mock_cat = MagicMock()
        db = _db(_scalars_result([mock_cat]))
        result = await self.repo.list_all_active(db)
        assert result == [mock_cat]

    async def test_get_by_id_returns_category(self):
        mock_cat = MagicMock()
        db = _db(_scalar_one_or_none(mock_cat))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_cat

    async def test_get_by_slug_returns_category(self):
        mock_cat = MagicMock()
        db = _db(_scalar_one_or_none(mock_cat))
        result = await self.repo.get_by_slug(db, "rings")
        assert result is mock_cat

    async def test_create_adds_and_refreshes(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.repo.create(db, {"id": uuid.uuid4(), "name": "Rings", "slug": "rings"})
        db.add.assert_called_once()

    async def test_update_executes_and_refetches(self):
        mock_cat = MagicMock()
        db = _db(MagicMock(), _scalar_one_or_none(mock_cat))
        result = await self.repo.update(db, uuid.uuid4(), {"is_active": False})
        assert result is mock_cat

    async def test_soft_delete_executes_update(self):
        db = _db(MagicMock())
        await self.repo.soft_delete(db, uuid.uuid4())
        db.execute.assert_awaited_once()

    async def test_has_active_products_returns_true(self):
        db = _db(_first(MagicMock()))  # result.first() → some row
        result = await self.repo.has_active_products(db, uuid.uuid4())
        assert result is True

    async def test_has_active_products_returns_false(self):
        db = _db(_first(None))  # result.first() → None
        result = await self.repo.has_active_products(db, uuid.uuid4())
        assert result is False
