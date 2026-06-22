# Frontend Backend-Integration Readiness Verification

**Project:** Hadha.co — Frontend (`F:\Work\Hadha.co\Project\Frontend`)
**Date:** 2026-06-18
**Premise:** Backend assumed production-ready. This report verifies **frontend-only** architectural readiness to integrate with it.
**Method:** Conclusions are traced from real imports and usage — `src/repositories/*`, `src/services/*`, `src/stores/*`, `src/routes/*`, `src/integrations/*`, `src/config/*`, `.env`. No code was modified.

**Classification legend:** ✅ Ready · 🟡 Needs Minor Changes · 🟠 Needs Significant Work · 🔴 Critical Blocker

---

## 1. Executive Summary

The frontend is a well-structured TanStack Start + React app with a **deliberately designed integration seam** (repository contract → service layer → components) and TanStack Query already provisioned. That seam is the project's single biggest asset: it means backend integration is mostly *additive* (write API adapters) rather than a rewrite. However, **every concrete piece needed to actually talk to a backend is absent**: no HTTP client, no API base URL, no real auth, no response/error abstraction, no route guards, and all 7 repositories are mock-only.

| Score | Value | Notes |
|---|---|---|
| **Overall Backend Integration Readiness** | **34 / 100** | Strong seam, zero wiring |
| **Production Readiness** | **12 / 100** | Cannot transact against a server |
| **API Layer Readiness** | **15 / 100** | No client, config, interceptors, or mapping |
| **State Management Readiness** | **55 / 100** | Query present but unused for server state; Zustand owns server data |
| **Authentication Readiness** | **10 / 100** | Fully mocked; no JWT, no guards |
| **Scalability Score** | **65 / 100** | Clean modular structure scales well once wired |

**Architecture quality:** Above average for a mock-stage app. Clear module boundaries, typed contracts, consistent conventions, a real repository pattern (not just folders named "repository").

**Biggest blockers:** (1) no API client / base URL, (2) auth is a fabricated Zustand stub, (3) no API repository implementations, (4) server state owned by persisted Zustand stores, (5) no response-envelope/DTO mapping layer.

**Overall integration effort:** **Medium-to-Large.** The seam saves significant work, but the API layer, auth, mapping, and guards must all be built from zero before the first real call succeeds.

---

## 2. Frontend Structure Verification

| Concern | Location | Status | Finding |
|---|---|---|---|
| API folders | *(none — `src/lib/api/example.functions.ts` only)* | 🔴 | No `src/lib/http` / `src/api` client module exists. |
| Repository pattern | `src/repositories/{index,types}.ts`, `src/repositories/mock/*` | ✅ | Genuine pattern: interface contract + mock impls + factory. Only mock branch is live. |
| Services | `src/services/{products,cart,coupons,orders,reviews,wishlist}.ts` | 🟡 | Thin orchestration over repos. Correctly placed; currently pass-through (no mapping). |
| React Query structure | `src/router.tsx`, `src/routes/__root.tsx` | 🟠 | `QueryClient` + `QueryClientProvider` wired, but only 3 `useQuery` sites and **0 `useMutation`**; no `queryKeys`, no hooks folder. |
| State management | `src/stores/*` (12 Zustand stores) | 🟠 | Used for both UI state *and* server-owned data (cart, orders, wishlist, admin entities). |
| Shared modules | `src/components/ui/*`, `src/components/common/*`, `src/lib/*` | ✅ | Solid shared layer (shadcn UI, format, utils, error capture). |
| Feature modules | `src/routes/*`, `src/components/site/*` | 🟡 | Feature-organized by route; data access leaks via direct `lib/shop-data` imports in 20 files. |
| Types | `src/types/shop.ts`, plus types embedded in `src/stores/orders.ts` | 🟠 | Frontend-shaped models only; no DTOs; `Order`/`OrderStatus` types live in a *store* and are imported by the repository contract (layering smell). |
| Validation | `react-hook-form` + `zod` installed; `src/components/ui/form.tsx` | 🟠 | Infrastructure present; little applied validation on real forms. |
| Constants | `src/constants/{routes,storage}.ts`, `src/config/{env,site,brand}.ts` | 🟡 | Good config split, but `config/env.ts` knows only Supabase — no API config. |

