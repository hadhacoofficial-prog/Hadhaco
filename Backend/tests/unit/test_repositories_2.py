"""Tests for remaining repositories: CMS, Notifications, Payments, Cart, Shipping, Settings, Analytics."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

# Force all SQLAlchemy mappers to initialize before any test runs
import app.modules.catalog.models  # noqa: F401
import app.modules.categories.models  # noqa: F401
import app.modules.orders.models  # noqa: F401
import app.modules.reviews.models  # noqa: F401
import app.modules.inventory.models  # noqa: F401
import app.modules.collections.models  # noqa: F401
import app.modules.coupons.models  # noqa: F401
import app.modules.payments.models  # noqa: F401
import app.modules.profiles.models  # noqa: F401
import app.modules.addresses.models  # noqa: F401
import app.modules.shipping.models  # noqa: F401
import app.modules.cart.models  # noqa: F401
import app.modules.wishlist.models  # noqa: F401
import app.modules.support.models  # noqa: F401
import app.modules.returns.models  # noqa: F401
import app.modules.cms.models  # noqa: F401
import app.modules.notifications.models  # noqa: F401
import app.modules.settings.models  # noqa: F401
import app.modules.analytics.models  # noqa: F401


# ─── Mock helpers ─────────────────────────────────────────────────────────────

def _scalars(items):
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


def _fetchall(rows):
    r = MagicMock()
    r.fetchall.return_value = rows
    return r


def _db(*results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


# ─── CMSRepository ────────────────────────────────────────────────────────────

class TestCMSRepository:
    def setup_method(self):
        from app.modules.cms.repository import CMSRepository
        self.repo = CMSRepository()

    async def test_get_active_banners_no_filter(self):
        mock_banner = MagicMock()
        db = _db(_scalars([mock_banner]))
        result = await self.repo.get_active_banners(db)
        assert result == [mock_banner]

    async def test_get_active_banners_with_type(self):
        db = _db(_scalars([]))
        result = await self.repo.get_active_banners(db, banner_type="hero")
        assert result == []

    async def test_get_active_sections(self):
        mock_sec = MagicMock()
        db = _db(_scalars([mock_sec]))
        result = await self.repo.get_active_sections(db)
        assert result == [mock_sec]

    async def test_get_section_by_key(self):
        mock_sec = MagicMock()
        db = _db(_scalar_one_or_none(mock_sec))
        result = await self.repo.get_section_by_key(db, "hero")
        assert result is mock_sec

    async def test_update_section_sets_attrs(self):
        db = _db()
        section = MagicMock()
        result = await self.repo.update_section(db, section, {"title": "New Title"})
        assert section.title == "New Title"
        assert result is section

    async def test_get_page_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_page(db, "about")
        assert result is None

    async def test_get_page_returns_page(self):
        mock_page = MagicMock()
        db = _db(_scalar_one_or_none(mock_page))
        result = await self.repo.get_page(db, "about")
        assert result is mock_page

    async def test_create_banner(self):
        from app.modules.cms.models import Banner
        db = _db()
        result = await self.repo.create_banner(db, name="sale", banner_type="hero", is_active=True)
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_update_banner_sets_attrs(self):
        db = _db()
        banner = MagicMock()
        result = await self.repo.update_banner(db, banner, {"title": "Updated"})
        assert banner.title == "Updated"
        assert result is banner

    async def test_get_banner_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_banner(db, uuid.uuid4())
        assert result is None

    async def test_get_banner_returns_banner(self):
        mock_banner = MagicMock()
        db = _db(_scalar_one_or_none(mock_banner))
        result = await self.repo.get_banner(db, uuid.uuid4())
        assert result is mock_banner

    async def test_delete_banner_sets_deleted_at(self):
        db = _db()
        banner = MagicMock()
        await self.repo.delete_banner(db, banner)
        assert banner.deleted_at is not None

    async def test_create_page(self):
        db = _db()
        await self.repo.create_page(db, slug="test-page", title="Test")
        db.add.assert_called_once()

    async def test_update_page_sets_attrs(self):
        db = _db()
        page = MagicMock()
        result = await self.repo.update_page(db, page, {"title": "New"})
        assert page.title == "New"

    async def test_get_page_by_id_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_page_by_id(db, uuid.uuid4())
        assert result is None

    async def test_get_setting_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_setting(db, "store_name")
        assert result is None

    async def test_get_public_settings(self):
        db = _db(_scalars([MagicMock()]))
        result = await self.repo.get_public_settings(db)
        assert len(result) == 1

    async def test_get_all_settings(self):
        db = _db(_scalars([MagicMock(), MagicMock()]))
        result = await self.repo.get_all_settings(db)
        assert len(result) == 2


# ─── NotificationRepository ───────────────────────────────────────────────────

class TestNotificationRepository:
    def setup_method(self):
        from app.modules.notifications.repository import NotificationRepository
        self.repo = NotificationRepository()

    async def test_get_template_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_template(db, event_type="order_confirmed", channel="email")
        assert result is None

    async def test_get_template_returns_template(self):
        mock_tpl = MagicMock()
        db = _db(_scalar_one_or_none(mock_tpl))
        result = await self.repo.get_template(db, event_type="order_confirmed", channel="email")
        assert result is mock_tpl

    async def test_create_log_adds_to_db(self):
        db = _db()
        log = await self.repo.create_log(db, event_type="order_confirmed", channel="email", user_id=uuid.uuid4())
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_mark_sent_updates_status(self):
        db = _db()
        db.add = MagicMock()
        log = MagicMock()
        log.attempt_count = 0
        await self.repo.mark_sent(db, log, "msg-123", "resend")
        assert log.status == "sent"
        assert log.provider == "resend"
        assert log.provider_message_id == "msg-123"
        assert log.attempt_count == 1

    async def test_mark_failed_under_retry_limit_sets_retrying(self):
        db = _db()
        db.add = MagicMock()
        log = MagicMock()
        log.attempt_count = 0
        await self.repo.mark_failed(db, log, "SMTP timeout")
        assert log.status == "retrying"
        assert log.next_retry_at is not None

    async def test_mark_failed_over_retry_limit_sets_failed(self):
        db = _db()
        db.add = MagicMock()
        log = MagicMock()
        log.attempt_count = 99  # over limit (len(_RETRY_DELAYS) = 3)
        await self.repo.mark_failed(db, log, "permanent failure")
        assert log.status == "failed"
        assert log.next_retry_at is None

    async def test_get_pending_retries_returns_list(self):
        mock_log = MagicMock()
        db = _db(_scalars([mock_log]))
        result = await self.repo.get_pending_retries(db)
        assert result == [mock_log]

    async def test_get_preferences_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_preferences(db, uuid.uuid4())
        assert result is None

    async def test_upsert_preferences_creates_new(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.upsert_preferences(db, uuid.uuid4(), {"email_enabled": True})
        db.add.assert_called_once()

    async def test_upsert_preferences_updates_existing(self):
        mock_pref = MagicMock()
        db = _db(_scalar_one_or_none(mock_pref))
        result = await self.repo.upsert_preferences(db, uuid.uuid4(), {"email_enabled": False})
        assert mock_pref.email_enabled is False


# ─── PaymentRepository ────────────────────────────────────────────────────────

class TestPaymentRepository:
    def setup_method(self):
        from app.modules.payments.repository import PaymentRepository
        self.repo = PaymentRepository()

    async def test_create_adds_and_returns(self):
        db = _db()
        await self.repo.create(db, {"order_id": uuid.uuid4(), "amount": 1000, "currency": "INR"})
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_get_by_id_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is None

    async def test_get_by_id_returns_payment(self):
        mock_payment = MagicMock()
        db = _db(_scalar_one_or_none(mock_payment))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_payment

    async def test_get_by_razorpay_order_id(self):
        mock_payment = MagicMock()
        db = _db(_scalar_one_or_none(mock_payment))
        result = await self.repo.get_by_razorpay_order_id(db, "order_abc123")
        assert result is mock_payment

    async def test_get_for_order_returns_latest(self):
        mock_payment = MagicMock()
        db = _db(_scalar_one_or_none(mock_payment))
        result = await self.repo.get_for_order(db, uuid.uuid4())
        assert result is mock_payment

    async def test_update_returns_updated_payment(self):
        mock_payment = MagicMock()
        # First execute: UPDATE (returns rowcount mock), second: SELECT get_by_id
        db = _db(MagicMock(), _scalar_one_or_none(mock_payment))
        result = await self.repo.update(db, uuid.uuid4(), {"status": "captured"})
        assert result is mock_payment

    async def test_create_refund(self):
        db = _db()
        await self.repo.create_refund(db, {"payment_id": uuid.uuid4(), "amount": 500})
        db.add.assert_called_once()

    async def test_update_refund(self):
        mock_refund = MagicMock()
        db = _db(MagicMock(), _scalar_one_or_none(mock_refund))
        result = await self.repo.update_refund(db, uuid.uuid4(), {"status": "processed"})
        assert result is mock_refund

    async def test_get_refunds_for_order(self):
        mock_refund = MagicMock()
        db = _db(_scalars([mock_refund]))
        result = await self.repo.get_refunds_for_order(db, uuid.uuid4())
        assert result == [mock_refund]

    async def test_create_invoice(self):
        db = _db()
        await self.repo.create_invoice(db, {"order_id": uuid.uuid4(), "invoice_number": "INV-202406-000001"})
        db.add.assert_called_once()

    async def test_get_invoice_for_order_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_invoice_for_order(db, uuid.uuid4())
        assert result is None

    async def test_generate_invoice_number_format(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        db = _db(mock_count)
        result = await self.repo.generate_invoice_number(db)
        assert result.startswith(f"INV-{now.year}{now.month:02d}-")
        assert result.endswith("000001")


# ─── CartRepository ───────────────────────────────────────────────────────────

class TestCartRepository:
    def setup_method(self):
        from app.modules.cart.repository import CartRepository
        self.repo = CartRepository()

    def test_expiry_returns_datetime(self):
        exp = self.repo._expiry(authenticated=False)
        assert isinstance(exp, datetime)

    def test_expiry_authenticated_is_later(self):
        guest = self.repo._expiry(authenticated=False)
        auth = self.repo._expiry(authenticated=True)
        assert auth > guest

    async def test_get_for_user_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_for_user(db, uuid.uuid4())
        assert result is None

    async def test_get_by_session_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_by_session(db, "session-abc")
        assert result is None

    async def test_get_by_id_returns_cart(self):
        mock_cart = MagicMock()
        db = _db(_scalar_one_or_none(mock_cart))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_cart

    async def test_create_for_user(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        result = await self.repo.create(db, user_id=uuid.uuid4(), session_id=None)
        db.add.assert_called_once()
        assert result is not None  # Cart object

    async def test_create_for_guest(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        result = await self.repo.create(db, user_id=None, session_id="session-xyz")
        db.add.assert_called_once()

    async def test_upsert_item_creates_new_when_not_exists(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # no existing item
        db.execute = AsyncMock(return_value=mock_result)
        await self.repo.upsert_item(db, uuid.uuid4(), uuid.uuid4(), None, 2, 599.0)
        db.add.assert_called_once()

    async def test_upsert_item_increments_existing(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        existing = MagicMock()
        existing.quantity = 3
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.repo.upsert_item(db, uuid.uuid4(), uuid.uuid4(), None, 2, 599.0)
        assert result is existing
        assert existing.quantity == 5  # 3 + 2

    async def test_upsert_item_caps_at_100(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        existing = MagicMock()
        existing.quantity = 99
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=mock_result)
        await self.repo.upsert_item(db, uuid.uuid4(), uuid.uuid4(), None, 10, 599.0)
        assert existing.quantity == 100  # capped

    async def test_update_item_quantity(self):
        mock_item = MagicMock()
        db = _db(MagicMock(), _scalar_one_or_none(mock_item))
        result = await self.repo.update_item_quantity(db, uuid.uuid4(), 5)
        assert result is mock_item

    async def test_remove_item_returns_true_on_found(self):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db = _db(mock_result)
        result = await self.repo.remove_item(db, uuid.uuid4())
        assert result is True

    async def test_remove_item_returns_false_on_not_found(self):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db = _db(mock_result)
        result = await self.repo.remove_item(db, uuid.uuid4())
        assert result is False

    async def test_clear_items(self):
        db = _db(MagicMock())
        await self.repo.clear_items(db, uuid.uuid4())
        db.execute.assert_awaited_once()

    async def test_update_cart(self):
        db = _db(MagicMock())
        await self.repo.update_cart(db, uuid.uuid4(), {"coupon_code": "SAVE10"})
        db.execute.assert_awaited_once()

    async def test_merge_guest_into_user_calls_upsert_for_each_item(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        guest_item1 = MagicMock()
        guest_item1.product_id = uuid.uuid4()
        guest_item1.variant_id = None
        guest_item1.quantity = 2
        guest_item1.unit_price = 500.0

        guest_cart = MagicMock()
        guest_cart.items = [guest_item1]
        guest_cart.id = uuid.uuid4()

        user_cart = MagicMock()
        user_cart.id = uuid.uuid4()

        # mock execute for upsert_item (select existing = None) + expire guest cart
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        mock_update = MagicMock()
        db.execute = AsyncMock(side_effect=[mock_none, mock_update])

        await self.repo.merge_guest_into_user(db, guest_cart, user_cart)
        assert db.execute.await_count == 2  # one select + one update


# ─── ShipmentRepository ───────────────────────────────────────────────────────

class TestShipmentRepository:
    def setup_method(self):
        from app.modules.shipping.repository import ShipmentRepository
        self.repo = ShipmentRepository()

    async def test_get_for_order_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_for_order(db, uuid.uuid4())
        assert result is None

    async def test_get_by_id_returns_shipment(self):
        mock_ship = MagicMock()
        db = _db(_scalar_one_or_none(mock_ship))
        result = await self.repo.get_by_id(db, uuid.uuid4())
        assert result is mock_ship

    async def test_get_by_awb_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_by_awb(db, "AWB-999")
        assert result is None

    async def test_create_shipment(self):
        db = _db()
        await self.repo.create(db, {"order_id": uuid.uuid4(), "status": "created", "awb_number": "AWB-001"})
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_update_calls_get_by_id(self):
        mock_ship = MagicMock()
        # First execute: UPDATE, second: SELECT (from get_by_id)
        db = _db(MagicMock(), _scalar_one_or_none(mock_ship))
        result = await self.repo.update(db, uuid.uuid4(), {"status": "delivered"})
        assert result is mock_ship

    async def test_add_event_adds_to_db(self):
        db = _db()
        await self.repo.add_event(db, {"shipment_id": uuid.uuid4(), "status": "in_transit", "description": "On the way"})
        db.add.assert_called_once()

    async def test_list_active_returns_list(self):
        mock_ship = MagicMock()
        db = _db(_scalars([mock_ship]))
        result = await self.repo.list_active(db)
        assert result == [mock_ship]


# ─── SettingsRepository ───────────────────────────────────────────────────────

class TestSettingsRepository:
    def setup_method(self):
        from app.modules.settings.repository import SettingsRepository
        self.repo = SettingsRepository()

    async def test_get_flag_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_flag(db, "enable_cod")
        assert result is None

    async def test_get_flag_returns_flag(self):
        mock_flag = MagicMock()
        db = _db(_scalar_one_or_none(mock_flag))
        result = await self.repo.get_flag(db, "enable_cod")
        assert result is mock_flag

    async def test_list_flags(self):
        db = _db(_scalars([MagicMock(), MagicMock()]))
        result = await self.repo.list_flags(db)
        assert len(result) == 2

    async def test_upsert_flag_returns_flag(self):
        mock_flag = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_flag
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        result = await self.repo.upsert_flag(db, key="enable_cod", value=True, description="Cash on delivery", updated_by=None)
        assert result is mock_flag


# ─── AnalyticsRepository ──────────────────────────────────────────────────────

class TestAnalyticsRepository:
    def setup_method(self):
        from app.modules.analytics.repository import AnalyticsRepository
        self.repo = AnalyticsRepository()

    async def test_record_adds_event(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        await self.repo.record(db, event_type="page_view", user_id=None, session_id="abc")
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_get_dashboard_returns_empty_when_no_row(self):
        from datetime import date
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.repo.get_dashboard(db, from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))
        assert result == {}

    async def test_get_dashboard_returns_dict_when_row_found(self):
        from datetime import date
        mock_row = MagicMock()
        mock_row._mapping = {"revenue": 10000, "total_orders": 5, "aov": 2000}
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.repo.get_dashboard(db, from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))
        assert result["revenue"] == 10000

    async def test_get_revenue_by_day_returns_list(self):
        from datetime import date
        mock_row = MagicMock()
        mock_row._mapping = {"date": date(2026, 1, 5), "revenue": 5000, "orders": 2}
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.repo.get_revenue_by_day(db, from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))
        assert len(result) == 1
        assert result[0]["revenue"] == 5000

    async def test_get_orders_by_status(self):
        from datetime import date
        mock_row = MagicMock()
        mock_row.status = "delivered"
        mock_row.cnt = 10
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.repo.get_orders_by_status(db, from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))
        assert result == {"delivered": 10}

    async def test_get_top_products_returns_list(self):
        from datetime import date
        mock_row = MagicMock()
        mock_row._mapping = {"product_id": uuid.uuid4(), "name": "Silver Ring", "slug": "silver-ring", "units_sold": 50, "revenue": 25000}
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.repo.get_top_products(db, from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))
        assert len(result) == 1
        assert result[0]["name"] == "Silver Ring"
