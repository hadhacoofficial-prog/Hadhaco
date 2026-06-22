# HADHA.CO — MASTER PRODUCTION ARCHITECTURE SPECIFICATION
> Version 1.0 | Silver Jewellery Ecommerce Platform | Production Grade

# HADHA.CO — MASTER ARCHITECTURE SPECIFICATION INDEX

> Production-Grade Silver Jewellery Ecommerce Backend  
> Generated: June 2026 | Status: Complete

---

## Document Map

| File | Contents | Parts |
|------|----------|-------|
| [MASTER_ARCHITECTURE.md](../MASTER_ARCHITECTURE.md) | Part 1 — Foundation | Critical Instructions, Tech Stack, Architecture, Project Structure, Supabase Strategy, Auth, Profiles, RBAC, Notifications, Environment Config | (PART2_CUSTOMER_MODULES.md) | Part 2 — Customer-Facing | Catalog, Categories, Collections, SEO, Search, Wishlist, Addresses, Media/CDN, Inventory, Advanced Inventory, Jewelry Requirements, Cart | (PART3_TRANSACTION_MODULES.md) | Part 3 — Transactions | Orders, Payments (Razorpay), Invoices, Shipping (Delivery One), Webhook Framework, Reviews, Coupons, Returns, Tax | (PART4_PLATFORM_MODULES.md) | Part 4 — Platform | CMS, Analytics, Customer Support, Admin, Security, Fraud Prevention, Audit Logs |(PART5_INFRASTRUCTURE.md) | Part 5 — Infrastructure | Database Architecture, SQL Structure, Supabase Setup, Views, Indexes, Triggers, RLS Policies, Performance, Monitoring, Deployment, Backup, Feature Flags, Business Rules, Seed Data, Implementation Order |

---

## Quick Reference

### Database Tables (complete list)
`profiles` · `admin_2fa` · `admin_sessions` · `products` · `categories` · `collections` · `product_collections` · `product_variants` · `product_attributes` · `product_images` · `inventory` · `inventory_movements` · `inventory_reservations` · `wishlists` · `wishlist_items` · `addresses` · `carts` · `cart_items` · `orders` · `order_items` · `order_status_history` · `payments` · `payment_events` · `refunds` · `invoices` · `shipments` · `shipment_events` · `reviews` · `review_images` · `review_votes` · `coupons` · `coupon_usage` · `returns` · `return_items` · `app_settings` · `notification_templates` · `notification_logs` · `notification_preferences` · `analytics_events` · `audit_logs` · `seo_pages` · `seo_redirects` · `seo_404_log` · `search_history` · `webhook_events` · `fraud_signals` · `support_tickets` · `support_messages` · `cms_pages` · `banners` · `landing_sections` · `feature_flags`

**Total: 50 tables**

### Views (complete list)
`product_listing_view` · `product_details_view` · `inventory_summary_view` · `customer_orders_view` · `admin_order_dashboard_view` · `review_summary_view` · `sales_dashboard_view` *(materialized)* · `top_products_view` *(materialized)* · `trending_searches` *(materialized)*

### Implementation Phases
1. Database Foundation (Auth, Profiles, RBAC)
2. Catalog (Products, Categories, Collections, Media, SEO)
3. Inventory
4. Customer Context (Addresses, Wishlist, Search)
5. Cart
6. Orders + Tax + Coupons
7. Payments (Razorpay) + Invoices + Webhook Framework
8. Shipping (Delivery One)
9. Reviews
10. Notifications
11. CMS + SEO
12. Analytics + Returns + Support
13. Security + Fraud + Audit
14. Database Finalization (Views, Indexes, RLS, Triggers, Seed)
15. Infrastructure (Docker, Nginx, CI/CD)
16. Admin Dashboard API
17. Testing

### Tech Stack Summary
- **Backend:** FastAPI 0.110 · Python 3.12 · SQLAlchemy 2 Async · Alembic · Pydantic V2
- **Database:** Supabase PostgreSQL · Redis
- **Auth:** Supabase Auth (JWT) · TOTP 2FA for admins
- **Storage:** Cloudflare R2 + CDN
- **Payments:** Razorpay
- **Shipping:** Delivery One
- **Email:** Resend (primary) · SendGrid (fallback)
- **SMS:** Twilio
- **Monitoring:** Sentry · Prometheus · BetterStack
- **Deploy:** Docker · Nginx · GitHub Actions


---

# PART 1 — FOUNDATION

---

## 1.1 CRITICAL INSTRUCTIONS

These instructions govern every file, every module, and every line of code generated for this project. No exceptions.

- Do NOT skip any module.
- Do NOT generate placeholder implementations.
- Do NOT generate TODO comments.
- Do NOT generate stub functions.
- Do NOT simplify schema for brevity.
- Do NOT omit SQL DDL.
- Do NOT omit Alembic migrations.
- Do NOT omit Supabase RLS policies.
- Do NOT omit indexes.
- Do NOT omit database views.
- Do NOT omit triggers.
- Do NOT omit constraints.
- Do NOT omit foreign keys.
- Do NOT omit soft delete fields.
- Do NOT omit audit fields.
- Do NOT omit error handling.
- Do NOT omit input validation.
- Do NOT omit authorization checks.
- Do NOT trust any value from the frontend for price, tax, discount, or shipping.
- Do NOT implement custom JWT issuance — Supabase Auth is the sole JWT authority.
- Do NOT implement custom password hashing.
- Do NOT implement custom session storage.
- Do NOT implement custom refresh token storage.
- Every API must include request schema, response schema, validation, error handling, authorization, and audit logging.
- Every generated file must be immediately deployable to production.
- All business logic must be testable with unit and integration tests.
- Application must refuse to start if any required environment variable is missing.

---

## 1.2 TECH STACK

### Backend
| Component | Technology |
|-----------|-----------|
| Framework | FastAPI (Python 3.12) |
| ORM | SQLAlchemy 2.0 Async |
| Migrations | Alembic |
| Validation | Pydantic V2 |
| Database | PostgreSQL via Supabase |
| Auth | Supabase Auth (JWT) |
| Cache | Redis (upstash or self-hosted) |
| Background Jobs | APScheduler (abstracted behind QueueService interface) |
| Storage | Cloudflare R2 |
| CDN | Cloudflare CDN |
| Payments | Razorpay |
| Shipping | Delivery One |
| Email (Primary) | Resend |
| Email (Fallback) | Twilio SendGrid |
| SMS | Twilio SMS |
| Logging | Structured JSON via structlog |
| Monitoring | Sentry + Prometheus metrics |
| Uptime | BetterStack |
| Server | Nginx (reverse proxy) |
| Containerization | Docker + docker-compose |

### Frontend
| Component | Technology |
|-----------|-----------|
| Framework | React (Vite + TypeScript) |
| Router | TanStack Router |
| Data Fetching | TanStack Query |
| Auth Client | supabase-js |

### Database
| Component | Technology |
|-----------|-----------|
| Primary DB | Supabase PostgreSQL (managed) |
| Extensions | pgcrypto, uuid-ossp, pg_trgm, unaccent, btree_gin |

---

## 1.3 ARCHITECTURE PRINCIPLES

### Layered Architecture (Clean Architecture + DDD)

```
HTTP Layer (FastAPI Routers)
      ↓
Service Layer (Business Logic)
      ↓
Repository Layer (Database Access via SQLAlchemy)
      ↓
Database (Supabase PostgreSQL)
```

### Rules
- **Routers** are thin. They validate input, call the service, return the response. No business logic.
- **Services** own all business logic. They orchestrate repositories, external services, and events. They never import SQLAlchemy models directly for query building — that belongs in repositories.
- **Repositories** own all database queries. They accept domain objects and return domain objects. Raw SQL is allowed only for complex aggregations.
- **Events** decouple modules. Services publish events; listeners react. No service calls another service's internal methods directly across module boundaries.
- **External Services** (Razorpay, Delivery One, Resend, Twilio, R2) are always accessed through abstraction interfaces — never imported directly in business logic.

### Event-Driven Workflow
```
Business Action (e.g., payment confirmed)
        ↓
Internal Event Published (e.g., PaymentCaptured)
        ↓
Event Bus dispatches to registered listeners
        ↓
Notification Service → sends email + SMS
Inventory Service → confirms reservation
Order Service → advances order state
Audit Service → logs the action
```

### Idempotency Contract
All webhook handlers, payment processors, order creation flows, and shipment status updates MUST be idempotent. Duplicate delivery of any event must produce no side effect beyond the first successful processing.

---

## 1.4 PROJECT STRUCTURE

```
hadha-backend/
├── app/
│   ├── main.py                          # FastAPI app factory, middleware registration, router mounting
│   ├── core/
│   │   ├── config.py                    # Pydantic Settings — typed env vars, startup validation
│   │   ├── security.py                  # Supabase JWT verification, RBAC dependencies
│   │   ├── database.py                  # Async SQLAlchemy engine, session factory
│   │   ├── redis.py                     # Redis client factory
│   │   ├── logging.py                   # structlog configuration, JSON formatter
│   │   ├── exceptions.py                # Custom exception hierarchy, global exception handlers
│   │   ├── dependencies.py              # Shared FastAPI dependencies (get_db, get_current_user, etc.)
│   │   ├── events.py                    # Internal event bus (publish/subscribe)
│   │   └── constants.py                 # Enums, status codes, role names
│   │
│   ├── modules/
│   │   ├── auth/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   └── dependencies.py
│   │   │
│   │   ├── profiles/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── catalog/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── categories/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── collections/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── seo/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── search/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── media/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── inventory/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── wishlist/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── addresses/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── cart/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── orders/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── payments/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── invoices/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── shipping/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── reviews/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── coupons/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── returns/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── tax/
│   │   │   ├── service.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── cms/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── analytics/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── support/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── admin/
│   │   │   ├── router.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── notifications/
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── providers/
│   │   │   │   ├── base.py           # NotificationProvider ABC
│   │   │   │   ├── resend.py         # Primary email
│   │   │   │   ├── sendgrid.py       # Fallback email
│   │   │   │   └── twilio_sms.py     # SMS
│   │   │   └── templates/
│   │   │       ├── welcome.html
│   │   │       ├── order_confirmation.html
│   │   │       ├── order_shipped.html
│   │   │       ├── order_delivered.html
│   │   │       ├── refund_confirmation.html
│   │   │       └── review_request.html
│   │   │
│   │   ├── webhooks/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── audit/
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── fraud/
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   └── models.py
│   │   │
│   │   └── settings/
│   │       ├── router.py
│   │       ├── service.py
│   │       ├── repository.py
│   │       ├── models.py
│   │       └── schemas.py
│   │
│   ├── workers/
│   │   ├── queue.py                     # QueueService interface + APScheduler implementation
│   │   ├── shipment_sync.py             # Poll Delivery One, update shipment status
│   │   ├── review_reminder.py           # Send review request emails post-delivery
│   │   ├── abandoned_cart.py            # Detect and notify abandoned carts
│   │   ├── inventory_alerts.py          # Check low stock thresholds, fire alerts
│   │   └── notification_retry.py        # Retry failed notifications (1m, 5m, 15m)
│   │
│   ├── middleware/
│   │   ├── rate_limit.py                # Redis-backed sliding window rate limiter
│   │   ├── request_id.py                # Inject X-Request-ID header
│   │   ├── security_headers.py          # HSTS, X-Frame-Options, CSP
│   │   └── audit_middleware.py          # Log every admin action automatically
│   │
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       └── integration/
│
├── supabase/
│   └── sql/
│       ├── 000_extensions.sql
│       ├── 001_profiles.sql
│       ├── 002_catalog.sql
│       ├── 003_inventory.sql
│       ├── 004_cart.sql
│       ├── 005_orders.sql
│       ├── 006_payments.sql
│       ├── 007_shipping.sql
│       ├── 008_reviews.sql
│       ├── 009_coupons.sql
│       ├── 010_cms.sql
│       ├── 011_analytics.sql
│       ├── 012_notifications.sql
│       ├── 013_audit_logs.sql
│       ├── 014_seo.sql
│       ├── 015_webhooks.sql
│       ├── 016_fraud.sql
│       ├── 017_support.sql
│       ├── 018_feature_flags.sql
│       ├── 019_views.sql
│       ├── 020_indexes.sql
│       ├── 021_rls.sql
│       ├── 022_triggers.sql
│       └── 023_seed_data.sql
│       └── setup.sql                    # Master script — sources all above in order
│
├── alembic/
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
│
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── docker-compose.staging.yml
│   └── nginx/
│       ├── nginx.conf
│       └── ssl/
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
│
├── .env.example
├── .env.staging.example
├── .env.production.example
├── pyproject.toml
└── requirements.txt
```

---

## 1.5 SUPABASE STRATEGY

### Philosophy
Supabase is the database host AND the authentication provider. The entire schema is managed as versioned SQL files — never through the Supabase dashboard UI. Running `setup.sql` must create the complete database from scratch, including all tables, indexes, views, RLS policies, triggers, and seed data.

### Database Access Pattern
- FastAPI connects to Supabase PostgreSQL via the **direct connection string** (port 5432) using SQLAlchemy async.
- The **service role key** is used server-side for all backend operations that bypass RLS (e.g., admin service layer).
- The **anon key** is used only in the frontend via `supabase-js`.
- RLS policies enforce data isolation at the database level as a second layer of defense.

### SQL File Execution Order
```
000_extensions.sql      → pg extensions (uuid-ossp, pgcrypto, pg_trgm, unaccent)
001_profiles.sql        → profiles table, trigger for auto-creation from auth.users
002_catalog.sql         → products, categories, collections, variants, attributes, images
003_inventory.sql       → inventory, inventory_movements
004_cart.sql            → carts, cart_items
005_orders.sql          → orders, order_items, order_status_history
006_payments.sql        → payments, payment_events, refunds
007_shipping.sql        → shipments, shipment_events
008_reviews.sql         → reviews, review_images, review_votes
009_coupons.sql         → coupons, coupon_usage
010_cms.sql             → banners, landing_sections
011_analytics.sql       → analytics_events
012_notifications.sql   → notification_templates, notification_logs, notification_preferences
013_audit_logs.sql      → audit_logs
014_seo.sql             → seo_pages, seo_redirects
015_webhooks.sql        → webhook_events
016_fraud.sql           → fraud_signals
017_support.sql         → support_tickets, support_messages
018_feature_flags.sql   → feature_flags
019_views.sql           → all materialized and standard views
020_indexes.sql         → all performance indexes
021_rls.sql             → all RLS policies
022_triggers.sql        → all triggers and functions
023_seed_data.sql       → roles, admin user, categories, settings, CMS defaults
```

### Required Manual Supabase Dashboard Tasks
Only the following require manual dashboard configuration. Everything else is automated via SQL.

1. Enable Google OAuth provider — paste Google Client ID and Secret
2. Configure SMTP settings — use Resend SMTP credentials
3. Set Auth redirect URLs — `https://hadha.co/auth/callback`, `https://hadha.co/auth/reset-password`
4. Configure Resend domain for transactional email
5. Configure Razorpay webhook endpoint — `https://api.hadha.co/webhooks/razorpay`
6. Configure Delivery One webhook endpoint — `https://api.hadha.co/webhooks/delivery-one`
7. Enable `pg_cron` extension if periodic DB-level cleanup jobs are needed

---

## 1.6 AUTHENTICATION MODULE

### Provider
Supabase Auth is the exclusive authentication provider. FastAPI does NOT issue JWTs, does NOT hash passwords, does NOT store sessions, and does NOT store refresh tokens.

### Supported Authentication Methods
- Email + Password (with email verification gate)
- Magic Link (passwordless email login)
- Google OAuth (via Supabase OAuth flow)
- Password Reset (via Supabase)

### Authentication Flow
```
User submits credentials (browser/app)
        ↓
supabase-js calls Supabase Auth
        ↓
Supabase validates and issues JWT (access_token) + refresh_token
        ↓
Frontend stores tokens (memory or httpOnly cookie — NOT localStorage)
        ↓
API request: Authorization: Bearer <access_token>
        ↓
FastAPI middleware: verify JWT signature using SUPABASE_JWT_SECRET
        ↓
Extract sub (user UUID), email, role from JWT claims
        ↓
Fetch profile from profiles table
        ↓
Inject CurrentUser into request context
        ↓
RBAC dependency enforces role requirements
        ↓
Business logic executes
```

### JWT Verification (FastAPI)
```python
# app/core/security.py
import jwt
from app.core.config import settings

async def verify_supabase_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### CurrentUser Dependency
```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    payload = await verify_supabase_jwt(token)
    user_id = payload.get("sub")
    profile = await profile_repository.get_by_id(db, user_id)
    if not profile or not profile.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return profile