**Verdict:** Structure is integration-*friendly* but integration-*incomplete*. The folders that matter for swapping (repositories/services) are correct; the folders that matter for *connecting* (api client, hooks, env, auth) are missing or Supabase-only.

---

## 3. API Layer Assessment

| Capability | Present? | Evidence / Gap |
|---|---|---|
| API client | 🔴 No | No axios/fetch wrapper. Grep for `api/v1`, `axios`, `VITE_API` → only Supabase + SSR `fetch` in `src/server.ts`. |
| Repository layer | ✅ Yes (mock) | `src/repositories/types.ts` contract + `mock/*`. |
| Service layer | 🟡 Yes (thin) | `src/services/*` delegate to `repositories` with no transformation. |
| Request abstraction | 🔴 No | No request builder, no base URL join, no query-param serializer. |
| Response abstraction | 🔴 No | Backend returns `{success,code,message,data}`; frontend has no unwrap helper. Mocks return raw entities. |
| Error abstraction | 🔴 No | No normalized `ApiError`; `lib/error-capture.ts` is render-level only. |
| Auth interceptor | 🔴 No | No Bearer-token injection anywhere. |
| Refresh-token handling | 🔴 No | Supabase client has `autoRefreshToken:true` (`src/integrations/supabase/client.ts`) but is **unused** by the app. |
| Retry strategy | 🟡 Default only | TanStack Query default retry; nothing custom; irrelevant vs mocks. |
| API configuration | 🔴 No | `src/config/env.ts` exposes only `supabaseUrl/Key/ProjectId`; no `apiBaseUrl`. |

**Missing, in priority order:** HTTP client → API base-URL config → response unwrap → error normalizer → auth interceptor → 401/refresh handling → query/mutation hook factory.

---

## 4. Repository Verification

| Item | Status | Evidence |
|---|---|---|
| Mock repositories | ✅ Present | `src/repositories/mock/{cart,collections,coupons,orders,products,reviews,wishlist}.repository.ts` — all 7 implement their interface and are already `async` with simulated latency (`delay()` in `products.repository.ts`). |
| Real (API) repositories | 🔴 Absent | No `src/repositories/api/*` (or `supabase/*`). Factory's real branch is commented out in `src/repositories/index.ts`. |
| Repository interfaces | ✅ Excellent | `src/repositories/types.ts` defines `ProductRepository`, `CollectionRepository`, `WishlistRepository`, `CartRepository`, `OrdersRepository`, `ReviewsRepository`, `CouponsRepository`, aggregated in `Repositories`. |
| Dependency injection | 🟡 Factory-based | `buildRepositories()` in `index.ts` selects implementations; consumed as a singleton `repositories`. Swap point is centralized (good) but static (no runtime DI/config switch). |
| Swappable implementation | 🟡 Designed, not exercised | `hasSupabase()` gate exists but is `void`-ed; only mock returned. |

**Can mocks be swapped easily?** **Mostly yes — with two caveats.** (1) Interfaces are clean and async, so an `api/*` impl drops in behind the factory with no call-site changes. (2) **But** mock contracts encode *frontend* shapes and conventions that won't match the backend 1:1:
- `WishlistRepository` returns `Promise<string[]>` (product-id arrays); backend wishlist returns entities.
- `CartRepository` works in `CartLine = {productId, qty}` and computes totals client-side; backend cart is server-authoritative with totals.
- `OrdersRepository.place()` takes `Omit<Order,"createdAt"|"status">` and the `Order` type comes from `src/stores/orders.ts`; backend issues the id/status/timestamps.
- `ReviewsRepository` is read-only (`listForProduct`, `summary`); backend supports create/vote/moderate — interface must **expand**.
- `CouponsRepository.validate(code, subtotal)` shape must map onto `POST /coupons/validate`.

