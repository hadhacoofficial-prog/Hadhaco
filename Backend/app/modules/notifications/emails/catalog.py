"""Default template catalog — every (event_type, channel) default, generated
from the storefront-derived design system in `components.py`.

This module is the single source of truth for default notification content.
Alembic migration 0051 seeds these into `notification_templates` (snapshotting
any existing row into `notification_template_versions` first, so admins can
always restore the previous content).

Variable contract (provided by `context.py` + `branding.py`):
- Brand (always present): brand_name, brand_short_name, brand_legal_name,
  brand_tagline, brand_description, brand_logo_url, brand_logo_dark_url,
  brand_address, support_email, support_phone, social_*, frontend_url,
  website_label, shop_url, new_arrivals_url, account_url, orders_url,
  order_url, cart_url, contact_url, returns_url, privacy_url, terms_url,
  admin_url, current_year.
- Order (order-lifecycle events): customer_name, order_number, order_date,
  order_url, payment_method_label, payment_status_label, estimated_delivery,
  shipping_provider_label, tracking_number, tracking_url, awb, items[],
  order_subtotal, order_discount, coupon_code, order_shipping, order_tax,
  order_total, order_savings, complimentary_gift, shipping_name,
  shipping_phone, shipping_address_lines, billing_name,
  billing_address_lines, timeline_stage, cancellation_reason.
- Event-specific: full_name (welcome), amount (payments/refunds, "1,299.00"),
  reason (payment_failed/refund_failed), refund_id (admin alert),
  old_status/new_status, item_count (abandoned cart).

Every order variable is guarded with {% if %} in the components, so a template
still renders cleanly when an event provides only a minimal context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.notifications.emails import components as c


@dataclass(frozen=True)
class TemplateDef:
    name: str
    channel: str
    event_type: str
    subject: str | None
    body: str
    variables: dict[str, Any] | None = field(default=None)


def _email(*, title: str, preheader: str, blocks: list[str]) -> str:
    return c.document(
        title=title,
        preheader=preheader,
        body_html=c.header() + "".join(blocks) + c.footer(),
    )


_GREETING = "{% if customer_name %}, {{ customer_name }}{% endif %}"

# ── Customer emails — account ─────────────────────────────────────────────────

_WELCOME = _email(
    title="Welcome to {{ brand_name }}",
    preheader="Your account is ready — handcrafted 92.5 silver jewellery awaits.",
    blocks=[
        c.hero(
            badge_text="Welcome",
            badge_bg=c.GOLD,
            title="Welcome{% if full_name %}, {{ full_name }}{% endif %}",
            subtitle=(
                "Thank you for joining {{ brand_name }} — handcrafted 92.5 "
                "silver jewellery rooted in South Indian heritage. Your account "
                "is ready: track orders, save your wishlist and enjoy a faster "
                "checkout."
            ),
        ),
        c.cta_block(
            ("Start Shopping", "{{ shop_url }}"),
            ("Visit My Account", "{{ account_url }}"),
        ),
        c.info_note(
            "Every {{ brand_short_name }} piece is handcrafted 92.5 sterling "
            "silver, quality-checked by hand before it ships — made for "
            "everyday and treasured for a lifetime."
        ),
        c.spacer(30),
    ],
)

# ── Customer emails — order lifecycle ─────────────────────────────────────────

_ORDER_CONFIRMATION = _email(
    title="Order {{ order_number }} confirmed",
    preheader="We’ve received your order {{ order_number }} — here’s everything inside it.",
    blocks=[
        c.hero(
            badge_text="Order Placed",
            badge_bg=c.NAVY,
            title=f"Thank You{_GREETING}",
            subtitle=(
                "Your order <strong>{{ order_number }}</strong> has been received. "
                "We’ll email you the moment it ships."
            ),
        ),
        c.order_timeline(),
        c.order_meta_grid(),
        c.product_items(),
        c.order_summary(),
        c.addresses(),
        c.cta_block(
            ("View Order", "{{ order_url }}"),
            ("Contact Support", "{{ contact_url }}"),
        ),
        c.spacer(30),
    ],
)

_ORDER_CONFIRMED = _email(
    title="Order {{ order_number }} confirmed",
    preheader="Your order {{ order_number }} is confirmed and moving to preparation.",
    blocks=[
        c.hero(
            badge_text="Confirmed",
            badge_bg=c.NAVY,
            title="Your Order Is Confirmed",
            subtitle=(
                "Great news{% if customer_name %}, {{ customer_name }}{% endif %} — "
                "order <strong>{{ order_number }}</strong> is confirmed and will "
                "move into preparation shortly."
            ),
        ),
        c.order_timeline(),
        c.order_meta_grid(),
        c.cta_block(("View Order", "{{ order_url }}")),
        c.spacer(30),
    ],
)

_ORDER_PROCESSING = _email(
    title="Order {{ order_number }} is being prepared",
    preheader="Our artisans are preparing your order {{ order_number }} with care.",
    blocks=[
        c.hero(
            badge_text="In Preparation",
            badge_bg=c.NAVY,
            title="Your Jewellery Is Being Prepared",
            subtitle=(
                "Order <strong>{{ order_number }}</strong> is being prepared and "
                "quality-checked with care. We’ll let you know as soon as it’s packed."
            ),
        ),
        c.order_timeline(),
        c.order_meta_grid(),
        c.cta_block(("View Order", "{{ order_url }}")),
        c.spacer(30),
    ],
)

_ORDER_PACKED = _email(
    title="Order {{ order_number }} is packed",
    preheader="Your order {{ order_number }} is packed and ready to ship.",
    blocks=[
        c.hero(
            badge_text="Packed",
            badge_bg=c.NAVY,
            title="Packed And Ready To Ship",
            subtitle=(
                "Order <strong>{{ order_number }}</strong> has been carefully "
                "packed. It will be handed to our courier shortly — tracking "
                "details are on their way."
            ),
        ),
        c.order_timeline(),
        c.order_meta_grid(),
        c.cta_block(("Track Order", "{{ order_url }}")),
        c.spacer(30),
    ],
)

_ORDER_SHIPPED = _email(
    title="Order {{ order_number }} has shipped",
    preheader="Your order is on its way — track it live with {{ tracking_number }}.",
    blocks=[
        c.hero(
            badge_text="Shipped",
            badge_bg=c.NAVY,
            title="Your Order Is On Its Way",
            subtitle=(
                "Order <strong>{{ order_number }}</strong> has left our studio."
                "{% if awb %} Airway bill: <strong>{{ awb }}</strong>.{% endif %}"
            ),
        ),
        c.order_timeline(),
        c.order_meta_grid(),
        c.product_items(),
        c.cta_block(
            (
                "Track Shipment",
                "{% if tracking_url %}{{ tracking_url }}{% else %}{{ order_url }}{% endif %}",
            ),
            ("View Order", "{{ order_url }}"),
            variant="gold",
        ),
        "{% if not tracking_url %}"
        + c.paragraph(
            "Live courier tracking will be available shortly — you can always "
            "check the latest status from your order page.",
            align="center",
        )
        + "{% endif %}",
        c.spacer(30),
    ],
)

_ORDER_DELIVERED = _email(
    title="Order {{ order_number }} delivered",
    preheader="Your {{ brand_short_name }} order has arrived — we hope you love it.",
    blocks=[
        c.hero(
            badge_text="Delivered",
            badge_bg=c.GOLD,
            title="Delivered — Enjoy",
            subtitle=(
                "Order <strong>{{ order_number }}</strong> has been delivered"
                "{% if customer_name %}, {{ customer_name }}{% endif %}. "
                "We hope your new jewellery makes you smile."
            ),
        ),
        c.order_timeline(),
        c.product_items(),
        c.review_cta(),
        c.info_note(
            "<strong>Care tip:</strong> store your silver in a dry pouch, keep "
            "it away from perfume and moisture, and polish gently with a soft "
            "cloth."
        ),
        c.cta_block(
            ("View Order", "{{ order_url }}"),
            ("Shop Again", "{{ shop_url }}"),
        ),
        c.spacer(30),
    ],
)

_ORDER_CANCELLED = _email(
    title="Order {{ order_number }} cancelled",
    preheader="Your order {{ order_number }} has been cancelled.",
    blocks=[
        c.hero(
            badge_text="Cancelled",
            badge_bg=c.DESTRUCTIVE,
            title="Your Order Has Been Cancelled",
            subtitle=(
                "Order <strong>{{ order_number }}</strong> has been cancelled"
                "{% if cancellation_reason %} ({{ cancellation_reason }}){% endif %}. "
                "If you already paid, your refund will be initiated automatically "
                "and confirmed by email."
            ),
        ),
        c.order_meta_grid(),
        c.cta_block(
            ("Browse Collections", "{{ shop_url }}"),
            ("Contact Support", "{{ contact_url }}"),
        ),
        c.spacer(30),
    ],
)

_ORDER_RETURN_REQUESTED = _email(
    title="Return requested for order {{ order_number }}",
    preheader="We’ve received your return request for order {{ order_number }}.",
    blocks=[
        c.hero(
            badge_text="Return Requested",
            badge_bg=c.NAVY,
            title="We’ve Received Your Return Request",
            subtitle=(
                "Your return request for order <strong>{{ order_number }}</strong> "
                "is being reviewed. We’ll confirm the pickup details and next steps "
                "within 1–2 business days."
            ),
        ),
        c.order_meta_grid(),
        c.cta_block(
            ("View Order", "{{ order_url }}"),
            ("Return Policy", "{{ returns_url }}"),
        ),
        c.spacer(30),
    ],
)

_ORDER_PAYMENT_FAILED_STATUS = _email(
    title="Payment issue on order {{ order_number }}",
    preheader="We need to follow up on the payment for order {{ order_number }}.",
    blocks=[
        c.hero(
            badge_text="Action Needed",
            badge_bg=c.DESTRUCTIVE,
            title="Payment Issue On Your Order",
            subtitle=(
                "We’ve flagged a payment issue on order "
                "<strong>{{ order_number }}</strong>. Our team may already be in "
                "touch, or you can reach us directly to resolve it."
            ),
        ),
        c.order_meta_grid(),
        c.cta_block(
            ("Contact Support", "{{ contact_url }}"),
            ("Try Again", "{{ cart_url }}"),
        ),
        c.spacer(30),
    ],
)

_ORDER_PAYMENT_EXPIRED = _email(
    title="Payment window expired for order {{ order_number }}",
    preheader="The payment window for order {{ order_number }} has closed.",
    blocks=[
        c.hero(
            badge_text="Payment Expired",
            badge_bg=c.DESTRUCTIVE,
            title="Your Payment Window Has Closed",
            subtitle=(
                "The payment window for order <strong>{{ order_number }}</strong> "
                "has expired and the reserved items were released back to stock. "
                "You’re welcome to place a fresh order any time."
            ),
        ),
        c.cta_block(
            ("Try Again", "{{ cart_url }}"),
            ("Contact Support", "{{ contact_url }}"),
        ),
        c.spacer(30),
    ],
)

_ORDER_REFUNDED_STATUS = _email(
    title="Order {{ order_number }} refunded",
    preheader="Order {{ order_number }} has been marked refunded.",
    blocks=[
        c.hero(
            badge_text="Refunded",
            badge_bg=c.GOLD,
            title="Your Order Has Been Refunded",
            subtitle=(
                "Order <strong>{{ order_number }}</strong> has been refunded to "
                "your original payment method. Depending on your bank, it may "
                "take 5–7 business days to appear."
            ),
        ),
        c.order_meta_grid(),
        c.cta_block(
            ("View Refund Details", "{{ order_url }}"),
            ("Contact Support", "{{ contact_url }}"),
        ),
        c.spacer(30),
    ],
)

_ORDER_RETURNED = _email(
    title="Return received for order {{ order_number }}",
    preheader="Your return for order {{ order_number }} has been received.",
    blocks=[
        c.hero(
            badge_text="Return Received",
            badge_bg=c.NAVY,
            title="Your Return Has Been Received",
            subtitle=(
                "We’ve received the items from order "
                "<strong>{{ order_number }}</strong>. Any refund due will be "
                "initiated after inspection and confirmed by email."
            ),
        ),
        c.order_meta_grid(),
        c.cta_block(("View Order", "{{ order_url }}")),
        c.spacer(30),
    ],
)

# ── Customer emails — payments & refunds ──────────────────────────────────────

_PAYMENT_RECEIPT = _email(
    title="Payment received for order {{ order_number }}",
    preheader="Payment of Rs. {{ amount }} received — your order is being prepared.",
    blocks=[
        c.hero(
            badge_text="Payment Received",
            badge_bg=c.NAVY,
            title="Payment Received",
            subtitle=(
                "We’ve received your payment of <strong>Rs. {{ amount }}</strong> "
                "for order <strong>{{ order_number }}</strong>. Your jewellery is "
                "now being prepared with care."
            ),
        ),
        c.order_meta_grid(),
        c.order_summary(),
        c.cta_block(
            ("View Order &amp; Invoice", "{{ order_url }}"),
            ("Contact Support", "{{ contact_url }}"),
        ),
        c.spacer(30),
    ],
)

_PAYMENT_FAILED = _email(
    title="Payment failed for order {{ order_number }}",
    preheader="Your payment could not be processed — your items are waiting.",
    blocks=[
        c.hero(
            badge_text="Action Needed",
            badge_bg=c.DESTRUCTIVE,
            title="We Couldn’t Process Your Payment",
            subtitle=(
                "Your payment for order <strong>{{ order_number }}</strong> could "
                "not be completed{% if reason %} ({{ reason }}){% endif %}."
            ),
        ),
        c.info_note(
            "Your cart items have been released back to stock — our pieces are "
            "made in small batches, so please try again soon or use a different "
            "payment method.",
            tone="destructive",
        ),
        c.cta_block(
            ("Try Again", "{{ cart_url }}"),
            ("Contact Support", "{{ contact_url }}"),
        ),
        c.spacer(30),
    ],
)

_REFUND_CREATED = _email(
    title="Refund initiated for order {{ order_number }}",
    preheader="A refund of Rs. {{ amount }} has been initiated.",
    blocks=[
        c.hero(
            badge_text="Refund Initiated",
            badge_bg=c.NAVY,
            title="Your Refund Is On Its Way",
            subtitle=(
                "A refund of <strong>Rs. {{ amount }}</strong> for order "
                "<strong>{{ order_number }}</strong> has been initiated. You’ll "
                "receive a confirmation once your bank processes it — typically "
                "5–7 business days."
            ),
        ),
        c.order_meta_grid(),
        c.cta_block(
            ("View Refund Details", "{{ order_url }}"),
            ("Refund Policy", "{{ returns_url }}"),
        ),
        c.spacer(30),
    ],
)

_REFUND_PROCESSED = _email(
    title="Refund completed for order {{ order_number }}",
    preheader="Rs. {{ amount }} has been refunded to your original payment method.",
    blocks=[
        c.hero(
            badge_text="Refund Complete",
            badge_bg=c.GOLD,
            title="Refund Processed",
            subtitle=(
                "Your refund of <strong>Rs. {{ amount }}</strong> for order "
                "<strong>{{ order_number }}</strong> has been processed to your "
                "original payment method. Depending on your bank, it may take "
                "5–7 business days to appear."
            ),
        ),
        c.cta_block(
            ("View Refund Details", "{{ order_url }}"),
            ("Shop New Arrivals", "{{ new_arrivals_url }}"),
        ),
        c.spacer(30),
    ],
)

# ── Customer emails — engagement ──────────────────────────────────────────────

_REVIEW_REQUEST = _email(
    title="How was your {{ brand_short_name }} order?",
    preheader="Loved your order {{ order_number }}? Tell us in under a minute.",
    blocks=[
        c.hero(
            badge_text="Your Opinion Matters",
            badge_bg=c.GOLD,
            title="How Is Your New Jewellery{% if customer_name %}, {{ customer_name }}{% endif %}?",
            subtitle=(
                "We hope you’re loving the pieces from order "
                "<strong>{{ order_number }}</strong>. Your review takes less than "
                "a minute and helps other shoppers choose with confidence."
            ),
        ),
        c.product_items(),
        c.cta_block(
            ("Write A Review", "{{ order_url }}"),
            ("Shop Again", "{{ shop_url }}"),
            variant="gold",
        ),
        c.spacer(30),
    ],
)

_ABANDONED_CART = _email(
    title="Your cart is waiting",
    preheader="You left something sparkly behind — complete your order before it sells out.",
    blocks=[
        c.hero(
            badge_text="Still Thinking It Over?",
            badge_bg=c.GOLD,
            title="You Left Something Sparkly Behind",
            subtitle=(
                "{% if full_name %}{{ full_name }}, you{% else %}You{% endif %} have "
                "{{ item_count }} item(s) waiting in your cart. Our handcrafted "
                "pieces are made in small batches — complete your order before "
                "they sell out."
            ),
        ),
        c.cta_block(
            ("Return To Cart", "{{ cart_url }}"),
            ("Browse Collections", "{{ shop_url }}"),
            variant="gold",
        ),
        c.spacer(30),
    ],
)

# ── Admin emails ──────────────────────────────────────────────────────────────

_REFUND_FAILED_ADMIN = _email(
    title="Refund failed — order {{ order_number }}",
    preheader="A refund needs manual follow-up with Razorpay.",
    blocks=[
        c.hero(
            badge_text="Admin Alert",
            badge_bg=c.DESTRUCTIVE,
            title="Refund Failed — Action Required",
            subtitle=(
                "Refund <strong>{{ refund_id }}</strong> of <strong>Rs. {{ amount }}"
                "</strong> for order <strong>{{ order_number }}</strong> failed at "
                "Razorpay{% if reason %}: <strong>{{ reason }}</strong>{% endif %}. "
                "This needs manual follow-up with Razorpay support or the customer."
            ),
        ),
        c.cta_block(
            (
                "View Order In Admin",
                "{% if admin_order_url %}{{ admin_order_url }}{% else %}"
                "{{ admin_url }}{% endif %}",
            )
        ),
        c.spacer(30),
    ],
)

# ── Email catalog ─────────────────────────────────────────────────────────────

EMAIL_TEMPLATES: list[TemplateDef] = [
    TemplateDef(
        "welcome_email",
        "email",
        "user_registered",
        "Welcome to {{ brand_name }}",
        _WELCOME,
    ),
    TemplateDef(
        "order_confirmation_email",
        "email",
        "order_created",
        "Order {{ order_number }} confirmed — thank you!",
        _ORDER_CONFIRMATION,
    ),
    TemplateDef(
        "order_confirmed_email",
        "email",
        "order_confirmed",
        "Your order {{ order_number }} is confirmed",
        _ORDER_CONFIRMED,
    ),
    TemplateDef(
        "order_processing_email",
        "email",
        "order_processing",
        "Your order {{ order_number }} is being prepared",
        _ORDER_PROCESSING,
    ),
    TemplateDef(
        "order_packed_email",
        "email",
        "order_packed",
        "Your order {{ order_number }} is packed",
        _ORDER_PACKED,
    ),
    TemplateDef(
        "order_shipped_email",
        "email",
        "order_shipped",
        "Your order {{ order_number }} has shipped",
        _ORDER_SHIPPED,
    ),
    TemplateDef(
        "order_delivered_email",
        "email",
        "order_delivered",
        "Delivered! Your order {{ order_number }} has arrived",
        _ORDER_DELIVERED,
    ),
    TemplateDef(
        "order_cancelled_email",
        "email",
        "order_cancelled",
        "Your order {{ order_number }} has been cancelled",
        _ORDER_CANCELLED,
    ),
    TemplateDef(
        "order_return_requested_email",
        "email",
        "order_return_requested",
        "Return requested for order {{ order_number }}",
        _ORDER_RETURN_REQUESTED,
    ),
    TemplateDef(
        "order_returned_email",
        "email",
        "order_returned",
        "Return received for order {{ order_number }}",
        _ORDER_RETURNED,
    ),
    TemplateDef(
        "order_payment_failed_status_email",
        "email",
        "order_payment_failed",
        "Payment issue on order {{ order_number }}",
        _ORDER_PAYMENT_FAILED_STATUS,
    ),
    TemplateDef(
        "order_payment_expired_email",
        "email",
        "order_payment_expired",
        "Payment window expired for order {{ order_number }}",
        _ORDER_PAYMENT_EXPIRED,
    ),
    TemplateDef(
        "order_refunded_status_email",
        "email",
        "order_refunded",
        "Order {{ order_number }} has been refunded",
        _ORDER_REFUNDED_STATUS,
    ),
    TemplateDef(
        "payment_receipt_email",
        "email",
        "payment_captured",
        "Payment received for order {{ order_number }}",
        _PAYMENT_RECEIPT,
    ),
    TemplateDef(
        "payment_failed_email",
        "email",
        "payment_failed",
        "Payment issue with order {{ order_number }} — let’s fix it",
        _PAYMENT_FAILED,
    ),
    TemplateDef(
        "refund_created_email",
        "email",
        "refund_created",
        "Refund initiated for order {{ order_number }}",
        _REFUND_CREATED,
    ),
    TemplateDef(
        "refund_processed_email",
        "email",
        "refund_processed",
        "Refund of Rs. {{ amount }} completed for order {{ order_number }}",
        _REFUND_PROCESSED,
    ),
    TemplateDef(
        "review_request_email",
        "email",
        "review_request",
        "How was your {{ brand_short_name }} order {{ order_number }}?",
        _REVIEW_REQUEST,
    ),
    TemplateDef(
        "abandoned_cart_email",
        "email",
        "abandoned_cart",
        "You left something sparkly behind",
        _ABANDONED_CART,
    ),
    TemplateDef(
        "refund_failed_admin_alert",
        "email",
        "refund_failed_admin_alert",
        "[{{ brand_short_name }} Admin] Refund failed for order {{ order_number }}",
        _REFUND_FAILED_ADMIN,
    ),
]

# ── WhatsApp catalog ──────────────────────────────────────────────────────────
# body = informational copy stored/rendered into the log; the actual send maps
# `variables.params` (ordered) onto the Meta-approved template of the same name.
# NOTE: the Meta Business Manager templates must be (re)registered to match the
# new parameter lists before switching over — see Docs/Notification_docs/README.


def _wa(name: str, event: str, body: str, params: list[str]) -> TemplateDef:
    return TemplateDef(
        name=name,
        channel="whatsapp",
        event_type=event,
        subject=None,
        body=body,
        variables={
            "whatsapp_template": event,
            "whatsapp_lang": "en_US",
            "params": params,
        },
    )


WHATSAPP_TEMPLATES: list[TemplateDef] = [
    _wa(
        "order_created_whatsapp",
        "order_created",
        "Hi {{ customer_name }}! 🎉 Your {{ brand_short_name }} order "
        "*{{ order_number }}* is confirmed.\n\n💰 Total: Rs. {{ total }}\n"
        "📦 We’ll message you the moment it ships.\n\n"
        "🔗 View order: {{ order_url }}\n💬 Help: {{ contact_url }}",
        ["customer_name", "order_number", "total", "order_url"],
    ),
    _wa(
        "payment_captured_whatsapp",
        "payment_captured",
        "✅ Payment received!\n\nHi {{ customer_name }}, we’ve received "
        "Rs. {{ amount }} for order *{{ order_number }}*. Your jewellery is now "
        "being prepared with care.\n\n🔗 Track: {{ order_url }}",
        ["customer_name", "amount", "order_number", "order_url"],
    ),
    _wa(
        "payment_failed_whatsapp",
        "payment_failed",
        "⚠️ Hi {{ customer_name }}, your payment for order *{{ order_number }}* "
        "could not be completed. Your items were released back to stock — retry "
        "before they sell out.\n\n🔗 Retry: {{ cart_url }}",
        ["customer_name", "order_number", "cart_url"],
    ),
    _wa(
        "order_packed_whatsapp",
        "order_packed",
        "📦 Hi {{ customer_name }}, order *{{ order_number }}* is packed and ready "
        "to ship. Tracking details coming soon!\n\n🔗 View order: {{ order_url }}",
        ["customer_name", "order_number", "order_url"],
    ),
    _wa(
        "order_shipped_whatsapp",
        "order_shipped",
        "🚚 On its way!\n\nHi {{ customer_name }}, order *{{ order_number }}* has "
        "shipped.\n\n📋 Tracking: {{ tracking_number }}\n🔗 Track live: "
        "{{ tracking_url }}",
        ["customer_name", "order_number", "tracking_number", "tracking_url"],
    ),
    _wa(
        "order_delivered_whatsapp",
        "order_delivered",
        "🎉 Delivered!\n\nHi {{ customer_name }}, order *{{ order_number }}* has "
        "arrived. We hope you love it! 💍\n\nCare tip: store silver in a dry pouch, "
        "away from perfume.\n\n⭐ We’d love your feedback!\nLeave a review for "
        "your purchase: {{ order_url }}",
        ["customer_name", "order_number", "order_url"],
    ),
    _wa(
        "order_cancelled_whatsapp",
        "order_cancelled",
        "Hi {{ customer_name }}, order *{{ order_number }}* has been cancelled. "
        "If you paid online, your refund is being initiated automatically.\n\n"
        "💬 Questions? {{ contact_url }}",
        ["customer_name", "order_number", "contact_url"],
    ),
    _wa(
        "refund_created_whatsapp",
        "refund_created",
        "💸 Refund initiated\n\nHi {{ customer_name }}, Rs. {{ amount }} for order "
        "*{{ order_number }}* is on its way back to you (5–7 business days).\n\n"
        "🔗 Details: {{ order_url }}",
        ["customer_name", "amount", "order_number", "order_url"],
    ),
    _wa(
        "refund_processed_whatsapp",
        "refund_processed",
        "✅ Refund complete\n\nHi {{ customer_name }}, Rs. {{ amount }} for order "
        "*{{ order_number }}* has been processed to your original payment method.",
        ["customer_name", "amount", "order_number"],
    ),
    _wa(
        "review_request_whatsapp",
        "review_request",
        "Hi {{ customer_name }}! 💎 How are you liking your jewellery from order "
        "*{{ order_number }}*? A quick review helps other shoppers.\n\n"
        "⭐ Review: {{ order_url }}",
        ["customer_name", "order_number", "order_url"],
    ),
]

ALL_TEMPLATES: list[TemplateDef] = EMAIL_TEMPLATES + WHATSAPP_TEMPLATES