```

### RBAC Dependencies
```python
def require_role(*roles: str):
    async def dependency(current_user: Profile = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return dependency

require_customer   = require_role("customer", "admin", "super_admin")
require_admin      = require_role("admin", "super_admin")
require_super_admin = require_role("super_admin")
```

### Admin 2FA (TOTP)
- Admin and super_admin accounts MUST have TOTP 2FA enabled before accessing admin routes.
- On first admin login, if TOTP is not configured, API returns `403` with `{"code": "2FA_REQUIRED", "setup_url": "/admin/2fa/setup"}`.
- TOTP secret is stored in `admin_2fa` table (encrypted at rest using `pgcrypto`).
- Backup codes: 10 single-use codes generated at setup, stored hashed (bcrypt).

### Admin 2FA Table
```sql
CREATE TABLE admin_2fa (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
    totp_secret  TEXT NOT NULL,               -- encrypted via pgcrypto
    backup_codes JSONB NOT NULL DEFAULT '[]', -- array of bcrypt-hashed codes
    is_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    enabled_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Admin Session Tracking Table
```sql
CREATE TABLE admin_sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    ip_address   INET NOT NULL,
    user_agent   TEXT,
    device_hash  TEXT,
    location     JSONB,                        -- {country, city, region}
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_admin_sessions_user_id ON admin_sessions(user_id);
CREATE INDEX idx_admin_sessions_ip ON admin_sessions(ip_address);
```

### Auth APIs

#### POST /auth/verify-token
Validates a Supabase JWT and returns the profile. Used by frontend on app load.

**Request:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "role": "customer",
  "is_active": true,
  "avatar_url": "https://cdn.hadha.co/avatars/uuid.webp"
}
```

**Errors:** `401 Token expired`, `401 Invalid token`, `403 Account inactive`

#### POST /auth/admin/2fa/setup
Generates TOTP secret and QR code URI for admin setup.
**Auth:** `require_admin`

#### POST /auth/admin/2fa/verify
Verifies TOTP token and activates 2FA.
**Auth:** `require_admin`

#### POST /auth/admin/2fa/validate
Validates TOTP code on every admin login attempt.
**Auth:** `require_admin`

#### POST /auth/logout
Revokes Supabase session (calls Supabase sign-out API via service role).
**Auth:** `get_current_user`

#### POST /auth/force-logout/{user_id}
Forces session revocation for any user.
**Auth:** `require_super_admin`

---

## 1.7 PROFILES MODULE

### Responsibilities
- Maintain extended user profile data linked to `auth.users`.
- Serve as the authority for role, display name, avatar, and account status.
- Automatically created via database trigger on Supabase Auth signup.

### Profile Table
```sql
CREATE TABLE profiles (
    id           UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email        TEXT NOT NULL UNIQUE,
    full_name    TEXT,
    phone        TEXT,
    avatar_url   TEXT,
    role         TEXT NOT NULL DEFAULT 'customer'
                     CHECK (role IN ('customer', 'admin', 'super_admin')),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_profiles_email   ON profiles(email);
CREATE INDEX idx_profiles_role    ON profiles(role);
CREATE INDEX idx_profiles_active  ON profiles(is_active) WHERE is_active = TRUE;
```

### Auto-Creation Trigger
```sql
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, avatar_url, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        NEW.raw_user_meta_data->>'avatar_url',
        'customer'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();
```

### Profile APIs

#### GET /me
Returns current user's profile.
**Auth:** `get_current_user`

**Response:**
```json
{
  "id": "uuid",
  "email": "jane@example.com",
  "full_name": "Jane Doe",
  "phone": "+919876543210",
  "avatar_url": "https://cdn.hadha.co/avatars/uuid.webp",
  "role": "customer",
  "is_active": true,
  "is_verified": true,
  "created_at": "2026-01-01T00:00:00Z"
}
```

#### PATCH /me
Update full_name, phone.
**Auth:** `get_current_user`
**Validation:** phone must match E.164 format, full_name max 100 chars.

**Request:**
```json
{ "full_name": "Jane Smith", "phone": "+919876543210" }
```

#### PATCH /me/avatar
Upload new avatar image. Processes through image pipeline → stores in R2 → updates `avatar_url`.
**Auth:** `get_current_user`
**Validation:** file type (jpg/jpeg/png/webp), max size 5MB.

#### GET /admin/users
Paginated list of all users.
**Auth:** `require_admin`
**Query params:** `page`, `page_size`, `role`, `is_active`, `search` (email/name), `sort_by`, `sort_dir`

#### PATCH /admin/users/{id}/role
Change user role.
**Auth:** `require_super_admin`
**Audit:** logged to `audit_logs` with actor, old_role, new_role.

#### PATCH /admin/users/{id}/status
Activate or deactivate user.
**Auth:** `require_admin`
**Audit:** logged.

---

## 1.8 RBAC

### Role Hierarchy
```
super_admin  →  full access to everything
    ↓
admin        →  manage all business resources, no role elevation
    ↓
customer     →  own data only (orders, cart, reviews, addresses, wishlist)
```

### Permission Matrix
| Resource | customer | admin | super_admin |
|----------|----------|-------|-------------|
| Own profile | RW | RW | RW |
| Other profiles | — | R | RW |
| Products | R | RW | RW |
| Orders (own) | R | RW | RW |
| Orders (all) | — | RW | RW |
| Payments | — | R | RW |
| Refunds | — | RW | RW |
| Reviews (own) | RW | RW | RW |
| Reviews (all) | — | RW | RW |
| Coupons | — | RW | RW |
| Inventory | — | RW | RW |
| Shipping | — | RW | RW |
| CMS | — | RW | RW |
| Analytics | — | R | RW |
| User roles | — | — | RW |
| Settings | — | R | RW |
| Audit logs | — | R | RW |
| Feature flags | — | — | RW |

---

## 1.9 NOTIFICATION SYSTEM

### Architecture
Event-driven. Business modules publish domain events. The NotificationService subscribes to events and routes to the appropriate provider. Business modules NEVER call SendGrid, Resend, or Twilio directly.

```
Business Module
      ↓ publishes event (e.g., OrderCreated)
Event Bus (app/core/events.py)
      ↓ dispatches to subscribers
NotificationService.handle(event)
      ↓ loads template from DB
      ↓ checks user preferences
      ↓ calls provider
EmailProvider (Resend → SendGrid fallback)
SMSProvider (Twilio)
      ↓ logs result to notification_logs
```

### Notification Events and Channels
| Event | Email | SMS | Notes |
|-------|-------|-----|-------|
| UserRegistered | ✓ | — | Welcome email |
| EmailVerification | ✓ | — | Supabase handles |
| PasswordReset | ✓ | — | Supabase handles |
| OrderCreated | ✓ | ✓ | SMS only after payment confirmed |
| PaymentReceived | ✓ | — | Payment receipt email |
| OrderProcessing | ✓ | — | |
| OrderShipped | ✓ | — | With tracking link |
| OutForDelivery | ✓ | — | |
| OrderDelivered | ✓ | — | |
| RefundCreated | ✓ | — | |
| RefundProcessed | ✓ | — | |
| ReviewRequest | ✓ | — | Sent 48h after delivery |
| LowInventoryAlert | ✓ | — | Admin only |
| AdminAlert | ✓ | — | Admin only |

**SMS Business Rule:** SMS is ONLY sent for OrderCreated and ONLY AFTER payment status = PAID. Do not send SMS for registration, password reset, shipping, or marketing unless explicitly enabled by a feature flag.

### Database Tables

#### notification_templates
```sql
CREATE TABLE notification_templates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL UNIQUE,   -- e.g., 'order_created_email'
    channel       TEXT NOT NULL CHECK (channel IN ('email', 'sms', 'push')),
    event_type    TEXT NOT NULL,          -- e.g., 'order_created'
    subject       TEXT,                   -- email only
    template_body TEXT NOT NULL,          -- Jinja2 template
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### notification_logs
```sql
CREATE TABLE notification_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES profiles(id),
    channel             TEXT NOT NULL CHECK (channel IN ('email', 'sms', 'push')),
    event_type          TEXT NOT NULL,
    recipient           TEXT NOT NULL,    -- email address or phone number
    status              TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed', 'retrying')),
    provider            TEXT,             -- 'resend', 'sendgrid', 'twilio'
    provider_message_id TEXT,
    error_message       TEXT,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    next_retry_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_notification_logs_user_id   ON notification_logs(user_id);
CREATE INDEX idx_notification_logs_status    ON notification_logs(status);
CREATE INDEX idx_notification_logs_retry     ON notification_logs(next_retry_at) WHERE status = 'retrying';
```

#### notification_preferences
```sql
CREATE TABLE notification_preferences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
    email_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
    sms_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    order_updates   BOOLEAN NOT NULL DEFAULT TRUE,
    marketing       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Provider Interface (ABC)
```python
# app/modules/notifications/providers/base.py
from abc import ABC, abstractmethod

class NotificationProvider(ABC):
    @abstractmethod
    async def send_email(self, to: str, subject: str, html: str) -> str:
        """Returns provider message ID."""

    @abstractmethod
    async def send_sms(self, to: str, body: str) -> str:
        """Returns provider message ID."""
```

### Retry Strategy
Failed notifications enter `status = 'retrying'` with `next_retry_at` set:
- Attempt 1 failed → retry at +1 minute
- Attempt 2 failed → retry at +5 minutes
- Attempt 3 failed → retry at +15 minutes
- Attempt 4+ failed → `status = 'failed'`, no more retries, admin alerted.

Worker `notification_retry.py` runs every 30 seconds and processes all records where `status = 'retrying' AND next_retry_at <= NOW()`.

### HTML Email Templates
All templates are responsive HTML (mobile-first), stored in `app/modules/notifications/templates/`. Rendered with Jinja2. Variables injected from event payload.

Required templates:
- `welcome.html` — UserRegistered
- `order_confirmation.html` — OrderCreated
- `payment_receipt.html` — PaymentReceived
- `order_processing.html` — OrderProcessing
- `order_shipped.html` — OrderShipped (includes tracking link)
- `out_for_delivery.html` — OutForDelivery
- `order_delivered.html` — OrderDelivered
- `refund_created.html` — RefundCreated
- `refund_processed.html` — RefundProcessed
- `review_request.html` — ReviewRequest
- `admin_alert.html` — AdminAlert
- `low_stock_alert.html` — LowInventoryAlert

SMS Template (single, parameterized):
```
"Thank you for shopping with Hadha.co. Your order {{order_number}} has been confirmed. Track your order at https://hadha.co/orders/{{order_number}}"
```

---

## 1.10 ENVIRONMENT CONFIGURATION

### Configuration Architecture
- All settings are loaded from environment variables via Pydantic `BaseSettings`.
- Settings are grouped into logical sub-settings classes.
- On startup, `validate_settings()` is called. If any required variable is missing, the application raises `SystemExit` with a descriptive message listing all missing variables.
- No secret is ever hardcoded or committed to source control.

### .env.example (complete)
```dotenv
# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────
APP_NAME=Hadha.co
APP_ENV=development          # development | staging | production
APP_DEBUG=true
APP_VERSION=1.0.0

# ─────────────────────────────────────────────
# API
# ─────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=http://localhost:8000
API_V1_PREFIX=/api/v1

# ─────────────────────────────────────────────
# SECURITY
# ─────────────────────────────────────────────
SECRET_KEY=                   # 64-char random hex, used for CSRF tokens
ENCRYPTION_KEY=               # 32-byte Fernet key for encrypting TOTP secrets
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1

# ─────────────────────────────────────────────
# SUPABASE
# ─────────────────────────────────────────────
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres:password@db.xxxx.supabase.co:5432/postgres
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30

# ─────────────────────────────────────────────
# REDIS
# ─────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_TTL=300           # seconds, default cache TTL
REDIS_RATE_LIMIT_TTL=60       # seconds, rate limit window

# ─────────────────────────────────────────────
# CLOUDFLARE R2 STORAGE
# ─────────────────────────────────────────────
STORAGE_PROVIDER=r2
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_R2_BUCKET=hadha-media
CLOUDFLARE_R2_ACCESS_KEY=
CLOUDFLARE_R2_SECRET_KEY=
CLOUDFLARE_R2_PUBLIC_URL=https://cdn.hadha.co
CLOUDFLARE_R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com

# ─────────────────────────────────────────────
# EMAIL — PRIMARY (RESEND)
# ─────────────────────────────────────────────
RESEND_API_KEY=
EMAIL_FROM=noreply@hadha.co
EMAIL_REPLY_TO=support@hadha.co
EMAIL_FROM_NAME=Hadha.co

# ─────────────────────────────────────────────
# EMAIL — FALLBACK (SENDGRID)
# ─────────────────────────────────────────────
SENDGRID_API_KEY=

# ─────────────────────────────────────────────
# SMS (TWILIO)
# ─────────────────────────────────────────────
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX

# ─────────────────────────────────────────────
# RAZORPAY
# ─────────────────────────────────────────────
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
RAZORPAY_CURRENCY=INR

# ─────────────────────────────────────────────
# DELIVERY ONE
# ─────────────────────────────────────────────
DELIVERY_ONE_BASE_URL=https://api.deliveryone.in
DELIVERY_ONE_API_KEY=
DELIVERY_ONE_WEBHOOK_SECRET=
DELIVERY_ONE_PICKUP_PINCODE=

# ─────────────────────────────────────────────
# SENTRY
# ─────────────────────────────────────────────
SENTRY_DSN=
SENTRY_TRACES_SAMPLE_RATE=0.1    # 10% for production
SENTRY_ENVIRONMENT=development

# ─────────────────────────────────────────────
# MONITORING
# ─────────────────────────────────────────────
BETTERSTACK_API_KEY=

# ─────────────────────────────────────────────
# FRONTEND
# ─────────────────────────────────────────────
FRONTEND_URL=http://localhost:3000
ADMIN_URL=http://localhost:3001

# ─────────────────────────────────────────────
# AUTH CALLBACKS
# ─────────────────────────────────────────────
SUPABASE_AUTH_REDIRECT_URL=http://localhost:3000/auth/callback
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# ─────────────────────────────────────────────
# RATE LIMITS (requests per window)
# ─────────────────────────────────────────────
RATE_LIMIT_AUTH=10            # login/signup per minute per IP
RATE_LIMIT_API=200            # general API per minute per user
RATE_LIMIT_UPLOAD=20          # file uploads per minute per user
RATE_LIMIT_WEBHOOK=500        # webhook endpoint per minute

# ─────────────────────────────────────────────
# WORKERS / CRON INTERVALS (seconds)
# ─────────────────────────────────────────────
SHIPMENT_SYNC_INTERVAL=300
REVIEW_REMINDER_DELAY_HOURS=48
ABANDONED_CART_THRESHOLD_HOURS=1
ABANDONED_CART_INTERVAL=3600
INVENTORY_ALERT_INTERVAL=1800
NOTIFICATION_RETRY_INTERVAL=30

# ─────────────────────────────────────────────
# BUSINESS SETTINGS
# ─────────────────────────────────────────────
FREE_SHIPPING_THRESHOLD=999   # INR, orders above this get free shipping
TAX_RATE_GST=3                # percent — 3% GST on silver jewellery (916 hallmark)
LOW_STOCK_THRESHOLD=5         # units, below this triggers alert
ORDER_NUMBER_PREFIX=HD
INVOICE_NUMBER_PREFIX=INV
```

### Pydantic Settings Class Structure
```python
# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Hadha.co"
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    # Redis
    REDIS_URL: str
    REDIS_CACHE_TTL: int = 300

    # R2 Storage
    CLOUDFLARE_ACCOUNT_ID: str
    CLOUDFLARE_R2_BUCKET: str
    CLOUDFLARE_R2_ACCESS_KEY: str
    CLOUDFLARE_R2_SECRET_KEY: str
    CLOUDFLARE_R2_PUBLIC_URL: str
    CLOUDFLARE_R2_ENDPOINT: str

    # Email
    RESEND_API_KEY: str
    EMAIL_FROM: str
    EMAIL_REPLY_TO: str
    SENDGRID_API_KEY: str = ""   # optional fallback

    # SMS
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBER: str

    # Razorpay
    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str
    RAZORPAY_CURRENCY: str = "INR"

    # Delivery One
    DELIVERY_ONE_BASE_URL: str
    DELIVERY_ONE_API_KEY: str
    DELIVERY_ONE_WEBHOOK_SECRET: str

    # Sentry
    SENTRY_DSN: str = ""

    # Frontend
    FRONTEND_URL: str
    ADMIN_URL: str

    # Security
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    ALLOWED_ORIGINS: str = ""

    # Business
    FREE_SHIPPING_THRESHOLD: int = 999
    TAX_RATE_GST: float = 3.0
    LOW_STOCK_THRESHOLD: int = 5
    ORDER_NUMBER_PREFIX: str = "HD"

    # Workers
    SHIPMENT_SYNC_INTERVAL: int = 300
    REVIEW_REMINDER_DELAY_HOURS: int = 48
    ABANDONED_CART_INTERVAL: int = 3600

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

### Startup Validation
On application startup in `main.py`, call `validate_required_settings()` which checks all fields without defaults. If any are empty strings or missing, collect all failures and raise `SystemExit` with a full list. The application must never start in a degraded state.

---

# HADHA.CO — PART 2: CUSTOMER-FACING MODULES
> Catalog · Categories · Collections · SEO · Search · Wishlist · Addresses · Media/CDN · Inventory · Advanced Inventory · Jewelry · Cart

---

## 2.1 CATALOG MODULE

### Responsibilities
- Define the full product catalogue for a silver jewellery store.
- Support all jewellery product types: Rings, Anklets, Bracelets, Chains, Necklaces, Pendants, Bangles, Earrings, Toe Rings, Kids Jewellery, Men Jewellery, Black Bead Sets, Nakshi jewellery, Bugadi (nose rings).
- Manage product lifecycle: draft → active → archived.
- Support product variants (size, finish) with independent SKU and inventory tracking.
- Expose all filtering, sorting, pagination, and search capabilities.

### Tables

#### products
```sql
CREATE TABLE products (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku                 TEXT NOT NULL UNIQUE,
    slug                TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    description         TEXT,
    short_description   TEXT,
    category_id         UUID NOT NULL REFERENCES categories(id),
    collection_ids      UUID[],                  -- denormalized for fast listing; source of truth is product_collections

    -- Jewellery-specific
    metal_type          TEXT NOT NULL CHECK (metal_type IN ('925_silver','oxidized_silver','gold_plated_silver','rhodium_plated_silver','other')),
    purity              TEXT,                    -- e.g. '925', '92.5%', 'Hallmarked'
    hallmark_number     TEXT,
    weight_grams        NUMERIC(8,3),
    length_mm           NUMERIC(7,2),
    width_mm            NUMERIC(7,2),
    height_mm           NUMERIC(7,2),
    diameter_mm         NUMERIC(7,2),            -- for rings, bangles, toe rings

    -- Pricing
    base_price          NUMERIC(12,2) NOT NULL,
    sale_price          NUMERIC(12,2),
    making_charges      NUMERIC(12,2) DEFAULT 0,
    cost_price          NUMERIC(12,2),           -- internal, never exposed to frontend

    -- Product attributes
    gender              TEXT CHECK (gender IN ('women','men','kids','unisex')),
    occasion            TEXT[],                  -- ['daily','wedding','festive','office']
    style               TEXT[],                  -- ['traditional','contemporary','fusion']
    finish              TEXT[],                  -- ['polished','matte','oxidized','rhodium']
    stone_type          TEXT[],                  -- ['cubic_zirconia','pearl','coral','none']
    stone_color         TEXT[],
    care_instructions   TEXT,
    certification_info  TEXT,

    -- Flags
    is_featured         BOOLEAN NOT NULL DEFAULT FALSE,
    is_new_arrival      BOOLEAN NOT NULL DEFAULT FALSE,
    is_bestseller       BOOLEAN NOT NULL DEFAULT FALSE,
    is_customizable     BOOLEAN NOT NULL DEFAULT FALSE,
    has_variants        BOOLEAN NOT NULL DEFAULT FALSE,

    -- SEO
    seo_title           TEXT,
    seo_description     TEXT,
    seo_keywords        TEXT[],

    -- Status
    status              TEXT NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft','active','archived')),

    -- Search vector (auto-updated via trigger)
    search_vector       TSVECTOR,

    -- Soft delete & audit
    deleted_at          TIMESTAMPTZ,
    created_by          UUID REFERENCES profiles(id),
    updated_by          UUID REFERENCES profiles(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### categories
```sql
CREATE TABLE categories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id   UUID REFERENCES categories(id),   -- supports subcategories
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    description TEXT,
    image_url   TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    seo_title   TEXT,
    seo_description TEXT,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Seed categories: Rings, Anklets, Bracelets, Chains, Necklaces, Pendants, Bangles, Earrings, Toe Rings, Kids Jewellery, Men Jewellery, Black Bead Sets, Nakshi, Bugadi.

#### collections
```sql
CREATE TABLE collections (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    description TEXT,
    image_url   TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    is_featured BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    seo_title   TEXT,
    seo_description TEXT,
    starts_at   TIMESTAMPTZ,
    ends_at     TIMESTAMPTZ,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### product_collections (join table)
```sql
CREATE TABLE product_collections (
    product_id    UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    sort_order    INTEGER DEFAULT 0,
    PRIMARY KEY (product_id, collection_id)
);
```

#### product_variants
```sql
CREATE TABLE product_variants (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id   UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sku          TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,              -- e.g. "Size 6 - Polished"
    size         TEXT,
    finish       TEXT,
    weight_grams NUMERIC(8,3),
    price_delta  NUMERIC(12,2) DEFAULT 0,   -- added to product base_price
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order   INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### product_attributes
```sql
CREATE TABLE product_attributes (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);
```

#### product_images
```sql
CREATE TABLE product_images (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id    UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_id    UUID REFERENCES product_variants(id),
    thumbnail_url TEXT NOT NULL,
    medium_url    TEXT NOT NULL,
    large_url     TEXT NOT NULL,
    alt_text      TEXT,
    is_primary    BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Indexes
```sql
CREATE INDEX idx_products_slug         ON products(slug);
CREATE INDEX idx_products_category_id  ON products(category_id);
CREATE INDEX idx_products_status       ON products(status);
CREATE INDEX idx_products_is_featured  ON products(is_featured) WHERE is_featured = TRUE;
CREATE INDEX idx_products_is_new       ON products(is_new_arrival) WHERE is_new_arrival = TRUE;
CREATE INDEX idx_products_metal_type   ON products(metal_type);
CREATE INDEX idx_products_gender       ON products(gender);
CREATE INDEX idx_products_price        ON products(sale_price, base_price);
CREATE INDEX idx_products_search       ON products USING GIN(search_vector);
CREATE INDEX idx_products_deleted      ON products(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_products_created      ON products(created_at DESC);
CREATE INDEX idx_categories_slug       ON categories(slug);
CREATE INDEX idx_categories_parent     ON categories(parent_id);
CREATE INDEX idx_collections_slug      ON collections(slug);
CREATE INDEX idx_product_images_prod   ON product_images(product_id, sort_order);
CREATE INDEX idx_product_variants_prod ON product_variants(product_id);
```

### Catalog APIs

#### GET /products
Public paginated product listing with filters.

**Query params:**
```
page           integer  default=1
page_size      integer  default=24, max=100
category_slug  string
collection_slug string
metal_type     string   (925_silver|oxidized_silver|...)
gender         string   (women|men|kids|unisex)
occasion       string[] comma-separated
min_price      number
max_price      number
is_featured    boolean
is_new_arrival boolean
is_bestseller  boolean
sort_by        string   (created_at|price_asc|price_desc|popularity|name)
search         string   full-text search query
```

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "sku": "HD-RNG-001",
      "slug": "oxidized-silver-midi-ring",
      "name": "Oxidized Silver Midi Ring",
      "short_description": "...",
      "metal_type": "oxidized_silver",
      "weight_grams": 3.5,
      "base_price": 649.00,
      "sale_price": 499.00,
      "is_featured": false,
      "is_new_arrival": true,
      "primary_image": {
        "thumbnail_url": "https://cdn.hadha.co/product-images/uuid/thumbnail.webp",
        "medium_url": "https://cdn.hadha.co/product-images/uuid/medium.webp",
        "large_url": "https://cdn.hadha.co/product-images/uuid/large.webp"
      },
      "category": { "id": "uuid", "name": "Rings", "slug": "rings" },
      "stock_status": "in_stock",
      "average_rating": 4.5,
      "review_count": 12
    }
  ],
  "total": 284,
  "page": 1,
  "page_size": 24,
  "total_pages": 12
}
```

**Auth:** None (public). Admin can see `draft` and `archived` products by passing `?status=draft` with admin token.

#### GET /products/{slug}
Full product detail including variants, images, attributes, related products.

**Response:**
```json
{
  "id": "uuid",
  "sku": "HD-RNG-001",
  "slug": "oxidized-silver-midi-ring",
  "name": "Oxidized Silver Midi Ring",
  "description": "<rich text>",
  "short_description": "...",
  "metal_type": "oxidized_silver",
  "purity": "925",
  "hallmark_number": "BIS925",
  "weight_grams": 3.5,
  "base_price": 649.00,
  "sale_price": 499.00,
  "making_charges": 50.00,
  "gender": "women",
  "occasion": ["daily", "festive"],
  "style": ["traditional"],
  "finish": ["oxidized"],
  "stone_type": ["none"],
  "care_instructions": "Store in a dry place...",
  "certification_info": "BIS Hallmarked 925",
  "is_featured": false,
  "is_new_arrival": true,
  "is_customizable": false,
  "has_variants": true,
  "status": "active",
  "images": [ { ... } ],
  "variants": [ { ... } ],
  "attributes": [ { "key": "Occasion", "value": "Daily Wear" } ],
  "category": { "id": "uuid", "name": "Rings", "slug": "rings" },
  "collections": [ { "id": "uuid", "name": "Festive Edit", "slug": "festive-edit" } ],
  "inventory": { "available_qty": 14, "stock_status": "in_stock" },
  "average_rating": 4.5,
  "review_count": 12,
  "seo": {
    "title": "Buy Oxidized Silver Midi Ring Online | Hadha.co",
    "description": "...",
    "canonical_url": "https://hadha.co/products/oxidized-silver-midi-ring"
  }
}
```

**Auth:** None (public).

#### POST /admin/products
Create product. **Auth:** `require_admin`

**Request:**
```json
{
  "sku": "HD-RNG-002",
  "name": "Sterling Silver Stacking Ring",
  "slug": "sterling-silver-stacking-ring",
  "description": "...",
  "short_description": "...",
  "category_id": "uuid",
  "metal_type": "925_silver",
  "purity": "925",
  "weight_grams": 2.8,
  "base_price": 549.00,
  "sale_price": 449.00,
  "making_charges": 40.00,
  "gender": "women",
  "occasion": ["daily"],
  "style": ["contemporary"],
  "finish": ["polished"],
  "stone_type": ["none"],
  "care_instructions": "...",
  "is_featured": false,
  "is_new_arrival": true,
  "status": "draft"
}
```

**Validation:** sku unique, slug unique (auto-generated from name if omitted), base_price > 0, sale_price ≤ base_price if provided, category_id must exist.

#### PATCH /admin/products/{id}
Partial update. **Auth:** `require_admin`
Any price change is logged to `audit_logs`.

#### DELETE /admin/products/{id}
Soft delete (sets `deleted_at`). **Auth:** `require_admin`
Products with active orders cannot be deleted — returns `409 Conflict`.

#### POST /admin/products/{id}/variants
Add a variant. **Auth:** `require_admin`

#### PATCH /admin/products/{id}/variants/{variant_id}
Update variant. **Auth:** `require_admin`

#### DELETE /admin/products/{id}/variants/{variant_id}
Soft delete variant (sets variant `is_active = false`). **Auth:** `require_admin`
Variant with active cart items cannot be deactivated — returns `409 Conflict`.

---

## 2.2 CATEGORIES MODULE

### APIs

#### GET /categories
Returns full category tree.
**Auth:** None.

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Rings",
    "slug": "rings",
    "image_url": "https://cdn.hadha.co/cms-assets/cat-rings.webp",
    "sort_order": 1,
    "product_count": 48,
    "children": []
  }
]
```

#### GET /categories/{slug}/products
Products within a category (uses the same filters as `GET /products`).
**Auth:** None.

#### POST /admin/categories
**Auth:** `require_admin`

#### PATCH /admin/categories/{id}
**Auth:** `require_admin`

#### DELETE /admin/categories/{id}
Soft delete. Returns `409` if category has active products.
**Auth:** `require_admin`

---

## 2.3 COLLECTIONS MODULE

### APIs

#### GET /collections
Active collections list.
**Auth:** None.

#### GET /collections/{slug}
Collection detail + products.
**Auth:** None.

#### POST /admin/collections
**Auth:** `require_admin`

#### PATCH /admin/collections/{id}
**Auth:** `require_admin`

#### POST /admin/collections/{id}/products
Add products to a collection.
**Auth:** `require_admin`

**Request:** `{ "product_ids": ["uuid", "uuid"] }`

#### DELETE /admin/collections/{id}/products/{product_id}
Remove product from collection.
**Auth:** `require_admin`

---

## 2.4 SEO MODULE

### Responsibilities
- Store page-level SEO metadata for products, categories, collections, and CMS pages.
- Generate automatic SEO metadata when not manually set.
- Handle 301 redirects (old slugs → new slugs after product renames).
- Track 404 hits for admin review.
- Generate sitemap.xml and robots.txt.

### Tables

#### seo_pages
```sql
CREATE TABLE seo_pages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     TEXT NOT NULL CHECK (entity_type IN ('product','category','collection','cms_page')),
    entity_id       UUID NOT NULL,
    canonical_url   TEXT NOT NULL,
    meta_title      TEXT,
    meta_description TEXT,
    meta_keywords   TEXT[],
    og_title        TEXT,
    og_description  TEXT,
    og_image_url    TEXT,
    twitter_title   TEXT,
    twitter_description TEXT,
    twitter_image_url TEXT,
    structured_data JSONB,       -- JSON-LD: ProductSchema, BreadcrumbSchema, etc.
    is_indexed      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_type, entity_id)
);
```

#### seo_redirects
```sql
CREATE TABLE seo_redirects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_path   TEXT NOT NULL UNIQUE,
    to_path     TEXT NOT NULL,
    status_code INTEGER NOT NULL DEFAULT 301 CHECK (status_code IN (301, 302)),
    hit_count   INTEGER NOT NULL DEFAULT 0,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_seo_redirects_from ON seo_redirects(from_path) WHERE is_active = TRUE;