So: **swappable at the wiring level, but each adapter needs a mapping layer** between backend DTOs and these interfaces — classify **🟠 Needs Significant Work** per repository.

---

## 5. Service Layer Verification

| Concern | Status | Evidence |
|---|---|---|
| Business logic location | 🟡 | Intended in `services/*` per `services/products.ts` doc comment; today services are pure delegation (`services/cart.ts` forwards 1:1 to `repositories.cart`). |
| API orchestration | 🟠 | No cross-call orchestration (e.g., checkout = validate coupon → create order → create payment) exists; checkout logic lives in the route component. |
| Data transformation | 🔴 | None. Services pass repository output straight through. The envelope-unwrap + DTO→model mapping has no home yet. |
| Mapping logic | 🔴 | Absent. No mappers/DTO types. |
| Duplicate logic | 🟡 | `getProductById` in `services/products.ts` reads `lib/shop-data` directly (a sync escape hatch flagged in its own comment); 20 files import `lib/shop-data` directly, bypassing services. |

**Backend-ready?** The service *layer* is correctly positioned and is the right place to host mapping/orchestration — but it currently contains **none** of it. Services are ready to *receive* integration logic, not yet performing it. **🟠**

---

## 6. State Management Verification

| Concern | Status | Evidence |
|---|---|---|
| React Query (server state) | 🟠 | Provider wired (`__root.tsx`), but only `products.$slug.tsx`, `collections.$slug.tsx`, `search.tsx` use `useQuery` — all against mock services. No mutations. |
| Zustand/Redux | 🟠 | 12 Zustand stores (`src/stores/*`). Several own **server data**: `cart.ts`, `orders.ts`, `wishlist.ts`, `admin-coupons.ts`, `admin-inventory.ts`, `admin-reviews.ts`, `cms.ts`. |
| Context | ✅ | Not over-used; Query context via router. |
| Local state | ✅ | Route-level `useState` for UI (tabs, filters) is appropriate. |
| Server vs UI state separation | 🔴 | Violated — cart/orders/wishlist/admin entities are persisted in Zustand (`persist` middleware, e.g. `hadha-auth`, `hadha-addresses`), which will collide with server as source of truth. |
| Cache ownership | 🟠 | Ambiguous: Query *and* Zustand both cache domain data. Ownership must be decided (Query = server cache; Zustand = pure UI). |
| Duplicate state | 🟠 | Cart exists in `stores/cart.ts` and conceptually in `repositories.cart`; wishlist likewise. |
| Synchronization issues | 🔴 | `persist`ed stores will hold stale server data across sessions with no invalidation path. Guest→user merge (`POST /cart/merge`) has no client counterpart. |

**Blockers:** persisted server-state in Zustand, no mutation/invalidation pattern, dual cache ownership.

---

## 7. API Usage Analysis (traced)

Data-source buckets: **(A)** static `src/lib/shop-data.ts`; **(B)** mock repo via `services/*`; **(C)** local Zustand. **Network calls to backend: 0.**

