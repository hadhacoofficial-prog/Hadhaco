"""End-to-end notification integration verification.

Two layers:

1. Static variable coverage — for every template, every undeclared Jinja
   variable must be provided by (brand context ∪ order context ∪ the exact
   keys that template's listener passes). This catches a placeholder added to
   a template without backend data ever feeding it.

2. Pipeline tests — fire the REAL registered listeners with realistic events,
   with fakes only at the process edges (DB session, repositories, provider
   HTTP call). The real code path runs: listener → load_order_context →
   dispatch gates → catalog template render → dispatcher boundary, and the
   FINAL HTML handed to the email provider is asserted on.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jinja2 import meta
from jinja2.sandbox import SandboxedEnvironment

from app.core.events import (
    OrderCreatedEvent,
    OrderShippedEvent,
    OrderStatusChangedEvent,
    PaymentCapturedEvent,
    RefundProcessedEvent,
    UserRegisteredEvent,
)
from app.modules.notifications.branding import get_brand_context
from app.modules.notifications.emails.catalog import (
    EMAIL_TEMPLATES,
    WHATSAPP_TEMPLATES,
)

_env = SandboxedEnvironment(autoescape=True)

# ── The integration matrix: event_type → keys its listener provides ───────────
# (Mirrors service.py listeners; ORDER_CTX comes from context.build_order_context.)

ORDER_CTX_KEYS = {
    "customer_name",
    "order_number",
    "order_date",
    "order_url",
    "payment_method_label",
    "payment_status_label",
    "estimated_delivery",
    "shipping_provider_label",
    "tracking_number",
    "tracking_url",
    "items",
    "order_subtotal",
    "order_discount",
    "coupon_code",
    "order_shipping",
    "order_tax",
    "order_total",
    "order_savings",
    "complimentary_gift",
    "shipping_name",
    "shipping_phone",
    "shipping_address_lines",
    "billing_name",
    "billing_address_lines",
    "timeline_stage",
    "cancellation_reason",
    "total",
}

STATUS_CHANGE_KEYS = ORDER_CTX_KEYS | {"old_status", "new_status", "frontend_url"}

EVENT_CONTEXT_KEYS: dict[str, set[str]] = {
    "user_registered": {"full_name", "frontend_url"},
    "order_created": ORDER_CTX_KEYS | {"frontend_url"},
    "payment_captured": ORDER_CTX_KEYS | {"amount", "frontend_url"},
    "payment_failed": ORDER_CTX_KEYS | {"reason", "frontend_url"},
    "order_confirmed": STATUS_CHANGE_KEYS,
    "order_processing": STATUS_CHANGE_KEYS,
    "order_packed": STATUS_CHANGE_KEYS,
    "order_cancelled": STATUS_CHANGE_KEYS,
    "order_return_requested": STATUS_CHANGE_KEYS,
    "order_returned": STATUS_CHANGE_KEYS,
    "order_payment_failed": STATUS_CHANGE_KEYS,
    "order_payment_expired": STATUS_CHANGE_KEYS,
    "order_refunded": STATUS_CHANGE_KEYS,
    "order_shipped": ORDER_CTX_KEYS | {"tracking_url", "awb", "frontend_url"},
    "order_delivered": ORDER_CTX_KEYS | {"frontend_url"},
    "refund_created": ORDER_CTX_KEYS | {"amount", "frontend_url"},
    "refund_processed": ORDER_CTX_KEYS | {"amount", "frontend_url"},
    "refund_failed_admin_alert": {
        "order_number",
        "refund_id",
        "amount",
        "reason",
        "admin_order_url",
    },
    "review_request": ORDER_CTX_KEYS | {"frontend_url"},
}

# Templates whose event has no publisher yet (kept in the catalog for when a
# trigger is built). They must still render safely — covered by the render
# tests — but variable coverage is not enforced against a listener.
DORMANT_EVENTS = {"abandoned_cart"}

BRAND_KEYS = set(get_brand_context().keys())

# {% set %} locals inside conditional blocks — jinja2.meta conservatively
# reports them as undeclared even though the template always assigns them.
_TEMPLATE_LOCALS = {"done"}


def _undeclared(source: str) -> set[str]:
    return meta.find_undeclared_variables(_env.parse(source)) - _TEMPLATE_LOCALS


def test_every_email_template_variable_is_provided() -> None:
    failures = []
    for tpl in EMAIL_TEMPLATES:
        if tpl.event_type in DORMANT_EVENTS:
            continue
        provided = BRAND_KEYS | EVENT_CONTEXT_KEYS[tpl.event_type]
        missing = (_undeclared(tpl.body) | _undeclared(tpl.subject or "")) - provided
        if missing:
            failures.append(f"{tpl.name}: missing {sorted(missing)}")
    assert not failures, "\n".join(failures)


def test_every_whatsapp_param_is_provided() -> None:
    failures = []
    for tpl in WHATSAPP_TEMPLATES:
        if tpl.event_type in DORMANT_EVENTS:
            continue
        provided = BRAND_KEYS | EVENT_CONTEXT_KEYS[tpl.event_type]
        assert tpl.variables is not None
        missing = set(tpl.variables["params"]) - provided
        body_missing = _undeclared(tpl.body) - provided
        if missing or body_missing:
            failures.append(
                f"{tpl.name}: params {sorted(missing)} body {sorted(body_missing)}"
            )
    assert not failures, "\n".join(failures)


# ── Pipeline fixtures ─────────────────────────────────────────────────────────

_ORDER_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PRODUCT_ID = uuid.uuid4()


def _fake_order() -> SimpleNamespace:
    return SimpleNamespace(
        id=_ORDER_ID,
        user_id=_USER_ID,
        order_number="HD10023",
        status="confirmed",
        payment_status="paid",
        payment_method="razorpay",
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
        estimated_delivery=date(2026, 7, 19),
        shipping_provider="delhivery",
        tracking_number="DL4429871650",
        subtotal=3097,
        discount=300,
        shipping_charge=0,
        tax_amount=92.91,
        total=2889.91,
        coupon_code="FESTIVE10",
        complimentary_gift="silver polishing cloth",
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
        items=[
            SimpleNamespace(
                product_id=_PRODUCT_ID,
                product_name="Aria Silver Ring",
                product_sku="HD-RING-014",
                variant_name="Size 7",
                image_url="https://cdn.hadha.co/products/aria.jpg",
                unit_price=1299,
                quantity=1,
                line_total=1299,
            )
        ],
    )


class _FakeSessionCtx:
    """Stands in for AsyncWorkerSessionLocal(): yields a mock session whose
    only direct use inside the pipeline is the product-slug SELECT."""

    def __init__(self, db: MagicMock) -> None:
        self._db = db

    async def __aenter__(self) -> MagicMock:
        return self._db

    async def __aexit__(self, *args: object) -> None:
        return None


def _mock_db() -> MagicMock:
    db = MagicMock()
    slug_rows = [SimpleNamespace(id=_PRODUCT_ID, slug="aria-silver-ring")]
    result = MagicMock()
    result.__iter__ = lambda self: iter(slug_rows)
    # The CMS footer-overlay lookup calls scalar_one_or_none(); None means
    # "no CMS config" so env/static brand defaults stay in effect.
    result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


@pytest.fixture
def pipeline(monkeypatch):
    """Real listeners + real dispatch/render; fakes only at the edges.

    Returns (fire, sent) where fire(event_cls, event) awaits every registered
    listener and sent collects dispatcher.send_email calls (final HTML).
    """
    from app.core.events import EventBus
    from app.modules.notifications import service as service_module
    from app.modules.notifications.emails.catalog import ALL_TEMPLATES
    from app.modules.notifications.repository import NotificationRepository
    from app.modules.settings.repository import SettingsRepository

    # Fresh bus so we exercise exactly one registration
    bus = EventBus()
    monkeypatch.setattr(service_module, "event_bus", bus)

    db = _mock_db()
    monkeypatch.setattr(
        "app.core.database.AsyncWorkerSessionLocal", lambda: _FakeSessionCtx(db)
    )

    # Repositories → realistic fakes
    order = _fake_order()

    async def _get_order(self, _db, order_id):
        return order if order_id == _ORDER_ID else None

    monkeypatch.setattr(
        "app.modules.orders.repository.OrderRepository.get_by_id", _get_order
    )

    profile = SimpleNamespace(
        id=_USER_ID,
        email="priya@example.com",
        phone="+91 98765 43210",
        full_name="Priya Sharma",
    )

    async def _get_profile(self, _db, _user_id):
        return profile

    monkeypatch.setattr(
        "app.modules.profiles.repository.ProfileRepository.get_by_id", _get_profile
    )

    # Notification repo: real catalog content behind the template lookup
    templates = {
        (t.event_type, t.channel): SimpleNamespace(
            id=uuid.uuid4(),
            name=t.name,
            subject=t.subject,
            template_body=t.body,
            variables=t.variables,
            version=2,
        )
        for t in ALL_TEMPLATES
    }

    async def _get_template(self, _db, *, event_type, channel):
        return templates.get((event_type, channel))

    async def _true(*args, **kwargs):
        return True

    async def _create_log(self, _db, **kwargs):
        return MagicMock()

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(NotificationRepository, "get_template", _get_template)
    monkeypatch.setattr(NotificationRepository, "should_send", _true)
    monkeypatch.setattr(NotificationRepository, "get_preferences_for_channel", _true)
    monkeypatch.setattr(NotificationRepository, "create_log", _create_log)
    monkeypatch.setattr(NotificationRepository, "mark_sent", _noop)

    async def _provider_config(self, _db, *, provider):
        return {"enabled": "true"}

    monkeypatch.setattr(SettingsRepository, "get_provider_config", _provider_config)

    # Provider boundary: capture the final rendered payload
    sent: list[dict] = []

    async def _send_email(_db, *, to, subject, html):
        sent.append({"to": to, "subject": subject, "html": html})
        return "msg_test_1"

    # Patch the class, not the singleton instance: monkeypatch teardown on an
    # instance would pin the original bound method as an instance attribute,
    # which then shadows the class-level patch.object other test files use.
    monkeypatch.setattr(
        type(service_module.dispatcher),
        "send_email",
        AsyncMock(side_effect=_send_email),
    )

    service_module.NotificationService.register_listeners()

    async def fire(event) -> None:
        for listener in bus._listeners[type(event)]:
            await listener(event)

    return fire, sent


ORDER_FACTS = [
    "HD10023",  # order number
    "Aria Silver Ring",  # item name with product link
    "aria-silver-ring",  # product deep link slug
    "Rs. 2,889.91",  # storefront-formatted total
    "FESTIVE10",  # coupon
    "Priya Sharma",  # shipping address
    "account?tab=orders",  # order deep link
]


@pytest.mark.asyncio
async def test_order_created_end_to_end(pipeline) -> None:
    fire, sent = pipeline
    await fire(
        OrderCreatedEvent(
            order_id=str(_ORDER_ID),
            user_id=str(_USER_ID),
            order_number="HD10023",
            total_amount=2889.91,
            customer_email="priya@example.com",
            customer_phone="+91 98765 43210",
        )
    )
    assert len(sent) == 1
    html = sent[0]["html"]
    assert sent[0]["to"] == "priya@example.com"
    assert sent[0]["subject"] == "Order HD10023 confirmed — thank you!"
    for fact in ORDER_FACTS:
        assert fact in html, f"missing {fact!r} in final HTML"
    # storefront identity markers in the final provider payload
    assert "#21334f" in html  # primary navy
    assert "#c99846" in html  # gold accent
    assert "Cinzel" in html
    assert "Popula Dabba" in html  # legal name in footer


@pytest.mark.asyncio
async def test_order_shipped_end_to_end(pipeline) -> None:
    fire, sent = pipeline
    await fire(
        OrderShippedEvent(
            order_id=str(_ORDER_ID),
            user_id=str(_USER_ID),
            shipment_id=str(uuid.uuid4()),
            tracking_number="DL4429871650",
            tracking_url="https://www.delhivery.com/track/DL4429871650",
            awb="DL4429871650",
            order_number="HD10023",
        )
    )
    assert len(sent) == 1
    html = sent[0]["html"]
    assert "https://www.delhivery.com/track/DL4429871650" in html
    assert "DL4429871650" in html
    assert "Delhivery" in html  # courier label from order context
    assert "19 Jul 2026" in html  # estimated delivery


@pytest.mark.asyncio
async def test_payment_captured_end_to_end(pipeline) -> None:
    fire, sent = pipeline
    await fire(
        PaymentCapturedEvent(
            payment_id="pay_1",
            order_id=str(_ORDER_ID),
            user_id=str(_USER_ID),
            amount=2889.91,
            order_number="HD10023",
            customer_email="priya@example.com",
        )
    )
    assert len(sent) == 1
    html = sent[0]["html"]
    assert "Rs. 2,889.91" in html  # amount + summary total
    assert "Paid Online (Razorpay)" in html
    assert "Paid" in html


@pytest.mark.asyncio
async def test_order_status_packed_end_to_end(pipeline) -> None:
    fire, sent = pipeline
    await fire(
        OrderStatusChangedEvent(
            order_id=str(_ORDER_ID),
            user_id=str(_USER_ID),
            old_status="processing",
            new_status="packed",
        )
    )
    assert len(sent) == 1
    assert "packed" in sent[0]["subject"].lower()
    assert "HD10023" in sent[0]["html"]


@pytest.mark.asyncio
async def test_admin_manual_refunded_status_end_to_end(pipeline) -> None:
    """Regression test for a real gap found in the final production audit:
    an admin can set order.status="refunded" directly via
    UpdateOrderStatusRequest (pattern allows it), which used to produce zero
    customer notification because no rule/template existed for the resulting
    "order_refunded" event_type. Proves the newly-added template closes it."""
    fire, sent = pipeline
    await fire(
        OrderStatusChangedEvent(
            order_id=str(_ORDER_ID),
            user_id=str(_USER_ID),
            old_status="delivered",
            new_status="refunded",
        )
    )
    assert len(sent) == 1
    assert "refunded" in sent[0]["subject"].lower()
    assert "HD10023" in sent[0]["html"]
    assert "View Refund Details" in sent[0]["html"]


@pytest.mark.asyncio
async def test_refund_processed_end_to_end(pipeline) -> None:
    fire, sent = pipeline
    await fire(
        RefundProcessedEvent(
            refund_id="rfnd_1",
            order_id=str(_ORDER_ID),
            user_id=str(_USER_ID),
            amount=500,
            order_number="HD10023",
            customer_email="priya@example.com",
        )
    )
    assert len(sent) == 1
    assert "Rs. 500.00" in sent[0]["html"]


@pytest.mark.asyncio
async def test_user_registered_end_to_end(pipeline) -> None:
    fire, sent = pipeline
    await fire(
        UserRegisteredEvent(
            user_id=str(_USER_ID),
            email="priya@example.com",
            full_name="Priya Sharma",
        )
    )
    assert len(sent) == 1
    html = sent[0]["html"]
    assert "Priya Sharma" in html
    assert "92.5" in html  # storefront brand language


@pytest.mark.asyncio
async def test_cms_footer_config_drives_email_footer() -> None:
    """Admin edits to the CMS footer section (contact info + link columns)
    must flow into the next rendered email — no deploy, no reseed."""
    from app.modules.notifications.branding import get_brand_context_db

    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(
        return_value={
            "email": "care@hadha.co",
            "phone": "+91 11111 22222",
            "company_address": "New Studio, Jubilee Hills, Hyderabad 500033",
            "copyright_name": "Hadha Jewels Pvt Ltd",
            "columns": [
                {
                    "title": "Explore",
                    "links": [
                        {"label": "Gift Cards", "url": "/gift-cards"},
                        {"label": "Store Locator", "url": "/store-locator"},
                    ],
                },
            ],
        }
    )
    db.execute = AsyncMock(return_value=result)

    ctx = await get_brand_context_db(db)
    assert ctx["support_email"] == "care@hadha.co"
    assert ctx["brand_address"] == "New Studio, Jubilee Hills, Hyderabad 500033"
    assert ctx["brand_legal_name"] == "Hadha Jewels Pvt Ltd"
    # the minimal footer has no link columns — CMS `columns` config is ignored
    assert "footer_columns" not in ctx

    tpl = next(t for t in EMAIL_TEMPLATES if t.name == "welcome_email")
    html = _env.from_string(tpl.body).render(**{**ctx, "full_name": "Priya"})
    assert "care@hadha.co" in html
    assert "+91 11111 22222" in html
    assert "Hadha Jewels Pvt Ltd" in html


def test_footer_is_minimal() -> None:
    """Luxury footer keep-list: brand, description, contact, socials,
    Track Order / Contact Support, Privacy/Terms, copyright — nothing else."""
    from app.modules.notifications.branding import get_brand_context

    brand = get_brand_context()
    tpl = next(t for t in EMAIL_TEMPLATES if t.name == "order_confirmation_email")
    html = _env.from_string(tpl.body).render(**brand)
    # kept
    for kept in (
        brand["support_email"],
        brand["website_label"],
        "Instagram",
        "Contact Support",
        "Track Order",
        "Privacy",
        "Terms",
        "© {}".format(brand["current_year"]),
    ):
        assert kept in html, f"missing {kept!r}"
    # removed navigation clutter
    for gone in (
        "Deals Of The Day",
        ">Women<",
        ">Men<",
        ">Kids<",
        "About Us",
        "Shipping Policy",
        "Returns Policy",
        "Notification preferences",
        "Shopping</div>",
        "Company</div>",
    ):
        assert gone not in html, f"{gone!r} should be removed"


def test_header_has_no_nav_links() -> None:
    """The header is just the brand mark — no nav row, no motto strip."""
    from app.modules.notifications.emails.components import header

    src = header()
    for label in (">Women<", ">Men<", "My&nbsp;Orders", ">Support<", "brand_motto"):
        assert label not in src


@pytest.mark.asyncio
async def test_welcome_bridge_publishes_once() -> None:
    """maybe_publish_welcome: publishes for a fresh profile, exactly once."""
    from app.modules.notifications import welcome as welcome_module

    profile = SimpleNamespace(
        id=_USER_ID,
        email="priya@example.com",
        full_name="Priya Sharma",
        created_at=datetime.now(UTC),
    )
    db = MagicMock()
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=[True, False])  # first claim wins

    published = []

    async def _publish(event):
        published.append(event)

    with (
        patch.object(welcome_module.event_bus, "publish", side_effect=_publish),
        patch.object(
            welcome_module.NotificationRepository,
            "has_log_for_user_event",
            AsyncMock(return_value=False),
        ),
    ):
        await welcome_module.maybe_publish_welcome(db, redis, profile)
        await welcome_module.maybe_publish_welcome(db, redis, profile)

    assert len(published) == 1
    assert published[0].full_name == "Priya Sharma"

    # Old profiles never trigger it
    stale = SimpleNamespace(
        id=_USER_ID,
        email="x@example.com",
        full_name="X",
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    with patch.object(welcome_module.event_bus, "publish", side_effect=_publish):
        await welcome_module.maybe_publish_welcome(db, redis, stale)
    assert len(published) == 1
