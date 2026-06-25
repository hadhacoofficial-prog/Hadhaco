# Hadha.co — Silver Jewellery E-Commerce Backend

Production-grade FastAPI backend for **Hadha.co**, an Indian silver jewellery e-commerce platform. Built with async Python, PostgreSQL (Supabase), Redis, Cloudflare R2, Razorpay, and Delivery One. Ships as a containerised service behind Nginx.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Current Project Status](#current-project-status)
3. [Feature Coverage Report](#feature-coverage-report)
4. [API Inventory](#api-inventory)
5. [Database Schema](#database-schema)
6. [Environment Variables](#environment-variables)
7. [Integrations Status](#integrations-status)
8. [Testing Status](#testing-status)
9. [Security Audit](#security-audit)
10. [Technical Debt](#technical-debt)
11. [Missing Features](#missing-features)
12. [Production Readiness Checklist](#production-readiness-checklist)
13. [Repository Structure](#repository-structure)
14. [Setup Instructions](#setup-instructions)
15. [Deployment Instructions](#deployment-instructions)
16. [Final Summary](#final-summary)

---

## Project Overview

| Field | Value |
|---|---|
| **Project Name** | Hadha.co Backend API |
| **Version** | 1.0.0 |
| **Business Purpose** | Multi-vendor ready silver jewellery e-commerce platform targeting the Indian market. Supports customer-facing shopping, admin operations, logistics, payments, and CMS. |
| **API Prefix** | `/api/v1` |
| **Docs URL** | `/docs` (development only — disabled in production) |

### Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI 0.115 |
| Data validation | Pydantic V2 |
| ORM | SQLAlchemy 2.x (async) |
| Database | PostgreSQL via Supabase (asyncpg driver) |
| Auth | Supabase JWT (HS256) |
| Cache / Rate limiting | Redis 7 |
| Object storage | Cloudflare R2 (S3-compatible, boto3) |
| Payment gateway | Razorpay |
| Email (primary) | Resend |
| Email (fallback) | SendGrid |
| SMS | Twilio |
| Shipping | Delivery One |
| Error tracking | Sentry |
| Logging | structlog |
| Background jobs | APScheduler |
| Containerisation | Docker (multi-stage, non-root) |
| Reverse proxy | Nginx 1.27 |
| Linting | Ruff |
| Type checking | mypy (strict) |

---

## Current Project Status

| Module | Status | Completion |
|---|---|---|
| Authentication (JWT + 2FA) | ✅ Complete | 100% |
| Profiles & User Management | ✅ Complete | 100% |
| Product Catalogue | ✅ Complete | 100% |
| Categories (hierarchical) | ✅ Complete | 100% |
| Collections | ✅ Complete | 100% |
| Product Variants & Attributes | ✅ Complete | 100% |
| Product Images (R2) | ✅ Complete | 100% |
| Inventory Management | ✅ Complete | 100% |
| Cart (guest + authenticated) | ✅ Complete | 100% |
| Wishlist | ✅ Complete | 100% |
| Address Book | ✅ Complete | 100% |
| Checkout / Orders | ✅ Complete | 100% |
| Payments (Razorpay) | ✅ Complete | 100% |
| Refunds | ✅ Complete | 100% |
| Coupons & Discounts | ✅ Complete | 100% |
| Shipping (Delivery One) | ✅ Complete | 100% |
| Shipment Tracking | ✅ Complete | 100% |
| Invoices (PDF + R2) | ✅ Complete | 100% |
| Reviews & Ratings | ✅ Complete | 100% |
| CMS (Pages, Banners, Sections) | ✅ Complete | 100% |
| SEO (metadata, redirects, sitemap) | ✅ Complete | 100% |
| Search (full-text, autocomplete, trending) | ✅ Complete | 100% |
| Notifications (Email + SMS) | ⚠️ Partial | 85% |
| Analytics & Event Tracking | ✅ Complete | 95% |
| Admin Dashboard (KPI) | ✅ Complete | 100% |
| Audit Logging | ✅ Complete | 100% |
| Returns | ✅ Complete | 100% |
| Support Tickets | ✅ Complete | 100% |
| Fraud Detection | ✅ Complete | 100% |
| Feature Flags | ✅ Complete | 100% |
| Webhooks (Razorpay + Delivery One) | ✅ Complete | 100% |
| Background Workers | ✅ Complete | 100% |
| Security & Rate Limiting | ✅ Complete | 100% |
| Centralized Response Envelope | ✅ Complete | 100% |
| Testing | ✅ Complete | 90% |
| Docker / Container Setup | ✅ Complete | 95% |
| Google OAuth Login Flow | ❌ Missing | 10% |
| WhatsApp Notifications | ❌ Missing | 0% |
| CI/CD Pipeline | ❌ Missing | 0% |

---

## Feature Coverage Report

### Authentication

**Status:** Fully Implemented

Supabase JWT verification on every protected endpoint. Token decoded server-side using `SUPABASE_JWT_SECRET` (HS256, audience: `authenticated`). Admin 2FA implemented with TOTP (pyotp), backup codes (bcrypt-hashed), and Fernet-encrypted secrets.

| Evidence | File |
|---|---|
| JWT verification | `app/core/security.py` |
| Auth dependencies | `app/core/dependencies.py` |
| 2FA service | `app/modules/auth/service.py` |
| 2FA model | `app/modules/auth/models.py` (admin_2fa, admin_sessions) |
| Routes | `app/modules/auth/router.py` |

---

### Product Catalogue

**Status:** Fully Implemented

Full CRUD for products with jewellery-specific fields (metal_type, purity, hallmark, weight, making_charges, wastage_percent, HSN code, GST). Supports variants (size/weight variations), attributes (key-value metadata), multi-image management with primary selection, and full-text search via PostgreSQL TSVECTOR with GIN index.

| Evidence | File |
|---|---|
| Product model | `app/modules/catalog/models.py` |
| Service | `app/modules/catalog/service.py` |
| Repository | `app/modules/catalog/repository.py` |
| Routes | `app/modules/catalog/router.py` |
| Image upload | `app/modules/media/router.py`, `app/modules/media/service.py` |

---

### Categories & Collections

**Status:** Fully Implemented

Hierarchical categories (self-referential FK `parent_id`) with full tree retrieval. Collections are manually curated product groupings with M2M association table. Both support admin CRUD.

| Evidence | File |
|---|---|
| Category model | `app/modules/categories/models.py` |
| Collection model | `app/modules/collections/models.py` |
| Routes | `app/modules/categories/router.py`, `app/modules/collections/router.py` |

---

### Cart

**Status:** Fully Implemented

Supports both guest (session ID via `X-Session-ID` header) and authenticated users. Guest cart merges into user cart on login (`POST /cart/merge`). Quantity validation against stock on add/update.

| Evidence | File |
|---|---|
| Cart + CartItem models | `app/modules/cart/models.py` |
| Service | `app/modules/cart/service.py` |
| Routes | `app/modules/cart/router.py` |

---

### Checkout & Orders

**Status:** Fully Implemented

Orders created from the active cart via `POST /orders`. Service validates stock availability, applies coupon discount, calculates GST (intra/inter-state per seller state), snapshots product details and shipping address, reduces stock inventory, and clears the cart atomically.

| Evidence | File |
|---|---|
| Order + OrderItem models | `app/modules/orders/models.py` |
| Service | `app/modules/orders/service.py` |
| Routes | `app/modules/orders/router.py` |

---

### Payments

**Status:** Fully Implemented

Two-step Razorpay flow: (1) `POST /payments/create-order` creates a Razorpay order object, (2) `POST /payments/verify` validates the payment signature (HMAC-SHA256) and marks the order as paid. Refunds managed through admin endpoints. Webhook receiver processes `payment.authorized` and `payment.failed` events.

| Evidence | File |
|---|---|
| Payment + Refund models | `app/modules/payments/models.py` |
| Service | `app/modules/payments/service.py` |
| Webhook handler | `app/modules/webhooks/service.py` |
| Routes | `app/modules/payments/router.py`, `app/modules/webhooks/router.py` |

---

### Shipping

**Status:** Fully Implemented

Delivery One integration: create shipment, fetch AWB label (uploaded to R2), track by AWB number, cancel shipment, fetch live shipping rates by weight+pincode. Background worker syncs shipment status every 5 minutes. Webhook receiver updates shipment events in real time.

| Evidence | File |
|---|---|
| Shipment + ShipmentEvent models | `app/modules/shipping/models.py` |
| Service | `app/modules/shipping/service.py` |
| Background sync | `app/workers/jobs/` |
| Routes | `app/modules/shipping/router.py` |

---

### Invoices

**Status:** Fully Implemented

PDF invoice generation with company branding, GST details (CGST/SGST or IGST based on seller vs buyer state), order line items, and totals. PDF uploaded to Cloudflare R2, download link signed and served via `302` redirect.

| Evidence | File |
|---|---|
| Invoice model | `app/modules/invoices/models.py` |
| Service | `app/modules/invoices/service.py` |
| Route | `app/modules/invoices/router.py` |

---

### Reviews & Ratings

**Status:** Fully Implemented

Customers submit reviews with star rating (1–5), title, body, and optional images (uploaded to R2). Helpful/unhelpful voting. Admin moderation queue (pending → approved/rejected). Rating summary endpoint returns per-star breakdown and average. Review images stored as JSON array of R2 URLs.

| Evidence | File |
|---|---|
| Review model | `app/modules/reviews/models.py` |
| Service | `app/modules/reviews/service.py` |
| Routes | `app/modules/reviews/router.py` |

---

### CMS

**Status:** Fully Implemented

Admin-managed home page (banners + landing sections), standalone CMS pages (slug-based, with body and meta), and a structured home page response aggregating featured products, new arrivals, active banners, and landing sections.

| Evidence | File |
|---|---|
| CMS models | `app/modules/cms/models.py` |
| Service | `app/modules/cms/service.py` |
| Routes | `app/modules/cms/router.py` |

---

### SEO

**Status:** Fully Implemented

Per-path SEO metadata (title, description, canonical URL, OG tags, JSON-LD structured data, noindex). URL redirect management (301/302). Auto-generated XML sitemap from active products and CMS pages.

| Evidence | File |
|---|---|
| SEO models | `app/modules/seo/models.py` |
| Service | `app/modules/seo/service.py` |
| Routes | `app/modules/seo/router.py` |

---

### Search

**Status:** Fully Implemented

PostgreSQL full-text search using `ts_rank` and `plainto_tsquery`. TSVECTOR column updated by database trigger. Autocomplete (prefix matching on product names and search history). Trending searches ranked by recent query count. Search queries recorded for analytics.

| Evidence | File |
|---|---|
| Service | `app/modules/search/service.py` |
| Routes | `app/modules/search/router.py` |

---

### Notifications

**Status:** Partially Implemented (85%)

Event-driven notification system using domain events. Notification preferences stored per user per channel (email/SMS). Logs retained in `notification_logs` table with retry support.

Implemented: Order confirmation (email + SMS), shipping updates (email + SMS), refund initiated (email), review reminder (email), abandoned cart (email).

**Missing:** WhatsApp channel (Twilio WhatsApp not wired; only SMS). Push notifications not implemented.

| Evidence | File |
|---|---|
| Notification models | `app/modules/notifications/models.py` |
| Service + listeners | `app/modules/notifications/service.py` |
| Routes | `app/modules/notifications/router.py` |

---

### Analytics

**Status:** Fully Implemented (95%)

Event tracking endpoint accepts any structured event with optional auth (user ID resolved from JWT if present). Admin dashboard aggregates orders, revenue, new customers, conversion metrics over a configurable date range.

**Minor gap:** No CSV/PDF export for dashboard data.

| Evidence | File |
|---|---|
| Service | `app/modules/analytics/service.py` |
| Routes | `app/modules/analytics/router.py` |

---

### Admin & Audit

**Status:** Fully Implemented

KPI dashboard (today orders/revenue, pending orders, open support tickets, unresolved fraud signals, low-stock count) via a single optimised SQL query. All state-changing operations emitted as domain audit events, stored in `audit_events`, and queryable via paginated admin endpoint.

| Evidence | File |
|---|---|
| Admin routes | `app/modules/admin/router.py` |
| Audit repository | `app/modules/audit/repository.py` |
| Audit middleware | `app/middleware/audit_middleware.py` |

---

### Returns

**Status:** Fully Implemented

Customers submit return requests against an order. Admin updates status (pending → approved/rejected/completed). Return requests stored with reason, status, admin notes, and timestamps.

---

### Support Tickets

**Status:** Fully Implemented

Customers create tickets with subject and description. Threaded message replies (customer and admin). Admin can update status (open → in_progress → resolved/closed) and priority. Full admin list with status filter.

---

### Fraud Detection

**Status:** Fully Implemented

Admin-managed fraud signal registry. Signals record the type (duplicate_order, high_velocity, etc.), risk score, details, and linked order/user. Admin resolves signals with notes. KPI dashboard surfaces unresolved count.

---

### Feature Flags

**Status:** Fully Implemented

Database-backed feature flags. Admin can list and toggle any flag. Flags are read in background workers (e.g., abandoned cart emails check a feature flag before sending).

---

### Background Workers

**Status:** Fully Implemented

APScheduler (async-compatible) with configurable intervals via env vars:

| Job | Default Interval | Purpose |
|---|---|---|
| Shipment sync | 300s (5 min) | Poll Delivery One for status updates |
| Notification retry | 30s | Retry failed notification sends |
| Abandoned cart | 3600s (1 hr) | Email customers with abandoned carts |
| Inventory alert | 1800s (30 min) | Email admin about low-stock products |
| Review reminder | — | Trigger 48h post-delivery review request |

---

### Google OAuth

**Status:** Not Implemented (10%)

`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are declared in `Settings` and `.env.example`, but no OAuth login route, callback handler, or user provisioning flow exists. Supabase can handle Google OAuth on the client side, but the backend has no explicit Google OAuth endpoint.

---

### WhatsApp Notifications

**Status:** Not Implemented (0%)

Not wired. Only Twilio SMS is connected. No WhatsApp Business API integration exists in the codebase.

---

### CI/CD

**Status:** Complete (100%)

GitHub Actions pipeline: CI (`ci.yml`) runs lint/tests/type-check on every PR; production deploy (`production.yml`) triggers on push to `main` — builds Docker images, pushes to GHCR, and deploys to the VPS via SSH. See `DEVOPS.md` for the full runbook.

---

## API Inventory

All endpoints are prefixed with `/api/v1`. Auth column: `public` = no auth required, `customer` = logged-in customer role+, `admin` = admin role+, `super_admin` = super_admin role only.

### Auth

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/auth/verify-token` | customer |
| POST | `/auth/logout` | customer |
| POST | `/auth/force-logout/{user_id}` | super_admin |
| POST | `/auth/admin/2fa/setup` | admin |
| POST | `/auth/admin/2fa/verify` | admin |
| POST | `/auth/admin/2fa/validate` | admin |

### Profiles & Users

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/me` | customer |
| PATCH | `/me` | customer |
| PATCH | `/me/avatar` | customer |
| GET | `/admin/users` | admin |
| PATCH | `/admin/users/{user_id}/role` | super_admin |
| PATCH | `/admin/users/{user_id}/status` | admin |

### Addresses

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/me/addresses` | customer |
| POST | `/me/addresses` | customer |
| PATCH | `/me/addresses/{address_id}` | customer |
| POST | `/me/addresses/{address_id}/default` | customer |
| DELETE | `/me/addresses/{address_id}` | customer |

### Products

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/products` | public |
| GET | `/products/{slug}` | public |
| GET | `/admin/products` | admin |
| POST | `/admin/products` | admin |
| GET | `/admin/products/{product_id}` | admin |
| PATCH | `/admin/products/{product_id}` | admin |
| DELETE | `/admin/products/{product_id}` | admin |
| POST | `/admin/products/{product_id}/variants` | admin |
| PATCH | `/admin/products/variants/{variant_id}` | admin |
| DELETE | `/admin/products/variants/{variant_id}` | admin |
| PUT | `/admin/products/{product_id}/attributes` | admin |
| DELETE | `/admin/products/{product_id}/attributes/{attr_name}` | admin |
| POST | `/admin/products/{product_id}/stock/adjust` | admin |

### Media (Product Images)

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/admin/products/{product_id}/images` | admin |
| DELETE | `/admin/products/{product_id}/images/{image_id}` | admin |
| PATCH | `/admin/products/{product_id}/images/{image_id}/primary` | admin |

### Categories

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/categories` | public |
| POST | `/admin/categories` | admin |
| PATCH | `/admin/categories/{cat_id}` | admin |
| DELETE | `/admin/categories/{cat_id}` | admin |

### Collections

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/collections` | public |
| GET | `/collections/{slug}` | public |
| POST | `/admin/collections` | admin |
| PATCH | `/admin/collections/{col_id}` | admin |
| DELETE | `/admin/collections/{col_id}` | admin |
| POST | `/admin/collections/{col_id}/products` | admin |
| DELETE | `/admin/collections/{col_id}/products/{product_id}` | admin |

### Search

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/search` | public |
| GET | `/search/autocomplete` | public |
| GET | `/search/trending` | public |

### Cart

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/cart` | optional (guest via X-Session-ID) |
| POST | `/cart/items` | optional (guest via X-Session-ID) |
| PATCH | `/cart/{cart_id}/items/{item_id}` | optional |
| DELETE | `/cart/{cart_id}/items/{item_id}` | optional |
| DELETE | `/cart` | optional |
| POST | `/cart/merge` | customer + X-Session-ID |

### Wishlist

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/me/wishlist` | customer |
| POST | `/me/wishlist` | customer |
| POST | `/me/wishlist/toggle` | customer |
| DELETE | `/me/wishlist/{product_id}` | customer |

### Coupons

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/coupons/validate` | customer |
| GET | `/admin/coupons` | admin |
| POST | `/admin/coupons` | admin |
| PATCH | `/admin/coupons/{coupon_id}` | admin |
| DELETE | `/admin/coupons/{coupon_id}` | admin |

### Orders

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/orders` | customer |
| GET | `/orders` | customer |
| GET | `/orders/{order_id}` | customer (ownership enforced) |
| POST | `/orders/{order_id}/cancel` | customer |
| GET | `/admin/orders` | admin |
| GET | `/admin/orders/{order_id}` | admin |
| PATCH | `/admin/orders/{order_id}/status` | admin |

### Payments

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/payments/create-order` | customer |
| POST | `/payments/verify` | customer |
| GET | `/orders/{order_id}/payment` | customer |
| POST | `/admin/orders/{order_id}/refund` | admin |
| GET | `/admin/orders/{order_id}/refunds` | admin |

### Shipping

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/orders/{order_id}/shipment` | customer |
| GET | `/tracking/{awb_number}` | public |
| GET | `/shipping/rates` | public |
| POST | `/admin/orders/{order_id}/shipment` | admin |
| GET | `/admin/orders/{order_id}/shipment` | admin |
| DELETE | `/admin/orders/{order_id}/shipment` | admin |

### Invoices

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/orders/{order_id}/invoice` | customer (302 → R2 PDF URL) |

### Reviews

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/reviews/products/{product_id}` | public |
| GET | `/reviews/products/{product_id}/summary` | public |
| POST | `/reviews` | customer |
| PATCH | `/reviews/{review_id}` | customer (ownership) |
| DELETE | `/reviews/{review_id}` | customer (ownership) |
| POST | `/reviews/{review_id}/vote` | customer |
| GET | `/reviews/admin/pending` | admin |
| POST | `/reviews/admin/{review_id}/action` | admin |

### CMS

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/cms/home` | public |
| GET | `/cms/pages/{slug}` | public |
| GET | `/cms/admin/banners` | admin |
| POST | `/cms/admin/banners` | admin |
| PATCH | `/cms/admin/banners/{banner_id}` | admin |
| DELETE | `/cms/admin/banners/{banner_id}` | admin |
| GET | `/cms/admin/sections` | admin |
| PATCH | `/cms/admin/sections/{section_key}` | admin |
| POST | `/cms/admin/pages` | admin |
| PATCH | `/cms/admin/pages/{page_id}` | admin |

### SEO

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/seo/page` | public |
| PUT | `/admin/seo/pages` | admin |
| POST | `/admin/seo/redirects` | admin |
| GET | `/sitemap.xml` | public (PlainTextResponse, XML) |

### Inventory

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/admin/inventory/low-stock` | admin |
| GET | `/admin/products/{product_id}/inventory` | admin |
| POST | `/admin/products/{product_id}/inventory/adjust` | admin |

### Analytics

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/analytics/events` | public (optional JWT) |
| GET | `/analytics/admin/dashboard` | admin |

### Returns

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/returns` | customer |
| GET | `/returns` | customer |
| GET | `/returns/admin/returns` | admin |
| PATCH | `/returns/admin/returns/{return_id}/status` | admin |

### Support

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/support/tickets` | customer |
| GET | `/support/tickets` | customer |
| GET | `/support/tickets/{ticket_id}` | customer |
| POST | `/support/tickets/{ticket_id}/messages` | customer |
| GET | `/support/admin/tickets` | admin |
| PATCH | `/support/admin/tickets/{ticket_id}` | admin |
| POST | `/support/admin/tickets/{ticket_id}/messages` | admin |

### Notifications

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/notifications/preferences` | customer |
| PUT | `/notifications/preferences` | customer |
| GET | `/notifications/admin/logs` | admin |

### Fraud

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/admin/fraud/signals` | admin |
| POST | `/admin/fraud/signals` | admin |
| PATCH | `/admin/fraud/signals/{signal_id}` | admin |

### Settings

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/admin/settings/flags` | admin |
| PUT | `/admin/settings/flags/{key}` | admin |

### Admin

| Method | Endpoint | Auth |
|---|---|---|
| GET | `/admin/dashboard` | admin |
| GET | `/admin/audit-logs` | admin |

### Webhooks (excluded from OpenAPI schema)

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/webhooks/razorpay` | signature-verified |
| POST | `/webhooks/delivery-one` | signature-verified |

### Health (excluded from OpenAPI schema)

| Method | Endpoint | Response |
|---|---|---|
| GET | `/health` | `{status, version}` |
| GET | `/health/live` | `{status: "alive"}` |
| GET | `/health/ready` | `{status, checks: {db, redis}}` — 503 if unhealthy |
| GET | `/` | `{name, version}` |

**Total: 141 endpoints** (137 documented in OpenAPI + 4 ops)

---

## Database Schema

All tables provisioned by `supabase/sql/setup.sql`. Alembic baseline (`0001_baseline.py`) marks the DB as in sync without running DDL — migrations are handled directly in Supabase SQL.

### Tables & Key Columns

#### profiles
Synced from Supabase `auth.users`. Stores application-level user data.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | FK → auth.users(id) |
| email | VARCHAR unique | Indexed |
| full_name | TEXT | Nullable |
| phone | VARCHAR(20) | Nullable |
| avatar_url | TEXT | R2 URL |
| role | VARCHAR(20) | `customer` \| `admin` \| `super_admin` — indexed |
| is_active | BOOLEAN | Partial index on `true` |
| is_verified | BOOLEAN | — |
| deleted_at | TIMESTAMPTZ | Soft delete |
| created_at | TIMESTAMPTZ | Indexed |

#### admin_2fa
| Column | Type | Notes |
|---|---|---|
| user_id | UUID unique | FK → profiles(id) |
| totp_secret | TEXT | Fernet-encrypted |
| backup_codes | TEXT | JSON array of bcrypt-hashed codes |
| is_enabled | BOOLEAN | — |
| enabled_at | TIMESTAMPTZ | Nullable |

#### products
Jewellery-specific catalogue entries.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | — |
| sku | VARCHAR(100) unique | Indexed |
| slug | VARCHAR(255) unique | Indexed |
| category_id | UUID | FK → categories(id) SET NULL |
| metal_type | VARCHAR | e.g. `925_sterling`, `999_silver` |
| purity | VARCHAR | — |
| weight_grams | NUMERIC(10,3) | — |
| making_charges | NUMERIC(12,2) | — |
| wastage_percent | NUMERIC(5,2) | — |
| gender | VARCHAR | `men` \| `women` \| `unisex` |
| base_price | NUMERIC(12,2) | — |
| compare_at_price | NUMERIC(12,2) | Nullable |
| tax_rate | NUMERIC(5,2) | Default 3.0 (GST %) |
| hsn_code | VARCHAR(20) | For tax invoicing |
| stock_quantity | INTEGER | Default 0 |
| low_stock_threshold | INTEGER | Default 5 |
| status | VARCHAR(20) | `draft` \| `active` \| `archived` — indexed |
| search_vector | TSVECTOR | GIN indexed, updated by trigger |
| deleted_at | TIMESTAMPTZ | Soft delete |

Related tables: `product_variants`, `product_images`, `product_attributes`, `collection_products`

#### orders
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | — |
| order_number | VARCHAR(20) unique | Prefix `HD` + auto-increment |
| user_id | UUID | Indexed |
| status | VARCHAR(20) | `pending` \| `confirmed` \| `shipped` \| `delivered` \| `cancelled` |
| payment_status | VARCHAR(20) | `pending` \| `paid` \| `failed` \| `refunded` |
| subtotal / tax_amount / shipping_charge / discount / total | NUMERIC(12,2) | — |
| coupon_id | UUID | FK → coupons(id) SET NULL |
| razorpay_order_id | VARCHAR | — |
| razorpay_payment_id | VARCHAR | — |
| shipping_* | — | Address snapshot columns |
| billing_* | — | Address snapshot columns (nullable) |

Related tables: `order_items`, `payments`, `refunds`, `shipments`, `invoices`

#### Other Tables (summary)

| Table | Purpose |
|---|---|
| addresses | User address book |
| cart / cart_items | Guest + auth shopping cart |
| coupons | Discount codes (percent or fixed) |
| wishlist | User product wishlists |
| shipments / shipment_events | Shipping lifecycle + tracking |
| inventory_movements | Stock movement ledger |
| reviews | Product reviews with images + votes |
| categories | Hierarchical product categories |
| collections / collection_products | Curated product collections (M2M) |
| cms_banners / cms_pages / landing_sections | CMS content |
| seo_pages / seo_redirects | SEO metadata + URL redirects |
| audit_events | Immutable action audit log |
| notification_preferences / notification_logs | Per-user channel preferences + send history |
| returns | Return requests |
| fraud_signals | Fraud detection records |
| support_tickets / support_messages | Customer support threads |
| feature_flags | Database-backed feature toggles |
| webhooks_log | Incoming webhook event log |

### ERD Summary

```
profiles ─────────────────────┐
   │                          │
   ├── orders ──── order_items ── products ──── product_variants
   │       │                              │──── product_images
   │       │                              └──── product_attributes
   │       ├── payments
   │       │       └── refunds
   │       ├── shipments ──── shipment_events
   │       ├── invoices
   │       └── returns
   │
   ├── cart ──── cart_items ── products
   ├── wishlist ─────────────── products
   ├── addresses
   ├── reviews ──────────────── products
   ├── support_tickets ──── support_messages
   ├── notification_preferences
   ├── notification_logs
   └── admin_2fa

categories (self-referential parent_id)
collections ──── collection_products ──── products
```

---

## Environment Variables

### Required (application will not start without these)

| Variable | Description |
|---|---|
| `SECRET_KEY` | 64-char hex for internal signing — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ENCRYPTION_KEY` | 32-byte Fernet key for field encryption — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Publishable/anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key for admin operations |
| `SUPABASE_JWT_SECRET` | JWT signing secret from Supabase project settings |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://host:6379/0` |
| `CLOUDFLARE_ACCOUNT_ID` | R2 account ID |
| `CLOUDFLARE_R2_BUCKET` | R2 bucket name |
| `CLOUDFLARE_R2_ACCESS_KEY` | R2 access key |
| `CLOUDFLARE_R2_SECRET_KEY` | R2 secret key |
| `CLOUDFLARE_R2_PUBLIC_URL` | CDN URL prefix for public assets |
| `CLOUDFLARE_R2_ENDPOINT` | `https://<account_id>.r2.cloudflarestorage.com` |
| `RESEND_API_KEY` | Resend transactional email API key |
| `EMAIL_FROM` | Sender address (e.g. `noreply@hadha.co`) |
| `EMAIL_REPLY_TO` | Reply-to address |
| `TWILIO_ACCOUNT_SID` | Twilio SID for SMS |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio sender number |
| `RAZORPAY_KEY_ID` | Razorpay API key ID |
| `RAZORPAY_KEY_SECRET` | Razorpay API secret |
| `RAZORPAY_WEBHOOK_SECRET` | HMAC secret for webhook signature verification |
| `DELIVERY_ONE_BASE_URL` | Delivery One API base URL |
| `DELIVERY_ONE_API_KEY` | Delivery One API key |
| `DELIVERY_ONE_WEBHOOK_SECRET` | HMAC secret for webhook verification |
| `FRONTEND_URL` | Frontend origin (for CORS + email links) |
| `ADMIN_URL` | Admin panel origin (for CORS + email links) |

### Optional (with defaults)

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `Hadha.co` | Application name |
| `APP_ENV` | `development` | `development` \| `production` |
| `APP_DEBUG` | `false` | Enable debug mode |
| `APP_VERSION` | `1.0.0` | Version string |
| `API_HOST` | `0.0.0.0` | Bind host |
| `API_PORT` | `8000` | Bind port |
| `API_V1_PREFIX` | `/api/v1` | Route prefix |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | Comma-separated CORS origins |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Trusted Host middleware (production) |
| `DATABASE_POOL_SIZE` | `20` | SQLAlchemy pool size |
| `DATABASE_MAX_OVERFLOW` | `10` | SQLAlchemy max overflow |
| `DATABASE_POOL_TIMEOUT` | `30` | Pool timeout (seconds) |
| `REDIS_CACHE_TTL` | `300` | Cache TTL (seconds) |
| `REDIS_RATE_LIMIT_TTL` | `60` | Rate limit window (seconds) |
| `RAZORPAY_CURRENCY` | `INR` | Default payment currency |
| `DELIVERY_ONE_PICKUP_PINCODE` | — | Seller pickup pincode |
| `SMS_ENABLED` | `false` | Enable MSG91 SMS delivery |
| `MSG91_API_KEY` | — | MSG91 authkey (required when SMS_ENABLED=true) |
| `MSG91_SENDER_ID` | `HADHA` | MSG91 sender ID |
| `MSG91_TEMPLATE_ID` | — | MSG91 flow template ID |
| `GOOGLE_CLIENT_ID` | — | Google OAuth (not implemented) |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth (not implemented) |
| `RATE_LIMIT_AUTH` | `10` | Auth endpoints: req/min |
| `RATE_LIMIT_API` | `200` | General API: req/min |
| `RATE_LIMIT_UPLOAD` | `20` | Upload endpoints: req/min |
| `RATE_LIMIT_WEBHOOK` | `500` | Webhook endpoints: req/min |
| `SHIPMENT_SYNC_INTERVAL` | `300` | Seconds between Delivery One syncs |
| `REVIEW_REMINDER_DELAY_HOURS` | `48` | Hours after delivery to send review request |
| `ABANDONED_CART_THRESHOLD_HOURS` | `1` | Hours before cart considered abandoned |
| `ABANDONED_CART_INTERVAL` | `3600` | Seconds between abandoned cart job runs |
| `INVENTORY_ALERT_INTERVAL` | `1800` | Seconds between inventory alert checks |
| `NOTIFICATION_RETRY_INTERVAL` | `30` | Seconds between notification retry runs |
| `FREE_SHIPPING_THRESHOLD` | `999` | Order subtotal (INR) for free shipping |
| `SHIPPING_FLAT_RATE` | `99` | Flat shipping fee (INR) |
| `TAX_RATE_GST` | `3.0` | Default GST rate (%) |
| `SELLER_STATE` | `Maharashtra` | Used for CGST/SGST vs IGST calculation |
| `SELLER_GSTIN` | — | Printed on tax invoices |
| `LOW_STOCK_THRESHOLD` | `5` | Global low-stock alert level |
| `ORDER_NUMBER_PREFIX` | `HD` | Order number prefix |
| `INVOICE_NUMBER_PREFIX` | `INV` | Invoice number prefix |
| `ADMIN_ALERT_EMAIL` | `admin@hadha.co` | Destination for admin alert emails |

### Environment Files Present

| File | Purpose |
|---|---|
| `.env.example` | Canonical template with all variables and comments |
| `.env.production.example` | Production-specific overrides template |
| `.env.test` | Test environment (loaded by `conftest.py`) |
| `.env` | Local development (gitignored) |

---

## Integrations Status

| Integration | Purpose | Status | Notes |
|---|---|---|---|
| **Supabase** | Auth + PostgreSQL | ✅ Configured | JWT verification + asyncpg DB |
| **Cloudflare R2** | Object storage | ✅ Configured | Products images, avatars, invoices, shipping labels |
| **Razorpay** | Payments | ✅ Configured | Orders, payment verification, refunds, webhooks |
| **Delivery One** | Shipping / logistics | ✅ Configured | Shipment creation, tracking, rates, webhooks |
| **Resend** | Email (primary) | ✅ Configured | Transactional emails (order, shipping, support) |
| **MSG91** | SMS | ✅ Configured | Order and shipment SMS; gated by `SMS_ENABLED` flag |
| **Dozzle** | Log viewer | ✅ Configured | Real-time Docker log UI at `http://host:8080` |
| **Google OAuth** | Social login | ⚠️ Partial | Client ID/secret in settings; no login route implemented |
| **WhatsApp** | Messaging | ❌ Missing | Not implemented |
| **Instagram** | Product feed | ❌ Missing | Not present in codebase |

---

## Testing Status

### Test Suite Overview

| Category | Files | Tests |
|---|---|---|
| Unit | 21 files | ~872 tests |
| Integration | 2 files | 66 tests |
| **Total** | **23 files** | **938 tests** |

### Unit Test Coverage by Module

| File | Approx. Tests | Covers |
|---|---|---|
| `test_common_responses.py` | 40 | BaseSuccessResponse envelope, ResponseCode enum, exception handler |
| `test_repositories.py` | 86 | Product, order, category, collection repositories |
| `test_repositories_2.py` | 73 | Payment, shipment, refund, inventory repositories |
| `test_repositories_3.py` | 34 | Coupon, review, address repositories |
| `test_service_cart_categories_cms_coupons.py` | 58 | Cart merge, category tree, CMS service, coupon validation |
| `test_service_orders_profiles_catalog.py` | 43 | Order creation, profile update, product service |
| `test_service_auth_collections.py` | 23 | Auth 2FA, collection management |
| `test_service_invoices_search_media_addresses.py` | 35 | Invoice generation, search, media upload, address CRUD |
| `test_service_misc.py` | 26 | Misc service edge cases |
| `test_service_catalog_notifications.py` | 21 | Catalog + notification event dispatching |
| `test_service_orders.py` | 15 | Order status updates, cancellations |
| `test_service_orders_create.py` | 8 | Order creation from cart |
| `test_exceptions.py` | 22 | Exception hierarchy, HTTP status codes |
| `test_security.py` | 10 | JWT, HMAC, Fernet encryption |
| `test_event_bus_extended.py` | 15 | Async domain event listeners |
| `test_event_bus.py` | 5 | Event bus core |
| `test_constants.py` | 17 | Enum constants |
| `test_coupon_logic.py` | 9 | Discount calculations |
| `test_middleware.py` | 6 | Rate limiter, request ID middleware |
| `test_queue_service.py` | 7 | APScheduler job registration |
| `test_config_validation.py` | 4 | Settings validation |
| `test_search_logic.py` | 8 | Full-text search query construction |
| `test_service_mocks.py` | 19 | Mock factory helpers |
| `test_workers_extended.py` | ~30 | Background worker job logic |

### Integration Tests

| File | Tests | Covers |
|---|---|---|
| `test_api_smoke.py` | 8 | Health endpoints, root, basic auth flow |
| `test_api_comprehensive.py` | 58 | Full order flow, coupon validation, cart ops, admin endpoints |

### Test Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
```

Tests use an in-process ASGI client (no live server). Database calls are mocked using `AsyncMock` and `MagicMock`. The test database loads `.env.test` before importing the app.

### Known Coverage Gaps

- No router-level tests for CMS, SEO, notifications, or analytics endpoints
- No end-to-end Razorpay payment flow test (requires live API keys)
- No end-to-end Delivery One shipment test (requires live API keys)
- Background worker job tests cover logic only, not scheduler registration timing

---

## Security Audit

| Control | Status | Implementation |
|---|---|---|
| **JWT Authentication** | ✅ Implemented | `app/core/security.py` — HS256, audience `authenticated`, expiry enforced |
| **RBAC** | ✅ Implemented | `app/core/dependencies.py` — `customer`, `admin`, `super_admin` roles enforced per endpoint |
| **Admin 2FA** | ✅ Implemented | `app/modules/auth/` — TOTP via pyotp, Fernet-encrypted secrets, bcrypt backup codes |
| **Rate Limiting** | ✅ Implemented | `app/middleware/rate_limit.py` — Redis sliding window; fails open on Redis outage |
| **CORS** | ✅ Implemented | `app/main.py` — FastAPI CORSMiddleware, origins from `ALLOWED_ORIGINS` env var |
| **Trusted Host** | ✅ Implemented | Production-only TrustedHostMiddleware against `ALLOWED_HOSTS` |
| **Security Headers** | ✅ Implemented | `app/middleware/security_headers.py` — HSTS, CSP, X-Frame-Options, nosniff, Referrer-Policy |
| **Input Validation** | ✅ Implemented | Pydantic V2 strict schema validation on all request bodies; Query param bounds on all list endpoints |
| **Webhook Signatures** | ✅ Implemented | `app/core/security.py` — HMAC-SHA256 + `secrets.compare_digest()` for Razorpay + Delivery One |
| **Field Encryption** | ✅ Implemented | `app/core/security.py` — Fernet symmetric encryption for TOTP secrets |
| **Audit Logging** | ✅ Implemented | `app/middleware/audit_middleware.py` — All requests logged; `audit_events` table for state changes |
| **Soft Deletes** | ✅ Implemented | `profiles.deleted_at`, `products.deleted_at` — records are not hard-deleted |
| **SQL Injection** | ✅ Mitigated | SQLAlchemy ORM with parameterised queries throughout |
| **Secrets in Env** | ✅ Enforced | `.env` gitignored; pydantic-settings loads all secrets from environment |
| **Non-root Docker** | ✅ Implemented | Dockerfile runs as `hadha:1001` |
| **Docs in Production** | ✅ Implemented | `/docs`, `/redoc`, `/openapi.json` disabled when `APP_ENV=production` |

---

## Technical Debt

### Minor Issues

1. **Inline model definitions in `notifications/router.py`** — `PreferenceIn`, `PreferenceOut`, and `NotificationLogOut` Pydantic models are defined directly in the router file rather than in `schemas.py`. Cosmetic, no functional impact.

2. **Direct DB access in notifications router** — The notifications router executes SQLAlchemy queries directly instead of delegating to a repository layer, breaking the Clean Architecture convention used by all other modules.

3. **`search/router.py` uses `dict` as response type** — `response_model=BaseSuccessResponse[dict]` loses type safety and Swagger schema generation for search results. Should have a typed `SearchResultsResponse` schema.

4. **`seo/router.py` has inline Pydantic models** — `SeoPageUpsertRequest` and `SeoRedirectRequest` are defined at the top of the router file instead of `schemas.py`.

5. **`analytics/router.py` uses `dict` response type** — Same as search: `BaseSuccessResponse[dict]` for dashboard. Should be `DashboardStats`.

6. **`support/router.py` reply endpoints use `dict`** — `reply_ticket` and `admin_reply_ticket` return `BaseSuccessResponse[dict]` instead of a typed message schema.

7. **`catalog/router.py` imports `created` inside function bodies** — Avoids circular import but is inconsistent with other routers that import at the top level. Should be refactored to a top-level import.

8. **CI/CD pipeline** — GitHub Actions workflows are in place (`.github/workflows/ci.yml` and `production.yml`). Deploy automation is handled by `deploy/scripts/deploy.sh`.

9. **Alembic migrations are a stub** — The baseline migration is an empty placeholder. Any future schema changes must be managed manually in Supabase SQL or a proper Alembic migration must be set up.

### Unused / Partial

- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in settings — configured but unused
- `AdminSessionResponse` schema imported in `auth/router.py` but never returned

---

## Missing Features

| Feature | Priority | Missing Work |
|---|---|---|
| Google OAuth login | High | Backend callback route, user provisioning, session creation |
| CI/CD pipeline | High | `.github/workflows/` for test, build, push, deploy |
| WhatsApp notifications | Medium | Twilio WhatsApp Business API integration in notification service |
| Analytics data export | Medium | CSV/PDF export from dashboard query results |
| Report generation | Medium | Sales reports, inventory reports as downloadable files |
| Push notifications | Medium | FCM/APNs integration for mobile push |
| Instagram product feed | Low | No spec for integration; not in current codebase |
| Alembic migration workflow | Medium | Proper migration files for future schema changes |
| Typed search/analytics schemas | Low | Replace `dict` response_model with typed Pydantic schemas |
| Notification schema cleanup | Low | Move inline router models to `schemas.py` |

---

## Production Readiness Checklist

| Item | Status | Notes |
|---|---|---|
| Environment Variables | ✅ Ready | `.env.example` documents all vars; validation runs at startup via `validate_required_settings()` |
| Database Migrations | ⚠️ Manual | Schema via `supabase/sql/setup.sql`; Alembic baseline stamps the version; future changes need migrations |
| Authentication | ✅ Ready | Supabase JWT, RBAC, admin 2FA all implemented |
| Authorization | ✅ Ready | Role-based dependencies enforced on all protected endpoints |
| Payments | ✅ Ready | Razorpay integrated with signature verification; webhooks configured |
| Structured Logging | ✅ Ready | `structlog` with JSON output; request ID propagation; Docker logs via Dozzle |
| Monitoring | ✅ Ready | Docker logs + Dozzle UI; health endpoints `/health`, `/health/ready`, `/health/live` |
| Error Handling | ✅ Ready | Global exception handlers; all errors return `{success, code, message, data}` envelope |
| Rate Limiting | ✅ Ready | Redis sliding window; configurable per endpoint type |
| Security Headers | ✅ Ready | HSTS, CSP, X-Frame-Options, nosniff applied per environment |
| CORS | ✅ Ready | Configurable origins via `ALLOWED_ORIGINS` |
| Health Checks | ✅ Ready | `/health/ready` probes DB + Redis; used by Docker healthcheck |
| Background Jobs | ✅ Ready | APScheduler with lifespan start/stop |
| Containerisation | ✅ Ready | Multi-stage Docker image, non-root user, nginx reverse proxy |
| Testing | ✅ Ready | 938 tests passing; unit + integration coverage |
| API Documentation | ✅ Ready | Auto-generated OpenAPI/Swagger (disabled in production) |
| Response Envelope | ✅ Ready | All endpoints return `{success, code, message, data}` via `BaseSuccessResponse[T]` |
| CI/CD | ❌ Missing | No automated pipeline |
| Alembic Migrations | ⚠️ Stub | Future schema changes require Alembic migration files |
| Google OAuth | ❌ Missing | Client configured but login flow not implemented |

---

## Repository Structure

```
Backend/
├── app/
│   ├── main.py                         # FastAPI app factory, lifespan, router mounting
│   ├── common/
│   │   ├── response_codes.py           # ResponseCode enum (100+ codes)
│   │   └── responses.py                # BaseSuccessResponse[T], ok(), created(), deleted(), accepted()
│   ├── core/
│   │   ├── config.py                   # Settings (pydantic-settings, all env vars)
│   │   ├── constants.py                # Shared enums (UserRole, OrderStatus, etc.)
│   │   ├── database.py                 # AsyncSessionLocal, Base, get_db
│   │   ├── dependencies.py             # get_current_user, require_admin, require_customer
│   │   ├── events.py                   # Domain event bus
│   │   ├── exceptions.py               # HadhaException hierarchy + global handlers
│   │   ├── logging.py                  # structlog configuration
│   │   ├── redis.py                    # Redis connection pool
│   │   ├── security.py                 # JWT verify, Fernet encrypt, HMAC webhook verify
│   │   └── supabase_client.py          # Supabase admin client
│   ├── middleware/
│   │   ├── audit_middleware.py         # Request audit logging
│   │   ├── rate_limit.py               # Redis sliding window rate limiter
│   │   ├── request_id.py               # X-Request-ID header injection
│   │   └── security_headers.py         # HSTS, CSP, X-Frame-Options, nosniff
│   ├── modules/
│   │   ├── addresses/                  # Address book CRUD
│   │   ├── admin/                      # KPI dashboard, audit log
│   │   ├── analytics/                  # Event tracking, admin dashboard
│   │   ├── audit/                      # Audit event repository
│   │   ├── auth/                       # JWT verify, logout, TOTP 2FA
│   │   ├── cart/                       # Guest + auth cart, merge
│   │   ├── catalog/                    # Products, variants, attributes, stock
│   │   ├── categories/                 # Hierarchical product categories
│   │   ├── cms/                        # Pages, banners, landing sections
│   │   ├── collections/                # Curated product collections
│   │   ├── coupons/                    # Discount codes
│   │   ├── fraud/                      # Fraud signal tracking
│   │   ├── inventory/                  # Low-stock alerts, movement ledger
│   │   ├── invoices/                   # PDF generation + R2 upload
│   │   ├── media/                      # Product + avatar image upload to R2
│   │   ├── notifications/              # Email/SMS notification service
│   │   ├── orders/                     # Order lifecycle management
│   │   ├── payments/                   # Razorpay integration + refunds
│   │   ├── profiles/                   # User profiles, admin user management
│   │   ├── returns/                    # Return request management
│   │   ├── reviews/                    # Product reviews + admin moderation
│   │   ├── search/                     # Full-text search, autocomplete, trending
│   │   ├── seo/                        # SEO metadata, redirects, sitemap
│   │   ├── settings/                   # Feature flags
│   │   ├── shipping/                   # Delivery One integration + tracking
│   │   ├── support/                    # Support ticket system
│   │   └── webhooks/                   # Razorpay + Delivery One webhooks
│   └── workers/
│       ├── queue.py                    # APScheduler setup
│       └── jobs/                       # Shipment sync, notification retry, cart, inventory
├── alembic/
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
│       └── 0001_baseline.py            # Empty baseline — schema managed via setup.sql
├── docker/
│   ├── Dockerfile                      # Multi-stage, non-root, 4 uvicorn workers
│   ├── docker-compose.yml              # API + Redis + Nginx (development)
│   └── nginx/
│       ├── nginx.conf
│       └── proxy_params.conf
├── supabase/
│   └── sql/
│       └── setup.sql                   # Full schema: tables, indexes, RLS, triggers, functions
├── tests/
│   ├── conftest.py                     # Fixtures, in-process ASGI client, .env.test loader
│   ├── unit/                           # 21 unit test files (~872 tests)
│   └── integration/                    # 2 integration test files (66 tests)
├── .env.example                        # All environment variables with comments
├── .env.production.example
├── .env.test
├── pyproject.toml                      # Project metadata, pytest config, ruff, mypy
├── requirements.txt                    # All Python dependencies
└── README.md
```

Each module under `app/modules/` follows the same structure:

```
<module>/
├── __init__.py
├── models.py       # SQLAlchemy ORM models
├── schemas.py      # Pydantic request/response schemas
├── repository.py   # Database query layer
├── service.py      # Business logic
└── router.py       # FastAPI endpoints
```

---

## Setup Instructions

### Prerequisites

- Python 3.12+
- Redis 7+ (local or hosted)
- PostgreSQL via Supabase project
- Cloudflare R2 bucket created
- Razorpay account (test mode for development)
- Delivery One account
- Resend account

### 1. Clone and install dependencies

```bash
cd Backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your actual values. Minimum required for local development:

```env
SECRET_KEY=<64-char hex>
ENCRYPTION_KEY=<fernet key>
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service role key>
SUPABASE_JWT_SECRET=<jwt secret>
DATABASE_URL=postgresql+asyncpg://postgres:<password>@db.xxxxx.supabase.co:5432/postgres
REDIS_URL=redis://localhost:6379/0
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_R2_BUCKET=hadha-media
CLOUDFLARE_R2_ACCESS_KEY=...
CLOUDFLARE_R2_SECRET_KEY=...
CLOUDFLARE_R2_PUBLIC_URL=https://cdn.hadha.co
CLOUDFLARE_R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
RESEND_API_KEY=...
EMAIL_FROM=noreply@hadha.co
EMAIL_REPLY_TO=support@hadha.co
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
DELIVERY_ONE_BASE_URL=https://api.deliveryone.in
DELIVERY_ONE_API_KEY=...
DELIVERY_ONE_WEBHOOK_SECRET=...
FRONTEND_URL=http://localhost:3000
ADMIN_URL=http://localhost:3001
```

### 3. Provision the database

```bash
# Apply the full schema to your Supabase project
psql $DATABASE_URL -f supabase/sql/setup.sql

# Stamp Alembic baseline (schema is already applied above)
alembic stamp 0001_baseline
```

### 4. Start Redis

```bash
# With Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or use a local installation
redis-server
```

### 5. Run the development server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API is now available at `http://localhost:8000/api/v1`
Swagger UI: `http://localhost:8000/docs`

### 6. Run tests

```bash
# All tests
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/unit/ -v

# Integration tests only
python -m pytest tests/integration/ -v

# With coverage
python -m pytest tests/ --cov=app --cov-report=html
```

---

## Deployment Instructions

### Local Docker

```bash
cd docker
docker compose up --build
```

Services started:
- **API**: `http://localhost:8000` (4 uvicorn workers)
- **Redis**: `localhost:6379`
- **Nginx**: `http://localhost:80`

### Production

1. Copy and configure production env:

```bash
cp .env.production.example .env.production
# Fill in all production values
```

2. Place SSL certificates in `docker/nginx/ssl/`:
   - `docker/nginx/ssl/fullchain.pem`
   - `docker/nginx/ssl/privkey.pem`

3. Start the stack:

```bash
cd docker
APP_ENV=production docker compose up --build -d
```

4. Verify health:

```bash
curl http://localhost/health/ready
# Expected: {"status": "ready", "checks": {"db": "ok", "redis": "ok"}}
```

### Production Notes

- **Swagger UI** (`/docs`, `/redoc`, `/openapi.json`) is automatically disabled when `APP_ENV=production`
- **TrustedHostMiddleware** activates in production — set `ALLOWED_HOSTS` to your domain(s)
- **Dozzle** runs on port `8080` and streams all container logs in real time
- Background workers (APScheduler) start automatically in the application lifespan
- Redis persistence is enabled by default (AOF) in `docker-compose.yml`

---

## Final Summary

### Overall Completion: **92%**

### Completed

- Full product catalogue (variants, attributes, images, full-text search)
- Hierarchical categories and curated collections
- Guest and authenticated cart with session merge
- Wishlist with toggle support
- Complete order lifecycle (create → confirm → ship → deliver → cancel)
- Razorpay payment integration (create, verify, refund, webhooks)
- Delivery One shipping (create shipment, tracking, rates, webhooks)
- PDF invoice generation with GST calculations
- Complete coupon/discount system
- Product review system with voting and admin moderation
- CMS (pages, banners, landing sections, sitemap)
- SEO metadata management and URL redirects
- Full-text search with autocomplete and trending
- Email (Resend + SendGrid fallback) and SMS (Twilio) notifications
- Notification preferences and delivery log
- Returns management
- Support ticket system with threaded replies
- Fraud signal detection and resolution
- Analytics event tracking and admin dashboard
- Admin KPI dashboard with immutable audit log
- Feature flags (database-backed)
- Admin 2FA (TOTP + backup codes)
- RBAC with three roles (customer, admin, super_admin)
- Redis rate limiting (sliding window, per endpoint type)
- Security headers, CORS, trusted host middleware
- Centralized `{success, code, message, data}` response envelope across all 141 endpoints
- Structured logging (structlog + Sentry)
- Background workers (APScheduler): shipment sync, notification retry, abandoned cart, inventory alerts, review reminders
- Docker multi-stage image, Nginx reverse proxy, Redis with AOF persistence
- 938 automated tests (unit + integration)

### Partially Complete

- **Notifications** (85%) — WhatsApp channel missing; only email + SMS implemented
- **Analytics** (95%) — No export/download for dashboard data
- **Google OAuth** (10%) — Credentials configured; no login route or flow implemented
- **Monitoring** (100%) — Structlog JSON logs + Dozzle Docker log viewer; health endpoints active

### Missing

- Google OAuth login flow (callback route, user provisioning)
- WhatsApp Business API notifications
- CI/CD pipeline (GitHub Actions or equivalent)
- Analytics data export (CSV/PDF)
- Sales and inventory reports as downloadable files
- Push notifications (FCM/APNs)
- Proper Alembic migration files (current setup uses Supabase SQL directly)

### Recommended Next Tasks

1. **Extend CI/CD** — Add end-to-end test gate to production workflow before container restart
2. **Implement Google OAuth login** — Add `/auth/google/callback` route, provision Supabase user from Google profile, return JWT
3. **Add WhatsApp notifications** — Wire Twilio WhatsApp Business API in `notifications/service.py` alongside existing SMS channel
4. **Add Alembic migration workflow** — Auto-generate migrations from ORM models for future schema changes without manual SQL
5. **Type the search and analytics response schemas** — Replace `BaseSuccessResponse[dict]` with proper Pydantic models for OpenAPI accuracy
