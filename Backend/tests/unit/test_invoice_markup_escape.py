from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.invoices.service import _build_pdf


def _order(line1: str):
    return SimpleNamespace(
        order_number="ORD-1",
        payment_method="razorpay",
        created_at=datetime.now(UTC),
        shipping_full_name="A B",
        shipping_line1=line1,
        shipping_line2=None,
        shipping_landmark=None,
        shipping_city="City",
        shipping_state="State",
        shipping_postal="560001",
        shipping_country="IN",
        shipping_phone=None,
        shipping_alternate_phone=None,
        items=[],
        subtotal=100,
        tax_amount=3,
        shipping_charge=0,
        discount=0,
        total=100,
    )


def test_address_markup_is_not_interpreted():
    """An <img src=...> in a customer address must never reach ImageReader."""
    payload = '<img src="https://attacker.invalid/x.png" width="1" height="1"/>'
    with patch("reportlab.platypus.paraparser.ImageReader") as reader:
        pdf = _build_pdf(_order(payload), "INV-1")
    assert pdf.startswith(b"%PDF")
    reader.assert_not_called()