```

#### seo_404_log
```sql
CREATE TABLE seo_404_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    path        TEXT NOT NULL,
    referrer    TEXT,
    user_agent  TEXT,
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_seo_404_path ON seo_404_log(path);
```

### Auto-Generation Logic
When a product is created/updated without a `seo_title`, the system auto-generates:
- `meta_title` = `"{product.name} | Buy Online | Hadha.co"`
- `meta_description` = `"Shop {product.name} in {metal_type} — {short_description} | Free Shipping above ₹999"`
- `canonical_url` = `"https://hadha.co/products/{slug}"`
- `structured_data` = Product JSON-LD schema with `offers`, `aggregateRating`, `brand`

### Structured Data Schemas Generated
- **ProductSchema** — all products
- **BreadcrumbSchema** — all product/category/collection pages
- **OrganizationSchema** — homepage
- **FAQSchema** — FAQ CMS pages

### APIs

#### GET /sitemap.xml
Generates dynamic XML sitemap.
**Auth:** None.

#### GET /robots.txt
**Auth:** None.

#### GET /seo/redirects/{path}
Check if a redirect exists for the given path.
**Auth:** None.

#### POST /admin/seo/redirects
**Auth:** `require_admin`

#### PATCH /admin/seo/pages/{entity_type}/{entity_id}
**Auth:** `require_admin`

---

## 2.5 SEARCH MODULE

### Strategy
PostgreSQL full-text search via `tsvector` + `tsquery`. Trigram indexes for autocomplete/fuzzy matching. No external search engine required at this scale (<200 concurrent users).

### Search Vector Update Trigger
```sql
CREATE OR REPLACE FUNCTION update_product_search_vector()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        coalesce(NEW.name, '') || ' ' ||
        coalesce(NEW.short_description, '') || ' ' ||
        coalesce(NEW.description, '') || ' ' ||
        coalesce(NEW.metal_type, '') || ' ' ||
        coalesce(NEW.purity, '') || ' ' ||
        coalesce(array_to_string(NEW.seo_keywords, ' '), '')
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER trgr_product_search_vector
    BEFORE INSERT OR UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_product_search_vector();
```

### Database Tables

#### search_history
```sql
CREATE TABLE search_history (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID REFERENCES profiles(id),
    session_id TEXT,
    query      TEXT NOT NULL,
    result_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_search_history_user    ON search_history(user_id);
CREATE INDEX idx_search_history_query   ON search_history(query);
CREATE INDEX idx_search_history_created ON search_history(created_at DESC);
```

#### search_suggestions (materialized, refreshed every 6h)
```sql
CREATE MATERIALIZED VIEW trending_searches AS
SELECT query, COUNT(*) AS search_count
FROM search_history
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY query
ORDER BY search_count DESC
LIMIT 20;
CREATE UNIQUE INDEX idx_trending_searches ON trending_searches(query);
```

### APIs

#### GET /search
Full-text product search.

**Query params:** `q` (required), `page`, `page_size`, `category_slug`, `min_price`, `max_price`, `metal_type`, `gender`

**Response:** Same shape as `GET /products` response.

**Implementation:**
```sql
SELECT p.*, ts_rank(p.search_vector, query) AS rank
FROM products p, plainto_tsquery('english', :q) query
WHERE p.search_vector @@ query
  AND p.status = 'active'
  AND p.deleted_at IS NULL
ORDER BY rank DESC, p.is_featured DESC
LIMIT :page_size OFFSET :offset;
```

#### GET /search/autocomplete
Prefix + trigram autocomplete for search box.

**Query params:** `q` (min 2 chars)

**Response:**
```json
{
  "suggestions": ["silver ring", "silver anklet", "silver bracelet"],
  "products": [
    { "id": "uuid", "name": "Oxidized Silver Ring", "slug": "...", "thumbnail_url": "..." }
  ]
}
```

**Implementation:** trigram similarity on `products.name` via `pg_trgm`:
```sql
SELECT name, slug, thumbnail_url FROM product_listing_view
WHERE name % :q AND status = 'active'
ORDER BY similarity(name, :q) DESC
LIMIT 5;
```

#### GET /search/trending
Returns top 10 trending searches.
**Auth:** None.

#### GET /search/recent
Returns current user's last 10 searches.
**Auth:** `get_current_user`

---

## 2.6 WISHLIST MODULE

### Responsibilities
- Allow customers to save products for later.
- Support both guest (session-based) and authenticated wishlists.
- Merge guest wishlist into authenticated wishlist on login.
- Allow sharing a wishlist via a unique URL.
- Allow moving items directly to cart.

### Tables

#### wishlists
```sql
CREATE TABLE wishlists (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID REFERENCES profiles(id),       -- null for guest
    session_id TEXT,                                -- for guest wishlist
    share_token TEXT UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT wishlist_owner CHECK (user_id IS NOT NULL OR session_id IS NOT NULL)
);
CREATE INDEX idx_wishlists_user_id    ON wishlists(user_id);
CREATE INDEX idx_wishlists_session_id ON wishlists(session_id);
```

#### wishlist_items
```sql
CREATE TABLE wishlist_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wishlist_id UUID NOT NULL REFERENCES wishlists(id) ON DELETE CASCADE,
    product_id  UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_id  UUID REFERENCES product_variants(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (wishlist_id, product_id, variant_id)
);
CREATE INDEX idx_wishlist_items_wishlist ON wishlist_items(wishlist_id);
CREATE INDEX idx_wishlist_items_product  ON wishlist_items(product_id);
```

### APIs

#### GET /wishlist
Returns current wishlist with product details.
**Auth:** `get_current_user` OR guest (session_id cookie).

**Response:**
```json
{
  "id": "uuid",
  "share_url": "https://hadha.co/wishlist/share/abc123def456",
  "items": [
    {
      "id": "uuid",
      "product": { "id": "uuid", "name": "...", "slug": "...", "sale_price": 499, "primary_image": {...} },
      "variant": null,
      "stock_status": "in_stock"
    }
  ],
  "total_items": 3
}
```

#### POST /wishlist/items
Add item to wishlist.
**Auth:** `get_current_user` OR guest.

**Request:** `{ "product_id": "uuid", "variant_id": "uuid|null" }`

**Validation:** product must exist and be active. Duplicate add is idempotent (no error).

#### DELETE /wishlist/items/{id}
Remove item from wishlist.
**Auth:** `get_current_user` OR guest (must own the wishlist).

#### POST /wishlist/items/{id}/move-to-cart
Moves wishlist item to cart. Removes from wishlist if successfully added to cart.
**Auth:** `get_current_user`

#### GET /wishlist/share/{token}
Public view of a shared wishlist (read-only).
**Auth:** None.

#### POST /wishlist/merge
Merges a guest wishlist (by session_id) into the authenticated user's wishlist. Called automatically on login.
**Auth:** `get_current_user`
**Request:** `{ "session_id": "xyz" }`

---

## 2.7 ADDRESS MODULE

### Responsibilities
- Store shipping and billing addresses for customers.
- Support multiple addresses per user with a default flag.
- Validate Indian pincodes.

### Table

#### addresses
```sql
CREATE TABLE addresses (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    label          TEXT,                          -- 'Home', 'Work', 'Other'
    full_name      TEXT NOT NULL,
    phone          TEXT NOT NULL,
    address_line_1 TEXT NOT NULL,
    address_line_2 TEXT,
    landmark       TEXT,
    city           TEXT NOT NULL,
    state          TEXT NOT NULL,
    country        TEXT NOT NULL DEFAULT 'India',
    postal_code    TEXT NOT NULL,
    is_default     BOOLEAN NOT NULL DEFAULT FALSE,
    address_type   TEXT NOT NULL DEFAULT 'shipping'
                       CHECK (address_type IN ('shipping', 'billing', 'both')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_addresses_user_id ON addresses(user_id);
CREATE INDEX idx_addresses_default ON addresses(user_id, is_default) WHERE is_default = TRUE;
```

### Business Rules
- Only one address per user can be `is_default = TRUE`.
- When a new address is set as default, all other addresses for the same user are updated to `is_default = FALSE` atomically within a transaction.
- Maximum 10 addresses per user.

### APIs

#### GET /addresses
Returns all addresses for the current user.
**Auth:** `get_current_user`

#### POST /addresses
Create a new address.
**Auth:** `get_current_user`

**Request:**
```json
{
  "label": "Home",
  "full_name": "Jane Doe",
  "phone": "+919876543210",
  "address_line_1": "12, Silver Lane",
  "address_line_2": "Opp. City Mall",
  "landmark": "Near Post Office",
  "city": "Pune",
  "state": "Maharashtra",
  "country": "India",
  "postal_code": "411001",
  "is_default": true,
  "address_type": "both"
}
```

**Validation:** phone E.164, postal_code 6 digits, all required fields present.

#### PATCH /addresses/{id}
**Auth:** `get_current_user` (must own address)

#### DELETE /addresses/{id}
**Auth:** `get_current_user` (must own address)
Returns `409` if address is attached to an active order.

#### PATCH /addresses/{id}/set-default
**Auth:** `get_current_user`

---

## 2.8 MEDIA / CDN MODULE

### Architecture
```
Admin Browser → POST /admin/media/upload (multipart)
                        ↓
              FastAPI receives file bytes
                        ↓
          Validate: type, size, dimensions
                        ↓
          Convert to WEBP using Pillow
                        ↓
    Generate 3 variants: thumbnail(200px), medium(600px), large(1200px)
                        ↓
    Upload all 3 to Cloudflare R2 (async parallel)
                        ↓
    Store CDN URLs in product_images table
                        ↓
    Return { thumbnail_url, medium_url, large_url }
                        ↓
              Frontend receives CDN URLs
```

### Storage Structure (R2 Bucket: hadha-media)
```
product-images/
  {product_id}/
    {image_id}_thumbnail.webp     (200×200)
    {image_id}_medium.webp        (600×600)
    {image_id}_large.webp         (1200×1200)

review-images/
  {review_id}/
    {image_id}_medium.webp        (800×800)

cms-assets/
  banners/
    {asset_id}_desktop.webp       (1440×600)
    {asset_id}_mobile.webp        (768×400)
  category-images/
    {category_id}.webp            (400×400)

avatars/
  {user_id}.webp                  (200×200)
```

### Image Processing Rules
- Accepted input formats: `jpg`, `jpeg`, `png`, `webp`, `heic`
- All outputs are converted to `WEBP` (Pillow `save(format='WEBP', quality=85, optimize=True)`)
- Maximum input file size: 15MB
- Generated variants (width×height, maintain aspect ratio, pad with white if needed):
  - `thumbnail`: 200×200 (square crop, centered)
  - `medium`: 600×600 (square crop, centered)
  - `large`: 1200×1200 (square crop, centered)
- EXIF data stripped on output
- Progressive encoding enabled

### CDN URL Structure
All URLs are served through Cloudflare CDN, never through FastAPI:
```
https://cdn.hadha.co/product-images/{product_id}/{image_id}_thumbnail.webp
https://cdn.hadha.co/product-images/{product_id}/{image_id}_medium.webp
https://cdn.hadha.co/product-images/{product_id}/{image_id}_large.webp
```

Internal R2 paths are never exposed in API responses.

### APIs

#### POST /admin/media/upload
Upload and process a product image.
**Auth:** `require_admin`
**Content-Type:** `multipart/form-data`

**Request fields:**
- `file` — the image file
- `product_id` — UUID (required)
- `variant_id` — UUID (optional)
- `alt_text` — string (optional)
- `is_primary` — boolean (optional)

**Validation:**
- MIME type must be `image/jpeg`, `image/png`, `image/webp`, `image/heic`
- Size must not exceed 15MB
- If `is_primary=true`, existing primary image for same product is updated to `is_primary=false`

**Response:**
```json
{
  "id": "uuid",
  "thumbnail_url": "https://cdn.hadha.co/product-images/uuid/uuid_thumbnail.webp",
  "medium_url": "https://cdn.hadha.co/product-images/uuid/uuid_medium.webp",
  "large_url": "https://cdn.hadha.co/product-images/uuid/uuid_large.webp",
  "alt_text": "Oxidized Silver Ring"
}
```

#### DELETE /admin/media/{id}
Delete image from R2 and database.
**Auth:** `require_admin`

#### PATCH /admin/media/{id}/sort
Reorder product images.
**Auth:** `require_admin`
**Request:** `{ "sort_order": 2 }`

#### POST /admin/media/cms-upload
Upload CMS banner or category image.
**Auth:** `require_admin`

#### PATCH /admin/media/{id}/set-primary
Set a product image as primary.
**Auth:** `require_admin`

---

## 2.9 INVENTORY MODULE

### Responsibilities
- Track stock quantity at SKU and variant level.
- Reserve stock when items are added to cart (soft reserve, with TTL).
- Confirm reservation on order creation.
- Release reservation on cart expiry, payment failure, or order cancellation.
- Record all inventory movements (purchase, sale, return, adjustment, damage).
- Trigger low-stock alerts when quantity drops below threshold.

### Tables

#### inventory
```sql
CREATE TABLE inventory (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id          UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_id          UUID REFERENCES product_variants(id),
    sku                 TEXT NOT NULL UNIQUE,
    qty_on_hand         INTEGER NOT NULL DEFAULT 0 CHECK (qty_on_hand >= 0),
    qty_reserved        INTEGER NOT NULL DEFAULT 0 CHECK (qty_reserved >= 0),
    qty_damaged         INTEGER NOT NULL DEFAULT 0 CHECK (qty_damaged >= 0),
    qty_returned        INTEGER NOT NULL DEFAULT 0 CHECK (qty_returned >= 0),
    low_stock_threshold INTEGER NOT NULL DEFAULT 5,
    reorder_point       INTEGER NOT NULL DEFAULT 10,
    reorder_qty         INTEGER NOT NULL DEFAULT 20,
    location            TEXT,                      -- warehouse/shelf reference
    last_reconciled_at  TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT inventory_product_variant UNIQUE NULLS NOT DISTINCT (product_id, variant_id)
);
CREATE INDEX idx_inventory_product_id ON inventory(product_id);
CREATE INDEX idx_inventory_sku        ON inventory(sku);
CREATE INDEX idx_inventory_low_stock  ON inventory(qty_on_hand, low_stock_threshold)
    WHERE qty_on_hand <= low_stock_threshold;
```

**Computed fields (virtual, via view):**
- `qty_available = qty_on_hand - qty_reserved`
- `is_in_stock = qty_available > 0`

#### inventory_movements
```sql
CREATE TABLE inventory_movements (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inventory_id UUID NOT NULL REFERENCES inventory(id),
    movement_type TEXT NOT NULL CHECK (movement_type IN (
        'purchase','sale','return','adjustment','damage',
        'reservation','reservation_release','reconciliation'
    )),
    quantity     INTEGER NOT NULL,                 -- positive=in, negative=out
    reference_type TEXT,                           -- 'order','return','adjustment'
    reference_id UUID,
    notes        TEXT,
    performed_by UUID REFERENCES profiles(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_inventory_movements_inventory_id ON inventory_movements(inventory_id);
CREATE INDEX idx_inventory_movements_reference    ON inventory_movements(reference_type, reference_id);
CREATE INDEX idx_inventory_movements_created      ON inventory_movements(created_at DESC);
```

#### inventory_reservations
```sql
CREATE TABLE inventory_reservations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inventory_id UUID NOT NULL REFERENCES inventory(id),
    cart_id      UUID REFERENCES carts(id),
    order_id     UUID REFERENCES orders(id),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    status       TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','confirmed','released','expired')),
    expires_at   TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 minutes'),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_inventory_reservations_inventory ON inventory_reservations(inventory_id, status);
CREATE INDEX idx_inventory_reservations_cart      ON inventory_reservations(cart_id);
CREATE INDEX idx_inventory_reservations_expires   ON inventory_reservations(expires_at) WHERE status = 'active';
```

### Reservation Flow
```
Item added to cart
      ↓
inventory.reserve(product_id, variant_id, qty)
      ↓
  Check: qty_available >= requested_qty
      ↓ yes
  INSERT inventory_reservations (cart_id, qty, expires_at = NOW()+30min)
  UPDATE inventory SET qty_reserved = qty_reserved + qty
      ↓
  Return reservation_id → stored on cart_item

Cart expires / payment fails / order cancelled
      ↓
inventory.release(reservation_id)
      ↓
  UPDATE inventory_reservations SET status = 'released'
  UPDATE inventory SET qty_reserved = qty_reserved - qty

Order confirmed (payment webhook)
      ↓
inventory.confirm(reservation_id, order_id)
      ↓
  UPDATE inventory_reservations SET status='confirmed', order_id=order_id
  UPDATE inventory SET qty_on_hand = qty_on_hand - qty, qty_reserved = qty_reserved - qty
  INSERT inventory_movements (type='sale', qty=-qty, reference_type='order', reference_id=order_id)
```

### Low Stock Alert Worker
`inventory_alerts.py` runs every 30 minutes:
```sql
SELECT i.*, p.name, p.sku
FROM inventory i
JOIN products p ON p.id = i.product_id
WHERE i.qty_on_hand <= i.low_stock_threshold
  AND p.status = 'active'
  AND p.deleted_at IS NULL;
```
For each result, fires `LowInventoryAlert` event → Notification Service sends admin email.

### APIs

#### GET /admin/inventory
Paginated inventory list with low-stock filtering.
**Auth:** `require_admin`
**Query params:** `low_stock=true`, `search` (sku/name), `page`, `page_size`

#### GET /admin/inventory/{id}
Single inventory record with movement history.
**Auth:** `require_admin`

#### PATCH /admin/inventory/{id}
Update `low_stock_threshold`, `reorder_point`, `location`.
**Auth:** `require_admin`

#### POST /admin/inventory/{id}/adjust
Manual inventory adjustment (purchase/damage/reconciliation).
**Auth:** `require_admin`

**Request:**
```json
{
  "movement_type": "purchase",
  "quantity": 50,
  "notes": "Received from supplier — Invoice #SUP-2026-001"
}
```

**Audit:** logged with `performed_by = current_user.id`.

#### GET /admin/inventory/{id}/movements
Full movement history for a SKU.
**Auth:** `require_admin`

---

## 2.10 ADVANCED INVENTORY

### Extended Features for Jewellery

#### Inventory Reconciliation
Admin can trigger a reconciliation event that sets `qty_on_hand` to a physically counted value. A movement of type `reconciliation` is recorded showing the delta. Reconciliation requires `require_admin` and is fully audited.

#### Damaged Stock
Admin can mark units as damaged via `POST /admin/inventory/{id}/adjust` with `movement_type=damage`. `qty_damaged` increases; `qty_on_hand` decreases by the same amount.

#### Returned Stock
When a return is processed and items are received in resellable condition, a movement of type `return` increases `qty_on_hand`. If received as damaged, a `damage` movement is recorded instead.

#### SKU-Level Tracking
Each `inventory` record maps to one SKU. For products with variants, each variant has its own inventory row. This allows independent stock tracking for e.g. "Ring Size 5 - Polished" vs "Ring Size 7 - Matte".

#### Inventory Audit Trail
Every change to `inventory.qty_on_hand` or `qty_reserved` MUST create a corresponding `inventory_movements` record. Direct `UPDATE inventory SET qty_on_hand = X` without an accompanying movement record is forbidden and enforced via a PostgreSQL trigger:

```sql
CREATE OR REPLACE FUNCTION enforce_inventory_movement()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- Log any qty_on_hand change automatically
    IF OLD.qty_on_hand <> NEW.qty_on_hand THEN
        INSERT INTO inventory_movements (inventory_id, movement_type, quantity, notes)
        VALUES (NEW.id, 'adjustment', NEW.qty_on_hand - OLD.qty_on_hand, 'Auto-logged by trigger');
    END IF;
    RETURN NEW;
END;
$$;
-- Only applied for direct admin updates; reservation paths use explicit movement inserts.
```

---

## 2.11 JEWELRY PRODUCT REQUIREMENTS

### Metal Types
| Code | Display Name |
|------|-------------|
| `925_silver` | 925 Sterling Silver |
| `oxidized_silver` | Oxidized Silver |
| `gold_plated_silver` | Gold Plated Silver (925 base) |
| `rhodium_plated_silver` | Rhodium Plated Silver |
| `other` | Other |

### Hallmarking
- `hallmark_number` stores BIS code (e.g. `BIS925`, `HUID: XXXXXX`).
- `purity` stores textual purity descriptor (e.g. `92.5%`, `925`).
- `certification_info` stores free text (e.g. `BIS Hallmarked under BIS Act 2016`).

### Weight-Based Pricing
- `weight_grams` — net jewellery weight excluding stones.
- `making_charges` — fixed INR amount added to `base_price`.
- `cost_price` — internal cost (admin only, never in public API responses).
- Effective price = `sale_price ?? base_price`; never calculated from weight on-the-fly (jewellery store uses fixed pricing, not live silver rate).

### Stone Information
- `stone_type[]` — array of stone types used (cubic zirconia, pearl, coral, garnet, turquoise, none)
- `stone_color[]` — corresponding colors
- Stored as arrays on the product row; extended detail stored as `product_attributes` rows if needed.

### Product Dimensions
All jewellery dimensions stored in millimeters:
- `length_mm`, `width_mm`, `height_mm` — general dimensions
- `diameter_mm` — for bangles, rings, toe rings

### Product Attributes (flexible EAV)
`product_attributes` table allows unlimited key-value pairs per product:
- `Chain Length`, `18 inches`
- `Clasp Type`, `Lobster Claw`
- `Plating Thickness`, `3 microns`
- `Inner Diameter`, `58mm`

### Occasion Tags
`occasion[]` array with values from a controlled vocabulary:
`daily`, `wedding`, `festive`, `office`, `party`, `gifting`

### Style Tags
`style[]`: `traditional`, `contemporary`, `fusion`, `minimalist`, `statement`

### Finish Tags
`finish[]`: `polished`, `matte`, `oxidized`, `rhodium`, `antique`, `hammered`

### Gender & Age
- `gender`: `women`, `men`, `kids`, `unisex`
- For kids jewellery, product must have `gender='kids'` and `category.slug='kids-jewellery'`

### Care Instructions (template)
Default care instructions template used when not explicitly provided:
> "Store in a cool, dry place away from moisture. Avoid contact with perfumes, lotions, and chemicals. Clean gently with a soft cloth. Remove before bathing or swimming."

---

## 2.12 CART MODULE

### Responsibilities
- Support both guest (anonymous) and authenticated carts.
- Merge guest cart into authenticated cart on login.
- Validate inventory availability on every cart mutation.
- Recalculate totals server-side on every response — never trust frontend totals.
- Expire carts after 30-day inactivity; send abandoned cart notification at 1h.
- Apply coupon codes with server-side validation.

### Tables

#### carts
```sql
CREATE TABLE carts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES profiles(id),
    session_id     TEXT,
    coupon_id      UUID REFERENCES coupons(id),
    coupon_code    TEXT,
    shipping_address_id UUID REFERENCES addresses(id),
    notes          TEXT,
    status         TEXT NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active','merged','abandoned','converted')),
    expires_at     TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
    last_activity  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT cart_owner CHECK (user_id IS NOT NULL OR session_id IS NOT NULL)
);
CREATE INDEX idx_carts_user_id    ON carts(user_id) WHERE status = 'active';
CREATE INDEX idx_carts_session_id ON carts(session_id) WHERE status = 'active';
CREATE INDEX idx_carts_expires    ON carts(expires_at) WHERE status = 'active';
```

#### cart_items
```sql
CREATE TABLE cart_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id         UUID NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
    product_id      UUID NOT NULL REFERENCES products(id),
    variant_id      UUID REFERENCES product_variants(id),
    reservation_id  UUID REFERENCES inventory_reservations(id),
    quantity        INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0 AND quantity <= 10),
    unit_price      NUMERIC(12,2) NOT NULL,   -- locked at time of add
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (cart_id, product_id, variant_id)
);
CREATE INDEX idx_cart_items_cart_id    ON cart_items(cart_id);
CREATE INDEX idx_cart_items_product_id ON cart_items(product_id);
```

### Pricing Computation (server-side, always)
```
subtotal         = SUM(item.unit_price * item.quantity)
discount_amount  = calculate_coupon(coupon, subtotal)
taxable_amount   = subtotal - discount_amount
gst_amount       = taxable_amount * (TAX_RATE_GST / 100)
shipping_amount  = 0 if subtotal >= FREE_SHIPPING_THRESHOLD else 99
total            = taxable_amount + gst_amount + shipping_amount
```

`unit_price` is locked from the product's `sale_price ?? base_price` at the time the item is added to cart. If the product price changes later, the cart item retains the locked price until the customer refreshes the cart (triggering a re-price check).

### Cart APIs

#### GET /cart
Returns current cart with computed totals.
**Auth:** `get_current_user` OR guest (session_id cookie).

**Response:**
```json
{
  "id": "uuid",
  "status": "active",
  "items": [
    {
      "id": "uuid",
      "product": { "id": "uuid", "name": "...", "slug": "...", "primary_image": {...} },
      "variant": null,
      "quantity": 2,
      "unit_price": 499.00,
      "line_total": 998.00,
      "stock_status": "in_stock",
      "price_changed": false
    }
  ],
  "coupon": { "code": "WELCOME10", "discount_amount": 99.80 },
  "subtotal": 998.00,
  "discount_amount": 99.80,
  "taxable_amount": 898.20,
  "gst_amount": 26.95,
  "shipping_amount": 0.00,
  "total": 925.15,
  "free_shipping_eligible": true,
  "item_count": 2
}
```

#### POST /cart/items
Add item to cart. Reserves inventory.
**Auth:** `get_current_user` OR guest.

**Request:** `{ "product_id": "uuid", "variant_id": "uuid|null", "quantity": 1 }`

**Validation:**
- Product must be active.
- Inventory must have sufficient `qty_available`.
- Quantity per line item max = 10.
- Creates inventory reservation with 30-minute TTL.

#### PATCH /cart/items/{id}
Update quantity. Adjusts reservation.
**Auth:** Must own cart.

**Request:** `{ "quantity": 3 }`

#### DELETE /cart/items/{id}
Remove item from cart. Releases inventory reservation.
**Auth:** Must own cart.

#### POST /cart/coupon
Apply a coupon code.
**Auth:** `get_current_user` OR guest.

**Request:** `{ "code": "WELCOME10" }`

**Validation (server-side):**
- Coupon exists and is active.
- Coupon not expired.
- Subtotal meets minimum order requirement.
- User has not exceeded per-user usage limit.
- Total usage has not exceeded global limit.

**Response:** Updated cart totals.

#### DELETE /cart/coupon
Remove applied coupon.
**Auth:** Must own cart.

#### POST /cart/merge
Merge guest cart into authenticated cart on login.
**Auth:** `get_current_user`
**Request:** `{ "session_id": "xyz" }`

#### POST /cart/refresh
Re-validates all cart items (inventory, price changes). Returns updated cart with `price_changed` flags.
**Auth:** Must own cart.

---

# HADHA.CO — PART 3: TRANSACTION MODULES
> Orders · Payments · Invoices · Shipping · Webhook Framework · Reviews · Coupons · Returns · Tax

---

## 3.1 ORDERS MODULE

### Responsibilities
- Create orders from confirmed carts with server-side price recalculation.
- Manage the full order lifecycle from PENDING to DELIVERED/CANCELLED/REFUNDED.
- Enforce idempotent order creation (duplicate cart checkout attempts must not create duplicate orders).
- Track every status transition with timestamp and actor.
- Generate human-readable order numbers with prefix `HD` (e.g. `HD20260001`).

### Order Status Lifecycle
```
PENDING         (order created, awaiting payment)
    ↓
PAID            (payment webhook confirmed)
    ↓
PROCESSING      (admin acknowledged, preparing)
    ↓
SHIPPED         (shipment created with AWB)
    ↓
OUT_FOR_DELIVERY (Delivery One webhook)
    ↓
DELIVERED       (Delivery One webhook or admin manual)
    ↓ or
CANCELLED       (by customer before SHIPPED, or by admin)
    ↓ or
REFUNDED        (after cancellation/return + Razorpay refund)
```

### Tables

#### orders
```sql
CREATE TABLE orders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number        TEXT NOT NULL UNIQUE,          -- HD20260001
    customer_id         UUID NOT NULL REFERENCES profiles(id),

    -- Snapshot of shipping address at time of order
    shipping_name       TEXT NOT NULL,
    shipping_phone      TEXT NOT NULL,
    shipping_address_1  TEXT NOT NULL,
    shipping_address_2  TEXT,
    shipping_city       TEXT NOT NULL,
    shipping_state      TEXT NOT NULL,
    shipping_country    TEXT NOT NULL DEFAULT 'India',
    shipping_postal_code TEXT NOT NULL,

    -- Snapshot of billing address
    billing_name        TEXT,
    billing_address_1   TEXT,
    billing_city        TEXT,
    billing_state       TEXT,
    billing_country     TEXT DEFAULT 'India',
    billing_postal_code TEXT,

    -- Pricing (all server-calculated, immutable after creation)
    subtotal            NUMERIC(12,2) NOT NULL,
    discount_amount     NUMERIC(12,2) NOT NULL DEFAULT 0,
    coupon_id           UUID REFERENCES coupons(id),
    coupon_code         TEXT,
    taxable_amount      NUMERIC(12,2) NOT NULL,
    cgst_amount         NUMERIC(12,2) NOT NULL DEFAULT 0,
    sgst_amount         NUMERIC(12,2) NOT NULL DEFAULT 0,
    igst_amount         NUMERIC(12,2) NOT NULL DEFAULT 0,
    gst_total           NUMERIC(12,2) NOT NULL DEFAULT 0,
    shipping_amount     NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_amount        NUMERIC(12,2) NOT NULL,

    -- Status
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','paid','processing','shipped',
                                              'out_for_delivery','delivered',
                                              'cancelled','refunded')),

    -- Payment
    payment_id          UUID REFERENCES payments(id),
    paid_at             TIMESTAMPTZ,

    -- Shipping
    shipment_id         UUID REFERENCES shipments(id),

    -- Notes
    customer_notes      TEXT,
    admin_notes         TEXT,

    -- Idempotency
    cart_id             UUID REFERENCES carts(id),     -- prevents duplicate checkout
    idempotency_key     TEXT UNIQUE,                   -- client-provided or cart_id

    -- Soft delete & audit
    cancelled_at        TIMESTAMPTZ,
    cancelled_by        UUID REFERENCES profiles(id),
    cancellation_reason TEXT,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_customer_id  ON orders(customer_id);
