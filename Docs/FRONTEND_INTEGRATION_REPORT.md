# Frontend Integration Readiness Report

**Project:** Hadha.co E-Commerce Platform
**Date:** 2026-06-18
**Scope:** Audit-only. No code was modified, refactored, or implemented.
**Method:** Endpoints were traced from `Backend/app/main.py` router registration and every `app/modules/*/router.py`. Frontend usage was traced from `src/repositories`, `src/services`, `src/stores`, `src/integrations`, and every `src/routes/*` page and `src/components/*`.

---

## 1. Executive Summary

The backend is a mature, feature-complete FastAPI application (~28 mounted API modules, ~132 endpoints, Supabase-JWT auth, role hierarchy, workers, webhooks). The frontend is a polished TanStack Start / React SPA that is **100% driven by in-memory mock data and local Zustand stores**. There is **no HTTP client, no API base URL, and no call** anywhere in the frontend that reaches the FastAPI backend.

| Metric | Value |
|---|---|
| **Overall frontend integration readiness** | **~3%** (architecture is mock-swappable, but nothing is wired) |
| Backend modules available (with routers) | **28** (+2 internal: `audit`, `tax`) |
| APIs implemented (backend) | **~132 endpoints** |
| APIs already integrated into frontend | **0** |
| APIs pending frontend integration | **~132 (all)** |

**High-level observations**

1. **Zero real integration.** `src/repositories/index.ts` always returns the `mock/*` repositories; the Supabase branch is commented out and no FastAPI branch exists.
2. **No backend client exists.** No `axios`/`fetch` to `/api/v1`, no `VITE_API_BASE_URL`. The only external env vars are Supabase (`VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`), and even those are only consumed by a lazily-instantiated, currently-unused `supabase` client.
3. **Auth is fully mocked.** `src/stores/auth.ts` fabricates a user object on any email/password; `signInWithGoogle` is a stub. The backend expects a **Supabase JWT Bearer token** on protected routes — the frontend never obtains or sends one.
4. **The architecture is integration-friendly.** A clean repository/service boundary already exists (`repositories/types.ts` → `services/*` → components). This is the intended seam for swapping mocks → real APIs, so most integration work is implementing repository adapters rather than rewriting UI.
5. **Backend response contract is uniform:** every endpoint returns `BaseSuccessResponse<T>` = `{ success, code, message, data }`. The frontend mock layer returns raw entities, so an unwrapping adapter will be required.
6. **Admin UI exists but is entirely static** — admin products/orders/inventory/customers/coupons/reviews/cms/reports all read from `src/lib/shop-data.ts` constants or local stores, despite full admin APIs existing on the backend.

---

## 2. Backend Module Inventory

Auth legend: **Public** = no token; **User** = `get_current_user` (any authenticated role); **Optional** = `get_current_user_optional`; **Admin** = `require_admin`; **Super** = `require_super_admin`. All modules are **Implemented** on the backend and **Not Integrated** on the frontend (see §1), so those two columns are stated once here and not repeated per row.

> Common contract for **all** modules
> - **Response schema:** `{ success: bool, code: string, message: string, data: T }` (`BaseSuccessResponse[T]`). Errors: `{ success: false, code, message, data: null }`.
> - **Auth transport:** `Authorization: Bearer <Supabase JWT>`.
> - **Backend status:** Implemented. **Frontend status:** Not Integrated (0 endpoints wired).

