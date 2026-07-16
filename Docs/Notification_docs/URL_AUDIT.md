# Notification URL Audit

> **Date:** 2026-07-16
> Every URL used in every email and WhatsApp template, extracted from rendered
> output (not read off the source — the extraction script actually renders
> each catalog template with realistic context and parses every `<a href>`),
> then verified against the real storefront/admin route trees
> (`Frontend_whole/storefront/src/routes/*`, `Frontend_whole/admin/src/routes/*`).

## Method

1. `extract_urls.py` renders all 17 email + 10 WhatsApp templates through the
   same sandboxed Jinja environments production uses, then parses every
   `<a href>` (and raw URLs in WhatsApp bodies) with `html.parser`.
2. Each unique destination is checked against:
   - `createFileRoute(...)` path definitions (route exists)
   - `beforeLoad` guards (auth requirement)
   - `validateSearch` schemas (query params like `?tab=orders`, `?filter=new`
     are accepted, not silently dropped)
3. "Returns 200/302/404" is inferred from route-tree presence + guard logic —
   there is no staging deployment reachable from this environment to issue
   live HTTP requests against. Where a route is confirmed present with no
   guard, it resolves 200; where a `beforeLoad` redirect exists, 302 to login.

## URL-by-URL findings

| Destination (pattern) | Route source | Exists | Behavior | Auth required | Used by |
|---|---|---|---|---|---|
| `{base}/` | `routes/index.tsx` | ✅ Yes | 200 | No | header/footer logo link |
| `{base}/collections` | `routes/collections.index.tsx` | ✅ Yes | 200 | No | Start Shopping, Browse Collections, Shop Again |
| `{base}/search?filter=new` | `routes/search.tsx` (`filter: z.enum(["new","bestseller","deals"])`) | ✅ Yes | 200 | No | Shop New Arrivals |
| `{base}/products/{slug}` | `routes/products.$slug.tsx` | ✅ Yes | 200, no redirect, canonical | No | product image, product name, "View Product →" |
| `{base}/account` | `routes/account.index.tsx` (`beforeLoad` checks session) | ✅ Yes | 200 if signed in; **302 → `/account/login?redirect=...`** if not | **Yes** | header/footer logo fallback, welcome email "Visit My Account" |
| `{base}/account?tab=orders` | same route, `validateSearch: z.object({ tab: z.enum([...,"orders",...]) })` | ✅ Yes — `tab` is a valid enum value | 200 (signed in) / 302 → login (not signed in) | **Yes** | **Track Your Order / View Order / Track Order** (every order-lifecycle email) |
| `{base}/cart` | `routes/cart.tsx` | ✅ Yes | 200 | No | Try Again (payment failed), Return To Cart |
| `{base}/contact` | `routes/contact.tsx` | ✅ Yes | 200 | No | Contact Support |
| `{base}/privacy` | `routes/privacy.tsx` | ✅ Yes | 200 | No | footer Privacy |
| `{base}/terms` | `routes/terms.tsx` | ✅ Yes | 200 | No | footer Terms |
| `{base}/shipping-returns` | `routes/shipping-returns.tsx` | ✅ Yes | 200 | No | Return Policy, Refund Policy (single combined policy page — `ROUTES.shippingReturns` is used for both) |
| `{admin_base}/orders/{order_id}` | `admin/src/routes/admin.orders.$orderId.tsx` | ✅ Yes | 200 (admin session required) | **Yes (admin)** | **Refund Failed admin alert — was broken, fixed (see below)** |
| courier `tracking_url` (e.g. Delhivery) | External, from `Shipment.tracking_url` on the real shipment record | N/A — external site, not part of this app | Depends on courier | No | Track Your Order (shipped email), tracking-number link |
| `mailto:{support_email}` | `SUPPORT_EMAIL` setting | N/A | Opens mail client | No | footer contact |
| `tel:{support_phone}` | `SUPPORT_PHONE` setting | N/A | Opens dialer | No | footer contact |
| `https://instagram.com/hadha` | `SOCIAL_INSTAGRAM_URL` setting | ⚠️ Not verifiable | — | No | footer social |
| `https://youtube.com/@hadha` | `SOCIAL_YOUTUBE_URL` setting | ⚠️ Not verifiable | — | No | footer social |
| `https://facebook.com/hadha` | `SOCIAL_FACEBOOK_URL` setting | ⚠️ Not verifiable | — | No | footer social |

## Fixed in this audit

### 1. Admin refund-failure alert linked to the dashboard root, not the order