| Page / Component | Currently uses | Should call (backend) |
|---|---|---|
| `routes/index.tsx` + `components/site/*` (Hero, Featured, NewArrivals, Trending, ShopByCategory) | A (direct `shop-data`) | `/cms/home`, `/products`, `/collections`, `/categories` |
| `routes/products.$slug.tsx` | B + A via `useQuery` | `/products/{slug}`, reviews |
| `routes/collections.index.tsx` / `collections.$slug.tsx` | B | `/collections*`, `/products` |
| `routes/search.tsx` + `components/common/SearchOverlay.tsx` | B (`services.suggest`) | `/search`, `/search/autocomplete`, `/search/trending` |
| `routes/cart.tsx` + `components/site/CartDrawer.tsx` | C (`stores/cart`) | `/cart*`, `/coupons/validate` |
| `routes/checkout.tsx` | C + B (`stores/cart`, `useAddresses`, `services/orders`,`coupons`) | addresses, orders, payments, coupons |
| `routes/checkout.success.tsx` | local | `/orders/{id}/payment`, `/orders/{id}` |
| `routes/wishlist.tsx` + `components/site/ProductCard.tsx` | C (`stores/wishlist`) | `/me/wishlist*` |
| `routes/account.login.tsx` / `account.register.tsx` | C (`stores/auth`) | real auth + `/auth/verify-token` |
| `routes/account.index.tsx` | C (`stores/auth`,`orders`,`useAddresses`) | `/me`, `/orders`, `/me/addresses` |
| `routes/contact.tsx` | none (static form) | `/support/tickets` |
| `routes/about|faq|privacy|terms|shipping-returns.tsx` | static | `/cms/pages/{slug}` |
| `routes/store-locator.tsx` | static | *(no backend — out of scope)* |
| `routes/admin.products.tsx` | A | `/admin/products*`, media |
| `routes/admin.orders.tsx` | C (`stores/orders`) | `/admin/orders*` |
| `routes/admin.inventory.tsx` | C + A | `/admin/inventory*` |
| `routes/admin.coupons.tsx` | C (`stores/admin-coupons`) | `/admin/coupons*` |
| `routes/admin.reviews.tsx` | C (`stores/admin-reviews`) | `/reviews/admin/*` |
| `routes/admin.cms.tsx` | C (`stores/cms`) | `/cms/admin/*` |
| `routes/admin.customers.tsx` | C/local | `/admin/users*` |
| `routes/admin.index.tsx` / `admin.reports.tsx` | A | `/admin/dashboard`, `/analytics/admin/dashboard` |

---

## 8. Mock Data Analysis

| Mock artifact | File path | Backend replacement | Complexity |
|---|---|---|---|
| Static catalog/collections/reviews data | `src/lib/shop-data.ts` | `/products`, `/collections`, `/categories`, `/reviews/*` | 🟠 Significant (drives 20 importers) |
| Mock product repo | `src/repositories/mock/products.repository.ts` | API product repo → catalog endpoints | 🟠 |
| Mock collections repo | `src/repositories/mock/collections.repository.ts` | collections endpoints | 🟡 |
| Mock cart repo | `src/repositories/mock/cart.repository.ts` | `/cart*` (server totals, merge) | 🟠 (shape change) |
| Mock orders repo | `src/repositories/mock/orders.repository.ts` | `/orders*` | 🟠 (server-issued id/status) |
| Mock wishlist repo | `src/repositories/mock/wishlist.repository.ts` | `/me/wishlist*` | 🟡 (string[]→entities) |
| Mock reviews repo | `src/repositories/mock/reviews.repository.ts` | `/reviews/*` | 🟠 (interface must add write/vote) |
| Mock coupons repo | `src/repositories/mock/coupons.repository.ts` | `/coupons/validate`, admin coupons | 🟡 |
| Mock auth store | `src/stores/auth.ts` (`useAuth`, `MockUser`) | Supabase/`dev-login` + `/auth/verify-token` | 🔴 Critical |
| Mock addresses store | `src/stores/auth.ts` (`useAddresses`) | `/me/addresses*` | 🟡 |
| Admin local stores | `src/stores/{admin-coupons,admin-inventory,admin-reviews,cms,orders}.ts` | corresponding admin endpoints | 🟠 |
| Static mega-menu | `src/components/site/mega-menu-data.ts` | `/categories` | 🟡 |
| Stub Google sign-in | `src/stores/auth.ts#signInWithGoogle` | Supabase OAuth | 🟡 |
| Sample functions | `src/lib/api/example.functions.ts` | remove / replace with real client | 🟢 trivial |

---

## 9. Authentication Readiness