| # | Module | Purpose | Key APIs (method · path under `/api/v1`) | Auth |
|---|---|---|---|---|
| 1 | **dev_auth** | DEV-only email/password → Supabase JWT (for QA/Postman) | `POST /dev/login`, `GET /dev/me` | Public (dev) / User |
| 2 | **auth** | Verify Supabase JWT, logout, force-logout, admin 2FA | `POST /auth/verify-token`, `POST /auth/logout`, `POST /auth/force-logout/{user_id}`, `POST /auth/admin/2fa/setup`, `/verify`, `/validate` | User / Super / Admin |
| 3 | **profiles** | Current-user profile + admin user management | `GET /me`, `PATCH /me`, `PATCH /me/avatar`, `GET /admin/users`, `PATCH /admin/users/{id}/role`, `PATCH /admin/users/{id}/status` | User / Admin |
| 4 | **categories** | Category tree + admin CRUD | `GET /categories`, `POST /admin/categories`, `PATCH /admin/categories/{id}`, `DELETE /admin/categories/{id}` | Public / Admin |
| 5 | **collections** | Collections browse + admin CRUD + product membership | `GET /collections`, `GET /collections/{slug}`, `POST/PATCH/DELETE /admin/collections...`, `POST/DELETE /admin/collections/{id}/products` | Public / Admin |
| 6 | **catalog** | Product listing/detail + full admin product/variant/attribute/stock management | `GET /products`, `GET /products/{slug}`, `GET/POST/PATCH/DELETE /admin/products...`, variants, attributes, `POST /admin/products/{id}/stock/adjust` | Public / Admin |
| 7 | **media** | Product image upload/delete/set-primary | `POST/DELETE /admin/products/{id}/images...`, `PATCH .../primary` | Admin |
| 8 | **search** | Full-text search, autocomplete, trending | `GET /search`, `GET /search/autocomplete`, `GET /search/trending` | Public |
| 9 | **seo** | SEO metadata, redirects, sitemap | `GET /seo/page`, `PUT /admin/seo/pages`, `POST /admin/seo/redirects`, `GET /sitemap.xml` | Public / Admin |
| 10 | **inventory** | Low-stock report, per-product inventory, adjustments | `GET /admin/inventory/low-stock`, `GET /admin/products/{id}/inventory`, `POST .../inventory/adjust` | Admin |
| 11 | **addresses** | Customer address book | `GET/POST /me/addresses`, `PATCH /me/addresses/{id}`, `POST .../default`, `DELETE /me/addresses/{id}` | User |
| 12 | **wishlist** | Wishlist list/add/toggle/remove | `GET /me/wishlist`, `POST /me/wishlist`, `POST /me/wishlist/toggle`, `DELETE /me/wishlist/{product_id}` | User |
| 13 | **cart** | Cart with server-side totals + guest merge | `GET /cart`, `POST /cart/items`, `PATCH /cart/{cart_id}/items/{item_id}`, `DELETE .../items/{item_id}`, `DELETE /cart`, `POST /cart/merge` | User/Optional |
| 14 | **coupons** | Coupon validation + admin CRUD | `POST /coupons/validate`, `GET/POST/PATCH/DELETE /admin/coupons...` | User / Admin |
| 15 | **orders** | Place order, list, detail, cancel + admin management | `POST /orders`, `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/cancel`, `GET /admin/orders`, `GET /admin/orders/{id}`, `PATCH /admin/orders/{id}/status` | User / Admin |
| 16 | **payments** | Razorpay-style create/verify + admin refunds | `POST /payments/create-order`, `POST /payments/verify`, `GET /orders/{id}/payment`, `POST /admin/orders/{id}/refund`, `GET /admin/orders/{id}/refunds` | User / Admin |
| 17 | **invoices** | Order invoice retrieval | `GET /orders/{id}/invoice` | User |
| 18 | **webhooks** | Inbound payment/shipping webhooks | `POST` (2 webhook receivers) | Public (signed) |
| 19 | **shipping** | Shipment tracking, rates, admin shipment lifecycle | `GET /orders/{id}/shipment`, `GET /tracking/{awb}`, `GET /shipping/rates`, admin create/get/delete shipment | User/Public / Admin |
| 20 | **reviews** | Product reviews, summary, voting + admin moderation | `GET /reviews/products/{id}`, `/summary`, `POST /reviews`, `PATCH/DELETE /reviews/{id}`, `POST /reviews/{id}/vote`, `GET /reviews/admin/pending`, `POST /reviews/admin/{id}/action` | Public / User / Admin |
| 21 | **cms** | Home page composition, CMS pages, banners, landing sections | `GET /cms/home`, `GET /cms/pages/{slug}`, admin banners/sections/pages CRUD | Public / Admin |
| 22 | **analytics** | Event ingestion + admin dashboard | `POST /analytics/events`, `GET /analytics/admin/dashboard` | Optional / Admin |
| 23 | **returns** | Return requests + admin processing | `POST /returns`, `GET /returns`, `GET /returns/admin/returns`, `PATCH /returns/admin/returns/{id}/status` | User / Admin |
| 24 | **support** | Support tickets + messages + admin desk | `POST/GET /support/tickets`, `GET /support/tickets/{id}`, `POST .../messages`, admin list/patch/messages | User / Admin |
| 25 | **notifications** | Notification preferences + admin logs | `GET/PUT /notifications/preferences`, `GET /notifications/admin/logs` | User / Admin |
| 26 | **fraud** | Fraud signals review | `GET/POST /admin/fraud/signals`, `PATCH /admin/fraud/signals/{id}` | Admin |
| 27 | **settings** | Feature flags | `GET /admin/settings/flags`, `PUT /admin/settings/flags/{key}` | Admin |
| 28 | **admin** | KPI dashboard + audit log viewer | `GET /admin/dashboard`, `GET /admin/audit-logs` | Admin |
| – | **audit** / **tax** | Internal services (no router; used by middleware/order pricing) | — | — |

