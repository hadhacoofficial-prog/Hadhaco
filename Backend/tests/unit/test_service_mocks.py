"""Mock-based service unit tests.

Uses AsyncMock for repository calls so no real database is needed.
Tests cover the business logic layer (error conditions, happy paths).
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── CMS Service ────────────────────────────────────────────────────────────────

class TestCMSService:
    def setup_method(self):
        from app.modules.cms.service import CMSService
        self.svc = CMSService()

    async def test_get_home_data_returns_required_keys(self):
        db = AsyncMock()
        with patch("app.modules.cms.repository.CMSRepository.get_active_banners", AsyncMock(return_value=[])), \
             patch("app.modules.cms.repository.CMSRepository.get_active_sections", AsyncMock(return_value=[])):
            result = await self.svc.get_home_data(db)
        assert "hero_banners" in result
        assert "sections" in result
        assert isinstance(result["hero_banners"], list)
        assert isinstance(result["sections"], list)

    async def test_get_page_raises_404_when_missing(self):
        from fastapi import HTTPException
        db = AsyncMock()
        with patch("app.modules.cms.repository.CMSRepository.get_page", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.get_page(db, "nonexistent-slug")
        assert exc.value.status_code == 404

    async def test_delete_banner_raises_404_when_missing(self):
        from fastapi import HTTPException
        db = AsyncMock()
        with patch("app.modules.cms.repository.CMSRepository.get_banner", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.delete_banner(db, uuid.uuid4())
        assert exc.value.status_code == 404

    async def test_update_section_raises_404_when_key_not_found(self):
        from fastapi import HTTPException
        from app.modules.cms.schemas import LandingSectionUpdate
        db = AsyncMock()
        with patch("app.modules.cms.repository.CMSRepository.get_section_by_key", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.update_section(db, "nonexistent-key", LandingSectionUpdate())
        assert exc.value.status_code == 404

    async def test_update_page_raises_404_when_not_found(self):
        from fastapi import HTTPException
        from app.modules.cms.schemas import CmsPageUpdate
        db = AsyncMock()
        with patch("app.modules.cms.repository.CMSRepository.get_page_by_id", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.update_page(db, uuid.uuid4(), CmsPageUpdate())
        assert exc.value.status_code == 404


# ─── Category Service ────────────────────────────────────────────────────────────

class TestCategoryService:
    def setup_method(self):
        from app.modules.categories.service import CategoryService
        self.svc = CategoryService()

    async def test_delete_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.categories.repository.CategoryRepository.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.delete(db, str(uuid.uuid4()))

    async def test_get_by_slug_raises_404_when_missing(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.categories.repository.CategoryRepository.get_by_slug", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_by_slug(db, "no-such-slug")

    async def test_create_raises_conflict_for_duplicate_slug(self):
        from app.core.exceptions import ConflictError
        from app.modules.categories.schemas import CategoryCreateRequest
        db = AsyncMock()
        existing = MagicMock()
        with patch("app.modules.categories.repository.CategoryRepository.get_by_slug", AsyncMock(return_value=existing)):
            with pytest.raises(ConflictError):
                await self.svc.create(db, CategoryCreateRequest(name="Silver", slug="silver"), actor_id="admin1")


# ─── Coupon Service ────────────────────────────────────────────────────────────

class TestCouponServiceMocked:
    def setup_method(self):
        from app.modules.coupons.service import CouponService
        self.svc = CouponService()

    async def test_create_raises_conflict_when_code_exists(self):
        from app.modules.coupons.schemas import CouponCreateRequest
        from app.core.exceptions import ConflictError
        db = AsyncMock()
        existing = MagicMock()
        with patch("app.modules.coupons.service._repo.get_by_code", AsyncMock(return_value=existing)):
            with pytest.raises(ConflictError):
                await self.svc.create(db, CouponCreateRequest(
                    code="EXIST10",
                    coupon_type="percentage",
                    value=10,
                    min_order_amount=0,
                    per_user_limit=1,
                ))

    async def test_update_raises_404_when_not_found(self):
        from app.modules.coupons.schemas import CouponUpdateRequest
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.coupons.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update(db, uuid.uuid4(), CouponUpdateRequest())

    async def test_delete_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.coupons.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.delete(db, uuid.uuid4())

    async def test_validate_invalid_for_unknown_code(self):
        db = AsyncMock()
        with patch("app.modules.coupons.service._repo.get_by_code", AsyncMock(return_value=None)):
            result = await self.svc.validate(db, "UNKNOWN", 500.0, uuid.uuid4())
        assert result.valid is False
        assert result.discount_amount == 0

    async def test_validate_invalid_for_inactive_coupon(self):
        db = AsyncMock()
        coupon = MagicMock()
        coupon.is_active = False
        with patch("app.modules.coupons.service._repo.get_by_code", AsyncMock(return_value=coupon)):
            result = await self.svc.validate(db, "INACTIVE", 500.0, uuid.uuid4())
        assert result.valid is False

    async def test_validate_invalid_for_expired_coupon(self):
        db = AsyncMock()
        coupon = MagicMock()
        coupon.is_active = True
        coupon.valid_from = datetime(2020, 1, 1, tzinfo=timezone.utc)
        coupon.valid_until = datetime(2020, 12, 31, tzinfo=timezone.utc)
        coupon.usage_limit = None
        with patch("app.modules.coupons.service._repo.get_by_code", AsyncMock(return_value=coupon)):
            result = await self.svc.validate(db, "EXPIRED", 500.0, uuid.uuid4())
        assert result.valid is False
        assert "expired" in result.message.lower()

    async def test_validate_invalid_below_min_order(self):
        db = AsyncMock()
        coupon = MagicMock()
        coupon.is_active = True
        coupon.valid_from = None
        coupon.valid_until = None
        coupon.usage_limit = None
        coupon.min_order_amount = Decimal("1000.00")
        with patch("app.modules.coupons.service._repo.get_by_code", AsyncMock(return_value=coupon)):
            result = await self.svc.validate(db, "BIG500", 500.0, uuid.uuid4())
        assert result.valid is False
        assert "minimum" in result.message.lower()


# ─── Address Service ────────────────────────────────────────────────────────────

class TestAddressService:
    def setup_method(self):
        from app.modules.addresses.service import AddressService
        self.svc = AddressService()

    async def test_update_raises_404_for_missing_address(self):
        from app.modules.addresses.schemas import AddressUpdateRequest
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.addresses.service._repo.get", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update(db, uuid.uuid4(), uuid.uuid4(), AddressUpdateRequest())


# ─── Inventory Service ────────────────────────────────────────────────────────────

class TestInventoryService:
    def setup_method(self):
        from app.modules.inventory.service import InventoryService
        self.svc = InventoryService()

    async def test_record_movement_raises_404_when_product_missing(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.inventory.service._repo.get_stock_snapshot", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.record_movement(
                    db,
                    product_id=uuid.uuid4(),
                    delta=-1,
                    movement_type="sale",
                )

    async def test_record_movement_raises_validation_on_insufficient_stock(self):
        from app.core.exceptions import ValidationError
        db = AsyncMock()
        with patch("app.modules.inventory.service._repo.get_stock_snapshot", AsyncMock(return_value={
            "stock_quantity": 2,
            "allow_backorder": False,
            "low_stock_threshold": 5,
            "sku": "SR-001",
            "product_name": "Silver Ring",
        })):
            with pytest.raises(ValidationError) as exc:
                await self.svc.record_movement(
                    db,
                    product_id=uuid.uuid4(),
                    delta=-10,
                    movement_type="sale",
                )
            assert "insufficient" in str(exc.value.message).lower()

    async def test_get_low_stock_delegates_to_repo(self):
        db = AsyncMock()
        with patch("app.modules.inventory.service._repo.get_low_stock", AsyncMock(return_value=[])):
            result = await self.svc.get_low_stock(db)
        assert result == []
