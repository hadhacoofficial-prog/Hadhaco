# Hadha.co — Notification System Documentation

> **Status:** Feature-complete and production-ready.
> **Last updated:** 2026-07-15 — premium design-system upgrade (see §13 and AUDIT.md)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Event Flow](#2-event-flow)
3. [Supported Notification Events](#3-supported-notification-events)
4. [Notification Lifecycle and Retry Flow](#4-notification-lifecycle-and-retry-flow)
5. [Email Provider Configuration (Resend)](#5-email-provider-configuration-resend)
6. [WhatsApp Provider Configuration (Meta Cloud API)](#6-whatsapp-provider-configuration-meta-cloud-api)
7. [Template Architecture and Versioning](#7-template-architecture-and-versioning)
8. [Notification Matrix Configuration](#8-notification-matrix-configuration)
9. [Admin Module Overview](#9-admin-module-overview)
10. [WhatsApp Webhook Setup](#10-whatsapp-webhook-setup)
11. [Production Deployment Checklist](#11-production-deployment-checklist)
12. [Troubleshooting Guide](#12-troubleshooting-guide)
13. [Email Design System & Premium Templates](#13-email-design-system--premium-templates)

---

## 1. Architecture Overview

The notification system is an event-driven, multi-channel (Email + WhatsApp) notification layer built on three pillars:

```
Business Events  →  Event Bus  →  Notification Service  →  Dispatcher  →  Provider  →  Log
```

### Core Components

| Component | Location | Responsibility |
|---|---|---|
| **Event Bus** | `app/core/events.py` | In-process pub/sub via `asyncio.create_task` (fire-and-forget). Decouples business logic from notification dispatch. |
| **Notification Service** | `app/modules/notifications/service.py` | Listens to events, resolves recipients, renders templates, gates dispatch through rules/preferences, delegates to dispatcher. |
| **Notification Dispatcher** | `app/modules/notifications/dispatcher.py` | Thin adapter. Resolves concrete provider via `ProviderRegistry`. No business logic. |
| **Provider Registry** | `app/modules/notifications/providers/registry.py` | Maps provider names to singleton instances. Adding a new provider = implement ABC + register. |
| **Providers** | `app/modules/notifications/providers/` | Concrete implementations: `ResendProvider` (email), `MetaWhatsAppProvider` (WhatsApp). |
| **Repository** | `app/modules/notifications/repository.py` | All database operations: template CRUD, log management, analytics queries, retry scheduling. |
| **Retry Worker** | `app/workers/notification_retry.py` | APScheduler job. Polls for `retrying` logs whose `next_retry_at <= now()` and dispatches retries. |

### Key Design Decisions

- **Event-driven, not cron-based:** Notifications fire immediately when business events occur.
- **Three-tier dispatch gate:** Global provider enabled → NotificationRule (matrix) → User preference. Any gate can suppress a send.
- **Template versioning:** Every content edit creates a snapshot. Logs pin the exact template + version that produced them.
- **Provider abstraction:** The dispatcher never imports providers directly. The registry resolves them at runtime.
- **DB-over-env config:** Provider credentials resolve from the database first, falling back to environment variables. This lets admins rotate keys without redeploying.

---

## 2. Event Flow

### Step-by-step: Business Event → Delivered Notification

```
1. Business action occurs (e.g. order placed)
2. Business module publishes event to EventBus
      event_bus.publish(OrderCreatedEvent(...))
3. EventBus fires registered listener as asyncio.create_task (fire-and-forget)
4. NotificationService.dispatch() is called with the event
5. For each channel (email, then whatsapp if phone available):
   a. Check NotificationRule → must exist, enabled=True, channel toggle on
   b. Check user preferences → skip if user disabled that channel
   c. Look up active NotificationTemplate for (event_type, channel)
   d. Render Jinja2 subject/body with event context dict
   e. Create NotificationLog (status=pending, pin template_id + version)
   f. Delegate to NotificationDispatcher → ProviderRegistry → concrete Provider
   g. Provider sends via external API (Resend / Meta Cloud API)
   h. On success: mark log as sent, record provider_message_id
   i. On auth error: mark permanently failed (no retry)
   j. On other error: mark failed, schedule retry
```

### Provider Enable/Disable Flow

```
Provider enabled check:
  1. Read DB config via SettingsRepository.get_provider_config(db, provider)
  2. If no config row exists → default: enabled
  3. If config row exists → use its "enabled" value
  4. WhatsApp has an additional gate: settings.WHATSAPP_ENABLED must be True
```

---

## 3. Supported Notification Events

| Event | `event_type` | Channels | Recipient Source | Template Variables |
|---|---|---|---|---|
| User Registered | `user_registered` | email, whatsapp | `event.email` | `full_name`, `frontend_url` |
| Order Created | `order_created` | email, whatsapp | `event.customer_email` / `_phone` | `order_number`, `total`, `frontend_url` |
| Payment Captured | `payment_captured` | email, whatsapp | `event.customer_email` / `_phone` | `order_number`, `amount`, `frontend_url` |
| Payment Failed | `payment_failed` | email, whatsapp | order → profile lookup | `order_number`, `reason`, `frontend_url` |
| Order Status Changed | `order_{status}` | email, whatsapp | order → profile lookup | `order_number`, `old_status`, `new_status`, `frontend_url` |
| Order Shipped | `order_shipped` | email, whatsapp | order → profile lookup | `order_number`, `tracking_number`, `tracking_url`, `awb`, `frontend_url` |
| Order Delivered | `order_delivered` | email, whatsapp | order → profile lookup | `order_number`, `frontend_url` |
| Refund Created | `refund_created` | email, whatsapp | `event.customer_email` | `order_number`, `amount`, `frontend_url` |
| Refund Processed | `refund_processed` | email, whatsapp | `event.customer_email` | `order_number`, `amount`, `frontend_url` |
| Refund Failed (Admin) | `refund_failed_admin_alert` | email | `ADMIN_ALERT_EMAIL` | `order_number`, `refund_id`, `amount`, `reason` |
| Review Request | `review_request` | email, whatsapp | `event.customer_email` + profile phone | `order_number`, `frontend_url` |

> **Note:** `order_{status}` is dynamic. The `event_type` becomes `order_cancelled`, `order_processing`, etc. based on the new status. The NotificationRule must be configured for the exact `event_type` string.

---

## 4. Notification Lifecycle and Retry Flow

### Log Statuses

```
pending → sent → delivered → read
                   ↓
               failed (permanent — auth/config error)
                   ↓
retrying → (retry) → sent  OR  failed (exhausted retries)
```

### Status Transitions

| From | To | Trigger |
|---|---|---|
| `pending` | `sent` | Provider returns success + message ID |
| `sent` | `delivered` | Webhook from provider confirms delivery |
| `delivered` | `read` | Webhook from provider confirms read (WhatsApp) |
| `pending`/`retrying` | `retrying` | Send fails and retry budget remains |
| `pending`/`retrying` | `failed` | Auth/config error (permanent) OR retries exhausted |

### Retry Schedule

Configured in `_RETRY_DELAYS = [1, 5, 15]` (minutes):

| Attempt | Delay After Failure | Cumulative Time |
|---|---|---|
| 1 | 1 minute | 1 min |
| 2 | 5 minutes | 6 min |
| 3 | 15 minutes | 21 min |
| ≥3 | No more retries | — |

### Retry Payload Strategy

Retries are **deterministic** — they resend the originally rendered content, not a re-render:

- **Email retries:** Use `rendered_subject` and `rendered_body` stored on the `NotificationLog`. Falls back to Jinja re-render (with empty context) only for legacy logs that predate these fields.
- **WhatsApp retries:** Use `whatsapp_params` — a minimal JSONB payload containing `{template_name, language, params}` — the exact parameters originally sent to the Meta Cloud API. Falls back to dispatcher-based template re-render for legacy logs.

### Retry Worker

- **Location:** `app/workers/notification_retry.py`
- **Mechanism:** APScheduler periodic job
- **Query:** `SELECT * FROM notification_logs WHERE status = 'retrying' AND next_retry_at <= NOW()`
- **Session:** Opens a fresh `AsyncWorkerSessionLocal` per invocation

---

## 5. Email Provider Configuration (Resend)

### API

- **Base URL:** `https://api.resend.com`
- **Endpoint:** `POST /emails`
- **Timeout:** 15 seconds

### Configuration Resolution

Provider config is resolved in this order:

```
1. Database: SettingsRepository.get_provider_config(db, provider="email")
2. Environment variables (fallback):
     RESEND_API_KEY     — must start with "re_"
     EMAIL_FROM         — must contain "@"
     EMAIL_FROM_NAME    — default: "Hadha.co"
     EMAIL_REPLY_TO
```

### Custom Exceptions

| Exception | HTTP Status | Behavior |
|---|---|---|
| `ResendAuthError` | 401 | `mark_permanently_failed` — no retry |
| `ResendDomainError` | 403 | `mark_permanently_failed` — no retry |

### Environment Variables

| Variable | Default | Required |
|---|---|---|
| `RESEND_API_KEY` | — | Yes |
| `EMAIL_FROM` | — | Yes |
| `EMAIL_FROM_NAME` | `"Hadha.co"` | No |
| `EMAIL_REPLY_TO` | — | Yes |
| `ADMIN_ALERT_EMAIL` | `"admin@hadha.co"` | No |

---

## 6. WhatsApp Provider Configuration (Meta Cloud API)

### API

- **Base URL:** `https://graph.facebook.com/{api_version}/{phone_number_id}/messages`
- **Timeout:** 30 seconds
- **Auth:** Bearer token (access token)

### Configuration Resolution

```
1. Database: SettingsRepository.get_provider_config(db, provider="whatsapp")
2. Environment variables (fallback):
     WHATSAPP_ACCESS_TOKEN
     WHATSAPP_PHONE_NUMBER_ID
     WHATSAPP_API_VERSION       — default: "v21.0"
```

### Phone Number Handling

- Strips spaces, dashes, and leading `+` before sending
- Example: `+91 98765 43210` → `919876543210`

### Template Message Payload

```json
{
  "messaging_product": "whatsapp",
  "to": "919876543210",
  "type": "template",
  "template": {
    "name": "order_created",
    "language": { "code": "en_US" },
    "components": [
      {
        "type": "body",
        "parameters": [
          { "type": "text", "text": "#12345" },
          { "type": "text", "text": "1299.00" }
        ]
      }
    ]
  }
}
```

### Custom Exceptions

| Exception | HTTP Status | Behavior |
|---|---|---|
| `WhatsAppAuthError` | 401/403 | `mark_permanently_failed` — no retry |
| `WhatsAppTemplateError` | — | Template rejected by Meta |

### Environment Variables

| Variable | Default | Required |
|---|---|---|
| `WHATSAPP_ENABLED` | `False` | Must be `True` to send |
| `WHATSAPP_ACCESS_TOKEN` | — | Yes (if enabled) |
| `WHATSAPP_PHONE_NUMBER_ID` | — | Yes (if enabled) |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | — | Yes (for webhook setup) |
| `WHATSAPP_BUSINESS_PHONE` | `""` | No |
| `WHATSAPP_VERIFY_TOKEN` | `""` | For webhook verification |
| `WHATSAPP_WEBHOOK_SECRET` | `""` | For webhook signature validation |
| `WHATSAPP_API_VERSION` | `"v21.0"` | No |

### Free-Form Text Messages

`WhatsAppProvider.send_whatsapp_text()` sends `type: "text"` messages — only valid within Meta's **24-hour customer service window** after the last user message. Never used for business-initiated notifications.

---

## 7. Template Architecture and Versioning

### Template Structure

Each template defines the content for a specific `(event_type, channel)` pair:

```
NotificationTemplate
├── id: UUID (PK)
├── name: Text (unique)          — e.g. "order_created_email"
├── channel: Text                — "email" or "whatsapp"
├── event_type: Text             — e.g. "order_created"
├── subject: Text (nullable)     — email subject (Jinja2)
├── template_body: Text          — body content (Jinja2)
├── variables: JSONB (nullable)  — WhatsApp param mapping
├── is_active: Boolean           — must be True to dispatch
├── version: Integer             — bumped on every content edit
├── created_at / updated_at
```

### Jinja2 Variables

Templates use Jinja2 syntax. Available variables depend on the event type. Example:

```html
<!-- order_created email -->
Subject: Your order #{{ order_number }} is confirmed
Body: Hi {{ full_name }}, your order for {{ total }} has been placed.
```

### WhatsApp Template Variables

The `variables` JSONB field maps template parameters to the Meta-approved template:

```json
{
  "whatsapp_template": "order_created",
  "whatsapp_lang": "en_US",
  "params": ["order_number", "total"]
}
```

- `whatsapp_template`: The template name registered with Meta
- `whatsapp_lang`: Language code (e.g. `en_US`)
- `params`: Array of variable names — values are extracted from the rendering context

### Versioning

- Every content edit (subject, template_body, variables) triggers an automatic version snapshot
- The `version` counter on the template is incremented
- Old content is stored in `notification_template_versions`
- Each `NotificationLog` pins the exact `template_id` + `template_version` that produced it
- Admin can restore any previous version via `POST /admin/templates/{id}/versions/{version}/restore`

### Template Duplication

Templates can be duplicated as inactive copies (name: `_copy_{hex}`) for safe editing.

---

## 8. Notification Matrix Configuration

The Notification Matrix is the central control panel for which notifications are sent, on which channels, and with what behavior.

### NotificationRule Structure

```
NotificationRule
├── event_type: Text (unique)    — e.g. "order_created"
├── display_name: Text           — human-readable name
├── category: Text               — grouping category
├── description: Text            — what this notification does
├── enabled: Boolean             — master switch (False = no sends for this event)
├── email_enabled: Boolean       — email channel toggle
├── whatsapp_enabled: Boolean    — whatsapp channel toggle
├── priority: Text               — "normal" / "high" / "low"
├── retry_policy: JSONB          — custom retry configuration
├── cooldown_seconds: Integer    — min seconds between sends to same recipient
├── customer_visible: Boolean    — shown in customer notification center
├── admin_visible: Boolean       — shown in admin logs
├── is_system: Boolean           — prevents deletion of core rules
├── display_order: Integer       — sort order in admin UI
├── last_triggered_at            — transient, computed from logs
├── last_sent_at                 — transient, computed from logs
```

### Dispatch Gate Logic

Before any notification is sent, three gates are checked in order:

```
1. Global provider gate:  _provider_enabled(db, "email") / _provider_enabled(db, "whatsapp")
   └─ If disabled → skip silently

2. NotificationRule gate: repo.should_send(db, event_type, channel)
   └─ Rule must exist AND enabled=True AND channel_enabled=True
   └─ If missing or disabled → skip silently

3. User preference gate:  repo.get_preferences_for_channel(db, user_id, channel)
   └─ If user disabled this channel → skip silently
```

### Default Rules (seeded)

| Event Type | Email | WhatsApp | Category |
|---|---|---|---|
| `user_registered` | On | Off | onboarding |
| `order_created` | On | On | orders |
| `payment_captured` | On | On | payments |
| `payment_failed` | On | On | payments |
| `order_shipped` | On | On | orders |
| `order_delivered` | On | On | orders |
| `refund_created` | On | On | refunds |
| `refund_processed` | On | On | refunds |
| `refund_failed_admin_alert` | On | Off | alerts |
| `review_request` | On | On | engagement |

---

## 9. Admin Module Overview

### Route Structure

| Route | Page |
|---|---|
| `/admin/notifications` | Dashboard with KPI cards and recent activity |
| `/admin/notifications/analytics` | Charts: delivery rates, top templates, provider health |
| `/admin/notifications/logs` | Searchable, filterable log table with detail drawer |
| `/admin/notifications/matrix` | Matrix editor — toggle rules per channel |
| `/admin/notifications/providers` | Provider settings (Resend + WhatsApp config) |
| `/admin/notifications/templates` | Template list grouped by event_type |
| `/admin/notifications/templates/:id` | Template editor with version history |

### Frontend Components

| Component | Purpose |
|---|---|
| `AnalyticsCharts.tsx` | Charts for delivery rate, provider success, daily totals |
| `EmailProviderSettings.tsx` | Resend API key, from address, reply-to configuration |
| `WhatsAppProviderSettings.tsx` | Meta Cloud API token, phone number ID, business account |
| `NotificationLogsTable.tsx` | Paginated logs with status/channel/event_type/provider filters |
| `NotificationDetailDrawer.tsx` | Slide-out showing full log details, rendered content, lifecycle timestamps |
| `NotificationMatrixTable.tsx` | Matrix grid — rules × channels with toggle switches |
| `TemplateEditor.tsx` | Jinja2 template editor with variable preview |
| `TemplateVersionHistory.tsx` | Version timeline with restore capability |
| `NotificationsNav.tsx` | Tab navigation between notification admin pages |

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/notifications/preferences` | Get current user's notification preferences |
| `PUT` | `/notifications/preferences` | Update current user's preferences |
| `GET` | `/notifications/admin/logs` | List logs with filters |
| `POST` | `/notifications/admin/logs/retry` | Retry specific logs by ID (bulk) |
| `POST` | `/notifications/admin/retry` | Retry all pending-retry logs |
| `GET` | `/notifications/admin/analytics` | Analytics data (configurable time window) |
| `GET` | `/notifications/admin/rules` | List all notification rules |
| `PUT` | `/notifications/admin/rules/{event_type}` | Upsert a notification rule |
| `GET` | `/notifications/admin/templates` | List all templates |
| `PUT` | `/notifications/admin/templates/{id}` | Update template (auto-snapshots version) |
| `GET` | `/notifications/admin/templates/{id}/versions` | List template version history |
| `POST` | `/notifications/admin/templates/{id}/versions/{v}/restore` | Restore a template version |
| `POST` | `/notifications/admin/templates/{id}/duplicate` | Duplicate template as inactive copy |

### Provider Test Endpoints

Located in the settings module:

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/settings/notification-providers/email/test` | Send test email |
| `POST` | `/admin/settings/notification-providers/whatsapp/test` | Send test WhatsApp template |

---

## 10. WhatsApp Webhook Setup

### Meta Cloud API Configuration

1. Go to [Meta Developer Dashboard](https://developers.facebook.com) → Your App → WhatsApp → Configuration
2. Set **Webhook URL** to: `https://{your-domain}/api/v1/notifications/webhooks/whatsapp`
3. Set **Verify Token** to your `WHATSAPP_VERIFY_TOKEN` env var
4. Subscribe to events: `messages`, `message_status`

### Webhook Verification (GET)

Meta sends a GET request with `hub.mode`, `hub.verify_token`, `hub.challenge`. The endpoint verifies the token matches `WHATSAPP_VERIFY_TOKEN` and responds with the challenge.

### Webhook Events (POST)

- **`message_status`**: Updates delivery/read status on `NotificationLog`
  - `sent` → `mark_sent` (already set, but ensures consistency)
  - `delivered` → `mark_delivered` (sets `delivered_at`)
  - `read` → `mark_read` (sets `read_at`)
- **Signature validation**: If `WHATSAPP_WEBHOOK_SECRET` is set, the `X-Hub-Signature-256` header is validated using HMAC-SHA256

### Environment Variables for Webhook

| Variable | Purpose |
|---|---|
| `WHATSAPP_VERIFY_TOKEN` | Token Meta uses to verify the webhook endpoint |
| `WHATSAPP_WEBHOOK_SECRET` | Secret for HMAC-SHA256 signature validation |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | Your Meta Business Account ID |

---

## 11. Production Deployment Checklist

### Environment Variables

```bash
# Required — Email
RESEND_API_KEY=re_xxxxxxxxxxxxx
EMAIL_FROM=noreply@hadha.co
EMAIL_FROM_NAME=Hadha.co
EMAIL_REPLY_TO=support@hadha.co
ADMIN_ALERT_EMAIL=admin@hadha.co

# Required — WhatsApp (if enabled)
WHATSAPP_ENABLED=true
WHATSAPP_ACCESS_TOKEN=your_meta_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id
WHATSAPP_API_VERSION=v21.0

# Optional — WhatsApp Webhook
WHATSAPP_VERIFY_TOKEN=your_verify_token
WHATSAPP_WEBHOOK_SECRET=your_webhook_secret

# Required — Application
FRONTEND_URL=https://hadha.co
```

### Pre-deployment Steps

1. **Run Alembic migrations:** `alembic upgrade head`
   - Ensures all notification tables exist (templates, rules, logs, preferences, versions)
   - Seeds default templates and rules (ON CONFLICT DO NOTHING — safe on repeated runs)

2. **Configure Resend:**
   - Verify DNS records: SPF, DKIM, DMARC for your sending domain
   - Verify the sending domain in Resend dashboard
   - Test with `POST /admin/settings/notification-providers/email/test`

3. **Configure WhatsApp (if enabled):**
   - Register templates with Meta (must be approved before sending)
   - Set up webhook in Meta Developer Dashboard
   - Test with `POST /admin/settings/notification-providers/whatsapp/test`

4. **Review Notification Matrix:**
   - Verify all event types have corresponding rules
   - Enable/disable channels as needed per business requirements
   - Set appropriate cooldown periods for high-frequency events

5. **Verify retry worker is running:**
   - The APScheduler job must be registered at application startup
   - Check logs for `notification_retry` worker activity

### Post-deployment Verification

1. Send a test email via the admin UI
2. Send a test WhatsApp template via the admin UI
3. Trigger a real event (e.g. create a test order) and verify:
   - Log appears in `/admin/notifications/logs`
   - Status transitions: `pending` → `sent` → `delivered`
   - Email received by recipient
   - WhatsApp message received by recipient
4. Check `/admin/notifications/analytics` for data
5. Verify webhook delivery status updates appear in logs

---

## 12. Troubleshooting Guide

### Email Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| Emails not sending | Resend API key invalid or missing | Check `RESEND_API_KEY` env var or DB provider config. Test with `/admin/settings/notification-providers/email/test` |
| `ResendAuthError` (401) | API key expired or revoked | Generate new API key in Resend dashboard, update env/DB |
| `ResendDomainError` (403) | Sending domain not verified | Verify DNS records (SPF, DKIM, DMARC) and domain in Resend dashboard |
| Emails going to spam | Missing/incorrect DNS records | Ensure SPF, DKIM, DMARC are correctly configured |
| Template variables empty | Jinja2 rendering with wrong context | Check the event type matches the template's `event_type`. Verify the context dict passed in `service.py` dispatch method |

### WhatsApp Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| WhatsApp not sending | `WHATSAPP_ENABLED=False` | Set `WHATSAPP_ENABLED=true` in env |
| `WhatsAppAuthError` (401/403) | Access token expired or invalid | Generate new token in Meta Business Dashboard, update env/DB |
| Template rejected by Meta | Template not approved or parameters wrong | Check Meta Business Dashboard for template approval status. Verify `whatsapp_template` name and `params` in template `variables` |
| Phone number not receiving | Number not on WhatsApp or format wrong | Ensure number includes country code, no spaces/dashes/`+` prefix |
| Delivery status not updating | Webhook not configured or failing | Verify webhook URL in Meta Dashboard. Check `WHATSAPP_WEBHOOK_SECRET` matches. Review webhook logs |

### Retry Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| Retries not happening | Retry worker not running | Ensure APScheduler is configured and the notification_retry job is registered |
| Retries sending empty content | Legacy log without stored content | Logs created before the rendered_content/whatsapp_params fields will retry with empty context. This is expected for legacy logs. |
| `retrying` status stuck | `next_retry_at` in the future | Check the timestamp. Retry will fire when `next_retry_at <= NOW()` |

### General Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| Notifications not firing at all | NotificationRule disabled or missing | Check `/admin/notifications/matrix` — rule must be enabled with channel toggles on |
| Notifications firing for some users but not others | User preference disabled | User has opted out via `/admin/notifications/preferences` or customer-facing preference center |
| Provider config not taking effect | DB config overrides env | Check `notification_provider_settings` table. DB values take precedence over env vars. Use the admin UI to update. |
| High latency on event dispatch | Jinja2 rendering slow or provider timeout | Check provider API response times. Rendering is synchronous in the request path — consider async preprocessing for complex templates |
| `template_id` / `template_version` is `NULL` on logs | Log created before migration 0044 | Expected for legacy logs. New logs always pin the template version |

### Log Status Quick Reference

| Status | Meaning | Action |
|---|---|---|
| `pending` | Created, awaiting provider send | Check provider config and logs |
| `sent` | Provider accepted, awaiting delivery | Normal — waiting for webhook confirmation |
| `retrying` | Failed, scheduled for retry | Check `next_retry_at` timestamp |
| `failed` | All retries exhausted or permanent error | Check `error_message` field |
| `delivered` | Provider confirmed delivery | Success |
| `read` | Recipient read the message | Success (WhatsApp only) |

### Useful Queries

```sql
-- Find all failed notifications in the last 24 hours
SELECT * FROM notification_logs
WHERE status = 'failed'
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;

-- Count notifications by status
SELECT status, COUNT(*) FROM notification_logs
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY status;

-- Find notifications with auth errors (need credential rotation)
SELECT * FROM notification_logs
WHERE error_message ILIKE '%auth%'
  OR error_message ILIKE '%401%'
  OR error_message ILIKE '%403%'
ORDER BY created_at DESC LIMIT 20;

-- Check template usage
SELECT t.name, t.event_type, t.channel, COUNT(l.id) as send_count
FROM notification_templates t
LEFT JOIN notification_logs l ON l.template_id = t.id
GROUP BY t.id, t.name, t.event_type, t.channel
ORDER BY send_count DESC;
```

---

## 13. Email Design System & Premium Templates

> Added 2026-07-15; rebuilt 2026-07-16 on the **storefront's exact visual
> identity** (no invented tokens), then simplified 2026-07-16 to a
> **luxury-minimal** design (Apple/Tiffany-adjacent — one primary CTA, no
> footer navigation), then given a **final production audit** 2026-07-16.
> Pre-upgrade audit: [AUDIT.md](AUDIT.md). Trigger verification:
> [INTEGRATION_MATRIX.md](INTEGRATION_MATRIX.md). URL verification:
> [URL_AUDIT.md](URL_AUDIT.md). **Final sign-off, read this one first:**
> [PRODUCTION_READINESS_REPORT.md](PRODUCTION_READINESS_REPORT.md).

### Storefront identity mapping (extracted, not invented)

| Email element | Storefront source |
|---|---|
| Palette (navy `#21334f`, gold `#c99846`, cream `#faf6f1`, slate `#1f2733`, silver, destructive `#be2323`) | `packages/shared-ui/src/globals.css` `:root` oklch tokens → hex; `.dark` tokens drive email dark mode |
| Typography (Cinzel display/CTAs, Cormorant Garamond decorative, Inter body) | `--font-serif-display` / `--font-serif-body` / `--font-sans` |
| Sharp corners everywhere | `--radius: 0rem` |
| CTA letterforms (Cinzel 11px uppercase, tracking 0.24em) + gradients | ProductCard "Add to cart" bar; `--gradient-luxury` / `--gradient-gold` |
| Header — wordmark/logo only, hairline rule beneath. No motto, no nav links. | `storefront/src/components/site/Header.tsx` (simplified further per luxury-minimal brief) |
| Footer — brand mark, short italic description, email/phone/website, plain gold social wordmarks (no boxes), "Need help? Contact Support · Track Order", Privacy · Terms, copyright. **No Shopping/Company link columns** — removed entirely (was CMS-driven; that machinery was deleted). | `storefront/src/components/site/Footer.tsx`, simplified to the luxury-minimal keep-list |
| Primary CTA — one full-width button per email (`cta_block()`); order emails lead with **Track Your Order**, with a quiet underlined secondary link (e.g. View Order) beneath, never a second competing button. | ProductCard CTA language, reduced to single-intent |
| Product cards — real product image (`OrderItem.image_url`, 80×80), name, variant/SKU/qty, price, "View Product →". Monogram is a last-resort fallback only. | ProductCard image treatment |
| Brand facts (names, motto, address, socials) | `packages/shared-utils/src/config/brand.ts` |
| Prices `Rs. 1,299.00` (en-IN grouping) | `formatINR` in `packages/shared-utils` |

### Single source of truth

Default template content is **generated in Python** and seeded into
`notification_templates` by migration `0051_premium_notification_templates`:

| Module | Responsibility |
|---|---|
| `app/modules/notifications/emails/components.py` | Design system: brand tokens + reusable components (header, footer, hero, buttons, product cards, order summary, addresses, 5-step timeline, notes). Emits email-client-safe HTML fragments containing Jinja placeholders. |
| `app/modules/notifications/emails/catalog.py` | Composes components into the 17 default email templates + 10 WhatsApp templates. |
| `app/modules/notifications/branding.py` | `get_brand_context()` / `get_brand_context_db()` — brand identity + every deep link (derived from `FRONTEND_URL`), **overlaid at send time by the CMS `footer` section config** (the same row the storefront footer renders from: logo, address, phone, email, socials, copyright name). Injected into every render; event context overrides it. |
| `app/modules/notifications/welcome.py` | Welcome-email bridge — publishes `UserRegisteredEvent` on the first authenticated `GET /me` after signup (Supabase handles signup client-side, so no backend hook existed). Idempotent via Redis SETNX + notification-log check. |
| `app/modules/notifications/context.py` | `build_order_context()` / `load_order_context()` — items (with product links + image fallbacks), addresses, ₹-formatted pricing breakdown, payment/tracking facts, timeline stage. |

DB template bodies stay **standalone HTML documents** (no `{% extends %}`) because
the admin Template Editor previews them client-side. Reuse happens at authoring
time in the Python builder; a change to the design system means regenerating and
re-seeding via a new migration (snapshotting old versions).

### Email engineering

600px hybrid table layout, inline CSS, MSO conditionals for Outlook, hidden
preheader, bulletproof table buttons, mobile breakpoints (`.stack`, `.px`), and
dark-mode support (`prefers-color-scheme` + `dm-*` utility classes). Product
images fall back to a styled monogram cell when `image_url` is empty.

### New brand settings (all optional, env-overridable)

`BRAND_NAME`, `BRAND_TAGLINE`, `BRAND_LOGO_URL`, `BRAND_ADDRESS`,
`SUPPORT_EMAIL`, `SUPPORT_PHONE`, `SOCIAL_INSTAGRAM_URL`, `SOCIAL_FACEBOOK_URL`,
`SOCIAL_YOUTUBE_URL`.

### New order-lifecycle events

`order_confirmed`, `order_processing`, `order_packed`,
`order_return_requested`, `order_returned` — fired by the existing
`OrderStatusChangedEvent` publisher; rules are auto-created at startup by
`sync_notification_rules()` (WhatsApp defaults ON only for `order_packed`).

### Rendering hardening

- Templates render in `jinja2.sandbox.SandboxedEnvironment` (SSTI defense).
- Subjects and WhatsApp bodies render **without** autoescape (plain text) —
  HTML entities no longer leak into subjects.
- Brand context is also merged into legacy-log retry re-renders.

### ⚠️ WhatsApp: Meta template re-registration required

The upgraded WhatsApp templates use new parameter lists (e.g. `order_created`
is now `customer_name, order_number, total, order_url`). Each template must be
re-registered/approved in Meta Business Manager with matching placeholder
counts before enabling the channel. `order_packed` is a brand-new Meta template.

### Previews

```bash
cd Backend
hadha/Scripts/python.exe scripts/render_email_previews.py
```

Writes every rendered template plus an interactive `gallery.html` (grouped
sidebar, desktop/mobile toggle, WhatsApp bubbles) to
`Backend/scripts/email_previews/` (gitignored). A `.claude/launch.json` entry
(`email-previews`, port 8765) serves it.

---

## File Reference

### Backend

```
app/modules/notifications/
├── __init__.py
├── models.py              — 5 SQLAlchemy models (Template, TemplateVersion, Log, Preference, Rule)
├── schemas.py             — 11 Pydantic schemas for API validation
├── service.py             — Core business logic, event listeners, retry orchestration
├── repository.py          — All DB operations (666 lines)
├── router.py              — FastAPI routes (385 lines)
├── dispatcher.py          — Thin adapter to providers
├── branding.py            — Brand context injected into every render
├── context.py             — Rich order context builders (items, addresses, pricing, timeline)
├── emails/
│   ├── components.py      — Email design system (reusable HTML components)
│   └── catalog.py         — Default template catalog (17 email + 10 WhatsApp)
└── providers/
    ├── base.py            — Abstract base classes for Email/WhatsApp
    ├── registry.py        — Provider registry (singleton pattern)
    ├── resend.py          — Resend email provider
    └── whatsapp.py        — Meta WhatsApp Cloud API provider

app/workers/
└── notification_retry.py  — APScheduler retry worker

app/core/
├── events.py              — 11 domain event dataclasses + EventBus
└── config.py              — All env var definitions
```

### Alembic Migrations

```
alembic/versions/
├── 0042_unified_notifications.py       — Core tables, default templates/rules
├── 0043_notification_provider_settings.py — Provider config table
├── 0044_notification_registry_refinements.py — Lifecycle timestamps, template versioning
├── 0045_notification_log_whatsapp_params.py — whatsapp_params JSONB for deterministic retries
├── 0051_premium_notification_templates.py — Premium design-system templates (snapshots old versions)
├── 0052_delivered_review_cta_templates.py — Post-delivery review CTA panel
└── 0053_final_audit_cta_and_status_templates.py — CTA wording fixes + 3 new order-status templates
```

### Frontend

```
admin/src/
├── routes/
│   ├── admin.notifications.tsx
│   ├── admin.notifications.index.tsx
│   ├── admin.notifications.analytics.tsx
│   ├── admin.notifications.logs.tsx
│   ├── admin.notifications.matrix.tsx
│   ├── admin.notifications.providers.tsx
│   ├── admin.notifications.templates.tsx
│   ├── admin.notifications.templates.index.tsx
│   └── admin.notifications.templates.$templateId.tsx
└── components/admin/notifications/
    ├── AnalyticsCharts.tsx
    ├── EmailProviderSettings.tsx
    ├── NotificationDetailDrawer.tsx
    ├── NotificationLogsTable.tsx
    ├── NotificationMatrixTable.tsx
    ├── NotificationsNav.tsx
    ├── TemplateEditor.tsx
    ├── TemplateVersionHistory.tsx
    └── WhatsAppProviderSettings.tsx

packages/shared-types/src/
└── notifications.ts        — TypeScript interfaces for all notification types
```