CREATE INDEX idx_orders_status       ON orders(status);
CREATE INDEX idx_orders_created_at   ON orders(created_at DESC);
CREATE INDEX idx_orders_order_number ON orders(order_number);
CREATE INDEX idx_orders_cart_id      ON orders(cart_id);
CREATE INDEX idx_orders_payment_id   ON orders(payment_id);
```

#### order_items
```sql
CREATE TABLE order_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id      UUID NOT NULL REFERENCES products(id),
    variant_id      UUID REFERENCES product_variants(id),

    -- Snapshots at time of order — immutable
    product_name    TEXT NOT NULL,
    product_sku     TEXT NOT NULL,
    variant_name    TEXT,
    product_image   TEXT,              -- thumbnail_url at time of order

    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(12,2) NOT NULL,
    line_total      NUMERIC(12,2) NOT NULL,

    -- GST breakdown per line
    cgst_rate       NUMERIC(5,2) DEFAULT 0,
    sgst_rate       NUMERIC(5,2) DEFAULT 0,
    igst_rate       NUMERIC(5,2) DEFAULT 0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_order_items_order_id   ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);
```

#### order_status_history
```sql
CREATE TABLE order_status_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id    UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status   TEXT NOT NULL,
    changed_by  UUID REFERENCES profiles(id),    -- null if changed by webhook
    source      TEXT NOT NULL DEFAULT 'system'   -- 'admin','customer','webhook','system'
                    CHECK (source IN ('admin','customer','webhook','system')),
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_order_status_history_order ON order_status_history(order_id);
```

### Order Number Generation
```sql
CREATE SEQUENCE order_number_seq START 1;

CREATE OR REPLACE FUNCTION generate_order_number()
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    seq_val BIGINT;
    year_str TEXT;
BEGIN
    seq_val := nextval('order_number_seq');
    year_str := to_char(NOW(), 'YYYY');
    RETURN 'HD' || year_str || lpad(seq_val::TEXT, 4, '0');
END;
$$;
```

### Order Creation Flow
```
POST /orders/checkout
        ↓
1. Begin DB transaction
2. Validate idempotency_key — if exists and status != 'pending', return existing order
3. Load cart with all items
4. Verify all products still active
5. Check inventory availability for all items simultaneously
6. Re-calculate all prices server-side (ignore any frontend prices)
7. Re-validate coupon if applied
8. Re-calculate GST (CGST+SGST for same-state, IGST for inter-state)
9. Create orders row
10. Create order_items rows (with product/variant snapshots)
11. Create order_status_history row (null → pending)
12. Confirm inventory reservations (reservation_id → order_id)
13. Mark cart status = 'converted'
14. Record coupon usage (coupon_usage insert)
15. Commit transaction
16. Publish OrderCreated event (async)
17. Create Razorpay order (async, returns razorpay_order_id to frontend)
```

### APIs

#### POST /orders/checkout
Create order from cart.
**Auth:** `get_current_user`

**Request:**
```json
{
  "cart_id": "uuid",
  "shipping_address_id": "uuid",
  "billing_address_id": "uuid",
  "idempotency_key": "cart_uuid_or_client_nonce",
  "customer_notes": "Please pack as gift"
}
```

**Response:**
```json
{
  "order_id": "uuid",
  "order_number": "HD20260001",
  "razorpay_order_id": "order_xyz",
  "total_amount": 925.15,
  "currency": "INR",
  "status": "pending"
}
```

**Errors:**
- `409 Conflict` — idempotency_key already used
- `400 Bad Request` — cart empty, product unavailable, insufficient stock
- `422 Unprocessable Entity` — coupon expired or invalid

#### GET /orders
Customer's order history.
**Auth:** `get_current_user`
**Query params:** `status`, `page`, `page_size`

#### GET /orders/{order_number}
Order detail by human-readable number.
**Auth:** `get_current_user` (customer sees own orders only) OR `require_admin`.

**Response:** Full order including items, status history, payment summary, shipment tracking.

#### POST /orders/{id}/cancel
Customer cancels order.
**Auth:** `get_current_user` (must own order, status must be `pending` or `paid`).
**Request:** `{ "reason": "Changed my mind" }`

After cancellation:
- Status → `cancelled`
- Inventory reservations released
- Refund initiated if payment was captured

#### GET /admin/orders
Paginated order management.
**Auth:** `require_admin`
**Query params:** `status`, `search` (order_number/customer email), `from_date`, `to_date`, `page`, `page_size`

#### PATCH /admin/orders/{id}/status
Manually advance order status.
**Auth:** `require_admin`

**Request:** `{ "status": "processing", "notes": "Item packed and ready" }`

**Validation:** Status transitions must follow the defined lifecycle. Backwards transitions forbidden except `delivered → refunded`.

---

## 3.2 PAYMENT MODULE (RAZORPAY)

### Architecture
```
Frontend                         FastAPI                    Razorpay
    │                               │                          │
    ├──POST /orders/checkout────────▶│                          │
    │                               ├──Create Razorpay Order───▶│
    │◀──{ razorpay_order_id }────────┤◀──{ id, amount }─────────┤
    │                               │                          │
    ├──Open Razorpay Checkout────────────────────────────────────▶
    │◀──Payment success/failure (frontend callback)──────────────┤
    │                               │                          │
    │  [FRONTEND CALLBACK IS NEVER TRUSTED]                     │
    │                               │◀──Webhook: payment.captured│
    │                               ├──Verify signature         │
    │                               ├──Update order status      │
    │                               ├──Confirm inventory        │
    │                               ├──Send email + SMS         │
    │                               └──Generate invoice         │
```

### Webhook Is Source of Truth
The frontend payment success callback is NEVER used to confirm a payment. Only the Razorpay webhook `payment.captured` (or `order.paid`) event is the authoritative signal that a payment succeeded. This prevents payment bypass attacks.

### Tables

#### payments
```sql
CREATE TABLE payments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID NOT NULL REFERENCES orders(id),
    razorpay_order_id   TEXT NOT NULL UNIQUE,
    razorpay_payment_id TEXT UNIQUE,
    razorpay_signature  TEXT,
    amount              NUMERIC(12,2) NOT NULL,      -- in INR (NOT paise)
    currency            TEXT NOT NULL DEFAULT 'INR',
    status              TEXT NOT NULL DEFAULT 'created'
                            CHECK (status IN ('created','authorized','captured','failed','refunded')),
    method              TEXT,                        -- card, upi, netbanking, wallet
    bank                TEXT,
    wallet              TEXT,
    vpa                 TEXT,                        -- for UPI
    captured_at         TIMESTAMPTZ,
    failure_reason      TEXT,
    raw_payload         JSONB,                       -- full Razorpay response stored for audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_payments_order_id           ON payments(order_id);
CREATE INDEX idx_payments_razorpay_order_id  ON payments(razorpay_order_id);
CREATE INDEX idx_payments_razorpay_payment_id ON payments(razorpay_payment_id);
CREATE INDEX idx_payments_status             ON payments(status);
```

#### payment_events
```sql
CREATE TABLE payment_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id       UUID REFERENCES payments(id),
    webhook_event_id UUID REFERENCES webhook_events(id),
    event_type       TEXT NOT NULL,
    payload          JSONB NOT NULL,
    processed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_payment_events_payment_id ON payment_events(payment_id);
