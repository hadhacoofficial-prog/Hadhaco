"""Tests for Wishlist, Support, Returns, Fraud, and Audit repositories."""

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import app.modules.addresses.models  # noqa: F401
import app.modules.analytics.models  # noqa: F401
import app.modules.audit.models  # noqa: F401
import app.modules.cart.models  # noqa: F401

# Force SQLAlchemy mapper init
import app.modules.catalog.models  # noqa: F401
import app.modules.categories.models  # noqa: F401
import app.modules.cms.models  # noqa: F401
import app.modules.collections.models  # noqa: F401
import app.modules.coupons.models  # noqa: F401
import app.modules.fraud.models  # noqa: F401
import app.modules.inventory.models  # noqa: F401
import app.modules.notifications.models  # noqa: F401
import app.modules.orders.models  # noqa: F401
import app.modules.payments.models  # noqa: F401
import app.modules.profiles.models  # noqa: F401
import app.modules.returns.models  # noqa: F401
import app.modules.reviews.models  # noqa: F401
import app.modules.settings.models  # noqa: F401
import app.modules.shipping.models  # noqa: F401
import app.modules.support.models  # noqa: F401
import app.modules.wishlist.models  # noqa: F401


def _scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _scalar_one_or_none(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalar_one(value):
    r = MagicMock()
    r.scalar_one.return_value = value
    return r


def _scalar(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _fetchone(value):
    r = MagicMock()
    r.fetchone.return_value = value
    return r


def _db(*results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


# ─── WishlistRepository ───────────────────────────────────────────────────────


class TestWishlistRepository:
    def setup_method(self):
        from app.modules.wishlist.repository import WishlistRepository

        self.repo = WishlistRepository()

    async def test_get_or_create_returns_existing(self):
        mock_wishlist = MagicMock()
        db = _db(_scalar_one_or_none(mock_wishlist))
        result = await self.repo.get_or_create(db, uuid.uuid4())
        assert result is mock_wishlist

    async def test_get_or_create_creates_new_when_not_found(self):
        from app.modules.wishlist.models import Wishlist

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        new_wishlist = MagicMock(spec=Wishlist)
        new_wishlist.id = uuid.uuid4()

        call_count = [0]

        async def mock_execute(stmt):
            r = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                r.scalar_one_or_none.return_value = None
            elif call_count[0] == 2:
                # reload after flush
                r.scalar_one_or_none.return_value = new_wishlist
                r.scalar_one.return_value = new_wishlist
            return r

        db.execute = mock_execute
        await self.repo.get_or_create(db, uuid.uuid4())
        db.add.assert_called_once()

    async def test_add_item_inserts_and_returns(self):
        mock_item = MagicMock()
        db = _db(MagicMock(), _scalar_one(mock_item))
        result = await self.repo.add_item(db, uuid.uuid4(), uuid.uuid4(), None)
        assert result is mock_item

    async def test_remove_item_returns_true_when_found(self):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db = _db(mock_result)
        result = await self.repo.remove_item(db, uuid.uuid4(), uuid.uuid4(), None)
        assert result is True

    async def test_remove_item_returns_false_when_not_found(self):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db = _db(mock_result)
        result = await self.repo.remove_item(db, uuid.uuid4(), uuid.uuid4(), None)
        assert result is False

    async def test_remove_item_with_variant(self):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db = _db(mock_result)
        result = await self.repo.remove_item(
            db, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        )
        assert result is True

    async def test_is_in_wishlist_true(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        db = _db(mock_result)
        result = await self.repo.is_in_wishlist(db, uuid.uuid4(), uuid.uuid4(), None)
        assert result is True

    async def test_is_in_wishlist_false(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.is_in_wishlist(db, uuid.uuid4(), uuid.uuid4(), None)
        assert result is False

    async def test_is_in_wishlist_with_variant(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        db = _db(mock_result)
        result = await self.repo.is_in_wishlist(
            db, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        )
        assert result is True


# ─── SupportRepository ────────────────────────────────────────────────────────


class TestSupportRepository:
    def setup_method(self):
        from app.modules.support.repository import SupportRepository

        self.repo = SupportRepository()

    async def test_create_ticket(self):
        db = _db()
        await self.repo.create_ticket(
            db, customer_id=uuid.uuid4(), subject="Order issue", status="open"
        )
        db.add.assert_called_once()

    async def test_add_message(self):
        db = _db()
        await self.repo.add_message(
            db, ticket_id=uuid.uuid4(), sender_id=uuid.uuid4(), body="Hello"
        )
        db.add.assert_called_once()

    async def test_get_ticket_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get_ticket(db, uuid.uuid4())
        assert result is None

    async def test_get_ticket_returns_ticket(self):
        mock_ticket = MagicMock()
        db = _db(_scalar_one_or_none(mock_ticket))
        result = await self.repo.get_ticket(db, uuid.uuid4())
        assert result is mock_ticket

    async def test_list_for_customer(self):
        mock_ticket = MagicMock()
        db = _db(_scalars([mock_ticket]))
        result = await self.repo.list_for_customer(db, uuid.uuid4())
        assert result == [mock_ticket]

    async def test_list_all_no_filter(self):
        mock_ticket = MagicMock()
        db = _db(_scalars([mock_ticket]))
        result = await self.repo.list_all(db)
        assert result == [mock_ticket]

    async def test_list_all_with_status_filter(self):
        db = _db(_scalars([]))
        result = await self.repo.list_all(db, status="open")
        assert result == []

    async def test_update_ticket_sets_attrs(self):
        db = _db()
        ticket = MagicMock()
        await self.repo.update_ticket(db, ticket, {"status": "resolved"})
        assert ticket.status == "resolved"

    async def test_next_ticket_number_format(self):
        from datetime import datetime

        year = datetime.now(UTC).year
        # next_sequence_value's INSERT ... RETURNING yields the new value
        # directly (already incremented), not a count to add 1 to.
        db = _db(_scalar_one(5))
        result = await self.repo.next_ticket_number(db)
        assert result.startswith(f"SUP-{year}-")
        assert result.endswith("0005")


# ─── ReturnRepository ─────────────────────────────────────────────────────────


class TestReturnRepository:
    def setup_method(self):
        from app.modules.returns.repository import ReturnRepository

        self.repo = ReturnRepository()

    async def test_get_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get(db, uuid.uuid4())
        assert result is None

    async def test_get_returns_return(self):
        mock_ret = MagicMock()
        db = _db(_scalar_one_or_none(mock_ret))
        result = await self.repo.get(db, uuid.uuid4())
        assert result is mock_ret

    async def test_list_for_customer(self):
        mock_ret = MagicMock()
        db = _db(_scalars([mock_ret]))
        result = await self.repo.list_for_customer(db, uuid.uuid4())
        assert result == [mock_ret]

    async def test_list_all(self):
        mock_ret = MagicMock()
        db = _db(_scalars([mock_ret]))
        result = await self.repo.list_all(db)
        assert result == [mock_ret]

    async def test_create_return(self):
        db = _db()
        await self.repo.create(
            db, order_id=uuid.uuid4(), customer_id=uuid.uuid4(), reason="Damaged"
        )
        db.add.assert_called_once()

    async def test_add_item(self):
        db = _db()
        await self.repo.add_item(
            db, return_id=uuid.uuid4(), order_item_id=uuid.uuid4(), quantity=1
        )
        db.add.assert_called_once()

    async def test_update_status(self):
        db = _db()
        ret = MagicMock()
        await self.repo.update_status(db, ret, "approved", notes="Looks good")
        assert ret.status == "approved"
        assert ret.notes == "Looks good"

    async def test_is_within_return_window_true(self):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock()
        db = _db(mock_result)
        result = await self.repo.is_within_return_window(db, uuid.uuid4())
        assert result is True

    async def test_is_within_return_window_false(self):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        db = _db(mock_result)
        result = await self.repo.is_within_return_window(db, uuid.uuid4())
        assert result is False


# ─── FraudRepository ──────────────────────────────────────────────────────────


class TestFraudRepository:
    def setup_method(self):
        from app.modules.fraud.repository import FraudRepository

        self.repo = FraudRepository()

    async def test_create_signal(self):
        db = _db()
        await self.repo.create(
            db, signal_type="multiple_orders", user_id=uuid.uuid4(), is_resolved=False
        )
        db.add.assert_called_once()

    async def test_get_returns_none(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get(db, uuid.uuid4())
        assert result is None

    async def test_get_returns_signal(self):
        mock_signal = MagicMock()
        db = _db(_scalar_one_or_none(mock_signal))
        result = await self.repo.get(db, uuid.uuid4())
        assert result is mock_signal

    async def test_list_unresolved(self):
        mock_signal = MagicMock()
        db = _db(_scalars([mock_signal]))
        result = await self.repo.list_unresolved(db)
        assert result == [mock_signal]

    async def test_update_sets_attrs(self):
        db = _db()
        signal = MagicMock()
        await self.repo.update(
            db, signal, {"is_resolved": True, "resolved_by": uuid.uuid4()}
        )
        assert signal.is_resolved is True


# ─── AuditRepository ──────────────────────────────────────────────────────────


class TestAuditRepository:
    def setup_method(self):
        from app.modules.audit.repository import AuditRepository

        self.repo = AuditRepository()

    async def test_list_paginated_no_filters(self):
        mock_log = MagicMock()
        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [mock_log]
        db = _db(total_result, items_result)
        items, total = await self.repo.list_paginated(db)
        assert total == 1
        assert items == [mock_log]

    async def test_list_paginated_with_all_filters(self):
        from datetime import datetime

        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        db = _db(total_result, items_result)
        items, total = await self.repo.list_paginated(
            db,
            actor_id=str(uuid.uuid4()),
            action="role_change",
            resource_type="profile",
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to=datetime(2026, 12, 31, tzinfo=UTC),
        )
        assert total == 0
        assert items == []