---

## 3. API Integration Matrix

Frontend Screen lists the page that *should* consume the endpoint. **Current Integration Status is "Not Integrated" for every row** (no exceptions found), so the table focuses on the mapping, the missing work, and priority. Grouped by feature for readability.

### Storefront — browse (High priority: the customer-facing core)

| Endpoint | Method | Module | Frontend Screen | Missing Frontend Work | Priority |
|---|---|---|---|---|---|
| `/products` | GET | catalog | `products` grid, `search`, `collections.$slug`, Featured/NewArrivals/Trending | Replace `mock products.repository`/`shop-data` with real list call; map filters & pagination | High |
| `/products/{slug}` | GET | catalog | `products.$slug` | Real product detail fetch | High |
| `/categories` | GET | categories | Header mega-menu, `ShopByCategory` | Replace `mega-menu-data.ts` static tree | High |
| `/collections`, `/collections/{slug}` | GET | collections | `collections.index`, `collections.$slug` | Real collection fetch (currently mock repo) | High |
| `/search`, `/search/autocomplete`, `/search/trending` | GET | search | `search`, `SearchOverlay` | Wire to real search; remove client-side `suggest` | High |
| `/cms/home` | GET | cms | `index` (home) | Home is fully hardcoded; fetch hero/sections/banners | Medium |
| `/cms/pages/{slug}` | GET | cms | `about`, `faq`, `privacy`, `terms`, `shipping-returns` | Static pages should pull CMS content | Low |
| `/reviews/products/{id}`, `/summary`, `/{id}/vote` | GET/POST | reviews | `products.$slug` Reviews, `Reviews` component | Replace mock reviews repo; add submit & vote | Medium |

### Cart & checkout (High priority: revenue path)

| Endpoint | Method | Module | Frontend Screen | Missing Frontend Work | Priority |
|---|---|---|---|---|---|
| `/cart` (+ items, merge, clear) | GET/POST/PATCH/DELETE | cart | `cart`, `CartDrawer`, `QuantityStepper` | Replace local `stores/cart.ts` + mock repo; adopt server totals; guest→user merge on login | High |
| `/coupons/validate` | POST | coupons | `checkout`, `cart` | Replace mock coupon repo validation | High |
| `/me/addresses` (CRUD + default) | GET/POST/PATCH/DELETE | addresses | `checkout`, `account.index` | Replace `useAddresses` Zustand store | High |
| `/orders` (create) | POST | orders | `checkout` | Real order placement | High |
| `/payments/create-order`, `/payments/verify` | POST | payments | `checkout`, `checkout.success` | Integrate payment gateway flow (currently faked success) | High |
| `/orders/{id}/payment` | GET | payments | `checkout.success` | Payment status confirmation | Medium |
| `/orders/{id}/invoice` | GET | invoices | `account.index`, order detail | Invoice download UI absent | Low |