```

#### refunds
```sql
CREATE TABLE refunds (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID NOT NULL REFERENCES orders(id),
    payment_id          UUID NOT NULL REFERENCES payments(id),
    razorpay_refund_id  TEXT UNIQUE,
    amount              NUMERIC(12,2) NOT NULL,
    reason              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'initiated'
                            CHECK (status IN ('initiated','processing','processed','failed')),
    initiated_by        UUID REFERENCES profiles(id),
    notes               TEXT,
    raw_payload         JSONB,
    processed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_refunds_order_id   ON refunds(order_id);
CREATE INDEX idx_refunds_payment_id ON refunds(payment_id);
```

### APIs

#### POST /payments/create-order
Creates a Razorpay order and returns the `razorpay_order_id` needed by frontend Checkout.
**Auth:** `get_current_user`

**Request:** `{ "order_id": "uuid" }` (internal order must be in `pending` status)

**Response:**
```json
{
  "razorpay_order_id": "order_xyz123",
  "amount": 92515,
  "currency": "INR",
  "key_id": "rzp_live_xxxxx"
}
```

Note: `amount` is returned in paise (×100) as required by Razorpay.

#### POST /webhooks/razorpay
Razorpay webhook handler (public endpoint, no auth token, verified by HMAC-SHA256 signature).
**Auth:** Signature verification via `X-Razorpay-Signature` header.

**Idempotency:** Webhook events are stored in `webhook_events` table by `event_id`. If the same `event_id` arrives twice, the second is logged and discarded without re-processing.

**Handled events:**
| Event | Action |
|-------|--------|
| `payment.authorized` | Record payment as authorized |
| `payment.captured` | Advance order to PAID, confirm inventory, send email+SMS, generate invoice |
| `payment.failed` | Record failure, release inventory reservation |
| `order.paid` | Secondary confirmation (idempotent) |
| `refund.created` | Create refund record |
| `refund.processed` | Mark refund complete, update order status |

**Signature Verification:**
```python
import hmac, hashlib

def verify_razorpay_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

#### POST /admin/orders/{id}/refund
Initiate a full or partial refund.
**Auth:** `require_admin`

**Request:**
```json
{
  "amount": 499.00,
  "reason": "Product damaged on delivery"
}
```

**Validation:** amount ≤ captured payment amount minus already-refunded amount.

---

## 3.3 INVOICE MODULE

### Responsibilities
- Generate a PDF invoice for every paid order.
- Store invoice in Cloudflare R2 and link URL in database.
- Allow customers to download their invoice.
- Allow admin to re-generate or email invoice.
- Invoices must include GST breakdown (CGST/SGST/IGST), company details, and customer details.

### Table

#### invoices
```sql
CREATE TABLE invoices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL UNIQUE REFERENCES orders(id),
    invoice_number  TEXT NOT NULL UNIQUE,    -- INV-2026-0001
    invoice_url     TEXT NOT NULL,           -- CDN URL to PDF
    r2_key          TEXT NOT NULL,           -- internal R2 path
    subtotal        NUMERIC(12,2) NOT NULL,
    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    cgst_amount     NUMERIC(12,2) NOT NULL DEFAULT 0,
    sgst_amount     NUMERIC(12,2) NOT NULL DEFAULT 0,
    igst_amount     NUMERIC(12,2) NOT NULL DEFAULT 0,
    shipping_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_amount    NUMERIC(12,2) NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    emailed_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_invoices_order_id ON invoices(order_id);
```

### Invoice Number Sequence
```sql
CREATE SEQUENCE invoice_number_seq START 1;

CREATE OR REPLACE FUNCTION generate_invoice_number()
RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    RETURN 'INV-' || to_char(NOW(), 'YYYY') || '-' ||
           lpad(nextval('invoice_number_seq')::TEXT, 4, '0');
END;
$$;
```

### Invoice PDF Content
Generated using `weasyprint` (Python library):
- Hadha.co company header with logo and GST number
- Invoice number, date, order number
- Customer details (name, shipping address)
- Line items table: product name, SKU, qty, unit price, line total
- Coupon discount row if applicable
- GST breakdown: CGST, SGST (or IGST for interstate), shipping
- Grand total
- Payment method and transaction ID
- "Thank you for shopping with Hadha.co"
- Terms: all sales final for jewellery (subject to return policy)

### APIs

#### GET /orders/{order_number}/invoice
Download invoice PDF.
**Auth:** `get_current_user` (must own order).
**Response:** Redirect to signed CDN URL (30-minute expiry), or stream PDF directly.

#### POST /admin/orders/{id}/invoice/resend
Re-send invoice email.
**Auth:** `require_admin`

#### POST /admin/orders/{id}/invoice/regenerate
Force-regenerate invoice PDF (e.g. after admin corrected data).
**Auth:** `require_admin`

---

## 3.4 SHIPPING MODULE (DELIVERY ONE)

### Architecture
```
Order status = PAID
        ↓
Admin clicks "Create Shipment" in dashboard
        ↓
POST /admin/shipments (FastAPI)
        ↓
DeliveryOneService.create_shipment(order)
        ↓
Delivery One API → returns AWB + tracking URL
        ↓
Insert shipments row
Update orders.shipment_id
Update order status → SHIPPED
Send "Order Shipped" email with tracking link
        ↓
Background worker runs every 5 minutes
        ↓
DeliveryOneService.sync_status(shipment)
        ↓
Update shipment_events
Advance order status as appropriate
```

### Abstraction Layer
`ShippingProvider` ABC ensures Delivery One can be swapped out without touching business logic:
```python
class ShippingProvider(ABC):
    @abstractmethod
    async def create_shipment(self, order: Order) -> ShipmentCreatedResult: ...

    @abstractmethod
    async def track_shipment(self, awb: str) -> ShipmentStatus: ...

    @abstractmethod
    async def cancel_shipment(self, awb: str) -> bool: ...
```

### Tables

#### shipments
```sql
CREATE TABLE shipments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID NOT NULL UNIQUE REFERENCES orders(id),
    provider            TEXT NOT NULL DEFAULT 'delivery_one',
    awb                 TEXT UNIQUE,                -- Air Waybill number
    tracking_url        TEXT,
    pickup_id           TEXT,
    estimated_delivery  DATE,
    status              TEXT NOT NULL DEFAULT 'created'
                            CHECK (status IN ('created','pickup_scheduled','picked_up',
                                              'in_transit','out_for_delivery',
                                              'delivered','failed','returned')),
    weight_kg           NUMERIC(6,3),
    dimensions_cm       JSONB,                      -- {length, width, height}
    cod_amount          NUMERIC(12,2) DEFAULT 0,
    provider_response   JSONB,                      -- full API response
    last_synced_at      TIMESTAMPTZ,
    delivered_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_shipments_order_id ON shipments(order_id);
CREATE INDEX idx_shipments_awb      ON shipments(awb);
CREATE INDEX idx_shipments_status   ON shipments(status);
```

#### shipment_events
```sql
CREATE TABLE shipment_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipment_id  UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    status       TEXT NOT NULL,
    description  TEXT,
    location     TEXT,
    event_time   TIMESTAMPTZ NOT NULL,
    source       TEXT NOT NULL DEFAULT 'webhook'
                     CHECK (source IN ('webhook','sync','manual')),
    raw_payload  JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_shipment_events_shipment_id ON shipment_events(shipment_id);
CREATE INDEX idx_shipment_events_event_time  ON shipment_events(event_time DESC);
```

### Status Mapping (Delivery One → Internal)
| Delivery One Status | Internal Status |
|--------------------|-----------------|
| `PICKUP_CREATED` | `pickup_scheduled` |
| `PICKED_UP` | `picked_up` |
| `IN_TRANSIT` | `in_transit` |
| `OUT_FOR_DELIVERY` | `out_for_delivery` |
| `DELIVERED` | `delivered` |
| `FAILED_DELIVERY` | `failed` |
| `RTO_INITIATED` | `returned` |

### APIs

#### POST /admin/shipments
Create a shipment for an order (calls Delivery One API).
**Auth:** `require_admin`

**Request:**
```json
{
  "order_id": "uuid",
  "weight_kg": 0.150,
  "dimensions_cm": { "length": 10, "width": 8, "height": 4 }
}
```

#### GET /admin/shipments
Paginated shipment list.
**Auth:** `require_admin`

#### GET /admin/shipments/{id}
Shipment detail with full event timeline.
**Auth:** `require_admin`

#### GET /orders/{order_number}/tracking
Customer tracking view.
**Auth:** `get_current_user` (must own order).

**Response:**
```json
{
  "order_number": "HD20260001",
  "awb": "DLV123456789",
  "tracking_url": "https://track.deliveryone.in/DLV123456789",
  "status": "in_transit",
  "estimated_delivery": "2026-06-15",
  "events": [
    { "status": "picked_up", "description": "Shipment picked up", "location": "Pune", "event_time": "2026-06-12T10:30:00Z" },
    { "status": "in_transit", "description": "In transit to Mumbai hub", "location": "Pune", "event_time": "2026-06-12T18:00:00Z" }
  ]
}
```

#### POST /webhooks/delivery-one
Delivery One webhook handler.
**Auth:** Signature verification (HMAC-SHA256, header `X-DeliveryOne-Signature`).
**Idempotency:** Keyed on `event_id` from payload.

---

## 3.5 WEBHOOK FRAMEWORK

### Architecture
All inbound webhooks (Razorpay, Delivery One, and any future providers) flow through a unified framework before provider-specific handling.

```
Inbound POST /webhooks/{provider}
        ↓
1. Extract raw body + signature header
2. Verify HMAC signature (provider-specific algorithm)
3. Store raw event in webhook_events table (BEFORE processing)
4. Check idempotency: has this event_id been processed before?
   → YES: return 200 immediately (already processed)
   → NO: continue
5. Dispatch to provider-specific handler
6. Mark webhook_events.processed_at
7. Return 200
```

If step 5 fails: mark `webhook_events.status = 'failed'`, store error. Retry worker will reprocess.

### Table

#### webhook_events
```sql
CREATE TABLE webhook_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider        TEXT NOT NULL CHECK (provider IN ('razorpay','delivery_one')),
    provider_event_id TEXT NOT NULL,               -- event ID from provider payload
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    signature       TEXT,
    status          TEXT NOT NULL DEFAULT 'received'
                        CHECK (status IN ('received','processing','processed','failed','duplicate')),
    error_message   TEXT,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_event_id)           -- idempotency key
);
CREATE INDEX idx_webhook_events_provider   ON webhook_events(provider, event_type);
CREATE INDEX idx_webhook_events_status     ON webhook_events(status);
CREATE INDEX idx_webhook_events_created    ON webhook_events(created_at DESC);
```

### Retry Strategy
Webhook processing failures are retried by `notification_retry.py` worker:
- Attempt 1 failed → retry at +2 minutes
- Attempt 2 failed → retry at +10 minutes
- Attempt 3 failed → retry at +30 minutes
- Attempt 4+ → `status = 'failed'`, admin alert fired

### Replay Protection
`UNIQUE (provider, provider_event_id)` in `webhook_events` guarantees at-database-level that the same event from the same provider cannot be inserted twice. The application layer checks `status` before dispatching to ensure already-processed events are not re-executed.

---

## 3.6 REVIEWS MODULE

### Responsibilities
- Allow only customers who have received a delivered order to review purchased products (verified purchase).
- Support 1–5 star rating with text review and up to 5 images.
- Moderation queue — reviews must be approved before appearing publicly.
- Allow customers to vote reviews as "helpful".
- Automatically send review request email 48 hours after `DELIVERED` status.

### Tables

#### reviews
```sql
CREATE TABLE reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id      UUID NOT NULL REFERENCES products(id),
    customer_id     UUID NOT NULL REFERENCES profiles(id),
    order_id        UUID NOT NULL REFERENCES orders(id),
    order_item_id   UUID NOT NULL REFERENCES order_items(id),
    rating          INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title           TEXT,
    body            TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','approved','rejected','hidden')),
    moderated_by    UUID REFERENCES profiles(id),
    moderated_at    TIMESTAMPTZ,
    moderation_note TEXT,
    helpful_count   INTEGER NOT NULL DEFAULT 0,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (customer_id, order_item_id)             -- one review per purchased item
);
CREATE INDEX idx_reviews_product_id ON reviews(product_id);
CREATE INDEX idx_reviews_customer_id ON reviews(customer_id);
CREATE INDEX idx_reviews_status      ON reviews(status);
CREATE INDEX idx_reviews_created     ON reviews(created_at DESC);
```

#### review_images
```sql
CREATE TABLE review_images (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id   UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    medium_url  TEXT NOT NULL,
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### review_votes
```sql
CREATE TABLE review_votes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id   UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES profiles(id),
    is_helpful  BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (review_id, customer_id)
);
```

### Eligibility Check
Before allowing a review submission:
```sql
SELECT oi.id
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
WHERE oi.product_id = :product_id
  AND o.customer_id = :customer_id
  AND o.status = 'delivered'
  AND NOT EXISTS (
      SELECT 1 FROM reviews r WHERE r.order_item_id = oi.id
  );
```
If no rows returned, customer is not eligible.

### APIs

#### GET /products/{slug}/reviews
Approved reviews for a product.
**Auth:** None.
**Query params:** `page`, `page_size`, `sort_by` (recent|helpful|rating_high|rating_low), `rating_filter`

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "rating": 5,
      "title": "Absolutely love it!",
      "body": "...",
      "customer_name": "Jane D.",
      "verified_purchase": true,
      "helpful_count": 7,
      "images": [{ "medium_url": "..." }],
      "created_at": "2026-03-15"
    }
  ],
  "total": 12,
  "average_rating": 4.5,
  "rating_distribution": { "5": 8, "4": 2, "3": 1, "2": 0, "1": 1 }
}
```

#### POST /reviews
Submit a review.
**Auth:** `get_current_user`

**Request:**
```json
{
  "product_id": "uuid",
  "order_item_id": "uuid",
  "rating": 5,
  "title": "Beautiful craftsmanship",
  "body": "The ring is exactly as pictured...",
  "image_ids": ["uuid", "uuid"]
}
```

**Validation:** eligibility check, rating 1–5, body max 1000 chars, max 5 images.

#### POST /reviews/{id}/vote
Vote a review helpful or not.
**Auth:** `get_current_user`
**Request:** `{ "is_helpful": true }`

#### GET /admin/reviews
All reviews with moderation queue.
**Auth:** `require_admin`
**Query params:** `status=pending`, `product_id`, `rating`, `page`

#### PATCH /admin/reviews/{id}/status
Approve, reject, or hide a review.
**Auth:** `require_admin`
**Request:** `{ "status": "approved", "moderation_note": "" }`

---

## 3.7 COUPONS MODULE

### Responsibilities
- Create and manage discount coupons.
- Support flat and percentage discounts.
- Enforce minimum order amounts, maximum discount caps, expiry, global usage limits, and per-user limits.
- Coupon validation ALWAYS on backend — never trusted from frontend.

### Tables

#### coupons
```sql
CREATE TABLE coupons (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                TEXT NOT NULL UNIQUE,
    description         TEXT,
    discount_type       TEXT NOT NULL CHECK (discount_type IN ('flat','percentage')),
    discount_value      NUMERIC(12,2) NOT NULL CHECK (discount_value > 0),
    max_discount_amount NUMERIC(12,2),              -- cap for percentage discounts
    min_order_amount    NUMERIC(12,2) NOT NULL DEFAULT 0,
    usage_limit         INTEGER,                    -- null = unlimited
    per_user_limit      INTEGER NOT NULL DEFAULT 1,
    used_count          INTEGER NOT NULL DEFAULT 0,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    starts_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ,
    applicable_to       TEXT NOT NULL DEFAULT 'all'
                            CHECK (applicable_to IN ('all','category','collection','product')),
    applicable_ids      UUID[],                     -- specific IDs when not 'all'
    created_by          UUID REFERENCES profiles(id),
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_coupons_code       ON coupons(code) WHERE is_active = TRUE AND deleted_at IS NULL;
CREATE INDEX idx_coupons_expires_at ON coupons(expires_at);
```

#### coupon_usage
```sql
CREATE TABLE coupon_usage (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coupon_id   UUID NOT NULL REFERENCES coupons(id),
    order_id    UUID NOT NULL REFERENCES orders(id),
    user_id     UUID NOT NULL REFERENCES profiles(id),
    discount_amount NUMERIC(12,2) NOT NULL,
    used_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (coupon_id, order_id)
);
CREATE INDEX idx_coupon_usage_coupon_id ON coupon_usage(coupon_id);
CREATE INDEX idx_coupon_usage_user_id   ON coupon_usage(user_id, coupon_id);
```

### Coupon Validation Logic (server-side)
```python
async def validate_coupon(code: str, subtotal: Decimal, user_id: UUID) -> CouponValidationResult:
    coupon = await coupon_repo.get_active_by_code(code)
    if not coupon:
        raise CouponNotFoundError("Coupon code not found")
    if coupon.expires_at and coupon.expires_at < datetime.utcnow():
        raise CouponExpiredError("Coupon has expired")
    if subtotal < coupon.min_order_amount:
        raise CouponMinimumNotMetError(f"Minimum order ₹{coupon.min_order_amount} required")
    if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
        raise CouponUsageLimitError("Coupon usage limit reached")
    user_usage = await coupon_repo.get_user_usage_count(coupon.id, user_id)
    if user_usage >= coupon.per_user_limit:
        raise CouponUserLimitError("You have already used this coupon")

    if coupon.discount_type == 'flat':
        discount = min(coupon.discount_value, subtotal)
    else:  # percentage
        discount = subtotal * (coupon.discount_value / 100)
        if coupon.max_discount_amount:
            discount = min(discount, coupon.max_discount_amount)

    return CouponValidationResult(coupon=coupon, discount_amount=discount)
```

### APIs

#### POST /cart/coupon (validate + apply)
Already defined in Cart module.

#### GET /admin/coupons
Paginated coupon list.
**Auth:** `require_admin`

#### POST /admin/coupons
Create coupon.
**Auth:** `require_admin`

**Request:**
```json
{
  "code": "WELCOME10",
  "description": "10% off for first-time buyers",
  "discount_type": "percentage",
  "discount_value": 10,
  "max_discount_amount": 200,
  "min_order_amount": 499,
  "usage_limit": 1000,
  "per_user_limit": 1,
  "expires_at": "2026-12-31T23:59:59Z"
}
```

#### PATCH /admin/coupons/{id}
**Auth:** `require_admin`

#### DELETE /admin/coupons/{id}
Soft delete.
**Auth:** `require_admin`

#### GET /admin/coupons/{id}/usage
Usage analytics for a specific coupon.
**Auth:** `require_admin`

---

## 3.8 RETURNS MODULE

### Responsibilities
- Allow customers to request returns within the return window (7 days of delivery).
- Support full and partial returns (multiple items from one order).
- Admin approves/rejects returns.
- Automatically initiate Razorpay refund on return approval.
- Track returned item condition (resellable vs. damaged).

### Tables

#### returns
```sql
CREATE TABLE returns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL REFERENCES orders(id),
    customer_id     UUID NOT NULL REFERENCES profiles(id),
    reason          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'requested'
                        CHECK (status IN ('requested','approved','rejected',
                                          'pickup_scheduled','received','refunded')),
    admin_notes     TEXT,
    reviewed_by     UUID REFERENCES profiles(id),
    reviewed_at     TIMESTAMPTZ,
    pickup_scheduled_at TIMESTAMPTZ,
    received_at     TIMESTAMPTZ,
    refund_id       UUID REFERENCES refunds(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_returns_order_id    ON returns(order_id);
CREATE INDEX idx_returns_customer_id ON returns(customer_id);
CREATE INDEX idx_returns_status      ON returns(status);
```

#### return_items
```sql
CREATE TABLE return_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    return_id       UUID NOT NULL REFERENCES returns(id) ON DELETE CASCADE,
    order_item_id   UUID NOT NULL REFERENCES order_items(id),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    reason          TEXT,
    condition       TEXT CHECK (condition IN ('resellable','damaged','missing')),
    received_qty    INTEGER,                       -- set when item physically received
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Return Eligibility Window
- Return window: 7 days from `orders.delivered_at`.
- Items marked as custom/engraved are non-returnable.

### Return Workflow
```
Customer POST /returns (status = 'requested')
        ↓
Admin reviews in dashboard
        ↓
PATCH /admin/returns/{id}/status → 'approved' or 'rejected'
        ↓ (if approved)
Admin schedules pickup with Delivery One reverse pickup API
Status → 'pickup_scheduled'
        ↓
Items received at warehouse
Admin marks status → 'received', sets condition per item
        ↓
If condition = 'resellable': add back to inventory
If condition = 'damaged': add to damaged stock
        ↓
POST /admin/orders/{id}/refund (initiated automatically)
Status → 'refunded'
```

### APIs

#### POST /returns
**Auth:** `get_current_user`

**Request:**
```json
{
  "order_id": "uuid",
  "reason": "Product is different from photos",
  "items": [
    { "order_item_id": "uuid", "quantity": 1, "reason": "Wrong item received" }
  ]
}
```

**Validation:** order must be `delivered`, within return window, order must belong to customer.

#### GET /returns
Customer's return history.
**Auth:** `get_current_user`

#### GET /admin/returns
All returns.
**Auth:** `require_admin`

#### PATCH /admin/returns/{id}/status
**Auth:** `require_admin`
**Request:** `{ "status": "approved", "admin_notes": "Return approved..." }`

---

## 3.9 TAX MODULE

### Indian GST Rules for Silver Jewellery
- Silver jewellery (HS Code 7113) attracts **3% GST** (1.5% CGST + 1.5% SGST for intra-state, or 3% IGST for inter-state).
- Making charges attract **5% GST** separately if billed separately (most jewellery stores bundle making charges into the item price).
- For simplicity and accuracy for Hadha.co: GST is applied at **3% on the taxable amount** (subtotal after discount). Making charges are bundled into `base_price`.
- **Intra-state sale** (seller in Maharashtra, buyer in Maharashtra): 1.5% CGST + 1.5% SGST.
- **Inter-state sale** (seller in Maharashtra, buyer in any other state): 3% IGST.

### Tax Calculation Service
```python
SELLER_STATE = "Maharashtra"  # loaded from settings

def calculate_gst(
    taxable_amount: Decimal,
    buyer_state: str,
    gst_rate: float = 3.0  # default from settings
) -> TaxBreakdown:
    if buyer_state.lower() == SELLER_STATE.lower():
        # Intra-state: CGST + SGST
        cgst = round(taxable_amount * Decimal(gst_rate / 2 / 100), 2)
        sgst = round(taxable_amount * Decimal(gst_rate / 2 / 100), 2)
        igst = Decimal("0.00")
    else:
        # Inter-state: IGST
        cgst = Decimal("0.00")
        sgst = Decimal("0.00")
        igst = round(taxable_amount * Decimal(gst_rate / 100), 2)

    return TaxBreakdown(cgst=cgst, sgst=sgst, igst=igst, total=cgst + sgst + igst)
```

### Tax on Orders
Tax is calculated at checkout using the buyer's shipping address state. Tax amounts are locked on the `orders` row at time of creation and reflected in the invoice. Tax is never recalculated after order creation.

### app_settings Table (for Tax Configuration)
```sql
CREATE TABLE app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    is_public   BOOLEAN NOT NULL DEFAULT FALSE,  -- if true, exposed via /settings endpoint
    updated_by  UUID REFERENCES profiles(id),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed
INSERT INTO app_settings (key, value, description, is_public) VALUES
('free_shipping_threshold', '999', 'Min order for free shipping (INR)', true),
('shipping_flat_rate', '99', 'Flat shipping charge below threshold (INR)', true),
('gst_rate', '3', 'GST rate % for silver jewellery', false),
('seller_state', 'Maharashtra', 'Seller GSTIN state for intra/inter determination', false),
('seller_gstin', '', 'Seller GST Identification Number', false),
('support_email', 'support@hadha.co', 'Customer support email', true),
('support_phone', '+919000000000', 'Customer support phone', true),
('return_window_days', '7', 'Number of days after delivery allowed for returns', true),
('maintenance_mode', 'false', 'Puts site in maintenance mode', false);
```

### Settings APIs

#### GET /settings
Returns public settings.
**Auth:** None.

#### GET /admin/settings
Returns all settings.
**Auth:** `require_admin`

#### PATCH /admin/settings/{key}
Update a setting value.
**Auth:** `require_super_admin`
**Audit:** logged with old_value, new_value.

---


# HADHA.CO — PART 4: PLATFORM MODULES
> CMS · Analytics · Customer Support · Admin · Security · Fraud Prevention · Audit Logs

---

## 4.1 CMS MODULE

### Responsibilities
- Allow admin to configure homepage content, banners, and promotional sections without code deployments.
- Support multiple banner types: hero, promotional strip, category features.
- Support landing page sections: featured collections, featured products, new arrivals, trending, why-choose-us.
- All CMS content served through a single `GET /cms/home` endpoint consumed by the frontend.

### Tables

#### banners
```sql
CREATE TABLE banners (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    banner_type     TEXT NOT NULL CHECK (banner_type IN ('hero','promo_strip','category_feature','popup')),
    title           TEXT,
    subtitle        TEXT,
    cta_text        TEXT,
    cta_url         TEXT,
    desktop_image_url TEXT,
    mobile_image_url  TEXT,
    background_color  TEXT,
    text_color        TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    starts_at       TIMESTAMPTZ,
    ends_at         TIMESTAMPTZ,
    target_audience TEXT DEFAULT 'all' CHECK (target_audience IN ('all','new_users','returning')),
    created_by      UUID REFERENCES profiles(id),
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_banners_active ON banners(banner_type, is_active, sort_order)
    WHERE is_active = TRUE AND deleted_at IS NULL;
```

#### landing_sections
```sql
CREATE TABLE landing_sections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_key     TEXT NOT NULL UNIQUE,  -- 'featured_collection','new_arrivals','why_choose_us'
    title           TEXT,
    subtitle        TEXT,
    config          JSONB NOT NULL DEFAULT '{}',  -- section-specific config
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_by      UUID REFERENCES profiles(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### cms_pages (for SEO-driven static pages: About, FAQ, Shipping Policy, etc.)
```sql
CREATE TABLE cms_pages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,          -- rich HTML content
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    seo_title   TEXT,
    seo_description TEXT,
    created_by  UUID REFERENCES profiles(id),
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cms_pages_slug ON cms_pages(slug) WHERE is_active = TRUE;
```

### APIs

#### GET /cms/home
Returns all active homepage content in a single payload.
**Auth:** None.

**Response:**
```json
{
  "hero_banners": [ { "id": "uuid", "title": "...", "cta_text": "Shop Now", "cta_url": "/collections/new-arrivals", "desktop_image_url": "...", "mobile_image_url": "..." } ],
  "promo_strip": { "title": "Free Shipping above ₹999 | Use WELCOME10 for 10% Off" },
  "featured_collections": [ { "id": "uuid", "name": "Festive Edit", "slug": "festive-edit", "image_url": "..." } ],
  "new_arrivals": [ { ...product cards... } ],
  "trending": [ { ...product cards... } ],
  "category_features": [ { "name": "Rings", "slug": "rings", "image_url": "..." } ],
  "why_choose_us": { "items": [ { "icon": "hallmark", "title": "BIS Hallmarked", "body": "..." } ] },
  "announcement_bar": { "message": "Free gift wrapping on orders above ₹1499" }
}
```

#### GET /cms/pages/{slug}
**Auth:** None.

#### GET /admin/cms/banners
**Auth:** `require_admin`

#### POST /admin/cms/banners
**Auth:** `require_admin`

#### PATCH /admin/cms/banners/{id}
**Auth:** `require_admin`

#### DELETE /admin/cms/banners/{id}
Soft delete. **Auth:** `require_admin`

#### GET /admin/cms/sections
**Auth:** `require_admin`

#### PATCH /admin/cms/sections/{section_key}
**Auth:** `require_admin`

#### POST /admin/cms/pages
**Auth:** `require_admin`

#### PATCH /admin/cms/pages/{id}
**Auth:** `require_admin`

---

## 4.2 ANALYTICS MODULE

### Responsibilities
- Capture key customer journey events: product views, add-to-cart, checkout started, purchase completed.
- Store raw events for future analysis.
- Power the admin sales dashboard with aggregated views.
- Track conversion funnel (view → cart → checkout → purchase).
- Track top products, categories, and collections.

### Tables

#### analytics_events
```sql
CREATE TABLE analytics_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type  TEXT NOT NULL CHECK (event_type IN (
                    'product_view','add_to_cart','remove_from_cart',
                    'checkout_started','purchase_completed',
                    'search','category_view','collection_view',
                    'wishlist_add','coupon_applied'
                )),
    user_id     UUID REFERENCES profiles(id),   -- null for guests
    session_id  TEXT,
    product_id  UUID REFERENCES products(id),
    category_id UUID REFERENCES categories(id),
    order_id    UUID REFERENCES orders(id),
    metadata    JSONB DEFAULT '{}',             -- event-specific data
    ip_address  INET,
    user_agent  TEXT,
    referrer    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- Partitions by month for performance
CREATE TABLE analytics_events_2026_06 PARTITION OF analytics_events
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
-- Additional monthly partitions generated by migration

CREATE INDEX idx_analytics_event_type ON analytics_events(event_type);
CREATE INDEX idx_analytics_user_id    ON analytics_events(user_id);
CREATE INDEX idx_analytics_product_id ON analytics_events(product_id);
CREATE INDEX idx_analytics_created    ON analytics_events(created_at DESC);
```

### APIs

#### POST /analytics/events
Track a customer event (fire-and-forget, non-blocking).
**Auth:** Optional (guest or authenticated).

**Request:**
```json
{
  "event_type": "product_view",
  "product_id": "uuid",
  "session_id": "sess_xyz",
  "metadata": { "source": "search", "query": "silver ring" }
}
```

**Response:** `202 Accepted` (does not block rendering).

#### GET /admin/analytics/dashboard
Sales summary dashboard.
**Auth:** `require_admin`
**Query params:** `from_date`, `to_date`, `granularity` (day|week|month)

**Response:**
```json
{
  "revenue": { "total": 284500.00, "previous_period": 241200.00, "change_pct": 17.9 },
  "orders": { "total": 312, "previous_period": 267, "change_pct": 16.9 },
  "aov": { "value": 911.86 },
  "conversion_rate": 3.2,
  "top_products": [ { "product_id": "uuid", "name": "...", "revenue": 45000, "units_sold": 90 } ],
  "revenue_by_day": [ { "date": "2026-06-01", "revenue": 9200.00, "orders": 10 } ],
  "orders_by_status": { "pending": 12, "paid": 5, "processing": 8, "shipped": 14, "delivered": 273 }
}
```

#### GET /admin/analytics/products
Product-level analytics.
**Auth:** `require_admin`

#### GET /admin/analytics/customers
Customer acquisition and retention metrics.
**Auth:** `require_admin`

#### GET /admin/analytics/funnel
Conversion funnel: views → cart → checkout → purchase.
**Auth:** `require_admin`

---

## 4.3 CUSTOMER SUPPORT MODULE

### Responsibilities
- Allow customers to submit support tickets.
- Admin can respond to tickets and update their status.
- Link tickets to orders if the inquiry is order-related.
- Email notifications on ticket creation and reply.

### Tables

#### support_tickets
```sql
CREATE TABLE support_tickets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_number   TEXT NOT NULL UNIQUE,       -- SUP-2026-0001
    customer_id     UUID NOT NULL REFERENCES profiles(id),
    order_id        UUID REFERENCES orders(id),
    subject         TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN ('order','product','payment','return','other')),
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','in_progress','resolved','closed')),
    priority        TEXT NOT NULL DEFAULT 'normal'
                        CHECK (priority IN ('low','normal','high','urgent')),
    assigned_to     UUID REFERENCES profiles(id),
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_support_tickets_customer ON support_tickets(customer_id);
CREATE INDEX idx_support_tickets_status   ON support_tickets(status);
CREATE INDEX idx_support_tickets_created  ON support_tickets(created_at DESC);
```

#### support_messages
```sql
CREATE TABLE support_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id   UUID NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    sender_id   UUID NOT NULL REFERENCES profiles(id),
    body        TEXT NOT NULL,
    is_internal BOOLEAN NOT NULL DEFAULT FALSE,  -- admin-only internal notes
    attachments JSONB DEFAULT '[]',              -- array of CDN URLs
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_support_messages_ticket ON support_messages(ticket_id);
```

### APIs

#### POST /support/tickets
**Auth:** `get_current_user`

#### GET /support/tickets
Customer's own tickets.
**Auth:** `get_current_user`

#### GET /support/tickets/{id}
**Auth:** `get_current_user` (must own ticket) OR `require_admin`

#### POST /support/tickets/{id}/messages
Reply to a ticket.
**Auth:** `get_current_user` (must own ticket) OR `require_admin`

#### GET /admin/support/tickets
All tickets with filtering.
**Auth:** `require_admin`

#### PATCH /admin/support/tickets/{id}
Update status, priority, assigned_to.
**Auth:** `require_admin`

---

## 4.4 ADMIN MODULE

### Responsibilities
- Provide a unified admin API surface for managing all business entities.
- Enforce RBAC throughout (no admin route is accessible without valid admin JWT + RBAC check).
- Admin routes are prefixed `/admin/`.
- All admin write operations are logged to `audit_logs`.

### Admin API Surface (summary by domain)

| Domain | Endpoints |
|--------|-----------|
| Users | GET /admin/users, PATCH /admin/users/{id}, PATCH /admin/users/{id}/role, PATCH /admin/users/{id}/status |
| Products | GET/POST /admin/products, GET/PATCH/DELETE /admin/products/{id}, variant/image sub-routes |
| Categories | GET/POST /admin/categories, PATCH/DELETE /admin/categories/{id} |
| Collections | GET/POST /admin/collections, PATCH/DELETE /admin/collections/{id}, product management |
| Inventory | GET /admin/inventory, PATCH /admin/inventory/{id}, POST /admin/inventory/{id}/adjust |
| Orders | GET /admin/orders, PATCH /admin/orders/{id}/status, POST /admin/orders/{id}/refund |
| Shipments | POST /admin/shipments, GET /admin/shipments, GET /admin/shipments/{id} |
| Payments | GET /admin/payments, GET /admin/payments/{id} |
| Reviews | GET /admin/reviews, PATCH /admin/reviews/{id}/status |
| Coupons | GET/POST /admin/coupons, PATCH/DELETE /admin/coupons/{id}, GET /admin/coupons/{id}/usage |
| Returns | GET /admin/returns, PATCH /admin/returns/{id}/status |
| CMS | All /admin/cms/* routes |
| Analytics | GET /admin/analytics/* |
| Support | GET /admin/support/tickets, PATCH /admin/support/tickets/{id} |
| Settings | GET /admin/settings, PATCH /admin/settings/{key} |
| Audit Logs | GET /admin/audit-logs |
| Fraud | GET /admin/fraud/signals |
| Feature Flags | GET/PATCH /admin/feature-flags |

### Admin Dashboard Summary Endpoint

#### GET /admin/dashboard
Returns a concise KPI snapshot for the admin home screen.
**Auth:** `require_admin`

**Response:**
```json
{
  "today": {
    "orders": 8,
    "revenue": 7320.00,
    "new_customers": 3
  },
  "pending_actions": {
    "orders_to_process": 5,
    "reviews_to_moderate": 3,
    "returns_to_review": 1,
    "support_tickets_open": 7,
    "low_stock_items": 4
  },
  "recent_orders": [ { ...order summary... } ]
}
```

---

## 4.5 SECURITY

### JWT Security
- All protected routes verify the Supabase JWT on every request — no caching of token validity.
- JWT expiry is enforced; expired tokens return `401`.
- JWT secret (`SUPABASE_JWT_SECRET`) is never logged or exposed.

### Rate Limiting
Redis-backed sliding window rate limiter applied per endpoint category:

| Endpoint Category | Limit | Window |
|------------------|-------|--------|
| Auth (login/signup) | 10 req | 1 min per IP |
| General API | 200 req | 1 min per user |
| File uploads | 20 req | 1 min per user |
| Webhook | 500 req | 1 min per IP |
| Admin API | 300 req | 1 min per admin |

Rate limit headers returned: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
Exceeded: `429 Too Many Requests` with `Retry-After` header.

### Input Validation
- All request bodies validated by Pydantic V2 before reaching service layer.
- All string inputs are stripped of leading/trailing whitespace.
- File uploads: MIME type validated by reading magic bytes (not just Content-Type header).
- SQL injection: impossible via SQLAlchemy parameterized queries (never use raw f-string SQL).
- SSRF prevention: any URL fields that trigger server-side HTTP requests are validated against an allowlist.

### Security Headers (Nginx + FastAPI middleware)
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: default-src 'self'; img-src 'self' https://cdn.hadha.co data:; ...
```

### CORS Configuration
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, settings.ADMIN_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
```

### CSRF Protection
- REST API is stateless (Bearer token based) — no session cookies → CSRF is not applicable for the API.
- If httpOnly cookies are used for token storage in future, implement Double Submit Cookie pattern.

### Webhook Signature Verification
- Razorpay: HMAC-SHA256 of raw request body using `RAZORPAY_WEBHOOK_SECRET`. Verified via `X-Razorpay-Signature` header.
- Delivery One: HMAC-SHA256 using `DELIVERY_ONE_WEBHOOK_SECRET`. Verified via `X-DeliveryOne-Signature` header.
- If signature verification fails: return `401`, log to `audit_logs` with event type `webhook_signature_failure`.

### Secrets Management
- All secrets in environment variables, never in source code.
- TOTP secrets encrypted at rest using Fernet symmetric encryption (`ENCRYPTION_KEY`).
- `cost_price` field on products never returned in public API responses.
- R2 internal paths never returned in API responses.
- `raw_payload` in `payments` and `webhook_events` accessible only to super_admin.

### Account Lockout
- 5 consecutive failed login attempts from same IP → temporary lockout via Redis key (15-minute TTL).
- Admin accounts: 3 consecutive failures → account flagged in `fraud_signals`.
- Suspicious login detection: new device/IP login for admin → email alert to admin email.

---

## 4.6 FRAUD PREVENTION

### Tables

#### fraud_signals
```sql
CREATE TABLE fraud_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES profiles(id),
    ip_address      INET,
    signal_type     TEXT NOT NULL CHECK (signal_type IN (
                        'duplicate_order','velocity_order','multiple_payment_failures',
                        'suspicious_login','account_lockout','unusual_refund_pattern',
                        'coupon_abuse','bot_detection'
                    )),
    severity        TEXT NOT NULL DEFAULT 'medium'
                        CHECK (severity IN ('low','medium','high','critical')),
    description     TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}',
    is_resolved     BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by     UUID REFERENCES profiles(id),
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fraud_signals_user_id    ON fraud_signals(user_id);
CREATE INDEX idx_fraud_signals_ip         ON fraud_signals(ip_address);
CREATE INDEX idx_fraud_signals_type       ON fraud_signals(signal_type);
CREATE INDEX idx_fraud_signals_resolved   ON fraud_signals(is_resolved) WHERE is_resolved = FALSE;
```

### Detection Rules

#### Duplicate Order Detection
Before creating a new order, check:
```sql
SELECT COUNT(*) FROM orders
WHERE customer_id = :customer_id
  AND status IN ('pending','paid','processing')
  AND total_amount = :total_amount
  AND created_at >= NOW() - INTERVAL '10 minutes';
```
If count > 0 and `idempotency_key` is different: flag as `duplicate_order`.

#### Velocity Check
```sql
SELECT COUNT(*) FROM orders
WHERE customer_id = :customer_id
  AND created_at >= NOW() - INTERVAL '24 hours';
```
If count > 10: flag as `velocity_order`, notify admin.

#### Multiple Payment Failures
```sql
SELECT COUNT(*) FROM payments
WHERE order_id IN (SELECT id FROM orders WHERE customer_id = :customer_id)
  AND status = 'failed'
  AND created_at >= NOW() - INTERVAL '1 hour';
```
If count >= 3: flag as `multiple_payment_failures`.

#### Coupon Abuse
```sql
SELECT COUNT(DISTINCT user_id) FROM coupon_usage
WHERE coupon_id = :coupon_id
  AND used_at >= NOW() - INTERVAL '24 hours';
```
Unusual cluster of same coupon from different accounts → flag `coupon_abuse`.

### Admin Fraud Dashboard

#### GET /admin/fraud/signals
**Auth:** `require_admin`
Returns unresolved fraud signals with filters.

#### PATCH /admin/fraud/signals/{id}/resolve
**Auth:** `require_admin`

---

## 4.7 AUDIT LOGS

### Responsibilities
- Immutable log of all significant system actions.
- Every admin write action is logged automatically via middleware.
- Authentication events (login, logout, password reset, role changes) are logged.
- Inventory changes, price changes, coupon changes, refunds are logged.
- Audit logs are never deleted or modified.

### Table

#### audit_logs
```sql
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id        UUID REFERENCES profiles(id),  -- null for system/webhook actions
    actor_email     TEXT,                           -- denormalized snapshot
    actor_role      TEXT,
    action          TEXT NOT NULL,                  -- e.g. 'product.price_changed'
    resource_type   TEXT NOT NULL,                  -- e.g. 'product'
    resource_id     UUID,
    old_value       JSONB,
    new_value       JSONB,
    metadata        JSONB DEFAULT '{}',
    ip_address      INET,
    user_agent      TEXT,
    request_id      TEXT,                           -- X-Request-ID
    source          TEXT NOT NULL DEFAULT 'api'
                        CHECK (source IN ('api','webhook','system','worker')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

CREATE TABLE audit_logs_2026_06 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE INDEX idx_audit_logs_actor_id      ON audit_logs(actor_id);
CREATE INDEX idx_audit_logs_resource      ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_action        ON audit_logs(action);
CREATE INDEX idx_audit_logs_created       ON audit_logs(created_at DESC);
```

### Audited Actions (complete list)
| Action | Trigger |
|--------|---------|
| `auth.login` | Successful JWT verification |
| `auth.logout` | POST /auth/logout |
| `auth.login_failed` | JWT invalid or user inactive |
| `auth.password_reset` | Supabase password reset callback |
| `auth.2fa_enabled` | Admin 2FA setup completed |
| `user.role_changed` | PATCH /admin/users/{id}/role |
| `user.status_changed` | PATCH /admin/users/{id}/status |
| `product.created` | POST /admin/products |
| `product.updated` | PATCH /admin/products/{id} |
| `product.price_changed` | Price field changed in PATCH |
| `product.deleted` | DELETE /admin/products/{id} |
| `inventory.adjusted` | POST /admin/inventory/{id}/adjust |
| `order.status_changed` | Any order status transition |
| `order.cancelled` | POST /orders/{id}/cancel |
| `payment.refund_initiated` | POST /admin/orders/{id}/refund |
| `coupon.created` | POST /admin/coupons |
| `coupon.updated` | PATCH /admin/coupons/{id} |
| `coupon.deleted` | DELETE /admin/coupons/{id} |
| `review.moderated` | PATCH /admin/reviews/{id}/status |
| `settings.updated` | PATCH /admin/settings/{key} |
| `webhook.signature_failure` | Invalid webhook signature |

### Audit Middleware
```python
# app/middleware/audit_middleware.py
# Automatically logs all ADMIN write operations (POST/PUT/PATCH/DELETE to /admin/* routes)
# Captures: actor, action derived from method+path, resource_id from path, request_id, IP, user_agent
# Implementation: FastAPI middleware that post-processes response, logs only on 2xx responses
```

### APIs

#### GET /admin/audit-logs
**Auth:** `require_admin`
**Query params:** `actor_id`, `resource_type`, `resource_id`, `action`, `from_date`, `to_date`, `page`, `page_size`

**Response:** Paginated list of audit log entries.

---


# HADHA.CO — PART 5: INFRASTRUCTURE & DATABASE
> Database · SQL Structure · Supabase Setup · Views · Indexes · Triggers · RLS · Performance · Monitoring · Deployment · Backup · Feature Flags · Business Rules · Seed Data · Implementation Order

---

## 5.1 DATABASE ARCHITECTURE

### Principles
- **Database First:** All tables, constraints, indexes, views, triggers, and RLS policies are defined as versioned SQL files. No table is created manually through the dashboard. Running `setup.sql` creates everything from scratch.
- **UUID Primary Keys:** All tables use `gen_random_uuid()` (from `pgcrypto`).
- **Soft Deletes:** All business entity tables have `deleted_at TIMESTAMPTZ`. Hard deletes are forbidden for `products`, `orders`, `customers`, `reviews`, `coupons`.
- **Audit Fields:** All tables have `created_at` and `updated_at`. Write-heavy tables also have `created_by` and `updated_by`.
- **Immutable Financial Records:** `orders`, `order_items`, `payments`, `invoices` rows are never modified after creation except for status fields.
- **Partitioned Tables:** `analytics_events` and `audit_logs` are range-partitioned by month to keep query performance stable as data grows.

### Connection Pooling
- SQLAlchemy async engine with `pool_size=20`, `max_overflow=10`, `pool_timeout=30`.
- Use `asyncpg` driver.
- Supabase connection pooler (PgBouncer) at port 5432 in session mode — use for transactional workloads.
- For direct migrations (Alembic), connect directly to port 5432 (not through PgBouncer).

---

## 5.2 SQL FILE STRUCTURE

### 000_extensions.sql
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
```

### setup.sql (master script)
```sql
-- HADHA.CO — Master Database Setup Script
-- Run this entire file in Supabase SQL Editor to create the complete schema.
-- Execution order is mandatory.

\i sql/000_extensions.sql
\i sql/001_profiles.sql
\i sql/002_catalog.sql
\i sql/003_inventory.sql
\i sql/004_cart.sql
\i sql/005_orders.sql
\i sql/006_payments.sql
\i sql/007_shipping.sql
\i sql/008_reviews.sql
\i sql/009_coupons.sql
\i sql/010_cms.sql
\i sql/011_analytics.sql
\i sql/012_notifications.sql
\i sql/013_audit_logs.sql
\i sql/014_seo.sql
\i sql/015_webhooks.sql
\i sql/016_fraud.sql
\i sql/017_support.sql
\i sql/018_feature_flags.sql
\i sql/019_views.sql
\i sql/020_indexes.sql
\i sql/021_rls.sql
\i sql/022_triggers.sql
\i sql/023_seed_data.sql

-- Verify setup
SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
```

---

## 5.3 SUPABASE SETUP

### Auth Configuration (via SQL where possible)
```sql
-- Auth email templates and URL config must be done in Dashboard (manual step).
-- Everything below is via SQL.

-- Ensure auth schema is accessible
GRANT USAGE ON SCHEMA auth TO postgres, service_role;

-- The profiles trigger references auth.users — ensure trigger function has SECURITY DEFINER
-- to allow cross-schema access (defined in 022_triggers.sql)
```

### RLS Enable Statements
```sql
-- Placed in 021_rls.sql, before all policies
ALTER TABLE profiles                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE addresses                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE wishlists                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE wishlist_items            ENABLE ROW LEVEL SECURITY;
ALTER TABLE carts                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE cart_items                ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items               ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_preferences  ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_tickets           ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_messages          ENABLE ROW LEVEL SECURITY;
-- Tables accessed only by service_role (backend) do NOT need RLS enabled:
-- payments, refunds, inventory, shipments, audit_logs, webhook_events, fraud_signals
-- These tables are protected by not being exposed through the anon/authenticated keys.
```

---

## 5.4 VIEWS

### product_listing_view
Used by `GET /products` — joins products with primary image and inventory summary.
```sql
CREATE VIEW product_listing_view AS
SELECT
    p.id,
    p.sku,
    p.slug,
    p.name,
    p.short_description,
    p.category_id,
    c.name AS category_name,
    c.slug AS category_slug,
    p.metal_type,
    p.weight_grams,
    p.base_price,
    p.sale_price,
    COALESCE(p.sale_price, p.base_price) AS effective_price,
    p.is_featured,
    p.is_new_arrival,
    p.is_bestseller,
    p.gender,
    p.status,
    p.created_at,

    -- Primary image
    pi.thumbnail_url AS thumbnail_url,
    pi.medium_url    AS medium_url,
    pi.large_url     AS large_url,

    -- Inventory
    COALESCE(inv.qty_on_hand - inv.qty_reserved, 0) AS qty_available,
    CASE WHEN COALESCE(inv.qty_on_hand - inv.qty_reserved, 0) > 0
         THEN 'in_stock' ELSE 'out_of_stock' END AS stock_status,

    -- Review aggregates
    COALESCE(r.avg_rating, 0)   AS average_rating,
    COALESCE(r.review_count, 0) AS review_count

FROM products p
LEFT JOIN categories c ON c.id = p.category_id
LEFT JOIN product_images pi ON pi.product_id = p.id AND pi.is_primary = TRUE
LEFT JOIN (
    SELECT product_id,
           SUM(qty_on_hand - qty_reserved) AS qty_on_hand,
           SUM(qty_reserved) AS qty_reserved
    FROM inventory GROUP BY product_id
) inv ON inv.product_id = p.id
LEFT JOIN (
    SELECT product_id,
           ROUND(AVG(rating)::numeric, 1) AS avg_rating,
           COUNT(*) AS review_count
    FROM reviews WHERE status = 'approved'
    GROUP BY product_id
) r ON r.product_id = p.id
WHERE p.deleted_at IS NULL;
```

### product_details_view
Extends `product_listing_view` with full description, attributes, and all images.
```sql
CREATE VIEW product_details_view AS
SELECT
    plv.*,
    p.description,
    p.hallmark_number,
    p.purity,
    p.length_mm, p.width_mm, p.height_mm, p.diameter_mm,
    p.making_charges,
    p.occasion,
    p.style,
    p.finish,
    p.stone_type,
    p.stone_color,
    p.care_instructions,
    p.certification_info,
    p.is_customizable,
    p.has_variants,
    p.seo_title,
    p.seo_description,
    p.seo_keywords
FROM product_listing_view plv
JOIN products p ON p.id = plv.id;
```

### inventory_summary_view
```sql
CREATE VIEW inventory_summary_view AS
SELECT
    i.id,
    i.sku,
    i.product_id,
    p.name AS product_name,
    i.variant_id,
    pv.name AS variant_name,
    i.qty_on_hand,
    i.qty_reserved,
    i.qty_damaged,
    i.qty_returned,
    GREATEST(i.qty_on_hand - i.qty_reserved, 0) AS qty_available,
    i.low_stock_threshold,
    CASE WHEN (i.qty_on_hand - i.qty_reserved) <= i.low_stock_threshold
         THEN TRUE ELSE FALSE END AS is_low_stock,
    CASE WHEN (i.qty_on_hand - i.qty_reserved) <= 0
         THEN TRUE ELSE FALSE END AS is_out_of_stock,
    i.last_reconciled_at,
    i.updated_at
FROM inventory i
JOIN products p ON p.id = i.product_id
LEFT JOIN product_variants pv ON pv.id = i.variant_id;
```

### customer_orders_view
```sql
CREATE VIEW customer_orders_view AS
SELECT
    o.id,
    o.order_number,
    o.customer_id,
    o.status,
    o.total_amount,
    o.item_count,
    o.paid_at,
    o.created_at,
    s.awb,
    s.tracking_url,
    s.status AS shipment_status,
    s.estimated_delivery,
    p.status AS payment_status,
    p.method AS payment_method,
    (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.id) AS item_count
FROM orders o
LEFT JOIN shipments s ON s.id = o.shipment_id
LEFT JOIN payments p ON p.id = o.payment_id
WHERE o.deleted_at IS NULL;
```

### admin_order_dashboard_view
```sql
CREATE VIEW admin_order_dashboard_view AS
SELECT
    o.id,
    o.order_number,
    o.status,
    o.total_amount,
    o.paid_at,
    o.created_at,
    pr.full_name AS customer_name,
    pr.email AS customer_email,
    pr.phone AS customer_phone,
    s.awb,
    s.status AS shipment_status,
    (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.id) AS item_count
FROM orders o
JOIN profiles pr ON pr.id = o.customer_id
LEFT JOIN shipments s ON s.id = o.shipment_id
WHERE o.deleted_at IS NULL;
```

### sales_dashboard_view (materialized, refreshed every hour)
```sql
CREATE MATERIALIZED VIEW sales_dashboard_view AS
SELECT
    DATE_TRUNC('day', o.created_at)::DATE AS date,
    COUNT(*) FILTER (WHERE o.status NOT IN ('cancelled'))  AS total_orders,
    COUNT(*) FILTER (WHERE o.status = 'delivered')         AS delivered_orders,
    COUNT(*) FILTER (WHERE o.status = 'cancelled')         AS cancelled_orders,
    SUM(o.total_amount) FILTER (WHERE o.status NOT IN ('cancelled','pending')) AS revenue,
    ROUND(AVG(o.total_amount) FILTER (WHERE o.status NOT IN ('cancelled','pending')), 2) AS aov,
    COUNT(DISTINCT o.customer_id)                          AS unique_customers
FROM orders o
WHERE o.deleted_at IS NULL
GROUP BY DATE_TRUNC('day', o.created_at)::DATE
ORDER BY date DESC;

CREATE UNIQUE INDEX idx_sales_dashboard_view_date ON sales_dashboard_view(date);
```

### top_products_view (materialized, refreshed daily)
```sql
CREATE MATERIALIZED VIEW top_products_view AS
SELECT
    oi.product_id,
    p.name,
    p.slug,
    p.metal_type,
    pi.thumbnail_url,
    SUM(oi.quantity)   AS total_units_sold,
    SUM(oi.line_total) AS total_revenue,
    COUNT(DISTINCT o.id) AS order_count
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
LEFT JOIN product_images pi ON pi.product_id = p.id AND pi.is_primary = TRUE
WHERE o.status NOT IN ('cancelled','pending')
  AND o.created_at >= NOW() - INTERVAL '90 days'
GROUP BY oi.product_id, p.name, p.slug, p.metal_type, pi.thumbnail_url
ORDER BY total_revenue DESC;

CREATE UNIQUE INDEX idx_top_products_view ON top_products_view(product_id);
```

### review_summary_view
```sql
CREATE VIEW review_summary_view AS
SELECT
    r.product_id,
    COUNT(*) FILTER (WHERE r.status = 'approved')    AS approved_count,
    COUNT(*) FILTER (WHERE r.status = 'pending')     AS pending_count,
    COUNT(*) FILTER (WHERE r.status = 'rejected')    AS rejected_count,
    ROUND(AVG(r.rating) FILTER (WHERE r.status = 'approved'), 1) AS avg_rating,
    COUNT(*) FILTER (WHERE r.rating = 5 AND r.status = 'approved') AS five_star,
    COUNT(*) FILTER (WHERE r.rating = 4 AND r.status = 'approved') AS four_star,
    COUNT(*) FILTER (WHERE r.rating = 3 AND r.status = 'approved') AS three_star,
    COUNT(*) FILTER (WHERE r.rating = 2 AND r.status = 'approved') AS two_star,
    COUNT(*) FILTER (WHERE r.rating = 1 AND r.status = 'approved') AS one_star
FROM reviews r
WHERE r.deleted_at IS NULL
GROUP BY r.product_id;
```

---

## 5.5 INDEXES

All indexes are defined in `020_indexes.sql`. The following is the complete canonical index list.

```sql
-- ─── PRODUCTS ───────────────────────────────────────────────────────────────
CREATE INDEX idx_products_slug          ON products(slug);
CREATE INDEX idx_products_category_id   ON products(category_id);
CREATE INDEX idx_products_status        ON products(status);
CREATE INDEX idx_products_is_featured   ON products(is_featured) WHERE is_featured = TRUE;
CREATE INDEX idx_products_is_new        ON products(is_new_arrival) WHERE is_new_arrival = TRUE;
CREATE INDEX idx_products_is_bestseller ON products(is_bestseller) WHERE is_bestseller = TRUE;
CREATE INDEX idx_products_metal_type    ON products(metal_type);
CREATE INDEX idx_products_gender        ON products(gender);
CREATE INDEX idx_products_price         ON products(COALESCE(sale_price, base_price));
CREATE INDEX idx_products_search        ON products USING GIN(search_vector);
CREATE INDEX idx_products_name_trgm     ON products USING GIN(name gin_trgm_ops);
CREATE INDEX idx_products_deleted       ON products(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_products_created_desc  ON products(created_at DESC);
-- Composite: active products by category sorted by price
CREATE INDEX idx_products_cat_price     ON products(category_id, COALESCE(sale_price, base_price))
    WHERE status = 'active' AND deleted_at IS NULL;

-- ─── CATEGORIES ─────────────────────────────────────────────────────────────
CREATE INDEX idx_categories_slug        ON categories(slug);
CREATE INDEX idx_categories_parent      ON categories(parent_id);
CREATE INDEX idx_categories_active      ON categories(is_active) WHERE is_active = TRUE;

-- ─── COLLECTIONS ─────────────────────────────────────────────────────────────
CREATE INDEX idx_collections_slug       ON collections(slug);
CREATE INDEX idx_collections_active     ON collections(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_collections_featured   ON collections(is_featured) WHERE is_featured = TRUE;

-- ─── INVENTORY ───────────────────────────────────────────────────────────────
CREATE INDEX idx_inventory_product_id   ON inventory(product_id);
CREATE INDEX idx_inventory_sku          ON inventory(sku);
CREATE INDEX idx_inventory_low_stock    ON inventory(qty_on_hand, low_stock_threshold);

-- ─── ORDERS ──────────────────────────────────────────────────────────────────
CREATE INDEX idx_orders_customer_id     ON orders(customer_id);
CREATE INDEX idx_orders_status          ON orders(status);
CREATE INDEX idx_orders_created_at      ON orders(created_at DESC);
CREATE INDEX idx_orders_order_number    ON orders(order_number);
CREATE INDEX idx_orders_cart_id         ON orders(cart_id);
CREATE INDEX idx_orders_payment_id      ON orders(payment_id);
-- Composite: admin order list (status + date)
CREATE INDEX idx_orders_status_created  ON orders(status, created_at DESC)
    WHERE deleted_at IS NULL;

-- ─── PAYMENTS ────────────────────────────────────────────────────────────────
CREATE INDEX idx_payments_order_id             ON payments(order_id);
CREATE INDEX idx_payments_razorpay_order_id    ON payments(razorpay_order_id);
CREATE INDEX idx_payments_razorpay_payment_id  ON payments(razorpay_payment_id);
CREATE INDEX idx_payments_status               ON payments(status);

-- ─── SHIPMENTS ───────────────────────────────────────────────────────────────
CREATE INDEX idx_shipments_order_id     ON shipments(order_id);
CREATE INDEX idx_shipments_awb          ON shipments(awb);
CREATE INDEX idx_shipments_status       ON shipments(status);

-- ─── REVIEWS ─────────────────────────────────────────────────────────────────
CREATE INDEX idx_reviews_product_id     ON reviews(product_id);
CREATE INDEX idx_reviews_customer_id    ON reviews(customer_id);
CREATE INDEX idx_reviews_status         ON reviews(status);
CREATE INDEX idx_reviews_created        ON reviews(created_at DESC);
-- Composite: approved reviews by product
CREATE INDEX idx_reviews_product_approved ON reviews(product_id, status, created_at DESC)
    WHERE status = 'approved' AND deleted_at IS NULL;

-- ─── COUPONS ─────────────────────────────────────────────────────────────────
CREATE INDEX idx_coupons_code           ON coupons(code) WHERE is_active = TRUE AND deleted_at IS NULL;
CREATE INDEX idx_coupons_expires_at     ON coupons(expires_at);

-- ─── ANALYTICS ───────────────────────────────────────────────────────────────
CREATE INDEX idx_analytics_event_type   ON analytics_events(event_type);
CREATE INDEX idx_analytics_user_id      ON analytics_events(user_id);
CREATE INDEX idx_analytics_product_id   ON analytics_events(product_id);
CREATE INDEX idx_analytics_created      ON analytics_events(created_at DESC);

-- ─── AUDIT LOGS ──────────────────────────────────────────────────────────────
CREATE INDEX idx_audit_logs_actor       ON audit_logs(actor_id);
CREATE INDEX idx_audit_logs_resource    ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_action      ON audit_logs(action);
CREATE INDEX idx_audit_logs_created     ON audit_logs(created_at DESC);

-- ─── SEARCH ──────────────────────────────────────────────────────────────────
CREATE INDEX idx_search_history_query   ON search_history USING GIN(query gin_trgm_ops);
```

---

## 5.6 TRIGGERS

All triggers defined in `022_triggers.sql`.

```sql
-- ── 1. Auto-create profile on Supabase Auth signup ──────────────────────────
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, avatar_url, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        NEW.raw_user_meta_data->>'avatar_url',
        'customer'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ── 2. Auto-update updated_at on all business tables ───────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- Apply to every table that has updated_at:
CREATE TRIGGER set_updated_at_profiles      BEFORE UPDATE ON profiles      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_products      BEFORE UPDATE ON products      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_categories    BEFORE UPDATE ON categories    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_collections   BEFORE UPDATE ON collections   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_inventory     BEFORE UPDATE ON inventory     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_carts         BEFORE UPDATE ON carts         FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_orders        BEFORE UPDATE ON orders        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_payments      BEFORE UPDATE ON payments      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_shipments     BEFORE UPDATE ON shipments     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_reviews       BEFORE UPDATE ON reviews       FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_coupons       BEFORE UPDATE ON coupons       FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_returns       BEFORE UPDATE ON returns       FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER set_updated_at_refunds       BEFORE UPDATE ON refunds       FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── 3. Product search vector auto-update ────────────────────────────────────
CREATE OR REPLACE FUNCTION update_product_search_vector()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        coalesce(NEW.name, '') || ' ' ||
        coalesce(NEW.short_description, '') || ' ' ||
        coalesce(NEW.description, '') || ' ' ||
        coalesce(NEW.metal_type, '') || ' ' ||
        coalesce(NEW.purity, '') || ' ' ||
        coalesce(array_to_string(NEW.seo_keywords, ' '), '')
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER trgr_product_search_vector
    BEFORE INSERT OR UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_product_search_vector();

-- ── 4. Enforce single default address per user ──────────────────────────────
CREATE OR REPLACE FUNCTION enforce_single_default_address()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.is_default = TRUE THEN
        UPDATE addresses
        SET is_default = FALSE
        WHERE user_id = NEW.user_id AND id <> NEW.id AND is_default = TRUE;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trgr_single_default_address
    AFTER INSERT OR UPDATE ON addresses
    FOR EACH ROW WHEN (NEW.is_default = TRUE)
    EXECUTE FUNCTION enforce_single_default_address();

-- ── 5. Auto-increment coupon used_count ─────────────────────────────────────
CREATE OR REPLACE FUNCTION increment_coupon_used_count()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE coupons SET used_count = used_count + 1 WHERE id = NEW.coupon_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trgr_coupon_used_count
    AFTER INSERT ON coupon_usage
    FOR EACH ROW EXECUTE FUNCTION increment_coupon_used_count();

-- ── 6. Auto-update review helpful_count ─────────────────────────────────────
CREATE OR REPLACE FUNCTION update_review_helpful_count()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE reviews
    SET helpful_count = (
        SELECT COUNT(*) FROM review_votes WHERE review_id = NEW.review_id AND is_helpful = TRUE
    )
    WHERE id = NEW.review_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trgr_review_helpful_count
    AFTER INSERT OR UPDATE OR DELETE ON review_votes
    FOR EACH ROW EXECUTE FUNCTION update_review_helpful_count();

-- ── 7. Expire inventory reservations ────────────────────────────────────────
-- Called by worker; also enforced on every reservation check:
CREATE OR REPLACE FUNCTION release_expired_reservations()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    WITH expired AS (
        UPDATE inventory_reservations
        SET status = 'expired'
        WHERE status = 'active' AND expires_at < NOW()
        RETURNING id, inventory_id, quantity
    )
    UPDATE inventory i
    SET qty_reserved = i.qty_reserved - e.quantity
    FROM expired e
    WHERE i.id = e.inventory_id;
END;
$$;
```

---

## 5.7 RLS POLICIES

All policies defined in `021_rls.sql`. The backend uses `service_role` key which bypasses RLS. These policies protect direct Supabase client access (e.g. from `supabase-js` in the frontend).

```sql
-- ─── PROFILES ────────────────────────────────────────────────────────────────
CREATE POLICY profiles_select_own ON profiles
    FOR SELECT TO authenticated
    USING (auth.uid() = id);

CREATE POLICY profiles_update_own ON profiles
    FOR UPDATE TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- Admin can read all profiles
CREATE POLICY profiles_admin_all ON profiles
    FOR ALL TO authenticated
    USING (
        EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin'))
    );

-- ─── ADDRESSES ───────────────────────────────────────────────────────────────
CREATE POLICY addresses_own ON addresses
    FOR ALL TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ─── WISHLISTS ───────────────────────────────────────────────────────────────
CREATE POLICY wishlists_own ON wishlists
    FOR ALL TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY wishlist_items_own ON wishlist_items
    FOR ALL TO authenticated
    USING (
        EXISTS (SELECT 1 FROM wishlists w WHERE w.id = wishlist_id AND w.user_id = auth.uid())
    );

-- ─── CARTS ───────────────────────────────────────────────────────────────────
CREATE POLICY carts_own ON carts
    FOR ALL TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY cart_items_own ON cart_items
    FOR ALL TO authenticated
    USING (
        EXISTS (SELECT 1 FROM carts c WHERE c.id = cart_id AND c.user_id = auth.uid())
    );

-- ─── ORDERS ──────────────────────────────────────────────────────────────────
CREATE POLICY orders_select_own ON orders
    FOR SELECT TO authenticated
    USING (customer_id = auth.uid());

CREATE POLICY orders_admin_all ON orders
    FOR ALL TO authenticated
    USING (
        EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin'))
    );

-- ─── REVIEWS ─────────────────────────────────────────────────────────────────
-- Customers can read approved reviews for any product
CREATE POLICY reviews_select_approved ON reviews
    FOR SELECT TO anon, authenticated
    USING (status = 'approved' AND deleted_at IS NULL);

-- Customers can insert/update their own reviews
CREATE POLICY reviews_own ON reviews
    FOR ALL TO authenticated
    USING (customer_id = auth.uid())
    WITH CHECK (customer_id = auth.uid());

-- Admin can manage all reviews
CREATE POLICY reviews_admin_all ON reviews
    FOR ALL TO authenticated
    USING (
        EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin'))
    );

-- ─── NOTIFICATION PREFERENCES ────────────────────────────────────────────────
CREATE POLICY notif_prefs_own ON notification_preferences
    FOR ALL TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ─── SUPPORT TICKETS ─────────────────────────────────────────────────────────
CREATE POLICY tickets_own ON support_tickets
    FOR ALL TO authenticated
    USING (customer_id = auth.uid())
    WITH CHECK (customer_id = auth.uid());

CREATE POLICY tickets_admin ON support_tickets
    FOR ALL TO authenticated
    USING (
        EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin'))
    );

-- ─── PRODUCTS (public read, admin write) ─────────────────────────────────────
CREATE POLICY products_public_read ON products
    FOR SELECT TO anon, authenticated
    USING (status = 'active' AND deleted_at IS NULL);

CREATE POLICY products_admin_all ON products
    FOR ALL TO authenticated
    USING (
        EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin'))
    );
```

---

## 5.8 PERFORMANCE

### Query Performance Targets
| Query | Target | Strategy |
|-------|--------|----------|
| GET /products (listing) | < 100ms | `product_listing_view` + composite index on (status, category_id, price) |
| GET /products/{slug} | < 200ms | `product_details_view` + Redis cache (TTL 5 min) |
| GET /admin/dashboard | < 300ms | `sales_dashboard_view` (materialized) |
| GET /search?q= | < 150ms | `search_vector` GIN index + tsrank |
| GET /orders (customer) | < 100ms | `customer_orders_view` + index on customer_id |

### Redis Caching Strategy
| Cache Key | TTL | Invalidated On |
|-----------|-----|----------------|
| `product:{slug}` | 300s | product update |
| `product_listing:{page}:{filters_hash}` | 60s | any product/inventory change |
| `categories:tree` | 600s | category create/update/delete |
| `collections:list` | 300s | collection create/update/delete |
| `cms:home` | 120s | any CMS change |
| `settings:public` | 600s | settings update |

### Connection Pooling
```python
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,        # 20
    max_overflow=settings.DATABASE_MAX_OVERFLOW,   # 10
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,   # 30 seconds
    pool_pre_ping=True,                            # validate connections
    pool_recycle=1800,                             # recycle connections every 30min
)
```

### Pagination
All list endpoints use cursor-based or offset-based pagination. Default `page_size=24` for product listing, `page_size=20` for admin tables. Maximum `page_size=100`.

```python
# Offset-based (used for catalog, admin tables)
SELECT * FROM products
WHERE status = 'active'
ORDER BY created_at DESC
LIMIT :page_size OFFSET (:page - 1) * :page_size;
```

### N+1 Prevention
- All list queries use JOINs or subqueries — never SELECT+loop.
- SQLAlchemy `selectinload` and `joinedload` used for relationship loading.
- `product_listing_view` pre-joins images and inventory to avoid N+1 on listing pages.

### Materialized View Refresh Schedule
```sql
-- Refresh sales dashboard every hour
SELECT cron.schedule('refresh-sales-dashboard', '0 * * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY sales_dashboard_view');

-- Refresh top products daily at 3am
SELECT cron.schedule('refresh-top-products', '0 3 * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY top_products_view');

-- Refresh trending searches every 6 hours
SELECT cron.schedule('refresh-trending-searches', '0 */6 * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY trending_searches');

-- Release expired inventory reservations every minute
SELECT cron.schedule('release-reservations', '* * * * *',
    'SELECT release_expired_reservations()');
```

---

## 5.9 MONITORING

### Health Endpoints
```
GET /health           → 200 OK, basic liveness check
GET /readiness        → 200 OK if DB + Redis reachable, else 503
GET /liveness         → 200 OK (process alive)
GET /metrics          → Prometheus metrics endpoint
```

**Readiness Response:**
```json
{
  "status": "ready",
  "checks": {
    "database": { "status": "ok", "latency_ms": 12 },
    "redis": { "status": "ok", "latency_ms": 2 },
    "storage": { "status": "ok" }
  },
  "version": "1.0.0",
  "environment": "production"
}
```

### Sentry Integration
```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    environment=settings.APP_ENV,
    traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    integrations=[FastApiIntegration(), SqlalchemyIntegration()],
)
```

### Prometheus Metrics
Exposed via `prometheus-fastapi-instrumentator`:
- `http_requests_total` — request count by method/path/status
- `http_request_duration_seconds` — histogram of latency
- `http_requests_in_progress` — gauge
- Custom: `db_query_duration_seconds`, `redis_operation_duration_seconds`

### Structured JSON Logging
```python
# app/core/logging.py using structlog
import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.contextvars.merge_contextvars,
        structlog.processors.JSONRenderer(),
    ]
)
```

Every request log includes: `request_id`, `user_id`, `method`, `path`, `status_code`, `duration_ms`.

---

## 5.10 DEPLOYMENT

### Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps for Pillow, WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libjpeg-dev libwebp-dev libheif-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### docker-compose.yml
```yaml
version: "3.9"
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [redis]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  worker:
    build: .
    command: python -m app.workers.runner
    env_file: .env
    depends_on: [redis, api]
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: ["redis_data:/data"]
    command: redis-server --appendonly yes
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s

  nginx:
    image: nginx:alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./docker/nginx/ssl:/etc/nginx/ssl:ro
    depends_on: [api]
    restart: unless-stopped

