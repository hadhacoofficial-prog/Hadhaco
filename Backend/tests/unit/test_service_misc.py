"""Tests for smaller service modules: audit, analytics, fraud, collections, cart (errors), auth, settings."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.analytics.repository import AnalyticsRepository
from app.modules.fraud.repository import FraudRepository
from app.modules.profiles.repository import ProfileRepository

# ─── AuditService ─────────────────────────────────────────────────────────────


class TestAuditService:
    def setup_method(self):
        from app.modules.audit.service import AuditService

        self.svc = AuditService()

    async def test_log_creates_entry_and_flushes(self):
        db = AsyncMock()
        db.add = MagicMock()
        result = await self.svc.log(
            db,
            actor_id=str(uuid.uuid4()),
            action="create",
            resource_type="product",
            resource_id=str(uuid.uuid4()),
            metadata={"key": "value"},
        )
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_log_works_with_minimal_args(self):
        db = AsyncMock()
        db.add = MagicMock()
        result = await self.svc.log(db, actor_id=None, action="login", resource_type="auth")
        db.add.assert_called_once()

    async def test_log_serializes_metadata(self):
        db = AsyncMock()
        db.add = MagicMock()
        from app.modules.audit.models import AuditLog

        captured = {}

        def capture_add(entry):
            if isinstance(entry, AuditLog):
                captured["entry"] = entry

        db.add = capture_add
        await self.svc.log(
            db,
            actor_id="actor-1",
            action="delete",
            resource_type="user",
            metadata={"reason": "spam"},
        )
        assert "entry" in captured
        import json

        assert json.loads(captured["entry"].meta) == {"reason": "spam"}


# ─── AnalyticsService ─────────────────────────────────────────────────────────


class TestAnalyticsService:
    def setup_method(self):
        from app.modules.analytics.service import AnalyticsService

        self.svc = AnalyticsService()

    async def test_track_delegates_to_repo(self):
        from app.modules.analytics.schemas import TrackEventRequest

        db = AsyncMock()
        with patch.object(AnalyticsRepository, "record", AsyncMock()):
            await self.svc.track(
                db,
                request=TrackEventRequest(event_type="product_view", product_id=uuid.uuid4()),
                user_id=None,
                ip_address="1.2.3.4",
                user_agent="Mozilla",
            )
        db.commit.assert_awaited_once()

    async def test_get_dashboard_returns_dict(self):
        db = AsyncMock()
        with (
            patch.object(
                AnalyticsRepository,
                "get_dashboard",
                AsyncMock(return_value={"revenue": 500, "total_orders": 10, "aov": 50}),
            ),
            patch.object(AnalyticsRepository, "get_revenue_by_day", AsyncMock(return_value=[])),
            patch.object(AnalyticsRepository, "get_orders_by_status", AsyncMock(return_value={})),
            patch.object(AnalyticsRepository, "get_top_products", AsyncMock(return_value=[])),
        ):
            result = await self.svc.get_dashboard(db, from_date=date.today(), to_date=date.today())
        assert "revenue" in result
        assert result["revenue"]["total"] == 500.0
        assert "orders" in result
        assert result["orders"]["total"] == 10
        assert "top_products" in result


# ─── FraudService ─────────────────────────────────────────────────────────────


class TestFraudService:
    def setup_method(self):
        from app.modules.fraud.service import FraudService

        self.svc = FraudService()

    async def test_resolve_signal_raises_404_when_not_found(self):
        from fastapi import HTTPException

        from app.modules.fraud.schemas import FraudResolveRequest

        db = AsyncMock()
        with patch.object(FraudRepository, "get", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.resolve_signal(
                    db,
                    signal_id=uuid.uuid4(),
                    resolver_id=uuid.uuid4(),
                    data=FraudResolveRequest(is_resolved=True),
                )
        assert exc.value.status_code == 404

    async def test_list_signals_delegates_to_repo(self):
        db = AsyncMock()
        with patch.object(FraudRepository, "list_unresolved", AsyncMock(return_value=[])):
            result = await self.svc.list_signals(db, offset=0, limit=20)
        assert result == []

    async def test_resolve_signal_success(self):
        from app.modules.fraud.schemas import FraudResolveRequest

        db = AsyncMock()
        mock_signal = MagicMock()
        mock_resolved = MagicMock()
        with (
            patch.object(FraudRepository, "get", AsyncMock(return_value=mock_signal)),
            patch.object(FraudRepository, "update", AsyncMock(return_value=mock_resolved)),
        ):
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            result = await self.svc.resolve_signal(
                db,
                signal_id=uuid.uuid4(),
                resolver_id=uuid.uuid4(),
                data=FraudResolveRequest(is_resolved=True),
            )
        assert result is mock_resolved


# ─── CollectionService ────────────────────────────────────────────────────────


class TestCollectionService:
    def setup_method(self):
        from app.modules.collections.service import CollectionService

        self.svc = CollectionService()

    async def test_get_by_slug_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.collections.service._repo.get_by_slug", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_by_slug(db, "no-such-slug")

    async def test_create_raises_conflict_for_existing_slug(self):
        from app.core.exceptions import ConflictError
        from app.modules.collections.schemas import CollectionCreateRequest

        db = AsyncMock()
        with patch(
            "app.modules.collections.service._repo.get_by_slug", AsyncMock(return_value=MagicMock())
        ):
            with pytest.raises(ConflictError):
                await self.svc.create(db, CollectionCreateRequest(name="Silver", slug="silver"))

    async def test_update_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.collections.schemas import CollectionUpdateRequest

        db = AsyncMock()
        with patch("app.modules.collections.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update(db, uuid.uuid4(), CollectionUpdateRequest())

    async def test_delete_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch("app.modules.collections.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.delete(db, uuid.uuid4())

    async def test_list_active_returns_empty_list(self):
        db = AsyncMock()
        with patch("app.modules.collections.service._repo.list_active", AsyncMock(return_value=[])):
            result = await self.svc.list_active(db)
        assert result == []


# ─── CartService (error paths only, no _build_summary) ────────────────────────


class TestCartServiceErrorPaths:
    def setup_method(self):
        from app.modules.cart.service import CartService

        self.svc = CartService()

    async def test_get_or_create_raises_validation_without_identifiers(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        with pytest.raises(ValidationError):
            await self.svc._get_or_create(db, user_id=None, session_id=None)

    async def test_update_item_raises_404_when_cart_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.cart.schemas import UpdateCartItemRequest

        db = AsyncMock()
        with patch("app.modules.cart.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update_item(
                    db, uuid.uuid4(), uuid.uuid4(), UpdateCartItemRequest(quantity=2)
                )

    async def test_update_item_raises_404_for_wrong_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.cart.schemas import UpdateCartItemRequest

        db = AsyncMock()
        mock_cart = MagicMock()
        mock_cart.user_id = uuid.uuid4()
        mock_cart.items = []
        with patch("app.modules.cart.service._repo.get_by_id", AsyncMock(return_value=mock_cart)):
            with pytest.raises(NotFoundError):
                await self.svc.update_item(
                    db,
                    uuid.uuid4(),
                    uuid.uuid4(),
                    UpdateCartItemRequest(quantity=2),
                    user_id=uuid.uuid4(),
                )

    async def test_update_item_raises_404_when_item_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.cart.schemas import UpdateCartItemRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_cart = MagicMock()
        mock_cart.user_id = user_id
        mock_cart.items = []  # no items
        with patch("app.modules.cart.service._repo.get_by_id", AsyncMock(return_value=mock_cart)):
            with pytest.raises(NotFoundError):
                await self.svc.update_item(
                    db,
                    uuid.uuid4(),
                    uuid.uuid4(),
                    UpdateCartItemRequest(quantity=2),
                    user_id=user_id,
                )

    async def test_remove_item_raises_404_when_cart_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch("app.modules.cart.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.remove_item(db, uuid.uuid4(), uuid.uuid4())

    async def test_remove_item_raises_404_for_wrong_user(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        mock_cart = MagicMock()
        mock_cart.user_id = uuid.uuid4()
        with patch("app.modules.cart.service._repo.get_by_id", AsyncMock(return_value=mock_cart)):
            with pytest.raises(NotFoundError):
                await self.svc.remove_item(db, uuid.uuid4(), uuid.uuid4(), user_id=uuid.uuid4())


# ─── AuthService ──────────────────────────────────────────────────────────────


class TestAuthService:
    def setup_method(self):
        from app.modules.auth.service import AuthService

        self.svc = AuthService()

    async def test_verify_token_raises_404_when_profile_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.verify_token_and_get_profile(db, str(uuid.uuid4()))

    async def test_verify_token_raises_authorization_error_when_inactive(self):
        from app.core.exceptions import AuthorizationError

        db = AsyncMock()
        mock_profile = MagicMock()
        mock_profile.is_active = False
        with patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)):
            with pytest.raises(AuthorizationError):
                await self.svc.verify_token_and_get_profile(db, str(uuid.uuid4()))

    async def test_verify_token_returns_active_profile(self):
        db = AsyncMock()
        mock_profile = MagicMock()
        mock_profile.is_active = True
        with patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)):
            result = await self.svc.verify_token_and_get_profile(db, str(uuid.uuid4()))
        assert result is mock_profile


# ─── SettingsService ──────────────────────────────────────────────────────────


class TestSettingsService:
    def setup_method(self):
        from app.modules.settings.service import SettingsService

        self.svc = SettingsService()

    async def test_is_feature_enabled_returns_false_when_flag_missing(self):
        db = AsyncMock()
        with patch("app.modules.settings.service._repo.get_flag", AsyncMock(return_value=None)):
            result = await self.svc.is_feature_enabled(db, "my_feature")
        assert result is False

    async def test_is_feature_enabled_returns_flag_value(self):
        db = AsyncMock()
        mock_flag = MagicMock()
        mock_flag.value = True
        with patch(
            "app.modules.settings.service._repo.get_flag", AsyncMock(return_value=mock_flag)
        ):
            result = await self.svc.is_feature_enabled(db, "my_feature")
        assert result is True

    async def test_list_flags_returns_empty(self):
        db = AsyncMock()
        with patch("app.modules.settings.service._repo.list_flags", AsyncMock(return_value=[])):
            result = await self.svc.list_flags(db)
        assert result == []

    async def test_set_flag_creates_and_commits(self):
        from app.modules.settings.schemas import FeatureFlagUpdate

        db = AsyncMock()
        mock_flag = MagicMock()
        with patch(
            "app.modules.settings.service._repo.upsert_flag", AsyncMock(return_value=mock_flag)
        ):
            result = await self.svc.set_flag(
                db,
                key="dark_mode",
                data=FeatureFlagUpdate(value=True),
                updated_by=uuid.uuid4(),
            )
        assert result is mock_flag
        db.commit.assert_awaited_once()