### Customer account (High/Medium)

| Endpoint | Method | Module | Frontend Screen | Missing Frontend Work | Priority |
|---|---|---|---|---|---|
| `/auth/verify-token`, `/auth/logout` | POST | auth | `account.login`, app boot | Real session bootstrap & logout | High |
| `/me`, `/me`(patch), `/me/avatar` | GET/PATCH | profiles | `account.index` | Real profile load/edit + avatar upload | High |
| `/orders`, `/orders/{id}`, `/orders/{id}/cancel` | GET/POST | orders | `account.index` (order history) | Replace `stores/orders.ts`; add cancel | High |
| `/me/wishlist` (+toggle/remove) | GET/POST/DELETE | wishlist | `wishlist`, `ProductCard` | Replace `stores/wishlist.ts` + mock repo | Medium |
| `/returns` (create/list) | POST/GET | returns | (no screen) | **Build return-request UI** | Medium |
| `/support/tickets` (+messages) | POST/GET | support | `contact` | `contact` is a static form; build ticketing | Medium |
| `/notifications/preferences` | GET/PUT | notifications | `account.index` | **Build notification-prefs UI** | Low |
| `/tracking/{awb}`, `/orders/{id}/shipment` | GET | shipping | order detail | Build shipment-tracking UI | Medium |

### Admin (Medium — internal, gated behind 2FA-capable admin auth)

| Endpoint group | Module | Frontend Screen | Missing Frontend Work | Priority |
|---|---|---|---|---|
| `/admin/dashboard`, `/admin/audit-logs`, `/analytics/admin/dashboard` | admin, analytics | `admin.index`, `admin.reports` | Replace static KPIs with real dashboard | Medium |
| `/admin/products...` (+variants, attributes, stock, images) | catalog, media | `admin.products` | Full product CRUD + image upload (currently read-only static) | Medium |
| `/admin/orders...` (+status, refund) | orders, payments | `admin.orders` | Order management + refunds | Medium |
| `/admin/inventory/low-stock`, `/inventory/adjust` | inventory | `admin.inventory` | Real inventory + adjustments (currently `stores/admin-inventory`) | Medium |
| `/admin/coupons...` | coupons | `admin.coupons` | Coupon CRUD (currently `stores/admin-coupons`) | Medium |
| `/reviews/admin/pending`, `/admin/{id}/action` | reviews | `admin.reviews` | Moderation (currently `stores/admin-reviews`) | Medium |
| `/cms/admin/banners|sections|pages` | cms | `admin.cms` | CMS management (currently `stores/cms`) | Medium |
| `/admin/users...` (role/status) | profiles | `admin.customers` | Customer management | Medium |
| `/returns/admin/...`, `/support/admin/...`, `/admin/fraud/...`, `/admin/settings/flags`, `/notifications/admin/logs` | returns, support, fraud, settings, notifications | (no screens) | **Build admin screens** | Low |
| `/auth/admin/2fa/setup|verify|validate`, `/auth/force-logout` | auth | (no screens) | **Build admin 2FA + session controls** | Medium |

---

## 4. Frontend Coverage Analysis

Every route was inspected. Data sources fall into three buckets: **(A)** `lib/shop-data.ts` static constants, **(B)** `repositories/mock/*` via `services/*` (still mock, but behind the swappable seam), **(C)** local `Zustand` stores. None reach the backend.