volumes:
  redis_data:
```

### Nginx Configuration
```nginx
# /docker/nginx/nginx.conf
upstream api {
    server api:8000;
    keepalive 64;
}

server {
    listen 80;
    server_name api.hadha.co;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.hadha.co;

    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    client_max_body_size 20M;  # for image uploads

    location / {
        proxy_pass         http://api;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection keep-alive;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /metrics { deny all; }  # Prometheus metrics — internal only
}
```

### GitHub Actions CI/CD (.github/workflows/deploy.yml)
```yaml
name: Deploy to Production
on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v --cov=app --cov-report=xml
      - uses: codecov/codecov-action@v4

  deploy:
    needs: test
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - name: Build and push Docker image
        run: |
          docker build -t ghcr.io/hadha-co/backend:${{ github.sha }} .
          docker push ghcr.io/hadha-co/backend:${{ github.sha }}
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_KEY }}
          script: |
            cd /opt/hadha-backend
            docker compose pull
            docker compose up -d --no-deps api worker
            docker compose exec api alembic upgrade head
```

---

## 5.11 BACKUP STRATEGY

### Supabase Managed Backups (Primary)
- Supabase Pro/Team plan: daily automated backups with 7-day retention.
- Point-in-Time Recovery (PITR) enabled: allows restore to any second within retention window.
- No manual configuration needed — enabled via Supabase dashboard.

### Manual Backup Script (Secondary)
```bash
#!/bin/bash
# Runs daily via cron; stores backup in R2
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
pg_dump $DATABASE_URL -Fc -f /tmp/hadha_backup_$TIMESTAMP.dump
aws s3 cp /tmp/hadha_backup_$TIMESTAMP.dump \
    s3://hadha-backups/postgres/hadha_backup_$TIMESTAMP.dump \
    --endpoint-url $CLOUDFLARE_R2_ENDPOINT