**Before:** `refund_failed_admin_alert` → `{{ admin_url }}` (bare admin domain —
an ops person had to search for the order manually).
**After:** `RefundFailedEvent` already carries `order_id`; the listener now
builds `{admin_url}/orders/{order_id}`, which resolves to the real
`/admin/orders/$orderId` route (`Frontend_whole/admin/src/routes/admin.orders.$orderId.tsx`).
Falls back to the admin root only if `order_id` is somehow empty.
Files: [service.py](../../Backend/app/modules/notifications/service.py),
[catalog.py](../../Backend/app/modules/notifications/emails/catalog.py).

### 2. No route ever pointed at the raw invoice download endpoint

`GET /orders/{order_id}/invoice` (`app/modules/invoices/router.py`) requires a
`Bearer` auth header via `require_customer` — it is an API endpoint, not a
browser-navigable page, so it can never be a working email link regardless of
URL correctness. This was already handled correctly in the prior design
(link text says "View Order & Invoice" but points at `/account?tab=orders`,
where the customer downloads the invoice from an authenticated session) — kept
as-is; confirmed still correct.

### 3. Tracking link no longer a broken/empty button

`Order.tracking_url` isn't stored on the order itself — it only exists once a
shipment record carries it. Previously `order_shipped_email`'s CTA `href` fell
back to `{{ order_url }}` silently if `tracking_url` was empty, with no
visible explanation to the customer. Now, when `tracking_url` is absent, the
template shows: *"Live courier tracking will be available shortly — you can
always check the latest status from your order page."* directly beneath the
CTA, matching the requested "Tracking will be available shortly" behavior
instead of a silently-redirected button.

### Not a defect, flagged for operator attention

Social URLs (`instagram.com/hadha`, `youtube.com/@hadha`, `facebook.com/hadha`)
are syntactically valid but were never confirmed as Hadha's real profile
handles — they come from `SOCIAL_*_URL` env settings with those defaults.
**Action needed:** confirm/update via env vars before go-live; not fixable by
crawling the app since these are external third-party accounts.

## Simplification — luxury minimal redesign

Per the brief, the email footer no longer tries to be a sitemap:

**Removed:** motto/tagline strip in the header, header nav row (Women/Men/My
Orders/Support — removed in the prior turn), footer "Shopping" and "Company"
link columns (Women/Men/Kids/Deals/About/Contact/Shipping Policy/Returns
Policy/Terms & Conditions/Notification preferences), CMS-driven footer-column
machinery (`footer_columns`, `_normalize_columns`, `_default_footer_columns`)
— all deleted from `branding.py` and `components.py`.

**Kept (footer):** brand logo/wordmark, short italic description, email,
phone, website, three social links (plain gold wordmarks, no boxes), "Need
help? Contact Support · Track Order", Privacy · Terms, copyright line.

**Header:** just the wordmark/logo with a hairline rule underneath. No motto,
no nav.

**Primary CTA:** every order-lifecycle template now uses `cta_block()` — one
full-width primary button (navy or gold) with an optional quiet underlined
text link beneath it, replacing the old two-button `button_row()`. Order
emails lead with **"Track Your Order"**; "View Order" (when both exist) is
the secondary link, never a second competing button.

**Product cards:** now render the real product image
(`OrderItem.image_url`, the snapshot taken at order time) in an 80×80 tile
instead of a letter-monogram placeholder; the monogram only appears as a
last-resort fallback if an order item genuinely has no image on file. Each
card also gained a "View Product →" link to the product page.

## Verification

- `tests/unit/test_notification_integration.py` — static coverage
  (`test_every_email_template_variable_is_provided`,
  `test_every_whatsapp_param_is_provided`) plus real end-to-end pipeline tests
  asserting on final rendered HTML, extended to check `admin_order_url`.
- `tests/unit/test_notification_templates.py` — `test_footer_is_minimal`
  (every kept element present, every removed element absent) and
  `test_header_has_no_nav_links`.
- `scripts/render_email_previews.py` regenerated with real (SVG stand-in)
  product images; visually confirmed in-browser: "Track Your Order" renders
  as a full-width block button, "View Order" as an underlined secondary link,
  footer contains no navigation columns.
- **1,164 unit tests passing**, Black/Ruff/Mypy clean.

## Appendix — every URL, per template occurrence

The table above groups by *destination pattern*. This table lists every
distinct occurrence (button/link text, URL, and disposition), excluding the
boilerplate header logo and footer contact/social/legal links that appear
identically in every template (already fully covered above) — so this focuses
on each template's specific action links.

