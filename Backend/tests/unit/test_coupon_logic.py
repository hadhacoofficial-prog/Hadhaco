"""Unit tests for coupon discount calculation logic (no DB required)."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.coupons.models import Coupon
from app.modules.coupons.service import _calculate_discount


def _make_coupon(
    coupon_type: str = "percentage",
    value: float = 10.0,
    max_discount: float | None = None,
    min_order_amount: float = 0.0,
    is_active: bool = True,
    usage_limit: int | None = None,
    usage_count: int = 0,
    per_user_limit: int = 1,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> Coupon:
    c = MagicMock(spec=Coupon)
    c.coupon_type = coupon_type
    c.value = Decimal(str(value))
    c.max_discount = Decimal(str(max_discount)) if max_discount is not None else None
    c.min_order_amount = Decimal(str(min_order_amount))
    c.is_active = is_active
    c.usage_limit = usage_limit
    c.usage_count = usage_count
    c.per_user_limit = per_user_limit
    c.valid_from = valid_from
    c.valid_until = valid_until
    c.id = uuid.uuid4()
    c.code = "TEST10"
    return c


class TestCalculateDiscount:
    def test_percentage_discount(self):
        coupon = _make_coupon(coupon_type="percentage", value=10.0)
        assert _calculate_discount(coupon, 500.0) == pytest.approx(50.0, abs=0.01)

    def test_percentage_capped_by_max_discount(self):
        coupon = _make_coupon(coupon_type="percentage", value=20.0, max_discount=50.0)
        # 20% of 1000 = 200, but capped at 50
        assert _calculate_discount(coupon, 1000.0) == pytest.approx(50.0, abs=0.01)

    def test_percentage_below_max_discount_cap(self):
        coupon = _make_coupon(coupon_type="percentage", value=10.0, max_discount=200.0)
        # 10% of 500 = 50, max_discount=200 doesn't cap it
        assert _calculate_discount(coupon, 500.0) == pytest.approx(50.0, abs=0.01)

    def test_fixed_amount_below_subtotal(self):
        coupon = _make_coupon(coupon_type="fixed_amount", value=100.0)
        assert _calculate_discount(coupon, 500.0) == pytest.approx(100.0, abs=0.01)

    def test_fixed_amount_capped_by_subtotal(self):
        # Discount cannot exceed subtotal
        coupon = _make_coupon(coupon_type="fixed_amount", value=1000.0)
        assert _calculate_discount(coupon, 200.0) == pytest.approx(200.0, abs=0.01)

    def test_free_shipping_returns_zero(self):
        coupon = _make_coupon(coupon_type="free_shipping")
        assert _calculate_discount(coupon, 999.0) == 0.0

    def test_zero_subtotal_percentage(self):
        coupon = _make_coupon(coupon_type="percentage", value=15.0)
        assert _calculate_discount(coupon, 0.0) == 0.0

    def test_zero_subtotal_fixed(self):
        coupon = _make_coupon(coupon_type="fixed_amount", value=50.0)
        assert _calculate_discount(coupon, 0.0) == 0.0

    def test_percentage_rounding(self):
        coupon = _make_coupon(coupon_type="percentage", value=10.0)
        # 10% of 333.33 = 33.333 → rounds to 33.33
        result = _calculate_discount(coupon, 333.33)
        assert result == pytest.approx(33.33, abs=0.01)