rm /tmp/hadha_backup_$TIMESTAMP.dump
# Retain 30 days, delete older backups
```

### Redis Backup
- Redis is configured with `appendonly yes` (AOF persistence).
- Docker volume persists data across restarts.
- Optional: use Upstash Redis (managed, with built-in persistence).

---

## 5.12 FEATURE FLAGS

### Table
```sql
CREATE TABLE feature_flags (
    key         TEXT PRIMARY KEY,
    value       BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT,
    updated_by  UUID REFERENCES profiles(id),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Seed Feature Flags
```sql
INSERT INTO feature_flags (key, value, description) VALUES
('sms_order_confirmation', true,  'Send SMS after order payment confirmed'),
('sms_shipping_updates',   false, 'Send SMS for shipping status updates'),
('whatsapp_notifications',  false, 'Enable WhatsApp notification channel'),
('google_oauth',            true,  'Enable Google OAuth login'),
('magic_link_login',        true,  'Enable magic link email login'),
('guest_checkout',          true,  'Allow checkout without account'),
('wishlist_sharing',        true,  'Allow sharing wishlists via public link'),
('review_images',           true,  'Allow customers to upload review images'),
('maintenance_mode',        false, 'Put frontend in maintenance mode'),
('free_shipping_banner',    true,  'Show free shipping threshold banner');
```

### Usage in Code
```python
async def is_enabled(flag_key: str) -> bool:
    # Check Redis cache first (TTL 60s)
    cached = await redis.get(f"feature:{flag_key}")
    if cached is not None:
        return cached == b"1"
    # Fall through to DB
    result = await db.execute(
        select(FeatureFlag.value).where(FeatureFlag.key == flag_key)
    )
    val = result.scalar_one_or_none()
    await redis.setex(f"feature:{flag_key}", 60, "1" if val else "0")
    return bool(val)
```

### APIs

#### GET /admin/feature-flags
**Auth:** `require_admin`

#### PATCH /admin/feature-flags/{key}
**Auth:** `require_super_admin`
**Request:** `{ "value": true }`
**Audit:** logged.

---

## 5.13 BUSINESS RULES

These rules are inviolable. Any code path that bypasses them is a production bug.

1. **Price Trust:** Product price, tax, shipping, and discount amounts MUST always be calculated on the backend. Any price received from the frontend is discarded and recalculated.

2. **Cart Totals:** Cart totals are recalculated server-side on every `GET /cart` response. The frontend displays what the server returns.

3. **Coupon Validation:** All coupon validation (eligibility, expiry, limits, minimum order) happens on the backend at checkout. Frontend coupon error display is based on API error responses.

4. **Inventory Gating:** Inventory is validated BOTH when adding to cart (reserve) AND when creating an order. Between these two events, reserved quantity prevents overselling.

5. **Payment Authority:** The Razorpay webhook is the ONLY source of payment confirmation. The frontend callback is used ONLY to redirect the user — it never triggers order fulfillment.

6. **Order Idempotency:** Order creation is gated on `idempotency_key`. A duplicate checkout with the same key returns the existing order without creating a new one.

7. **Webhook Idempotency:** Webhook events are stored with `UNIQUE (provider, provider_event_id)`. Processing a duplicate event is a no-op.

8. **Soft Deletes:** `products`, `orders`, `customers (profiles)`, `reviews`, `coupons` are NEVER hard-deleted. All have `deleted_at` field. API queries MUST filter `WHERE deleted_at IS NULL`.

9. **Immutable Financial Records:** `order_items` prices, `payments.amount`, `invoices.*` are set at creation and never modified. If a correction is needed, a new record is created.

10. **GST on Shipping State:** Tax type (CGST+SGST vs. IGST) is determined by comparing seller state (`Maharashtra`) with buyer's shipping address state. This must be evaluated at order creation and locked.

11. **SMS Business Rule:** SMS is only sent for `OrderCreated` event AND only when `payment.status = 'captured'`. The `sms_order_confirmation` feature flag must be enabled. Never send SMS for registration, password reset, or marketing unless feature flag explicitly enables it.

12. **Admin 2FA:** Admin and super_admin accounts MUST complete TOTP 2FA setup. Any admin route called without verified 2FA returns `403` with `{"code":"2FA_REQUIRED"}`.

13. **Review Eligibility:** Reviews can only be submitted by customers who have a `delivered` order containing the reviewed product. One review per order_item.

14. **Address Immutability on Orders:** At order creation, the full address is snapshotted into `orders` row columns. Subsequent address changes by the customer do not affect existing orders.

15. **Return Window:** Returns are only accepted within 7 days of `orders.delivered_at`. The system enforces this at the API level.

---

## 5.14 SEED DATA

Defined in `023_seed_data.sql`. Running this file populates the database with initial data needed to operate the store.

```sql
-- ── Categories ───────────────────────────────────────────────────────────────
INSERT INTO categories (id, name, slug, sort_order, is_active) VALUES
    (gen_random_uuid(), 'Rings',          'rings',          1,  true),
    (gen_random_uuid(), 'Anklets',        'anklets',        2,  true),
    (gen_random_uuid(), 'Bracelets',      'bracelets',      3,  true),
    (gen_random_uuid(), 'Chains',         'chains',         4,  true),
    (gen_random_uuid(), 'Necklaces',      'necklaces',      5,  true),
    (gen_random_uuid(), 'Pendants',       'pendants',       6,  true),
    (gen_random_uuid(), 'Bangles',        'bangles',        7,  true),
    (gen_random_uuid(), 'Earrings',       'earrings',       8,  true),
    (gen_random_uuid(), 'Toe Rings',      'toe-rings',      9,  true),
    (gen_random_uuid(), 'Kids Jewellery', 'kids-jewellery', 10, true),
    (gen_random_uuid(), 'Men Jewellery',  'men-jewellery',  11, true),
    (gen_random_uuid(), 'Black Bead Sets','black-bead-sets',12, true),
    (gen_random_uuid(), 'Nakshi',         'nakshi',         13, true),
    (gen_random_uuid(), 'Bugadi',         'bugadi',         14, true);

-- ── Collections ───────────────────────────────────────────────────────────────
INSERT INTO collections (name, slug, is_active, is_featured, sort_order) VALUES
    ('New Arrivals',   'new-arrivals',   true, true, 1),
    ('Bestsellers',    'bestsellers',    true, true, 2),
    ('Festive Edit',   'festive-edit',   true, true, 3),
    ('Daily Wear',     'daily-wear',     true, false, 4),
    ('Gift Sets',      'gift-sets',      true, false, 5);

-- ── App Settings ─────────────────────────────────────────────────────────────
INSERT INTO app_settings (key, value, description, is_public) VALUES
    ('free_shipping_threshold', '999',          'Min order for free shipping (INR)',   true),
    ('shipping_flat_rate',      '99',           'Flat shipping rate (INR)',            true),
    ('gst_rate',                '3',            'GST rate % for silver jewellery',     false),
    ('seller_state',            'Maharashtra',  'Seller state',                         false),
    ('seller_gstin',            '',             'GSTIN of seller',                      false),
    ('support_email',           'support@hadha.co', 'Support email',                  true),
    ('support_phone',           '+919000000000','Support phone',                       true),
    ('return_window_days',      '7',            'Days for return after delivery',       true),
    ('maintenance_mode',        'false',        'Maintenance mode flag',                false);

-- ── Feature Flags ────────────────────────────────────────────────────────────
INSERT INTO feature_flags (key, value, description) VALUES
    ('sms_order_confirmation', true,  'SMS after order payment'),
    ('sms_shipping_updates',   false, 'SMS for shipping updates'),
    ('whatsapp_notifications',  false, 'WhatsApp channel'),
    ('google_oauth',            true,  'Google OAuth login'),
    ('magic_link_login',        true,  'Magic link login'),
    ('guest_checkout',          true,  'Guest checkout'),
    ('wishlist_sharing',        true,  'Share wishlists'),
    ('review_images',           true,  'Review image uploads'),
    ('maintenance_mode',        false, 'Maintenance mode'),
    ('free_shipping_banner',    true,  'Free shipping banner');

-- ── CMS Home ─────────────────────────────────────────────────────────────────
INSERT INTO landing_sections (section_key, title, subtitle, is_active, sort_order, config) VALUES
    ('announcement_bar', NULL, 'Free Shipping above ₹999 | Use WELCOME10 for 10% Off', true, 0, '{}'),
    ('hero',             'Crafted in Silver. Worn with Love.', 'Explore our latest collection of BIS Hallmarked 925 silver jewellery', true, 1, '{}'),
    ('featured_categories', 'Shop by Category', NULL, true, 2, '{}'),
    ('new_arrivals',     'New Arrivals', 'Fresh pieces, just for you', true, 3, '{"limit": 8}'),
    ('featured_collection', 'Festive Edit', 'Celebrate every occasion', true, 4, '{"collection_slug": "festive-edit"}'),
    ('bestsellers',      'Our Bestsellers', 'Loved by thousands', true, 5, '{"limit": 8}'),
    ('why_choose_us',    'Why Hadha.co?', NULL, true, 6, '{"items": [{"icon":"hallmark","title":"BIS Hallmarked 925","body":"Certified purity, every time."},{"icon":"shipping","title":"Free Shipping","body":"On all orders above ₹999."},{"icon":"returns","title":"Easy Returns","body":"7-day hassle-free returns."},{"icon":"craftsmanship","title":"Handcrafted","body":"Made by skilled artisans."}]}');

-- ── Notification Templates ────────────────────────────────────────────────────
INSERT INTO notification_templates (name, channel, event_type, subject, template_body) VALUES
    ('order_confirmation_email', 'email', 'order_created',    'Your Hadha.co Order #{{order_number}} is Confirmed!', '<!-- order_confirmation.html template body -->'),
    ('order_shipped_email',      'email', 'order_shipped',    'Your Order #{{order_number}} is On Its Way!',         '<!-- order_shipped.html -->'),
    ('order_delivered_email',    'email', 'order_delivered',  'Your Order #{{order_number}} has been Delivered!',    '<!-- order_delivered.html -->'),
    ('review_request_email',     'email', 'review_request',   'How was your Hadha.co purchase?',                     '<!-- review_request.html -->'),
    ('order_sms',                'sms',   'order_created',    NULL, 'Thank you for shopping with Hadha.co. Your order {{order_number}} has been confirmed. Track at https://hadha.co/orders/{{order_number}}');
```

---

## 5.15 MODULE IMPLEMENTATION ORDER

Build in this exact sequence. Each phase must be fully complete — tables, models, schemas, service, repository, router, tests, SQL — before starting the next.

### Phase 1 — Database Foundation
- `supabase/sql/000_extensions.sql`
- `supabase/sql/001_profiles.sql` (tables + trigger + RLS)
- `app/core/config.py` (Settings with startup validation)
- `app/core/database.py` (async SQLAlchemy engine)
- `app/core/security.py` (JWT verification)
- `app/core/dependencies.py` (get_current_user, require_role)
- `app/modules/auth/` (token verify, logout, 2FA)
- `app/modules/profiles/` (CRUD)
- Alembic initial migration

### Phase 2 — Catalog
- `supabase/sql/002_catalog.sql`
- `app/modules/catalog/` (products, variants, attributes, images)
- `app/modules/categories/`
- `app/modules/collections/`
- `app/modules/media/` (upload pipeline + R2)
- `app/modules/seo/`

### Phase 3 — Inventory
- `supabase/sql/003_inventory.sql`
- `app/modules/inventory/`
- `app/workers/inventory_alerts.py`

### Phase 4 — Customer Context
- `app/modules/addresses/`
- `app/modules/wishlist/`
- `app/modules/search/` (full-text + autocomplete)

### Phase 5 — Cart
- `supabase/sql/004_cart.sql`
- `app/modules/cart/`
- `app/workers/abandoned_cart.py`

### Phase 6 — Orders
- `supabase/sql/005_orders.sql`
- `app/modules/orders/`
- `app/modules/tax/` (GST calculation)
- `app/modules/coupons/`

### Phase 7 — Payments (Razorpay)
- `supabase/sql/006_payments.sql`
- `app/modules/payments/`
- `app/modules/webhooks/` (framework + Razorpay handler)
- `app/modules/invoices/`

### Phase 8 — Shipping (Delivery One)
- `supabase/sql/007_shipping.sql`
- `app/modules/shipping/`
- `app/workers/shipment_sync.py`
- Delivery One webhook handler

### Phase 9 — Reviews
- `supabase/sql/008_reviews.sql`
- `app/modules/reviews/`
- `app/workers/review_reminder.py`

### Phase 10 — Notifications
- `supabase/sql/012_notifications.sql`
- `app/modules/notifications/`
- `app/workers/notification_retry.py`
- All email HTML templates

### Phase 11 — CMS + SEO
- `supabase/sql/010_cms.sql`, `supabase/sql/014_seo.sql`
- `app/modules/cms/`
- `app/modules/seo/` (sitemap, robots.txt)

### Phase 12 — Analytics + Returns + Support
- `supabase/sql/011_analytics.sql`
- `app/modules/analytics/`
- `app/modules/returns/`
- `app/modules/support/`

### Phase 13 — Security + Fraud
- `supabase/sql/016_fraud.sql`
- `app/modules/fraud/`
- `app/middleware/rate_limit.py`
- `app/middleware/audit_middleware.py`
- `supabase/sql/013_audit_logs.sql`

### Phase 14 — Database Finalization
- `supabase/sql/019_views.sql` (all views)
- `supabase/sql/020_indexes.sql` (all indexes)
- `supabase/sql/021_rls.sql` (all RLS policies)
- `supabase/sql/022_triggers.sql` (all triggers)
- `supabase/sql/023_seed_data.sql`

### Phase 15 — Infrastructure
- `Dockerfile` + `docker-compose.yml`
- `docker/nginx/nginx.conf`
- `.github/workflows/ci.yml` + `deploy.yml`
- Sentry + Prometheus instrumentation
- Health/readiness/liveness endpoints
- Feature flags API

### Phase 16 — Admin Dashboard API
- `app/modules/admin/` (aggregated admin router)
- `GET /admin/dashboard` KPI endpoint
- All admin sub-routes (verified against RBAC matrix)

### Phase 17 — Testing
- `tests/conftest.py` (test DB setup, fixtures)
- Unit tests: service layer (mock repositories)
- Integration tests: full HTTP layer with test DB
- Webhook integration tests (Razorpay + Delivery One)
- Load testing: `k6` script targeting 200 concurrent users

---

## APPENDIX: REQUIRED MANUAL SUPABASE DASHBOARD TASKS

The following CANNOT be automated via SQL and must be done manually in the Supabase Dashboard after running `setup.sql`:

1. **Enable Google OAuth** — Authentication → Providers → Google → paste `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
2. **Configure SMTP** — Authentication → Email → Custom SMTP → enter Resend SMTP credentials (host: smtp.resend.com, port: 587)
3. **Set Auth Redirect URLs** — Authentication → URL Configuration:
   - Site URL: `https://hadha.co`
   - Redirect URLs: `https://hadha.co/auth/callback`, `https://hadha.co/auth/reset-password`
4. **Configure Resend Domain** — Verify `hadha.co` in Resend dashboard + add DNS records
5. **Configure Razorpay Webhook** — Razorpay Dashboard → Webhooks → Add endpoint `https://api.hadha.co/webhooks/razorpay` with events: `payment.authorized`, `payment.captured`, `payment.failed`, `order.paid`, `refund.created`, `refund.processed`
6. **Configure Delivery One Webhook** — Delivery One Dashboard → Webhooks → Add endpoint `https://api.hadha.co/webhooks/delivery-one`
7. **Enable `pg_cron` extension** — Supabase Dashboard → Database → Extensions → enable `pg_cron` (required for materialized view refresh schedules)

---