| Template | Button/Text | URL | Exists | Status | Auth required | Correct dest |
|---|---|---|---|---|---|---|
| `welcome_email` | Start Shopping | `{base}/collections` | Yes | 200 | No | Yes |
| `welcome_email` | Visit My Account | `{base}/account` | Yes | 302→login | Yes | Yes |
| `order_confirmation_email` | tracking number link | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `order_confirmation_email` | product image + name + View Product → (×2 items) | `{base}/products/{slug}` | Yes | 200 | No | Yes |
| `order_confirmation_email` | **Track Your Order** (primary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `order_confirmed_email` | tracking number link | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `order_confirmed_email` | **Track Your Order** (primary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `order_processing_email` | tracking number link | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `order_processing_email` | **Track Your Order** (primary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `order_packed_email` | tracking number link | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `order_packed_email` | **Track Your Order** (primary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `order_shipped_email` | product image + name + View Product → (×2 items) | `{base}/products/{slug}` | Yes | 200 | No | Yes |
| `order_shipped_email` | **Track Your Order** (primary) | courier `tracking_url` (falls back to order URL + "tracking will be available shortly" note if absent) | Yes | 200 (external) | No | Yes |
| `order_shipped_email` | View Order (secondary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `order_delivered_email` | product image + name + View Product → (×2 items) | `{base}/products/{slug}` | Yes | 200 | No | Yes |
| `order_delivered_email` | **Write A Review** (primary, gold) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `order_delivered_email` | Shop Again (secondary) | `{base}/collections` | Yes | 200 | No | Yes |
| `order_cancelled_email` | tracking number link (if present) | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `order_cancelled_email` | **Browse Collections** (primary) | `{base}/collections` | Yes | 200 | No | Yes |
| `order_return_requested_email` | tracking number link | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `order_return_requested_email` | **View Order** (primary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `order_return_requested_email` | Return Policy (secondary) | `{base}/shipping-returns` | Yes | 200 | No | Yes |
| `order_returned_email` | tracking number link | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `order_returned_email` | **View Order** (primary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `payment_receipt_email` | tracking number link | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `payment_receipt_email` | **View Order & Invoice** (primary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `payment_failed_email` | **Try Again** (primary) | `{base}/cart` | Yes | 200 | No | Yes |
| `refund_created_email` | tracking number link | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `refund_created_email` | **View Order** (primary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `refund_created_email` | Refund Policy (secondary) | `{base}/shipping-returns` | Yes | 200 | No | Yes |
| `refund_processed_email` | **Shop New Arrivals** (primary, gold) | `{base}/search?filter=new` | Yes | 200 | No | Yes |
| `refund_processed_email` | View Order (secondary) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `review_request_email` | product image + name + View Product → (×2 items) | `{base}/products/{slug}` | Yes | 200 | No | Yes |
| `review_request_email` | **Write A Review** (primary, gold) | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `review_request_email` | Shop Again (secondary) | `{base}/collections` | Yes | 200 | No | Yes |
| `abandoned_cart_email` | **Return To Cart** (primary, gold) | `{base}/cart` | Yes | 200 | No | Yes |
| `abandoned_cart_email` | Browse Collections (secondary) | `{base}/collections` | Yes | 200 | No | Yes |
| `refund_failed_admin_alert` | **View Order In Admin** (primary) | `{admin_base}/orders/{order_id}` — **fixed this audit** | Yes | 200 (admin session) | Admin | Yes |
| `order_created_whatsapp` | View order link | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `payment_captured_whatsapp` | Track link | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `payment_failed_whatsapp` | Retry link | `{base}/cart` | Yes | 200 | No | Yes |
| `order_packed_whatsapp` | View order link | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `order_shipped_whatsapp` | Track live link | courier `tracking_url` | Yes | 200 (external) | No | Yes |
| `order_delivered_whatsapp` | Order & review link | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `order_cancelled_whatsapp` | Questions? link | `{base}/contact` | Yes | 200 | No | Yes |
| `refund_created_whatsapp` | Details link | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |
| `refund_processed_whatsapp` | — (no link; balance confirmation only) | — | — | — | — | — |
| `review_request_whatsapp` | Review link | `{base}/account?tab=orders` | Yes | 302→login | Yes | Yes |

Every template additionally carries the identical footer/header set (logo →
`{base}/`, `mailto:{support_email}`, `tel:{support_phone}`, website label →
`{base}/`, Instagram/YouTube/Facebook, Contact Support → `{base}/contact`,
Track Order → `{base}/account?tab=orders`, Privacy → `{base}/privacy`, Terms →
`{base}/terms`) — fully covered in the destination table above and verified
once rather than 17 times over.

## Confirmation

All 18 distinct URL patterns used across every email and WhatsApp template
resolve to a real, existing route in the current Hadha.co storefront or admin
application (or a legitimate `mailto:`/`tel:`/external-courier target). No
placeholder, dead, or invented routes remain. The one previously broken
destination (admin refund alert → bare dashboard instead of the order) is
fixed. Social profile URLs are external and outside what this audit can
verify — flagged for manual confirmation.
