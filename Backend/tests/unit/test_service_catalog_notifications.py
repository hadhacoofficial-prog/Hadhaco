"""Tests for CatalogService and NotificationService."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.catalog.repository import ProductRepository
from app.modules.notifications.repository import NotificationRepository


# ─── CatalogService ───────────────────────────────────────────────────────────

class TestCatalogService:
    def setup_method(self):
        from app.modules.catalog.service import CatalogService
        self.svc = CatalogService()

    async def test_get_by_id_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_by_id(db, uuid.uuid4())

    async def test_get_by_slug_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_slug", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_by_slug(db, "no-product")

    async def test_list_products_returns_empty_response(self):
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.list_paginated", AsyncMock(return_value=([], 0))):
            result = await self.svc.list_products(db)
        assert result.total == 0
        assert result.items == []

    async def test_list_products_pagination(self):
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.list_paginated", AsyncMock(return_value=([], 50))):
            result = await self.svc.list_products(db, page=3, page_size=10)
        assert result.page == 3
        assert result.total == 50
        assert result.total_pages == 5

    async def test_create_raises_conflict_for_duplicate_sku(self):
        from app.core.exceptions import ConflictError
        from app.modules.catalog.schemas import ProductCreateRequest
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_sku", AsyncMock(return_value=MagicMock())):
            with pytest.raises(ConflictError):
                await self.svc.create(
                    db,
                    ProductCreateRequest(
                        name="Ring", slug="ring", sku="SR-001",
                        base_price=1000.0, tax_rate=3.0,
                    ),
                )

    async def test_create_raises_conflict_for_duplicate_slug(self):
        from app.core.exceptions import ConflictError
        from app.modules.catalog.schemas import ProductCreateRequest
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_sku", AsyncMock(return_value=None)), \
             patch("app.modules.catalog.service._repo.get_by_slug", AsyncMock(return_value=MagicMock())):
            with pytest.raises(ConflictError):
                await self.svc.create(
                    db,
                    ProductCreateRequest(
                        name="Ring", slug="ring", sku="SR-NEW",
                        base_price=1000.0, tax_rate=3.0,
                    ),
                )

    async def test_update_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.catalog.schemas import ProductUpdateRequest
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update(db, uuid.uuid4(), ProductUpdateRequest())

    async def test_delete_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.delete(db, uuid.uuid4())

    async def test_add_variant_raises_404_when_product_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.catalog.schemas import ProductVariantCreateRequest
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.add_variant(
                    db,
                    uuid.uuid4(),
                    ProductVariantCreateRequest(name="Large", sku="SR-001-L"),
                )

    async def test_upsert_attribute_raises_404_when_product_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.catalog.schemas import ProductAttributeCreateRequest
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.upsert_attribute(
                    db,
                    uuid.uuid4(),
                    ProductAttributeCreateRequest(name="Material", value="Silver"),
                )

    async def test_adjust_stock_raises_404_when_product_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.catalog.schemas import StockAdjustRequest
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.adjust_stock(db, uuid.uuid4(), StockAdjustRequest(delta=-5))

    async def test_adjust_stock_raises_validation_on_insufficient_stock(self):
        from app.core.exceptions import ValidationError
        from app.modules.catalog.schemas import StockAdjustRequest
        db = AsyncMock()
        mock_product = MagicMock()
        with patch("app.modules.catalog.service._repo.get_by_id", AsyncMock(return_value=mock_product)), \
             patch("app.modules.catalog.service._repo.adjust_stock", AsyncMock(side_effect=[-5, 5])):
            with pytest.raises(ValidationError):
                await self.svc.adjust_stock(db, uuid.uuid4(), StockAdjustRequest(delta=-5))

    async def test_update_variant_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.catalog.schemas import ProductVariantUpdateRequest
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.get_variant", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update_variant(db, uuid.uuid4(), ProductVariantUpdateRequest())

    async def test_delete_variant_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.delete_variant", AsyncMock(return_value=False)):
            with pytest.raises(NotFoundError):
                await self.svc.delete_variant(db, uuid.uuid4())

    async def test_delete_attribute_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.catalog.service._repo.delete_attribute", AsyncMock(return_value=False)):
            with pytest.raises(NotFoundError):
                await self.svc.delete_attribute(db, uuid.uuid4(), "Color")


# ─── NotificationService ──────────────────────────────────────────────────────

class TestNotificationService:
    def setup_method(self):
        from app.modules.notifications.service import NotificationService
        self.svc = NotificationService()

    async def test_send_email_skips_when_no_template(self):
        db = AsyncMock()
        with patch.object(NotificationRepository, "get_template", AsyncMock(return_value=None)):
            await self.svc.send_email(
                db,
                user_id=uuid.uuid4(),
                event_type="nonexistent_event",
                recipient="test@example.com",
                context={},
            )
        db.commit.assert_not_called()

    async def test_send_sms_skips_when_no_template(self):
        db = AsyncMock()
        with patch.object(NotificationRepository, "get_template", AsyncMock(return_value=None)):
            await self.svc.send_sms(
                db,
                user_id=uuid.uuid4(),
                event_type="nonexistent_event",
                recipient="+919999999999",
                context={},
            )

    async def test_send_email_creates_log_and_sends(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.subject = "Hello {{ name }}"
        mock_template.template_body = "<p>Hi {{ name }}</p>"
        mock_log = MagicMock()
        mock_log.id = uuid.uuid4()

        with patch.object(NotificationRepository, "get_template", AsyncMock(return_value=mock_template)), \
             patch.object(NotificationRepository, "create_log", AsyncMock(return_value=mock_log)), \
             patch.object(NotificationRepository, "mark_sent", AsyncMock()), \
             patch.object(type(self.svc._email_primary), "send_email", AsyncMock(return_value="msg-123")):
            await self.svc.send_email(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                context={"name": "Alice"},
            )

    async def test_send_email_marks_failed_when_primary_fails(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.subject = "Test"
        mock_template.template_body = "<p>Test</p>"
        mock_log = MagicMock()

        with patch.object(NotificationRepository, "get_template", AsyncMock(return_value=mock_template)), \
             patch.object(NotificationRepository, "create_log", AsyncMock(return_value=mock_log)), \
             patch.object(NotificationRepository, "mark_failed", AsyncMock()), \
             patch.object(type(self.svc._email_primary), "send_email", AsyncMock(side_effect=Exception("SMTP error"))):
            await self.svc.send_email(
                db,
                user_id=None,
                event_type="test",
                recipient="test@example.com",
                context={},
            )

    async def test_retry_pending_with_no_retries(self):
        db = AsyncMock()
        with patch.object(NotificationRepository, "get_pending_retries", AsyncMock(return_value=[])):
            await self.svc.retry_pending(db)

    async def test_send_sms_creates_log_and_sends_when_enabled(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.template_body = "Your order {{ order_number }} is confirmed"
        mock_log = MagicMock()
        with patch("app.modules.notifications.service.settings") as mock_settings, \
             patch.object(NotificationRepository, "get_template", AsyncMock(return_value=mock_template)), \
             patch.object(NotificationRepository, "create_log", AsyncMock(return_value=mock_log)), \
             patch.object(NotificationRepository, "mark_sent", AsyncMock()), \
             patch.object(type(self.svc._sms), "send_sms", AsyncMock(return_value="req-456")):
            mock_settings.SMS_ENABLED = True
            await self.svc.send_sms(
                db,
                user_id=uuid.uuid4(),
                event_type="order_shipped",
                recipient="+919999999999",
                context={"order_number": "ORD-001"},
            )

    async def test_send_sms_skipped_when_disabled(self):
        db = AsyncMock()
        with patch("app.modules.notifications.service.settings") as mock_settings:
            mock_settings.SMS_ENABLED = False
            await self.svc.send_sms(
                db,
                user_id=uuid.uuid4(),
                event_type="order_shipped",
                recipient="+919999999999",
                context={},
            )
        db.commit.assert_not_called()