| Concern | Status | Evidence |
|---|---|---|
| Login architecture | 🔴 | `src/stores/auth.ts` fabricates a `MockUser` from the email string; no network call. |
| Logout | 🟡 | Local `set({user:null})` only; backend `/auth/logout` not called. |
| Protected routes | 🔴 | No router `beforeLoad` guards. `account.index.tsx` does an in-component `if (!isAuthenticated)` render-gate; **`admin.tsx` has no auth check at all** — admin UI is publicly reachable. |
| Role handling | 🔴 | `MockUser` has no `role`; backend enforces `customer/admin/super_admin`. |
| Token storage | 🔴 | No JWT captured/stored. `persist` stores only the mock user (`hadha-auth`). |
| Session persistence | 🟡 | Zustand `persist` keeps a fake session; not a real token session. |
| Refresh-token support | 🔴 | Unused Supabase client has it configured; app never invokes it. |

**Can it integrate easily?** No — auth is the **heaviest** lift. Requires: real identity provider call (Supabase OAuth/password or backend `dev/login`), JWT capture + storage, Bearer interceptor, `verify-token` boot check, router-level guards, and role gating. Note also the **anon Supabase key is committed in `.env`** (acceptable for the publishable anon key, but the file is checked in — confirm no service-role key follows).

---

## 10. Forms & Validation

| Concern | Status | Evidence |
|---|---|---|
| Form architecture | 🟡 | `react-hook-form`, `zod`, `@hookform/resolvers`, `components/ui/form.tsx` all available. |
| Validation | 🟠 | Sparse on real forms (login, register, checkout address, contact); mostly uncontrolled/ad-hoc. |
| Error handling | 🔴 | No path to display server (`422`/business-rule) errors; no mutation error surface. |
| API response handling | 🔴 | Forms write to Zustand or no-op (`contact.tsx` submits nowhere). |

**Missing:** zod schemas mirroring backend Pydantic constraints, mutation wiring, server-error → field-error mapping.

---

## 11. File Upload Readiness

| Capability | Status | Evidence |
|---|---|---|
| Multipart uploads | 🔴 | No multipart/FormData usage anywhere. |
| Image uploads | 🔴 | `PATCH /me/avatar` and `POST /admin/products/{id}/images` have no UI (`account.index.tsx`, `admin.products.tsx` lack file inputs). |
| Progress tracking | 🔴 | None (no `ui/progress` upload usage). |
| Download endpoints | 🔴 | Invoice (`/orders/{id}/invoice`) has no download control. |

**Verdict:** Upload/download is greenfield; requires client support for `multipart/form-data` + progress.

---

## 12. Error Handling

| Concern | Status | Evidence |
|---|---|---|
| Global API errors | 🔴 | No interceptor/normalizer. `lib/error-capture.ts`, `lib/lovable-error-reporting.ts` are render/runtime capture, not network. |
| Toast handling | ✅ | `sonner` installed and used for local actions — good substrate for mutation feedback. |
| Retry | 🟡 | TanStack default only. |
| Loading states | 🟠 | `ui/skeleton.tsx` exists but applied sparsely; mocks resolve instantly so loading is rarely exercised. |
| Empty states | ✅ | `components/site/EmptyState.tsx` reusable, used in cart/wishlist. |
| Validation errors | 🔴 | No server-validation rendering. |

**Can backend responses be handled consistently?** Not yet — there is no central place that understands the `{success,code,message,data}` envelope. One normalizer + a query/mutation error toast convention would make it consistent.

---

## 13. Type Compatibility

| Concern | Status | Evidence |
|---|---|---|
| Missing types | 🟠 | No DTO types for any backend module; no `ApiResponse<T>` envelope type. |
| Duplicate types | 🟡 | Domain types split between `src/types/shop.ts` and `src/stores/orders.ts`. |
| Contract mismatches | 🟠 | `CartLine={productId,qty}` (no server totals); `MockUser` lacks `role`; wishlist as `string[]`; IDs are mock strings (`usr_…`, `adr_…`) vs backend UUIDs; money is a plain `number` (`Money`) with no currency/precision contract. |
| Missing DTOs | 🔴 | None exist; backend Pydantic schemas unmirrored. |
| Mapping requirements | 🟠 | Every adapter needs DTO→model mapping + envelope unwrap; `Order` type must move out of the store and align with backend order schema. |
| Generated types | 🟡 | `src/integrations/supabase/types.ts` exists (Supabase DB types) but is unrelated to the FastAPI contract. |

