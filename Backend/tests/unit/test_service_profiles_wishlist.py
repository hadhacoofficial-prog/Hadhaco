"""ProfileService and WishlistService mock-based tests."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.profiles.repository import ProfileRepository
from app.modules.profiles.schemas import ProfileUpdateRequest


class TestProfileService:
    def setup_method(self):
        from app.modules.profiles.service import ProfileService
        self.svc = ProfileService()

    async def test_get_profile_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_profile(db, uuid.uuid4())

    async def test_get_profile_returns_profile(self):
        db = AsyncMock()
        mock_profile = MagicMock()
        with patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)):
            result = await self.svc.get_profile(db, uuid.uuid4())
        assert result is mock_profile

    async def test_update_profile_returns_current_when_no_data(self):
        db = AsyncMock()
        mock_profile = MagicMock()
        with patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)):
            result = await self.svc.update_profile(db, uuid.uuid4(), ProfileUpdateRequest())
        assert result is mock_profile

    async def test_update_profile_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch.object(ProfileRepository, "update", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update_profile(db, uuid.uuid4(), ProfileUpdateRequest(full_name="Alice"))

    async def test_update_profile_success(self):
        db = AsyncMock()
        mock_profile = MagicMock()
        with patch.object(ProfileRepository, "update", AsyncMock(return_value=mock_profile)):
            result = await self.svc.update_profile(db, uuid.uuid4(), ProfileUpdateRequest(full_name="Alice"))
        assert result is mock_profile

    async def test_update_avatar_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch.object(ProfileRepository, "update", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update_avatar(db, uuid.uuid4(), "https://example.com/avatar.jpg")

    async def test_update_avatar_success(self):
        db = AsyncMock()
        mock_profile = MagicMock()
        with patch.object(ProfileRepository, "update", AsyncMock(return_value=mock_profile)):
            result = await self.svc.update_avatar(db, uuid.uuid4(), "https://example.com/avatar.jpg")
        assert result is mock_profile

    async def test_change_role_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.core.constants import UserRole
        db = AsyncMock()
        with patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.change_role(db, uuid.uuid4(), UserRole.ADMIN, uuid.uuid4())

    async def test_set_status_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.set_status(db, uuid.uuid4(), False, uuid.uuid4())

    async def test_list_users_empty_returns_response(self):
        db = AsyncMock()
        with patch.object(ProfileRepository, "list_paginated", AsyncMock(return_value=([], 0))):
            result = await self.svc.list_users(db)
        assert result.total == 0
        assert result.items == []

    async def test_list_users_pagination_params(self):
        db = AsyncMock()
        with patch.object(ProfileRepository, "list_paginated", AsyncMock(return_value=([], 100))):
            result = await self.svc.list_users(db, page=3, page_size=20)
        assert result.page == 3
        assert result.page_size == 20
        assert result.total == 100
        assert result.total_pages == 5


class TestWishlistService:
    def setup_method(self):
        from app.modules.wishlist.service import WishlistService
        self.svc = WishlistService()

    def _make_wishlist(self, items=None):
        w = MagicMock()
        w.id = uuid.uuid4()
        w.items = items or []
        return w

    async def test_get_returns_empty_wishlist(self):
        db = AsyncMock()
        wishlist = self._make_wishlist()
        with patch("app.modules.wishlist.service._repo.get_or_create", AsyncMock(return_value=wishlist)):
            result = await self.svc.get(db, uuid.uuid4())
        assert result.total == 0
        assert result.items == []

    async def test_get_returns_items(self):
        from datetime import datetime, timezone
        from app.modules.wishlist.schemas import WishlistItemResponse
        db = AsyncMock()
        real_item = WishlistItemResponse(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            variant_id=None,
            added_at=datetime.now(timezone.utc),
        )
        mock_schema_cls = MagicMock()
        mock_schema_cls.model_validate.return_value = real_item
        wishlist = self._make_wishlist(items=[MagicMock()])
        with patch("app.modules.wishlist.service._repo.get_or_create", AsyncMock(return_value=wishlist)), \
             patch("app.modules.wishlist.service.WishlistItemResponse", mock_schema_cls):
            result = await self.svc.get(db, uuid.uuid4())
        assert result.total == 1

    async def test_toggle_removes_when_already_in_wishlist(self):
        db = AsyncMock()
        wishlist = self._make_wishlist()
        product_id = uuid.uuid4()
        from app.modules.wishlist.schemas import AddToWishlistRequest
        with patch("app.modules.wishlist.service._repo.get_or_create", AsyncMock(return_value=wishlist)), \
             patch("app.modules.wishlist.service._repo.is_in_wishlist", AsyncMock(return_value=True)), \
             patch("app.modules.wishlist.service._repo.remove_item", AsyncMock()):
            result = await self.svc.toggle(db, uuid.uuid4(), AddToWishlistRequest(product_id=product_id))
        assert result["action"] == "removed"
        assert result["product_id"] == str(product_id)

    async def test_toggle_adds_when_not_in_wishlist(self):
        db = AsyncMock()
        wishlist = self._make_wishlist()
        product_id = uuid.uuid4()
        from app.modules.wishlist.schemas import AddToWishlistRequest
        with patch("app.modules.wishlist.service._repo.get_or_create", AsyncMock(return_value=wishlist)), \
             patch("app.modules.wishlist.service._repo.is_in_wishlist", AsyncMock(return_value=False)), \
             patch("app.modules.wishlist.service._repo.add_item", AsyncMock()):
            result = await self.svc.toggle(db, uuid.uuid4(), AddToWishlistRequest(product_id=product_id))
        assert result["action"] == "added"