| Screen / Component | Consumes today | Should consume | Mock / hardcoded | Missing CRUD |
|---|---|---|---|---|
| `index.tsx` (Home) | Static components | `/cms/home`, `/products`, `/collections` | Hero, sections, Instagram, "why choose us" all hardcoded | — |
| `products.$slug.tsx` | `services` (B) + shop-data (A) via `useQuery` | `/products/{slug}`, reviews, related | Mock product; reviews mock | Add-to-cart hits local store |
| `collections.index/$slug` | `services` (B) | `/collections...`, `/products` | Mock collections | — |
| `search.tsx` + `SearchOverlay` | `services.suggest` (B) | `/search*` | Client-side filtering of mock list | — |
| `cart.tsx` + `CartDrawer` | `stores/cart` (C) + `services` | `/cart*`, `/coupons/validate` | Totals computed client-side | Server cart sync missing |
| `checkout.tsx` | `stores/cart`, `useAddresses`, `services/orders`/`coupons` (B/C) | addresses, orders, payments, coupons | Payment faked; order id generated locally | Order create/pay not wired |
| `checkout.success.tsx` | local | `/orders/{id}/payment`, `/orders/{id}` | Static success | — |
| `wishlist.tsx` + `ProductCard` | `stores/wishlist` (C) | `/me/wishlist*` | Local list | — |
| `account.login/register` | `stores/auth` (C) | `/dev/login` or Supabase + `/auth/verify-token` | Fabricated user | Real login/register |
| `account.index` | `stores/auth`, `stores/orders`, `useAddresses` | `/me`, `/orders`, `/me/addresses` | All local | Profile/address/order CRUD |
| `contact.tsx` | none (static form) | `/support/tickets` | Form does nothing | Ticket create |
| `about/faq/privacy/terms/shipping-returns` | static | `/cms/pages/{slug}` | Hardcoded copy | — |
| `store-locator.tsx` | static | (no backend) | Hardcoded stores — **Backend Not Available** | — |
| `admin.index` | shop-data (A) | `/admin/dashboard` | Static KPIs | — |
| `admin.products` | shop-data (A) | `/admin/products*`, media | Static table; edit/delete are no-ops | Full CRUD + image upload |
| `admin.orders` | `stores/orders` (C) | `/admin/orders*` | Local | Status/refund |
| `admin.inventory` | `stores/admin-inventory` (C) + shop-data | `/admin/inventory*` | Local | Adjustments |
| `admin.coupons` | `stores/admin-coupons` (C) | `/admin/coupons*` | Local | CRUD |
| `admin.reviews` | `stores/admin-reviews` (C) | `/reviews/admin/*` | Local | Moderation |
| `admin.cms` | `stores/cms` (C) | `/cms/admin/*` | Local | CRUD |
| `admin.customers` | static/local | `/admin/users*` | Local | Role/status |
| `admin.reports` | shop-data (A) | `/admin/dashboard`, `/analytics/admin/dashboard` | Static charts | — |

---

## 5. Missing Integrations (everything below exists in backend, unused in frontend)

- **Auth/session:** `verify-token`, `logout`, `force-logout`, admin 2FA (setup/verify/validate). No real session anywhere.
- **Catalog:** product list/detail, all admin product/variant/attribute/stock endpoints, product image upload.
- **Taxonomy:** categories tree, collections + membership management.
- **Search:** server search, autocomplete, trending.
- **Cart:** server cart + line ops + guest merge + server totals.
- **Checkout:** coupon validation, order create, payment create/verify, payment status, invoice.
- **Account:** profile get/update, avatar upload, addresses CRUD, wishlist, order history/cancel.
- **Post-purchase:** returns (customer + admin), shipment tracking/rates, invoices.
- **Engagement:** reviews (read/write/vote/moderate), support tickets + messaging, notification preferences.
- **CMS:** home composition, CMS pages, banners, landing sections (read + admin CRUD).
- **Admin ops:** KPI dashboard, audit logs, analytics dashboard, user management, inventory, coupons, fraud signals, feature flags, notification logs.
- **Analytics:** event ingestion (`POST /analytics/events`) — no events emitted from the frontend.