---

## 14. Environment Configuration

| Concern | Status | Evidence |
|---|---|---|
| API Base URL | 🔴 | **Absent.** No `VITE_API_BASE_URL` in `.env` or `config/env.ts`. |
| Environment variables | 🟡 | `.env` defines only Supabase (`VITE_SUPABASE_URL/PUBLISHABLE_KEY/PROJECT_ID` + SSR duplicates). |
| Development config | 🟡 | `ENV.isDev/isProd` via Vite; no API env split. |
| Production config | 🔴 | No prod API URL, no per-env API switching. |
| Secrets hygiene | 🟡 | `.env` is committed with the Supabase **anon** key (publishable — acceptable) but confirm `.gitignore` policy and that no service-role key is added later. |

**Missing:** `VITE_API_BASE_URL` (+ per-env values) surfaced through `config/env.ts`.

---

## 15. Integration Blockers (ranked by severity)

| # | Blocker | Severity | File(s) |
|---|---|---|---|
| 1 | No HTTP/API client (no base URL join, headers, unwrap, errors) | 🔴 | *(missing)* `src/config/env.ts`, `.env` |
| 2 | Authentication fully mocked; no JWT, no token storage | 🔴 | `src/stores/auth.ts` |
| 3 | No route guards (admin publicly reachable) | 🔴 | `src/routes/admin.tsx`, `src/router.tsx` |
| 4 | No API repository implementations (mock-only factory) | 🔴 | `src/repositories/index.ts`, `src/repositories/api/*` (missing) |
| 5 | No response-envelope / DTO mapping layer | 🔴 | `src/services/*` |
| 6 | Server state persisted in Zustand (no invalidation) | 🟠 | `src/stores/{cart,orders,wishlist,cms,admin-*}.ts` |
| 7 | No `useMutation` / mutation+invalidation pattern | 🟠 | all write paths |
| 8 | No API error normalizer / interceptor | 🟠 | `src/lib/*` |
| 9 | Repository interfaces encode frontend shapes (need expansion: reviews write, wishlist entities, cart totals) | 🟠 | `src/repositories/types.ts` |
| 10 | Direct `lib/shop-data` imports bypass the service seam (20 files) | 🟠 | `src/lib/shop-data.ts` + importers |
| 11 | No DTO types / `ApiResponse<T>` | 🟠 | `src/types/*` |
| 12 | No upload/download support | 🟠 | `account.index.tsx`, `admin.products.tsx` |
| 13 | Validation infra present but unapplied; no server-error surfacing | 🟡 | forms across `src/routes/*` |
| 14 | `Order` type located in a store, imported by repo contract | 🟡 | `src/stores/orders.ts`, `src/repositories/types.ts` |
| 15 | No `VITE_API_BASE_URL` config | 🟡 | `.env`, `src/config/env.ts` |

---

## 16. Integration Readiness Scorecard

| Layer | Score | Class |
|---|---|---|
| API Layer | 15 | 🔴 |
| Repository Layer | 70 | 🟡 (excellent contract, mock-only impls) |
| Service Layer | 50 | 🟠 |
| Authentication | 10 | 🔴 |
| State Management | 55 | 🟠 |
| Routing | 45 | 🟠 (router solid; no guards) |
| React Query | 40 | 🟠 |
| Type Safety | 55 | 🟠 (strong internal types; no DTOs/mapping) |
| Error Handling | 35 | 🟠 |
| Environment Configuration | 25 | 🔴 |
| Backend Compatibility | 30 | 🟠 |
| **Weighted overall** | **~34** | 🟠 |

---

## 17. Integration Roadmap

