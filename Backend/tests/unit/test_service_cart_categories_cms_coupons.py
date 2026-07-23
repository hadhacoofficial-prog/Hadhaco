"""Tests for CartService, CategoryService, CMSService, and CouponService."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.categories.repository import CategoryRepository
from app.modules.cms.repository import CMSRepository

# ─── CouponService pure functions ─────────────────────────────────────────────


class TestCalculateDiscount:
    def _make_coupon(self, coupon_type, value, max_discount=None):
        c = MagicMock()
        c.coupon_type = coupon_type
        c.value = value
        c.max_discount = max_discount
        return c

    def test_percentage_discount(self):
        from app.modules.coupons.service import _calculate_discount

        c = self._make_coupon("percentage", 10)
        assert _calculate_discount(c, 1000) == 100.0

    def test_percentage_capped_by_max_discount(self):
        from app.modules.coupons.service import _calculate_discount

        c = self._make_coupon("percentage", 10, max_discount=50)
        assert _calculate_discount(c, 1000) == 50.0

    def test_percentage_below_max(self):
        from app.modules.coupons.service import _calculate_discount

        c = self._make_coupon("percentage", 5, max_discount=100)
        assert _calculate_discount(c, 500) == 25.0

    def test_fixed_amount_discount(self):
        from app.modules.coupons.service import _calculate_discount

        c = self._make_coupon("fixed_amount", 200)
        assert _calculate_discount(c, 1000) == 200.0

    def test_fixed_amount_capped_by_subtotal(self):
        from app.modules.coupons.service import _calculate_discount

        c = self._make_coupon("fixed_amount", 500)
        assert _calculate_discount(c, 100) == 100.0  # can't discount more than subtotal

    def test_free_shipping_returns_zero(self):
        from app.modules.coupons.service import _calculate_discount

        c = self._make_coupon("free_shipping", 0)
        assert _calculate_discount(c, 1000) == 0.0


# ─── CouponService.validate ───────────────────────────────────────────────────


class TestCouponServiceValidate:
    def setup_method(self):
        from app.modules.coupons.service import CouponService

        self.svc = CouponService()

    def _active_coupon(self, **overrides):
        now = datetime.now(UTC)
        c = MagicMock()
        c.is_active = True
        c.status = "active"
        c.valid_from = now - timedelta(days=1)
        c.valid_until = None
        c.usage_limit = None
        c.usage_count = 0
        c.min_order_amount = 0
        c.per_user_limit = 5
        c.one_time_per_customer = False
        c.first_order_only = False
        c.new_customer_only = False
        c.returning_customer_only = False
        c.max_order_amount = None
        c.coupon_type = "percentage"
        c.value = 10
        c.max_discount = None
        c.id = uuid.uuid4()
        for k, v in overrides.items():
            setattr(c, k, v)
        return c

    async def test_invalid_code_returns_invalid(self):
        db = AsyncMock()
        with patch(
            "app.modules.coupons.service._repo.get_by_code",
            AsyncMock(return_value=None),
        ):
            result = await self.svc.validate(db, "BADCODE", 1000, uuid.uuid4())
        assert result.valid is False
        assert "Invalid" in result.message

    async def test_inactive_coupon_returns_invalid(self):
        db = AsyncMock()
        c = self._active_coupon(is_active=False, status="inactive")
        with patch(
            "app.modules.coupons.service._repo.get_by_code", AsyncMock(return_value=c)
        ):
            result = await self.svc.validate(db, "SAVE10", 1000, uuid.uuid4())
        assert result.valid is False
        assert "inactive" in result.message

    async def test_not_yet_active_coupon_returns_invalid(self):
        db = AsyncMock()
        c = self._active_coupon(valid_from=datetime.now(UTC) + timedelta(hours=1))
        with patch(
            "app.modules.coupons.service._repo.get_by_code", AsyncMock(return_value=c)
        ):
            result = await self.svc.validate(db, "SAVE10", 1000, uuid.uuid4())
        assert result.valid is False
        assert "not yet" in result.message

    async def test_expired_coupon_returns_invalid(self):
        db = AsyncMock()
        c = self._active_coupon(valid_until=datetime.now(UTC) - timedelta(days=1))
        with patch(
            "app.modules.coupons.service._repo.get_by_code", AsyncMock(return_value=c)
        ):
            result = await self.svc.validate(db, "SAVE10", 1000, uuid.uuid4())
        assert result.valid is False
        assert "expired" in result.message

    async def test_usage_limit_reached_returns_invalid(self):
        db = AsyncMock()
        c = self._active_coupon(usage_limit=10, usage_count=10)
        with patch(
            "app.modules.coupons.service._repo.get_by_code", AsyncMock(return_value=c)
        ):
            result = await self.svc.validate(db, "SAVE10", 1000, uuid.uuid4())
        assert result.valid is False
        assert "available" in result.message

    async def test_below_minimum_order_returns_invalid(self):
        db = AsyncMock()
        c = self._active_coupon(min_order_amount=500)
        with (
            patch(
                "app.modules.coupons.service._repo.get_by_code",
                AsyncMock(return_value=c),
            ),
            patch(
                "app.modules.coupons.service._repo.get_user_usage_count",
                AsyncMock(return_value=0),
            ),
        ):
            result = await self.svc.validate(db, "SAVE10", 100, uuid.uuid4())
        assert result.valid is False
        assert "Add" in result.message

    async def test_per_user_limit_exceeded_returns_invalid(self):
        db = AsyncMock()
        c = self._active_coupon(per_user_limit=2)
        with (
            patch(
                "app.modules.coupons.service._repo.get_by_code",
                AsyncMock(return_value=c),
            ),
            patch(
                "app.modules.coupons.service._repo.get_user_usage_count",
                AsyncMock(return_value=2),
            ),
        ):
            result = await self.svc.validate(db, "SAVE10", 1000, uuid.uuid4())
        assert result.valid is False
        assert "already used" in result.message

    async def test_valid_coupon_returns_discount(self):
        db = AsyncMock()
        c = self._active_coupon()
        # Return None so CouponValidateResponse(coupon=None) passes Pydantic validation
        with (
            patch(
                "app.modules.coupons.service._repo.get_by_code",
                AsyncMock(return_value=c),
            ),
            patch(
                "app.modules.coupons.service._repo.get_user_usage_count",
                AsyncMock(return_value=0),
            ),
            patch(
                "app.modules.coupons.service.CouponResponse.model_validate",
                return_value=None,
            ),
        ):
            result = await self.svc.validate(db, "SAVE10", 1000, uuid.uuid4())
        assert result.valid is True
        assert result.discount_amount == 100.0


# ─── CouponService CRUD ───────────────────────────────────────────────────────


class TestCouponServiceCRUD:
    def setup_method(self):
        from app.modules.coupons.service import CouponService

        self.svc = CouponService()

    async def test_list_all_empty(self):
        db = AsyncMock()
        with patch(
            "app.modules.coupons.service._repo.list_all", AsyncMock(return_value=[])
        ):
            result = await self.svc.list_all(db)
        assert result == []

    async def test_create_raises_conflict_for_existing_code(self):
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
                    CouponCreateRequest(
                        code="SAVE10",
                        coupon_type="percentage",
                        value=10,
                    ),
                )

    async def test_update_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.coupons.schemas import CouponUpdateRequest

        db = AsyncMock()
        with patch(
            "app.modules.coupons.service._repo.get_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.update(db, uuid.uuid4(), CouponUpdateRequest())

    async def test_delete_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.coupons.service._repo.get_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.delete(db, uuid.uuid4())

    async def test_delete_calls_repo_and_commits(self):
        db = AsyncMock()
        mock_coupon = MagicMock()
        with (
            patch(
                "app.modules.coupons.service._repo.get_by_id",
                AsyncMock(return_value=mock_coupon),
            ),
            patch("app.modules.coupons.service._repo.delete", AsyncMock()) as mock_del,
        ):
            await self.svc.delete(db, uuid.uuid4())
        mock_del.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_apply_and_reserve_raises_validation_on_invalid_coupon(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        with patch(
            "app.modules.coupons.service._repo.get_by_code",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(ValidationError):
                await self.svc.apply_and_reserve(db, "BAD", 500, uuid.uuid4())

    async def test_finalize_usage_calls_repo(self):
        db = AsyncMock()
        with patch(
            "app.modules.coupons.service._repo.update_usage_order_id", AsyncMock()
        ) as mock_upd:
            await self.svc.finalize_usage(db, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
        mock_upd.assert_awaited_once()


# ─── CategoryService ──────────────────────────────────────────────────────────


class TestCategoryService:
    def setup_method(self):
        from app.modules.categories.service import CategoryService

        self.svc = CategoryService()

    async def test_get_tree_returns_empty_when_no_categories(self):
        db = AsyncMock()
        with patch.object(
            CategoryRepository, "list_all_active", AsyncMock(return_value=[])
        ):
            result = await self.svc.get_tree(db)
        assert result == []

    async def test_get_tree_returns_sorted_nodes(self):
        db = AsyncMock()
        # Two top-level categories with different sort orders
        cat1 = MagicMock()
        cat1.id = uuid.uuid4()
        cat1.parent_id = None
        cat1.name = "Rings"
        cat1.slug = "rings"
        cat1.image_url = None
        cat1.sort_order = 2

        cat2 = MagicMock()
        cat2.id = uuid.uuid4()
        cat2.parent_id = None
        cat2.name = "Bangles"
        cat2.slug = "bangles"
        cat2.image_url = None
        cat2.sort_order = 1

        with patch.object(
            CategoryRepository, "list_all_active", AsyncMock(return_value=[cat1, cat2])
        ):
            result = await self.svc.get_tree(db)
        assert len(result) == 2
        assert result[0].name == "Bangles"  # sort_order=1 first
        assert result[1].name == "Rings"

    async def test_get_by_slug_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch.object(
            CategoryRepository, "get_by_slug", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_by_slug(db, "nonexistent")

    async def test_get_by_slug_returns_category(self):
        db = AsyncMock()
        mock_cat = MagicMock()
        with patch.object(
            CategoryRepository, "get_by_slug", AsyncMock(return_value=mock_cat)
        ):
            result = await self.svc.get_by_slug(db, "rings")
        assert result is mock_cat

    async def test_get_tree_resolves_image_despite_stale_primary_image_id_column(self):
        """Regression guard: `categories.primary_image_id` is a denormalized
        column the universal media attach/crop/set-primary flow never writes
        (it only touches the `images` table) — the tree builder must resolve
        each category's image from the live images table, not gate on that
        column being set, or every successfully-attached image silently
        disappears from the storefront nav."""
        from app.modules.media.repository import ImageRepository

        db = AsyncMock()
        cat = MagicMock()
        cat.id = uuid.uuid4()
        cat.parent_id = None
        cat.name = "Rings"
        cat.slug = "rings"
        cat.sort_order = 1
        cat.primary_image_id = None  # stale/never-written, as in production

        with (
            patch.object(
                CategoryRepository, "list_all_active", AsyncMock(return_value=[cat])
            ),
            patch.object(
                ImageRepository,
                "get_primary_variant_urls",
                AsyncMock(return_value={cat.id: "https://cdn/rings.webp?v=1"}),
            ),
        ):
            result = await self.svc.get_tree(db)

        assert result[0].image_url == "https://cdn/rings.webp?v=1"

    async def test_get_detail_populates_primary_image_id_from_live_lookup(self):
        from app.modules.categories.schemas import CategoryDetailResponse
        from app.modules.media.repository import ImageRepository

        db = AsyncMock()
        cat = MagicMock()
        cat.id = uuid.uuid4()
        cat.primary_image_id = None  # stale/never-written, as in production
        image_id = uuid.uuid4()

        validated = MagicMock()
        validated.id = cat.id
        validated.primary_image_id = None
        validated.image_url = None

        with (
            patch.object(CategoryRepository, "get_by_id", AsyncMock(return_value=cat)),
            patch.object(
                CategoryRepository, "get_product_count", AsyncMock(return_value=0)
            ),
            patch.object(
                CategoryRepository, "get_children_count", AsyncMock(return_value=0)
            ),
            patch.object(
                CategoryDetailResponse, "model_validate", return_value=validated
            ),
            patch.object(
                ImageRepository,
                "get_primary_image_ids",
                AsyncMock(return_value={cat.id: image_id}),
            ),
            patch.object(
                ImageRepository,
                "get_primary_variant_urls",
                AsyncMock(return_value={cat.id: "https://cdn/rings.webp?v=1"}),
            ),
        ):
            result = await self.svc.get_detail(db, cat.id)

        assert result.primary_image_id == image_id
        assert result.image_url == "https://cdn/rings.webp?v=1"

    async def test_create_raises_conflict_for_existing_slug(self):
        from app.core.exceptions import ConflictError
        from app.modules.categories.schemas import CategoryCreateRequest

        db = AsyncMock()
        with patch.object(
            CategoryRepository, "get_by_slug", AsyncMock(return_value=MagicMock())
        ):
            with pytest.raises(ConflictError):
                await self.svc.create(
                    db,
                    CategoryCreateRequest(name="Rings", slug="rings"),
                    actor_id="admin",
                )

    async def test_create_success(self):
        from app.modules.categories.schemas import CategoryCreateRequest

        db = AsyncMock()
        mock_cat = MagicMock()
        with (
            patch.object(
                CategoryRepository, "get_by_slug", AsyncMock(return_value=None)
            ),
            patch.object(
                CategoryRepository, "create", AsyncMock(return_value=mock_cat)
            ),
        ):
            result = await self.svc.create(
                db, CategoryCreateRequest(name="Rings", slug="rings"), actor_id="admin"
            )
        assert result is mock_cat

    async def test_update_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.categories.schemas import CategoryUpdateRequest

        db = AsyncMock()
        with patch.object(
            CategoryRepository, "get_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.update(
                    db, uuid.uuid4(), CategoryUpdateRequest(name="NewName")
                )

    async def test_update_raises_conflict_on_slug_taken(self):
        from app.core.exceptions import ConflictError
        from app.modules.categories.schemas import CategoryUpdateRequest

        db = AsyncMock()
        cat_id = uuid.uuid4()
        mock_existing_cat = MagicMock()
        mock_existing_cat.id = cat_id
        mock_slug_taken = MagicMock()
        mock_slug_taken.id = uuid.uuid4()  # different id = conflict
        with (
            patch.object(
                CategoryRepository,
                "get_by_id",
                AsyncMock(return_value=mock_existing_cat),
            ),
            patch.object(
                CategoryRepository,
                "get_by_slug",
                AsyncMock(return_value=mock_slug_taken),
            ),
        ):
            with pytest.raises(ConflictError):
                await self.svc.update(
                    db, cat_id, CategoryUpdateRequest(slug="taken-slug")
                )

    async def test_update_success(self):
        from app.modules.categories.schemas import CategoryUpdateRequest

        db = AsyncMock()
        cat_id = uuid.uuid4()
        mock_existing = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(
                CategoryRepository, "get_by_id", AsyncMock(return_value=mock_existing)
            ),
            patch.object(
                CategoryRepository, "update", AsyncMock(return_value=mock_updated)
            ),
        ):
            result = await self.svc.update(
                db, cat_id, CategoryUpdateRequest(is_active=False)
            )
        assert result is mock_updated

    async def test_delete_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch.object(
            CategoryRepository, "get_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.delete(db, uuid.uuid4())

    async def test_delete_raises_conflict_when_has_active_products(self):
        from app.core.exceptions import ConflictError

        db = AsyncMock()
        with (
            patch.object(
                CategoryRepository, "get_by_id", AsyncMock(return_value=MagicMock())
            ),
            patch.object(
                CategoryRepository, "has_children", AsyncMock(return_value=True)
            ),
        ):
            with pytest.raises(ConflictError):
                await self.svc.delete(db, uuid.uuid4())

    async def test_delete_success(self):
        db = AsyncMock()
        with (
            patch.object(
                CategoryRepository, "get_by_id", AsyncMock(return_value=MagicMock())
            ),
            patch.object(
                CategoryRepository, "has_children", AsyncMock(return_value=False)
            ),
            patch.object(CategoryRepository, "soft_delete", AsyncMock()) as mock_del,
        ):
            await self.svc.delete(db, uuid.uuid4())
        mock_del.assert_awaited_once()


# ─── CMSService ───────────────────────────────────────────────────────────────


class TestCMSService:
    def setup_method(self):
        from app.modules.cms.service import CMSService

        self.svc = CMSService()

    async def test_get_home_data_returns_structure(self):
        db = AsyncMock()
        mock_hero = [MagicMock()]
        mock_promo = []
        mock_sections = [MagicMock()]

        with (
            patch.object(
                CMSRepository,
                "get_active_banners",
                AsyncMock(side_effect=[mock_hero, mock_promo]),
            ),
            patch.object(
                CMSRepository,
                "get_active_sections",
                AsyncMock(return_value=mock_sections),
            ),
        ):
            result = await self.svc.get_home_data(db)

        assert "hero_banners" in result
        assert len(result["hero_banners"]) == 1
        assert (
            result["promo_strip"] is None
        )  # promo_strip = promo[0] if promo else None

    async def test_get_page_raises_404_when_not_found(self):
        from fastapi import HTTPException

        db = AsyncMock()
        with patch.object(CMSRepository, "get_page", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.get_page(db, "nonexistent")
        assert exc.value.status_code == 404

    async def test_get_page_returns_page(self):
        db = AsyncMock()
        mock_page = MagicMock()
        with patch.object(CMSRepository, "get_page", AsyncMock(return_value=mock_page)):
            result = await self.svc.get_page(db, "about")
        assert result is mock_page

    async def test_list_banners_returns_list(self):
        db = AsyncMock()
        mock_banners = [MagicMock(), MagicMock()]
        with patch.object(
            CMSRepository, "get_active_banners", AsyncMock(return_value=mock_banners)
        ):
            result = await self.svc.list_banners(db)
        assert len(result) == 2

    async def test_create_banner_commits_and_refreshes(self):
        from app.modules.cms.schemas import BannerCreate

        db = AsyncMock()
        mock_banner = MagicMock()
        with patch.object(
            CMSRepository, "create_banner", AsyncMock(return_value=mock_banner)
        ):
            await self.svc.create_banner(
                db, BannerCreate(name="sale-hero", banner_type="hero")
            )
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(mock_banner)

    async def test_update_banner_raises_404_when_not_found(self):
        from fastapi import HTTPException

        from app.modules.cms.schemas import BannerUpdate

        db = AsyncMock()
        with patch.object(CMSRepository, "get_banner", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.update_banner(db, uuid.uuid4(), BannerUpdate())
        assert exc.value.status_code == 404

    async def test_update_banner_success(self):
        from app.modules.cms.schemas import BannerUpdate

        db = AsyncMock()
        mock_banner = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(
                CMSRepository, "get_banner", AsyncMock(return_value=mock_banner)
            ),
            patch.object(
                CMSRepository, "update_banner", AsyncMock(return_value=mock_updated)
            ),
        ):
            result = await self.svc.update_banner(
                db, uuid.uuid4(), BannerUpdate(title="New Title")
            )
        db.commit.assert_awaited_once()
        assert result is mock_updated

    async def test_delete_banner_raises_404_when_not_found(self):
        from fastapi import HTTPException

        db = AsyncMock()
        with patch.object(CMSRepository, "get_banner", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.delete_banner(db, uuid.uuid4())
        assert exc.value.status_code == 404

    async def test_delete_banner_success(self):
        db = AsyncMock()
        mock_banner = MagicMock()
        with (
            patch.object(
                CMSRepository, "get_banner", AsyncMock(return_value=mock_banner)
            ),
            patch.object(CMSRepository, "delete_banner", AsyncMock()) as mock_del,
        ):
            await self.svc.delete_banner(db, uuid.uuid4())
        mock_del.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_list_sections_returns_list(self):
        db = AsyncMock()
        with patch.object(
            CMSRepository, "get_all_sections", AsyncMock(return_value=[])
        ):
            result = await self.svc.list_sections(db)
        assert result == []

    async def test_update_section_raises_404_when_not_found(self):
        from fastapi import HTTPException

        from app.modules.cms.schemas import LandingSectionUpdate

        db = AsyncMock()
        with patch.object(
            CMSRepository, "get_section_by_key", AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.update_section(db, "nonexistent", LandingSectionUpdate())
        assert exc.value.status_code == 404

    async def test_update_section_success(self):
        from app.modules.cms.schemas import LandingSectionUpdate

        db = AsyncMock()
        mock_section = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(
                CMSRepository,
                "get_section_by_key",
                AsyncMock(return_value=mock_section),
            ),
            patch.object(
                CMSRepository, "update_section", AsyncMock(return_value=mock_updated)
            ),
        ):
            result = await self.svc.update_section(
                db, "featured", LandingSectionUpdate(is_active=True)
            )
        db.commit.assert_awaited_once()
        assert result is mock_updated

    async def test_create_page_commits_and_returns(self):
        from app.modules.cms.schemas import CmsPageCreate

        db = AsyncMock()
        mock_page = MagicMock()
        with patch.object(
            CMSRepository, "create_page", AsyncMock(return_value=mock_page)
        ):
            result = await self.svc.create_page(
                db, CmsPageCreate(title="About", slug="about", content="<p>About</p>")
            )
        db.commit.assert_awaited_once()
        assert result is mock_page

    async def test_update_page_raises_404_when_not_found(self):
        from fastapi import HTTPException

        from app.modules.cms.schemas import CmsPageUpdate

        db = AsyncMock()
        with patch.object(
            CMSRepository, "get_page_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.update_page(db, uuid.uuid4(), CmsPageUpdate())
        assert exc.value.status_code == 404

    async def test_delete_media_purges_r2_before_db_row(self):
        """MP-3 regression guard: deleting a cms_media row used to leave its
        R2 object(s) orphaned forever — the delete must call R2 cleanup
        before the row disappears."""
        from app.modules.cms.media_service import CmsMediaService

        db = AsyncMock()
        media = MagicMock()
        media_id = uuid.uuid4()

        with (
            patch.object(CMSRepository, "get_media", AsyncMock(return_value=media)),
            patch.object(CMSRepository, "delete_media", AsyncMock()) as delete_media,
            patch.object(CmsMediaService, "delete_r2_objects") as delete_r2,
        ):
            await self.svc.delete_media(db, media_id)

        delete_r2.assert_called_once_with(media)
        delete_media.assert_awaited_once_with(db, media)
        db.commit.assert_awaited_once()

    async def test_delete_media_raises_404_when_not_found(self):
        from fastapi import HTTPException

        db = AsyncMock()
        with patch.object(CMSRepository, "get_media", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.delete_media(db, uuid.uuid4())
        assert exc.value.status_code == 404


# ─── CmsMediaService ────────────────────────────────────────────────────────


class TestCmsMediaServiceDeleteR2Objects:
    def test_deletes_main_object_only_when_no_thumbnail(self):
        from app.modules.cms.media_service import CmsMediaService

        svc = CmsMediaService()
        media = MagicMock()
        media.filename = "cms/abc.jpg"
        media.thumbnail_url = None

        mock_client = MagicMock()
        with patch("app.modules.cms.media_service._r2", return_value=mock_client):
            svc.delete_r2_objects(media)

        deleted_keys = [
            o["Key"]
            for o in mock_client.delete_objects.call_args.kwargs["Delete"]["Objects"]
        ]
        assert deleted_keys == ["cms/abc.jpg"]

    def test_deletes_thumbnail_key_derived_from_filename(self):
        from app.modules.cms.media_service import CmsMediaService

        svc = CmsMediaService()
        media = MagicMock()
        media.filename = "cms/abc.jpg"
        media.thumbnail_url = "https://cdn.example/cms/abc_thumb.webp"

        mock_client = MagicMock()
        with patch("app.modules.cms.media_service._r2", return_value=mock_client):
            svc.delete_r2_objects(media)

        deleted_keys = {
            o["Key"]
            for o in mock_client.delete_objects.call_args.kwargs["Delete"]["Objects"]
        }
        assert deleted_keys == {"cms/abc.jpg", "cms/abc_thumb.webp"}

    def test_swallows_client_error(self):
        from botocore.exceptions import ClientError

        from app.modules.cms.media_service import CmsMediaService

        svc = CmsMediaService()
        media = MagicMock()
        media.filename = "cms/abc.jpg"
        media.thumbnail_url = None

        mock_client = MagicMock()
        mock_client.delete_objects.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "boom"}}, "DeleteObjects"
        )
        with patch("app.modules.cms.media_service._r2", return_value=mock_client):
            svc.delete_r2_objects(media)  # must not raise


# ─── CartService ──────────────────────────────────────────────────────────────


class TestCartServiceSuccessPaths:
    def setup_method(self):
        from app.modules.cart.service import CartService

        self.svc = CartService()
        # Customer holds no reservation of their own by default, so cart
        # availability is unchanged (stub the new DB-backed lookup).
        self.svc._own_active_reserved_qty = AsyncMock(return_value=0)

    def _mock_cart(self, items=None, discount=0, coupon_code=None):
        cart = MagicMock()
        cart.id = uuid.uuid4()
        cart.user_id = uuid.uuid4()
        cart.items = items or []
        cart.discount = discount
        cart.coupon_code = coupon_code
        cart.expires_at = datetime.now(UTC) + timedelta(days=7)
        return cart

    async def test_get_cart_returns_empty_summary_by_user(self):
        db = AsyncMock()
        mock_cart = self._mock_cart()
        with patch(
            "app.modules.cart.service._repo.get_for_user",
            AsyncMock(return_value=mock_cart),
        ):
            result = await self.svc.get_cart(db, user_id=uuid.uuid4())
        assert result.item_count == 0
        assert result.total == 0

    async def test_get_cart_creates_new_when_not_found(self):
        db = AsyncMock()
        mock_cart = self._mock_cart()
        with (
            patch(
                "app.modules.cart.service._repo.get_for_user",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.cart.service._repo.create",
                AsyncMock(return_value=mock_cart),
            ),
            patch(
                "app.modules.cart.service._repo.get_by_id",
                AsyncMock(return_value=mock_cart),
            ),
        ):
            result = await self.svc.get_cart(db, user_id=uuid.uuid4())
        assert result.item_count == 0

    async def test_get_cart_by_session_id(self):
        db = AsyncMock()
        mock_cart = self._mock_cart()
        with patch(
            "app.modules.cart.service._repo.get_by_session",
            AsyncMock(return_value=mock_cart),
        ):
            result = await self.svc.get_cart(db, session_id="sess-123")
        assert result.id == mock_cart.id

    async def test_get_cart_creates_by_session_when_not_found(self):
        db = AsyncMock()
        mock_cart = self._mock_cart()
        with (
            patch(
                "app.modules.cart.service._repo.get_by_session",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.cart.service._repo.create",
                AsyncMock(return_value=mock_cart),
            ),
            patch(
                "app.modules.cart.service._repo.get_by_id",
                AsyncMock(return_value=mock_cart),
            ),
        ):
            result = await self.svc.get_cart(db, session_id="sess-new")
        assert result.item_count == 0

    async def test_fetch_product_price_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        with pytest.raises(NotFoundError):
            await self.svc._fetch_product_price(db, uuid.uuid4(), None)

    async def test_fetch_product_price_with_variant(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: 999.0
        mock_result.fetchone.return_value = mock_row
        db.execute = AsyncMock(return_value=mock_result)
        price = await self.svc._fetch_product_price(db, uuid.uuid4(), uuid.uuid4())
        assert price == 999.0

    async def test_add_item_returns_updated_cart(self):
        from app.modules.cart.schemas import AddToCartRequest

        db = AsyncMock()
        mock_cart = self._mock_cart()
        mock_updated_cart = self._mock_cart()
        product_id = uuid.uuid4()

        with (
            patch(
                "app.modules.cart.service._repo.get_for_user",
                AsyncMock(return_value=mock_cart),
            ),
            patch.object(
                self.svc,
                "_fetch_add_item_validations",
                AsyncMock(return_value=(10, True, False, 0, 999.0)),
            ),
            patch("app.modules.cart.service._repo.upsert_item", AsyncMock()),
            patch(
                "app.modules.cart.service._repo.get_by_id",
                AsyncMock(return_value=mock_updated_cart),
            ),
        ):
            result = await self.svc.add_item(
                db,
                AddToCartRequest(product_id=product_id, quantity=2),
                user_id=uuid.uuid4(),
            )
        assert result.id == mock_updated_cart.id

    async def test_clear_clears_items_and_coupon(self):
        db = AsyncMock()
        mock_cart = self._mock_cart()
        mock_cleared = self._mock_cart()
        with (
            patch(
                "app.modules.cart.service._repo.get_for_user",
                AsyncMock(return_value=mock_cart),
            ),
            patch("app.modules.cart.service._repo.clear_items", AsyncMock()),
            patch("app.modules.cart.service._repo.update_cart", AsyncMock()),
            patch(
                "app.modules.cart.service._repo.get_by_id",
                AsyncMock(return_value=mock_cleared),
            ),
        ):
            result = await self.svc.clear(db, user_id=uuid.uuid4())
        assert result is not None

    async def test_merge_guest_cart_no_op_when_no_guest_cart(self):
        db = AsyncMock()
        mock_user_cart = self._mock_cart()
        with (
            patch(
                "app.modules.cart.service._repo.get_by_session",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.cart.service._repo.get_for_user",
                AsyncMock(return_value=mock_user_cart),
            ),
        ):
            result = await self.svc.merge_guest_cart(
                db, user_id=uuid.uuid4(), session_id="old-sess"
            )
        assert result.id == mock_user_cart.id

    async def test_merge_guest_cart_no_op_when_guest_cart_is_empty(self):
        db = AsyncMock()
        mock_guest_cart = self._mock_cart(items=[])  # no items
        mock_user_cart = self._mock_cart()
        with (
            patch(
                "app.modules.cart.service._repo.get_by_session",
                AsyncMock(return_value=mock_guest_cart),
            ),
            patch(
                "app.modules.cart.service._repo.get_for_user",
                AsyncMock(return_value=mock_user_cart),
            ),
        ):
            result = await self.svc.merge_guest_cart(
                db, user_id=uuid.uuid4(), session_id="old-sess"
            )
        assert result.id == mock_user_cart.id

    async def test_merge_guest_cart_merges_items(self):
        db = AsyncMock()
        mock_guest_item = MagicMock()
        mock_guest_cart = self._mock_cart(items=[mock_guest_item])
        mock_user_cart = self._mock_cart()
        mock_merged = self._mock_cart()
        with (
            patch(
                "app.modules.cart.service._repo.get_by_session",
                AsyncMock(return_value=mock_guest_cart),
            ),
            patch(
                "app.modules.cart.service._repo.get_for_user",
                AsyncMock(return_value=mock_user_cart),
            ),
            patch("app.modules.cart.service._repo.merge_guest_into_user", AsyncMock()),
            patch(
                "app.modules.cart.service._repo.get_by_id",
                AsyncMock(return_value=mock_merged),
            ),
        ):
            result = await self.svc.merge_guest_cart(
                db, user_id=uuid.uuid4(), session_id="old-sess"
            )
        assert result is not None