**Backend Not Available (frontend feature with no API):** Store Locator (`store-locator.tsx`), Instagram feed section, newsletter signup (`Newsletter.tsx`), WhatsApp FAB.

---

## 6. Authentication & Authorization Review

| Concern | Backend | Frontend | Verdict |
|---|---|---|---|
| Login flow | Supabase Auth → JWT; `dev/login` for QA | `stores/auth.login` fabricates a user from the email string; no network call | **Not Integrated** |
| Google OAuth | Supabase OAuth supported | `signInWithGoogle` is an explicit stub | Not Integrated |
| Token handling | Expects `Authorization: Bearer <JWT>` | No token captured or stored; `supabase` client exists but unused by auth store | Not Integrated |
| Refresh logic | Supabase auto-refresh (if client used) | `persistSession`/`autoRefreshToken` configured on the unused client; not wired to requests | Not Integrated |
| Protected routes | Per-endpoint `Depends(get_current_user / require_admin / require_super_admin)` | No route guards; `/admin/*` and `/account/*` are reachable without auth | **Missing** |
| Role-based access | `customer < admin < super_admin` hierarchy enforced server-side | No role concept in `MockUser`; admin UI ungated | Missing |
| Permission checks | `require_2fa_verified` gate for admin; `X-Required-Roles` headers | None | Missing |
| Admin 2FA | Full TOTP setup/verify/validate | No UI | Missing |

**Recommended integration order:** Supabase client → real login/register → capture JWT → attach to an HTTP client → `verify-token` on boot → route guards → role gating → admin 2FA.

---

## 7. State Management Analysis (TanStack Query + Zustand)

- **Existing queries:** Only **3 `useQuery` call sites** — `products.$slug.tsx`, `collections.$slug.tsx`, `search.tsx` — and all resolve against **mock services**, not the network. `QueryClient` is provisioned in `router.tsx`/`__root.tsx`.
- **Mutations:** **Zero `useMutation`** anywhere. All writes (cart, wishlist, auth, admin edits) mutate Zustand stores synchronously.
- **Cache invalidation:** None (no mutations → nothing to invalidate).
- **Optimistic updates:** None via Query. Zustand stores update immediately, which *looks* optimistic but has no server reconciliation.
- **Duplicate requests:** Not applicable yet (no requests). Risk later: home page components each import `shop-data` directly instead of sharing a query.
- **Missing API hooks:** No `useCart`, `useProfile`, `useOrders`, `useWishlist`, `useAdmin*` query hooks exist. The `services/*` layer is the natural home for query/mutation factories.
- **Reuse opportunities:** The `repositories` + `services` seam is well-designed — implement `repositories/api/*.repository.ts` adapters and the existing `useQuery` sites work unchanged. Zustand stores backing cart/wishlist/orders should become thin caches over query state to avoid dual sources of truth.

---

## 8. Forms & Validation

- **Forms connected to backend:** None.
- **Forms using mock/local data:** login, register (`account.*`), checkout (address + payment), contact, admin product/coupon/cms editors. All write to Zustand or do nothing.
- **Validation:** `react-hook-form` + `zod` + `@hookform/resolvers` are installed and `components/ui/form.tsx` exists, but client validation is minimal/ad-hoc on the audited forms.
- **Backend validation not reflected:** Pydantic schemas (e.g. address pincode/phone, coupon rules, review rating bounds, order payloads) are not mirrored client-side, so server `422`/business errors won't surface meaningfully.
- **Missing error handling:** Forms have no error display path for server responses (no mutation error states).

---

## 9. File Upload & Download Integration

| Capability | Backend | Frontend |
|---|---|---|
| Avatar upload | `PATCH /me/avatar` | No upload UI/call |
| Product image upload | `POST /admin/products/{id}/images` (+ delete, set-primary) | `admin.products` has no upload control |
| Invoice download | `GET /orders/{id}/invoice` | No download button |
| Sitemap | `GET /sitemap.xml` | N/A (SEO infra) |

