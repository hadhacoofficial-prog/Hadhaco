# Notification Integration Matrix

> **Date:** 2026-07-16
> Every template traced end-to-end: Trigger → Listener → Context Builder →
> Template Render → Provider → Final HTML. Verified by
> `tests/unit/test_notification_integration.py`, which (a) statically proves
> every Jinja placeholder has a provider-side value and (b) fires the real
> listeners with realistic events and asserts on the final HTML handed to the
> email provider. **1,162 unit tests green.**

Legend — Context builders:
- **BRAND** = `branding.get_brand_context_db()` (env defaults ← storefront
  `BRAND` config, overlaid by the CMS `footer` section at send time). Injected
  into *every* render.
- **ORDER** = `context.load_order_context()` → order + items (eager-loaded),
  product slugs joined from `products` for deep links, addresses, Rs.-formatted
  pricing, payment/tracking facts, timeline stage.

## Email templates

| Template | Trigger (publisher) | Listener | Context | Event-specific vars | Missing | Status |
|---|---|---|---|---|---|---|
| `welcome_email` | **NEW:** first authenticated `GET /me` after signup (`notifications/welcome.py` bridge; Supabase handles signup client-side so no backend hook existed) | `_handle_user_registered` | BRAND | `full_name` | none | ✅ PASS *(was ❌ — no publisher existed)* |
| `order_confirmation_email` | `orders/service.py` payment verification → `OrderCreatedEvent` | `_handle_order_created` | BRAND + ORDER | `total` | none | ✅ PASS |
| `order_confirmed_email` | `orders/service.py update_order_status` → `order_confirmed` | `_handle_order_status_changed` | BRAND + ORDER | `old_status`, `new_status` | none | ✅ PASS |
| `order_processing_email` | same → `order_processing` | same | BRAND + ORDER | 〃 | none | ✅ PASS |
| `order_packed_email` | same → `order_packed` | same | BRAND + ORDER | 〃 | none | ✅ PASS |
| `order_shipped_email` | `shipping/service.py create_shipment` → `OrderShippedEvent` | `_handle_order_shipped` | BRAND + ORDER | `tracking_number`, `tracking_url`, `awb`, `timeline_stage=4` | none | ✅ PASS |
| `order_delivered_email` | `shipping/service.py` delivery update → `OrderDeliveredEvent` (admin manual `status=delivered` reaches the same template via `order_{status}`) | `_handle_order_delivered` | BRAND + ORDER | `timeline_stage=5` | none | ✅ PASS |
| `order_cancelled_email` | `update_order_status` / customer `cancel_order` → `order_cancelled` | `_handle_order_status_changed` | BRAND + ORDER (incl. `cancellation_reason`) | 〃 | none | ✅ PASS |
| `order_return_requested_email` | `update_order_status` → `order_return_requested` | same | BRAND + ORDER | 〃 | none | ✅ PASS |
| `order_returned_email` | `update_order_status` → `order_returned` | same | BRAND + ORDER | 〃 | none | ✅ PASS |
| `payment_receipt_email` | `orders/service.py` verify + `webhooks _on_payment_captured` | `_handle_payment_captured` | BRAND + ORDER | `amount` | none | ✅ PASS |
| `payment_failed_email` | `webhooks _on_payment_failed` | `_handle_payment_failed` | BRAND + ORDER | `reason` | none | ✅ PASS |
| `refund_created_email` | `payments/service.py create_refund` | `_handle_refund_created` | BRAND + ORDER | `amount` | none | ✅ PASS |
| `refund_processed_email` | `webhooks _on_refund_processed` | `_handle_refund_processed` | BRAND + ORDER | `amount` | none | ✅ PASS |
| `review_request_email` | `reviews/router.py` reminder trigger (post-delivery) | `_handle_review_request` | BRAND + ORDER (incl. items for product cards) | — | none | ✅ PASS |
| `refund_failed_admin_alert` | `webhooks _on_refund_failed` → `ADMIN_ALERT_EMAIL` | `_handle_refund_failed` | BRAND | `order_number`, `refund_id`, `amount`, `reason` | none | ✅ PASS |
| `abandoned_cart_email` | — none — | — | — | `full_name`, `item_count` | trigger itself | ⚠️ DORMANT (renders safely; needs a cart-abandonment worker — separate feature) |