### Phase 1 — Foundation (before any backend call) 🔴
- **Tasks:** Build typed HTTP client (base URL + Bearer injector + `{data}` unwrap + `ApiError` normalizer); add `VITE_API_BASE_URL` to `.env` and expose via `config/env.ts`; define `ApiResponse<T>` + DTO type conventions; add a `queryKeys` registry.
- **Dependencies:** none.
- **Effort:** Medium.
- **Outcome:** A single tested entry point for all backend calls; consistent error/response handling.

### Phase 2 — Core API Integration 🟠
- **Tasks:** Implement `src/repositories/api/{products,collections,reviews,cart,coupons}.repository.ts`; add DTO→model mappers in `services/*`; flip `repositories/index.ts` to select API impls (env-gated); expand `ReviewsRepository`/`CartRepository`/`WishlistRepository` interfaces to match backend; replace `lib/shop-data` importers with service calls; introduce `useQuery`/`useMutation` hooks + cache invalidation.
- **Dependencies:** Phase 1.
- **Effort:** Large.
- **Outcome:** Catalog, search, cart, coupons, reviews served by real APIs; the 3 existing `useQuery` sites light up first.

### Phase 3 — Authentication & User Features 🔴
- **Tasks:** Replace `stores/auth.ts` with real auth (Supabase/`dev-login`) → JWT capture/storage → wire interceptor; `verify-token` on boot; add TanStack Router `beforeLoad` guards for `/account/*` and `/admin/*` with role checks; profile/addresses/orders/wishlist endpoints; checkout orchestration (coupon→order→payment) in a service; logout via `/auth/logout`.
- **Dependencies:** Phases 1–2.
- **Effort:** Large.
- **Outcome:** Real sessions, protected routes, role gating, working checkout.

### Phase 4 — Admin Integration 🟠
- **Tasks:** Replace admin Zustand stores with admin endpoints (products+media upload, orders+refunds, inventory, coupons, reviews moderation, cms, customers, dashboard/analytics/audit); build missing admin screens; admin 2FA flow.
- **Dependencies:** Phases 1–3.
- **Effort:** Large.
- **Outcome:** Fully functional admin backed by APIs.

### Phase 5 — Optimization & Cleanup 🟡
- **Tasks:** Remove `lib/shop-data` and `repositories/mock/*`; consolidate domain types (move `Order` out of store; add DTOs); migrate persisted server-state out of Zustand to Query cache; apply zod validation + server-error surfacing; add upload progress, retry/backoff, loading/empty states; global mutation-error toasts; 401→re-auth redirect.
- **Dependencies:** Phases 1–4.
- **Effort:** Medium.
- **Outcome:** Single source of truth, no mock residue, production-grade UX.

---

## 18. Final Verdict

- **Is the frontend architecture ready for backend integration?** **Partially.** The *seam* (repository contract → services → components, with Query provisioned) is genuinely well-designed and ready to receive integration. The *connective tissue* (API client, auth, config, guards, mapping) is entirely absent. Net: a solid foundation but not yet integratable. **🟠**
- **Can mock repositories be swapped easily?** **At the wiring level, yes** — interfaces are clean, async, and centrally selected in `repositories/index.ts`. **At the data level, no** — each adapter needs DTO mapping and several interfaces (`reviews`, `cart`, `wishlist`) must expand to match backend capabilities. **🟠**
- **Is there clean UI/API separation?** **Largely yes**, via repositories + services — undermined in two ways: 20 files import `lib/shop-data` directly, and server state lives in persisted Zustand stores. **🟡**
- **Biggest architectural blockers:** (1) no API client/base URL, (2) mocked auth with no JWT or route guards, (3) no response-envelope/DTO mapping layer, (4) server state owned by persisted Zustand.
- **Complete before starting integration:** Phase 1 in full — HTTP client + API config + `ApiResponse`/DTO conventions + error normalizer — and decide cache ownership (Query for server state, Zustand for UI only). With that foundation, the existing seam makes the remaining phases predictable and low-risk.

---

*End of report. No source files were modified.*