- **Progress handling:** None (no uploads exist).
- **Error handling:** None.
- **Missing UI:** All upload/download flows must be built (file input, multipart request, progress, primary-image toggle, invoice link).

---

## 10. Real-Time Features

| Mechanism | Backend support | Frontend |
|---|---|---|
| WebSockets | None found | None |
| SSE | None found | None |
| Polling | Not used | Not used |
| Background jobs | **Yes** — `app/workers/*` (abandoned cart, inventory alerts, notification retry, review reminder, shipment sync, partition manager) | No UI surfaces their effects |
| Notifications | `notifications` module (Resend email, MSG91 SMS) + preferences + admin logs | No notification-prefs or in-app notification UI |
| Webhooks | Inbound payment/shipping webhooks | N/A (server-to-server) |

**Verdict:** No real-time channel exists on either side. Order/shipment status changes (driven by workers/webhooks) would require polling or a future WS/SSE channel; today the frontend cannot reflect them at all.

---

## 11. Error Handling Review

- **API error handling:** None — no API calls. The uniform `{ success, code, message }` error envelope is unused; no central error normalizer exists.
- **Loading states:** Minimal. The 3 `useQuery` sites resolve from memory near-instantly; skeletons (`ui/skeleton.tsx`) exist but are sparsely applied.
- **Empty states:** `components/site/EmptyState.tsx` exists and is used in a few places (cart/wishlist) — reusable once data is real.
- **Retry logic:** Default TanStack Query retry only; irrelevant against mocks.
- **Toasts:** `sonner` is installed and used for local actions (add to cart, etc.) — good foundation for surfacing mutation results.
- **Global error boundary:** `lib/error-capture.ts`, `lib/error-page.ts`, `lib/lovable-error-reporting.ts` and a root error component exist. This is render-level, not network-level.
- **Missing:** Central API-error interceptor, per-mutation error toasts, 401→re-auth redirect, 403 role messaging, server-validation surfacing.

---

## 12. Frontend Architecture Gaps

1. **No HTTP client / API layer.** Add a single typed client (base URL `VITE_API_BASE_URL` + `/api/v1`, Bearer injection, response-envelope unwrapping, error normalization). This is the keystone gap.
2. **No env var for the backend.** `config/env.ts` only knows Supabase; add API base URL.
3. **Repository adapters missing.** Implement `repositories/api/*.repository.ts` and switch `repositories/index.ts` to select them — the seam is already designed for this.
4. **Dual sources of truth.** Cart/wishlist/orders live in Zustand *and* will live in Query; define ownership (Query as server cache; Zustand for pure UI state only).
5. **Static data leakage.** 20 files import `lib/shop-data` directly (incl. home components and admin pages), bypassing the service seam. These need to route through services to become integratable.
6. **No auth/role guards** at the router level (TanStack Router `beforeLoad`).
7. **Response unwrapping.** Mocks return raw entities; real API returns `data` wrapped. Adapters must unwrap consistently.

---

## 13. Integration Priority Roadmap

**Phase 0 — Foundation (blocking everything)** · Effort: **Medium**
- HTTP client + `VITE_API_BASE_URL` + envelope unwrap + error normalizer.
- Real auth (Supabase or `dev/login`) → JWT capture → Bearer attach → `verify-token` on boot.
- Route guards + role gating.

**Phase 1 — Critical (customer revenue path)**
- Catalog list/detail + categories + collections (api repositories). · Large
- Search + autocomplete + trending. · Medium
- Server cart + coupon validation. · Medium
- Checkout: addresses → order create → payment create/verify → success confirmation. · Large
- Profile + order history/cancel. · Medium

**Phase 2 — Important (engagement & post-purchase)**
- Wishlist server sync. · Small
- Reviews read/write/vote. · Medium
- Returns + shipment tracking + invoices. · Medium
- Support tickets + messaging. · Medium
- CMS-driven home + static pages. · Medium
- Avatar + product image upload. · Medium

