# Notification System Audit — Phase 1

> **Date:** 2026-07-15
> **Scope:** Every email/WhatsApp template, the data flowing into them, and the gaps
> blocking a premium, enterprise-grade communication experience.

---

## 1. System inventory

### Architecture (sound — kept as-is)

```
Business Events → EventBus → NotificationService → Dispatcher → ProviderRegistry → Resend / Meta Cloud API → NotificationLog
```

Templates are **stored in the database** (`notification_templates`), edited in the
admin UI, versioned via `notification_template_versions`, and rendered with Jinja2
(`Environment(loader=BaseLoader, autoescape=True)`) in
`app/modules/notifications/service.py`. This architecture is good and is preserved;
the upgrade targets **content generation, context richness, and reuse**.

### Template inventory (as seeded today)

| Template | Channel | Event | Seeded by | State |
|---|---|---|---|---|
| `welcome_email` | email | `user_registered` | 023_seed_data.sql | Live, minimal |
| `order_confirmation_email` | email | `order_created` | 023 | Live, minimal |
| `payment_receipt_email` | email | `payment_captured` | 023 | Live, minimal |
| `order_shipped_email` | email | `order_shipped` | 023 | Live, minimal |
| `order_delivered_email` | email | `order_delivered` | 023 | Live, minimal |
| `refund_created_email` | email | `refund_created` | 023 | Live, minimal |
| `refund_processed_email` | email | `refund_processed` | 023 | Live, minimal |
| `review_request_email` | email | `review_request` | 023 | Live, minimal |
| `payment_failed_email` | email | `payment_failed` | 0030 | Live, minimal |
| `refund_failed_admin_alert` | email | `refund_failed_admin_alert` | 0030 | Live, minimal |
| `order_cancelled_email` | email | `order_cancelled` | 0042 | Live, minimal |
| `order_created_whatsapp` … `review_request_whatsapp` (9 rows) | whatsapp | various | 0042 | Live, terse one-liners |
| `abandoned_cart_email` | email | `abandoned_cart` | 023 | **Dead** — no publisher, no rule |
| `order_confirmation_sms` (+ other `sms` rows) | sms | various | 023 | **Dead** — SMS provider removed |
| `low_stock_alert_email` | email | `low_inventory_alert` | 023 | **Deleted** by 0044 (deliberate — no publisher) |

### Events that actually fire (publishers confirmed)

`user_registered`, `order_created`, `payment_captured`, `payment_failed`,
`order_shipped` (shipping service), `order_delivered`, `order_{status}` (admin
status updates + customer cancellation → `order_confirmed`, `order_processing`,
`order_packed`, `order_cancelled`, `order_return_requested`, `order_returned`,
`order_refunded` are all reachable), `refund_created`, `refund_processed`,
`refund_failed_admin_alert`, `review_request`.

**Gap:** dynamic `order_{status}` events other than `order_cancelled` have **no
rule and no template**, so admin status changes to `processing`/`packed` etc.
silently send nothing.

---

## 2. Findings

### 2.1 Broken deep links (bug)

Every seeded template hardcodes `https://hadha.co/orders/{{order_number}}` and
`https://hadha.co/orders/{{order_number}}/review` — **routes that do not exist**
in the storefront (orders live under `/account`). `frontend_url` is passed in
every context but never used by any template.

### 2.2 Hardcoded values (13× duplication)

- `https://hadha.co/...` absolute URLs → breaks staging/preview environments.
- Brand name, colors (`#1c1b1a`, `#e8e2d9`, `#f7f5f2`), header, and footer HTML
  copy-pasted into every template body with slight drift.
- No single source of truth — a brand change requires editing 20+ DB rows.

### 2.3 Missing variables (data exists, never passed)

The `Order` model already snapshots everything premium order emails need, but the
notification context only receives `order_number` + `total`:

