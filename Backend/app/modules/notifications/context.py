"""Rich notification context builders.

`build_order_context` turns an `Order` (with its eagerly-loaded items) into the
full variable set the premium templates consume — items with product links,
address blocks, a pricing breakdown, payment/tracking facts, and the timeline
stage. Every value is pre-formatted (₹ with Indian digit grouping, friendly
dates) so templates never need filters and retries stay deterministic.

Formatting contract:
- `order_*` money vars and item prices are fully formatted ("Rs. 1,299.00") —
  the same rendering as the storefront's `formatINR` helper.
- Legacy vars (`total`, `amount`) stay prefix-less strings ("1,299.00")
  because templates/WhatsApp bodies prepend the currency themselves.
- Money vars that are zero are passed as "" so `{% if %}` guards skip the row.
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

if TYPE_CHECKING:
    from app.modules.orders.models import Order

_PAYMENT_METHOD_LABELS = {
    "razorpay": "Paid Online (Razorpay)",
    "cod": "Cash on Delivery",
    "card": "Card",
    "upi": "UPI",
    "netbanking": "Net Banking",
    "wallet": "Wallet",
}

_PAYMENT_STATUS_LABELS = {
    "pending": "Pending",
    "paid": "Paid ✓",
    "failed": "Failed",
    "refunded": "Refunded",
    "partially_refunded": "Partially Refunded",
}

_PROVIDER_LABELS = {
    "india_post": "India Post",
    "dtdc": "DTDC",
    "delhivery": "Delhivery",
    "blue_dart": "Blue Dart",
    "xpressbees": "XpressBees",
    "shadowfax": "Shadowfax",
    "ekart": "Ekart",
    "other": "Courier Partner",
}

# Placed → Confirmed → Packed → Shipped → Delivered (components.TIMELINE_STAGES)
_TIMELINE_BY_STATUS = {
    "pending": 1,
    "stock_reserved": 1,
    "payment_pending": 1,
    "confirmed": 2,
    "processing": 2,
    "packed": 3,
    "shipped": 4,
    "delivered": 5,
}


def format_inr_number(value: Any) -> str:
    """Indian digit grouping, two decimals, no symbol: 129900 → '1,29,900.00'."""
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    d = abs(d)
    whole = int(d)
    frac = f"{d:.2f}".split(".")[1]
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts: list[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join([*parts, tail])
    return f"{sign}{s}.{frac}"


def format_inr(value: Any) -> str:
    """Match the storefront's formatINR: "Rs. " + en-IN grouped amount."""
    return f"Rs. {format_inr_number(value)}"


def _address_lines(*parts: str | None) -> str:
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _first_name(full_name: str | None) -> str:
    return (full_name or "").strip().split(" ")[0] if full_name else ""


def build_order_context(
    order: Order, *, product_slugs: dict[uuid.UUID, str] | None = None
) -> dict[str, Any]:
    base = settings.FRONTEND_URL.rstrip("/")
    slugs = product_slugs or {}

    items: list[dict[str, Any]] = []
    for item in order.items:
        slug = slugs.get(item.product_id) if item.product_id else None
        items.append(
            {
                "name": item.product_name,
                "sku": item.product_sku,
                "variant": item.variant_name or "",
                "quantity": item.quantity,
                "unit_price": format_inr(item.unit_price),
                "line_total": format_inr(item.line_total),
                "image_url": item.image_url or "",
                "product_url": f"{base}/products/{slug}" if slug else "",
                # Deep link into the product page's review section (the page
                # opens the Reviews tab and scrolls when ?review=1 is present).
                "review_url": f"{base}/products/{slug}?review=1" if slug else "",
            }
        )

    discount = float(order.discount or 0)
    shipping = float(order.shipping_charge or 0)
    tax = float(order.tax_amount or 0)

    return {
        # Customer & order facts
        "customer_name": _first_name(order.shipping_full_name),
        "order_number": order.order_number,
        "order_date": order.created_at.strftime("%d %b %Y") if order.created_at else "",
        "order_url": f"{base}/account?tab=orders",
        "payment_method_label": _PAYMENT_METHOD_LABELS.get(
            (order.payment_method or "").lower(), order.payment_method or ""
        ),
        "payment_status_label": _PAYMENT_STATUS_LABELS.get(
            order.payment_status or "", ""
        ),
        "estimated_delivery": (
            order.estimated_delivery.strftime("%d %b %Y")
            if order.estimated_delivery
            else ""
        ),
        "shipping_provider_label": _PROVIDER_LABELS.get(
            order.shipping_provider or "", ""
        ),
        "tracking_number": order.tracking_number or "",
        # Orders don't store a tracking URL (it arrives with the shipment
        # event, which overrides this); always present so templates degrade
        # to plain-text tracking numbers.
        "tracking_url": "",
        # Items
        "items": items,
        # Pricing breakdown (symbols included; "" hides conditional rows)
        "order_subtotal": format_inr(order.subtotal),
        "order_discount": format_inr(discount) if discount > 0 else "",
        "coupon_code": order.coupon_code or "",
        "order_shipping": format_inr(shipping) if shipping > 0 else "",
        "order_tax": format_inr(tax) if tax > 0 else "",
        "order_total": format_inr(order.total),
        "order_savings": format_inr(discount) if discount > 0 else "",
        "complimentary_gift": order.complimentary_gift or "",
        # Addresses
        "shipping_name": order.shipping_full_name or "",
        "shipping_phone": order.shipping_phone or "",
        "shipping_address_lines": _address_lines(
            order.shipping_line1,
            order.shipping_line2,
            order.shipping_landmark,
            order.shipping_city,
            order.shipping_state,
            order.shipping_postal,
        ),
        "billing_name": order.billing_full_name or "",
        "billing_address_lines": _address_lines(
            order.billing_line1,
            order.billing_line2,
            order.billing_landmark,
            order.billing_city,
            order.billing_state,
            order.billing_postal,
        ),
        # Status
        "timeline_stage": _TIMELINE_BY_STATUS.get(order.status or "", 0),
        "cancellation_reason": order.cancellation_reason or "",
        # Legacy contract (symbol-less; templates prepend ₹)
        "total": format_inr_number(order.total),
    }


async def load_order_context(
    db: AsyncSession, order_id: str | uuid.UUID
) -> tuple[Any, dict[str, Any]]:
    """Load an order (items eager-loaded) plus its template context.

    Returns (order, context); (None, {}) when the order doesn't exist. Imports
    are lazy to keep module import order clean across business modules.
    """
    from app.modules.catalog.models import Product
    from app.modules.orders.repository import OrderRepository

    if not order_id:
        return None, {}
    order = await OrderRepository().get_by_id(db, uuid.UUID(str(order_id)))
    if not order:
        return None, {}

    product_ids = [i.product_id for i in order.items if i.product_id]
    slugs: dict[uuid.UUID, str] = {}
    if product_ids:
        rows = await db.execute(
            select(Product.id, Product.slug).where(Product.id.in_(product_ids))
        )
        slugs = {row.id: row.slug for row in rows}

    return order, build_order_context(order, product_slugs=slugs)