**Phase 3 — Enhancements (admin & ops)**
- Admin product/order/inventory/coupon/review/cms/customer management. · Large
- Admin dashboard + analytics + audit logs. · Medium
- Admin 2FA + force-logout. · Medium
- Fraud signals, feature flags, notification prefs/logs. · Medium
- Analytics event emission (`POST /analytics/events`). · Small

---

## 14. Risks & Blockers

- **Missing backend APIs (frontend features unsupported):** Store Locator, Instagram feed, Newsletter signup — no endpoints. Decide build-vs-remove.
- **Missing frontend components/screens:** Returns, support ticketing, notification preferences, shipment tracking, admin 2FA, and several admin desks (fraud, settings, notification logs, audit) have **no UI at all**.
- **Contract mismatches:**
  - Response envelope `{ success, code, message, data }` vs. mocks returning raw entities → adapter required everywhere.
  - Cart totals computed client-side vs. server-authoritative totals → must defer to server.
  - Order ID generated locally vs. server-issued → checkout flow must change ordering.
- **Naming inconsistencies:** Frontend `MockUser`/`Address` shapes vs. backend `Profile`/address schemas; field naming (`pincode` vs backend fields) and ID formats (`usr_…` mock vs UUID) differ — type alignment needed.
- **Auth model gap:** Frontend has no role/JWT concept; backend enforces 3-tier roles + admin 2FA. Largest single blocker for admin integration.
- **Technical debt:** 20 direct `shop-data` imports bypass the service seam; dual state (Zustand + future Query); no API error handling primitives.
- **Dependency blockers:** Requires Supabase project credentials (or enabled `dev/login`) and a deployed backend base URL before any integration can be tested. CORS must allow the frontend origin.

---

## 15. Final Integration Score

| Dimension | Score | Basis |
|---|---|---|
| **Backend completeness** | **~90%** | 28 modules, ~132 endpoints, auth, workers, webhooks, uniform contract; internal-only gaps and unverified runtime depth |
| **Frontend integration completeness** | **~3%** | 0 endpoints wired; only a well-designed swap seam + Query provider in place |
| **API coverage (frontend → backend)** | **0%** | 0 / ~132 endpoints consumed |
| **Production readiness** | **~10%** | Backend likely deployable; frontend cannot transact, authenticate, or persist anything against the server |

---

## Action Plan — exact order to reach a fully integrated, production-ready app

1. **Add the API client & env** (`VITE_API_BASE_URL`, Bearer injector, `{data}` unwrap, error normalizer).
2. **Wire real auth:** Supabase (or `dev/login`) → store JWT → attach to client → `verify-token` on app boot → `logout`.
3. **Add router guards & role gating** for `/account/*` and `/admin/*`.
4. **Implement `repositories/api/*` adapters** for products, categories, collections; flip `repositories/index.ts` to use them (the 3 existing `useQuery` sites light up first).
5. **Search** (search/autocomplete/trending) → replace client-side suggest.
6. **Server cart** + **coupon validation**; make Zustand cart a thin cache.
7. **Checkout pipeline:** addresses CRUD → `orders` create → `payments` create/verify → success via `orders/{id}/payment`.
8. **Account:** profile get/update + avatar upload + order history/cancel.
9. **Wishlist** server sync.
10. **Reviews** read/write/vote; **CMS** home + static pages.
11. **Returns, shipment tracking, invoices, support tickets, notification preferences** (build missing UIs).
12. **Admin desks:** products (+images), orders (+refunds), inventory, coupons, reviews moderation, customers, CMS — then dashboard/analytics/audit.
13. **Admin 2FA + force-logout.**
14. **Analytics event emission**, then fraud/feature-flags/notification-logs admin tools.
15. **Cross-cutting hardening:** global API-error toasts, 401→re-auth, 403 messaging, loading/empty/skeleton states, optimistic updates + cache invalidation on all mutations.

---

*End of report. No source files were modified.*