| Available on `Order`/`OrderItem` | Passed today |
|---|---|
| Items (name, SKU, variant, image_url, qty, unit_price, line_total) | ❌ |
| Shipping + billing address snapshots | ❌ |
| subtotal / discount / coupon_code / shipping_charge / tax_amount / total | only `total` |
| payment_method, payment_status | ❌ |
| estimated_delivery, tracking_number, shipping_provider | only on `order_shipped` |
| complimentary_gift | ❌ |
| Customer name (shipping_full_name) | ❌ (only welcome email gets a name) |
| Invoice download (`GET /orders/{id}/invoice` exists) | ❌ |

### 2.4 Missing branding & compliance

No template has: logo image, support email/phone, social links, physical address,
legal links (privacy/terms), preference-center/unsubscribe link, or copyright year.
The customer-facing notification preference center exists (`/notifications/preferences`)
but is never linked from emails.

### 2.5 Missing email-engineering fundamentals

- No preheader text, no `lang`/`dir` attributes, no `role="presentation"` gaps.
- No mobile breakpoints (`@media`), no dark-mode handling (`prefers-color-scheme`),
  no Outlook (MSO) conditionals, no bulletproof buttons.
- No image fallbacks / alt text discipline; no product imagery at all.

### 2.6 Duplicates / dead rows

- `abandoned_cart_email` + all `sms` templates are unreachable (no publisher /
  provider). Kept in DB (additive policy) but must be marked inactive or left
  documented as dormant.
- `low_inventory_alert` was **deliberately removed** in migration 0044 — do not
  resurrect without building a publisher (explicit prior decision).

### 2.7 Security

- ✅ `autoescape=True` — user-provided strings are HTML-escaped.
- ⚠️ Templates render in a full `jinja2.Environment` — admin-edited templates can
  reach dunder attributes (SSTI). Admins are trusted, but defense-in-depth says use
  `jinja2.sandbox.SandboxedEnvironment`.
- ⚠️ Subjects render with `autoescape=True` — HTML entities (`&amp;`) can leak into
  plain-text subjects. Subjects should render unescaped (they are not HTML).
- ✅ WhatsApp params are stringified before hitting the Meta API.

### 2.8 Preview constraint (drives the design)

`TemplateEditor.tsx` previews templates **client-side** with naive `{{var}}`
substitution. Therefore DB template bodies must remain **self-contained HTML**
(no `{% extends %}`/`{% include %}`). Reuse must happen at *authoring* time: a
Python design-system builder generates the full HTML that is seeded into the DB.

---

## 3. Upgrade plan (Phases 2–6)

1. **Design system** — `app/modules/notifications/emails/components.py`: brand
   tokens + reusable components (header, footer, button, status badge, product
   cards, order-summary table, order timeline, info grids, support block) that
   compose into complete, email-client-safe HTML documents (600 px hybrid tables,
   inline CSS, MSO conditionals, dark-mode + mobile `<style>` block, preheader).
2. **Catalog** — `emails/catalog.py`: one entry per (event, channel) generated from
   the design system; single source of truth for default template content.
3. **Brand context** — `branding.py` + new optional `Settings` fields
   (support email/phone, social URLs, logo URL). Injected into **every** render so
   all templates can use `{{ brand_name }}`, `{{ support_email }}`, `{{ frontend_url }}`, etc.
4. **Context enrichment** — `context.py` builds a rich order context (items with
   product links, addresses, totals breakdown, payment, tracking, timeline stage,
   invoice link); service listeners load the order (items eager-loaded already) and
   product slugs.
5. **New rules** — registry entries for `order_confirmed`, `order_processing`,
   `order_packed`, `order_return_requested`, `order_returned` (publishers already
   fire these).
6. **Migration 0047** — snapshot existing template versions, then upgrade all
   default templates + insert the new ones. Admin restore path keeps backward
   compatibility.
7. **Hardening** — sandboxed Jinja environment; subjects rendered without
   autoescape.
8. **Verification** — lint/type/test gates, rendered previews for every template.

**Explicitly out of scope (no backend triggers exist; separate features):**
abandoned-cart / wishlist / price-drop / back-in-stock / newsletter campaigns,
OTP/password emails (Supabase Auth sends these), admin daily/weekly summaries.