## WhatsApp templates

All gated by: `WHATSAPP_ENABLED` + provider config + rule toggle + user
preference + **recipient phone present**. Params verified against each event's
context by `test_every_whatsapp_param_is_provided`.

| Template | Trigger | Phone source | Params (ordered) | Status |
|---|---|---|---|---|
| `order_created_whatsapp` | order placed | event `customer_phone` | customer_name, order_number, total, order_url | ✅ PASS |
| `payment_captured_whatsapp` | payment captured | event / profile | customer_name, amount, order_number, order_url | ✅ PASS |
| `payment_failed_whatsapp` | payment failed | profile | customer_name, order_number, cart_url | ✅ PASS |
| `order_packed_whatsapp` | status → packed | profile | customer_name, order_number, order_url | ✅ PASS |
| `order_shipped_whatsapp` | shipment created | profile | customer_name, order_number, tracking_number, tracking_url | ✅ PASS |
| `order_delivered_whatsapp` | delivered | profile | customer_name, order_number, order_url | ✅ PASS |
| `order_cancelled_whatsapp` | cancelled | profile | customer_name, order_number, contact_url | ✅ PASS |
| `refund_created_whatsapp` | refund initiated | **profile (FIXED — listener previously passed no phone, so this could never send)** | customer_name, amount, order_number, order_url | ✅ PASS |
| `refund_processed_whatsapp` | refund completed | **profile (FIXED — same)** | customer_name, amount, order_number | ✅ PASS |
| `review_request_whatsapp` | review reminder | profile | customer_name, order_number, order_url | ✅ PASS |

> ⚠️ Operational prerequisite: each template must be registered/approved in
> Meta Business Manager with the exact parameter counts above.

## Gaps found & fixed in this audit

1. **`user_registered` had no publisher** — signup is Supabase client-side; a
   DB trigger creates the profile and the backend never saw it. Fixed with an
   idempotent bridge on `GET /me` (Redis SETNX claim + `notification_logs`
   existence check + 48 h freshness window): `app/modules/notifications/welcome.py`,
   `NotificationRepository.has_log_for_user_event`.
2. **Refund WhatsApp unreachable** — `_handle_refund_created/_processed`
   dispatched without `recipient_phone`, so the (rule-enabled) refund WhatsApp
   templates could never send. Fixed via `_profile_phone()` lookup.
3. **`tracking_url` referenced but not always provided** — the order meta grid
   links the tracking number in every order email, but only the shipped
   listener supplied `tracking_url`. Now always present in the order context
   (empty ⇒ plain-text tracking number). Caught by the static coverage test.
4. **Brand/footer data now dynamic** — brand context reads the same CMS
   `footer` section the storefront header/footer render from (logo, address,
   phone, email, socials, copyright name), falling back to env → storefront
   `BRAND` defaults. Admin CMS edits propagate to emails without a deploy.

## Deep-link inventory (all derived from `FRONTEND_URL`)

| Link | Value | Used by |
|---|---|---|
| Product page | `/products/{slug}` (slug joined from `products` at send time) | product card image + title |
| Order / invoice | `/account?tab=orders` (invoice download lives in the order view; the raw invoice API needs an auth header, unusable from email) | View Order / View Order & Invoice / Track Order fallback |
| Tracking | courier `tracking_url` from the shipment payload | Track Shipment CTA, tracking number link |
| Account / preferences | `/account`, `/account?tab=profile` | header nav, footer |
| Shop / gender / new arrivals | `/collections`, `/search?gender=…`, `/search?filter=new` | header nav, footer Shopping column, CTAs |
| Support & legal | `/contact`, `/faq`, `/shipping-returns`, `/privacy`, `/terms` | footer |
| Cart / wishlist | `/cart`, `/wishlist` | payment-failed retry, abandoned cart |
