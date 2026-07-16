"""Tests for the premium notification design system.

Covers: catalog completeness against the event registry, safe rendering under
both the production sandboxed environments (with and without event context),
brand-context injection, INR formatting, and the order context builder.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

from jinja2.sandbox import SandboxedEnvironment
from markupsafe import escape

from app.modules.notifications.branding import get_brand_context
from app.modules.notifications.context import (
    build_order_context,
    format_inr_number,
)
from app.modules.notifications.emails.catalog import (
    ALL_TEMPLATES,
    EMAIL_TEMPLATES,
    WHATSAPP_TEMPLATES,
)
from app.modules.notifications.event_registry import NOTIFICATION_EVENTS

_env_html = SandboxedEnvironment(autoescape=True)
_env_text = SandboxedEnvironment(autoescape=False)


# ── Catalog completeness ──────────────────────────────────────────────────────


def test_template_names_are_unique() -> None:
    names = [t.name for t in ALL_TEMPLATES]
    assert len(names) == len(set(names))


def test_every_email_enabled_event_has_email_template() -> None:
    email_events = {t.event_type for t in EMAIL_TEMPLATES}
    for event in NOTIFICATION_EVENTS:
        if event.default_email_enabled:
            assert (
                event.event_type in email_events
            ), f"registry event {event.event_type} has no default email template"


def test_every_whatsapp_enabled_event_has_whatsapp_template() -> None:
    wa_events = {t.event_type for t in WHATSAPP_TEMPLATES}
    for event in NOTIFICATION_EVENTS:
        if event.default_whatsapp_enabled:
            assert (
                event.event_type in wa_events
            ), f"registry event {event.event_type} has no default whatsapp template"


def test_whatsapp_templates_declare_param_mapping() -> None:
    for tpl in WHATSAPP_TEMPLATES:
        assert tpl.variables is not None
        assert tpl.variables["whatsapp_template"] == tpl.event_type
        assert tpl.variables["whatsapp_lang"]
        assert tpl.variables["params"], f"{tpl.name} has no params"


# ── Rendering safety ──────────────────────────────────────────────────────────


def test_all_templates_render_with_brand_context_only() -> None:
    """Templates must degrade gracefully when an event provides no variables."""
    brand = get_brand_context()
    for tpl in ALL_TEMPLATES:
        env = _env_html if tpl.channel == "email" else _env_text
        html = env.from_string(tpl.body).render(**brand)
        assert html
        if tpl.channel == "email":
            assert brand["brand_short_name"] in html
            assert brand["support_email"] in html
            assert brand["privacy_url"] in html
            assert str(escape(brand["brand_legal_name"])) in html
        subject = _env_text.from_string(tpl.subject or "").render(**brand)
        if tpl.channel == "email":
            assert subject


def test_email_bodies_are_standalone_documents() -> None:
    """The admin editor previews raw bodies — they must be full documents."""
    for tpl in EMAIL_TEMPLATES:
        assert tpl.body.startswith("<!DOCTYPE html>"), tpl.name
        assert "{% extends" not in tpl.body
        assert "{% include" not in tpl.body


def test_email_bodies_have_no_hardcoded_production_urls() -> None:
    for tpl in EMAIL_TEMPLATES:
        assert (
            "https://hadha.co" not in tpl.body
        ), f"{tpl.name} hardcodes a production URL — use a brand-context var"


# ── INR formatting ────────────────────────────────────────────────────────────


def test_format_inr_number_indian_grouping() -> None:
    assert format_inr_number(0) == "0.00"
    assert format_inr_number(999) == "999.00"
    assert format_inr_number(1299) == "1,299.00"
    assert format_inr_number(129900) == "1,29,900.00"
    assert format_inr_number(12345678.5) == "1,23,45,678.50"
    assert format_inr_number("2889.905") == "2,889.91"


# ── Order context builder ─────────────────────────────────────────────────────


def _fake_order() -> SimpleNamespace:
    item = SimpleNamespace(
        product_id=uuid.uuid4(),
        product_name="Aria Silver Ring",
        product_sku="HD-RING-014",
        variant_name="Size 7",
        image_url="https://cdn.example/ring.jpg",
        unit_price=1299,
        quantity=2,
        line_total=2598,
    )
    return SimpleNamespace(
        order_number="HD10023",
        status="confirmed",
        payment_status="paid",
        payment_method="razorpay",
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
        estimated_delivery=date(2026, 7, 19),
        shipping_provider="delhivery",
        tracking_number="DL123",
        subtotal=2598,
        discount=0,
        shipping_charge=0,
        tax_amount=77.94,
        total=2675.94,
        coupon_code=None,
        complimentary_gift=None,
        cancellation_reason=None,
        shipping_full_name="Priya Sharma",
        shipping_phone="+91 98765 43210",
        shipping_line1="221B Residency Road",
        shipping_line2="Apt 4",
        shipping_landmark=None,
        shipping_city="Bengaluru",
        shipping_state="Karnataka",
        shipping_postal="560025",
        billing_full_name=None,
        billing_line1=None,
        billing_line2=None,
        billing_landmark=None,
        billing_city=None,
        billing_state=None,
        billing_postal=None,
        items=[item],
    )


def test_build_order_context_core_fields() -> None:
    order = _fake_order()
    slug_map = {order.items[0].product_id: "aria-silver-ring"}
    ctx = build_order_context(order, product_slugs=slug_map)  # type: ignore[arg-type]

    assert ctx["customer_name"] == "Priya"
    assert ctx["order_number"] == "HD10023"
    assert ctx["order_date"] == "15 Jul 2026"
    assert ctx["payment_method_label"] == "Paid Online (Razorpay)"
    assert ctx["payment_status_label"] == "Paid ✓"
    assert ctx["estimated_delivery"] == "19 Jul 2026"
    assert ctx["shipping_provider_label"] == "Delhivery"
    assert ctx["timeline_stage"] == 2  # confirmed
    assert ctx["total"] == "2,675.94"
    assert ctx["order_total"] == "Rs. 2,675.94"
    # zero-valued rows are passed as "" so {% if %} guards hide them
    assert ctx["order_discount"] == ""
    assert ctx["order_shipping"] == ""
    assert ctx["order_tax"] == "Rs. 77.94"
    assert "221B Residency Road, Apt 4, Bengaluru" in ctx["shipping_address_lines"]
    assert ctx["billing_address_lines"] == ""

    item = ctx["items"][0]
    assert item["product_url"].endswith("/products/aria-silver-ring")
    assert item["unit_price"] == "Rs. 1,299.00"
    assert item["line_total"] == "Rs. 2,598.00"


def test_order_context_renders_rich_confirmation_email() -> None:
    """End-to-end: builder output + brand context renders the full template."""
    order = _fake_order()
    ctx = {**get_brand_context(), **build_order_context(order)}  # type: ignore[arg-type]
    tpl = next(t for t in EMAIL_TEMPLATES if t.name == "order_confirmation_email")
    html = _env_html.from_string(tpl.body).render(**ctx)

    assert "HD10023" in html
    assert "Aria Silver Ring" in html
    assert "Rs. 2,675.94" in html  # total
    assert "Priya Sharma" in html  # shipping address
    assert "FREE" in html  # zero shipping renders the FREE badge
    assert "Delivered" in html  # timeline stages present
