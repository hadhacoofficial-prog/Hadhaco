# E-Commerce User Experience & Functional Flow Audit

**Date:** 2026-07-23
**Codebase:** Hadha.co (FastAPI + React/TanStack Router + Zustand + Supabase Auth + Razorpay)
**Scope:** Complete customer journey audit derived entirely from source code.

---

## Table of Contents

1. [Complete User Journey](#1-complete-user-journey)
2. [Current Behaviour](#2-current-behaviour)
3. [UX Flow Diagrams](#3-ux-flow-diagrams)
4. [State Transition Tables](#4-state-transition-tables)
5. [Functional Gaps](#5-functional-gaps)
6. [Code References](#6-code-references)

---

## 1. Complete User Journey

### 1.1 Guest Browsing Journey

```
Landing Page → Browse categories/collections → View product → Add to cart →
Cart page (stock validation) → Checkout → Login/Register → Address → Payment → Success
```

Or:

```
Landing Page → "Buy It Now" on product → Checkout (auth required) →
Login/Register → Address → Payment → Success
```

### 1.2 Authenticated User Journey

```
Login → Browse → Add to cart → Cart → Checkout → Payment → Success →
Order confirmation → Account dashboard → View orders
```

### 1.3 Wishlist Journey

```
Browse → Toggle wishlist (localStorage) → /wishlist page →
"Move to Cart" → Cart → Checkout
```

### 1.4 Search Journey

```
Search overlay/page → Enter query → Results with filters →
Sort/filter → Product detail → Add to cart or Buy Now
```

### 1.5 Account Management Journey

```
Login → Account dashboard → Overview/Orders/Addresses/Wishlist/Profile/Security tabs →
Edit profile, manage addresses, change password
```

---

## 2. Current Behaviour

### 2.1 AUTHENTICATION

#### 2.1.1 Guest Browsing

**UI Actions:** User can browse all pages without authentication.

**Behaviour:**
- Guest users can view homepage, products, collections, search, cart, and static pages.
- Cart is stored in `localStorage` as `hadha-cart` (Zustand persist).
- Wishlist is stored in `localStorage` as `hadha-wishlist` (Zustand persist).
- Recently viewed products stored in `hadha-recent` (max 8 entries).
- Recent searches stored in `hadha-recent-search` (max 6 entries).

**Code:** `Frontend_whole/storefront/src/stores/cart.ts:75-94`, `Frontend_whole/storefront/src/stores/wishlist.ts:43-49`

#### 2.1.2 Registration

**UI Actions:** User navigates to `/account/register`, enters name/email/password, clicks "Create Account".

**Backend Flow:**
- Frontend calls `signUpWithPassword(name, email, password)` → Supabase `auth.signUp()`.
- Supabase creates the user record with `full_name` in `user_metadata`.
- No backend API call is made during registration (Supabase handles it).
- On success, user sees success toast and is redirected to `/account/login`.

**Edge Cases:**
- If email already exists, Supabase throws error → displayed as toast.
- Google OAuth button available on registration page → redirects to Google.
- No email verification flow is implemented (Supabase may send one by default, but the app doesn't check for it).

**Code:** `Frontend_whole/storefront/src/routes/account.register.tsx:55-67`, `Frontend_whole/packages/shared-api/src/lib/supabase/auth.ts:signUpWithPassword()`

#### 2.1.3 Login

**UI Actions:** User enters email/password on `/account/login`, clicks "Sign In".

**Backend Flow:**
- Frontend calls `signInWithPassword(email, password)` → Supabase `auth.signInWithPassword()`.
- On success, Supabase returns session (JWT + refresh token).
- `AuthProvider` receives the session, updates React state: `session`, `role` (from metadata), `status: "authenticated"`.
- `ProfileSyncer` in `__root.tsx` calls `GET /me` to fetch backend profile for role assignment.
- If `redirect` search param exists, user is redirected there; otherwise to `/account`.

**Failure Flow:**
- Invalid credentials → Supabase throws error → toast displayed.
- Rate limiting: backend has Redis-based rate limiting at middleware level.

**Remember Me:**
- Supabase session persistence is enabled (`persistSession: true`). The session persists in `localStorage` automatically. No explicit "Remember me" checkbox exists in the login form.

**Code:** `Frontend_whole/storefront/src/routes/account.login.tsx:65-72`, `Frontend_whole/packages/shared-api/src/providers/AuthProvider.tsx:75-85`

#### 2.1.4 Google Login

**UI Actions:** User clicks "Continue with Google" button on login or register page.

**Backend Flow:**
- Calls `signInWithGoogle(redirectTo?)` → Supabase `auth.signInWithOAuth({ provider: "google" })`.
- Browser redirects to Google OAuth consent screen.
- On callback, Supabase processes the OAuth tokens and creates/updates the user.
- `onAuthStateChange` fires in `AuthProvider`, updating session state.
- User lands on the redirect URL or `/account`.

**Code:** `Frontend_whole/storefront/src/components/common/GoogleAuthButton.tsx:22-30`, `Frontend_whole/packages/shared-api/src/lib/supabase/auth.ts:signInWithGoogle()`

#### 2.1.5 Logout

**UI Actions:** User clicks logout (trigger not visible in storefront routes — likely in account dropdown or header).

**Backend Flow:**
- Calls `signOut()` → Supabase `auth.signOut()`.
- `AuthProvider.logout()` sets session to null, role to null, status to "unauthenticated".
- `queryClient.clear()` clears all React Query cache.
- `sessionStorage.removeItem("hadha:2fa_verified")` clears 2FA flag.
- `BroadcastChannel.postMessage("logout")` notifies other tabs.
- `AuthCleanup` component in `__root.tsx` watches `!isAuthenticated` and clears all persisted stores: cart, checkout, buyNow, wishlist, recentlyViewed, recentSearches.

**Cross-Tab Sync:**
- BroadcastChannel `hadha:auth` receives "logout" message → clears session, role, status, query cache.

**Code:** `Frontend_whole/packages/shared-api/src/providers/AuthProvider.tsx:89-103`, `Frontend_whole/storefront/src/routes/__root.tsx:AuthCleanup`

#### 2.1.6 Session Persistence

- Supabase client config: `persistSession: true`, `autoRefreshToken: true`, `detectSessionInUrl: true`.
- On app boot, `AuthProvider` calls `getSession()` to restore session from localStorage.
- If session exists, status transitions to "authenticated"; otherwise "unauthenticated".
- `initialized` flag set to true after restore attempt → prevents premature redirects.

**Code:** `Frontend_whole/packages/shared-api/src/providers/AuthProvider.tsx:62-72`

#### 2.1.7 Token Refresh

- Supabase handles token refresh automatically via `autoRefreshToken: true`.
- The API client (`lib/api/client.ts`) reads a fresh JWT per request via `authHeader()`.
- On 401 response, the client attempts one silent refresh via Supabase, then retries the request.

**Code:** `Frontend_whole/packages/shared-api/src/lib/api/client.ts` (401 retry logic)

#### 2.1.8 Password Reset

**Forgot Password (`/account/forgot-password`):**
- User enters email → calls `resetPasswordForEmail(email)` → Supabase sends reset email with link to `/account/reset-password`.

**Reset Password (`/account/reset-password`):**
- User arrives via email link (Supabase handles token in URL).
- User enters new password + confirmation.
- Calls `updatePassword(password)` → Supabase `auth.updateUser({ password })`.
- Client-side validation: password and confirm must match.

**Code:** `Frontend_whole/storefront/src/routes/account.forgot-password.tsx`, `Frontend_whole/storefront/src/routes/account.reset-password.tsx`

#### 2.1.9 Email Verification

- No explicit email verification flow is implemented in the storefront.
- Supabase may send verification emails by default (depends on Supabase project settings), but the app code does not check for or handle email verification status.

#### 2.1.10 Protected Routes

**Mechanism:**
- Route-level: `beforeLoad` in checkout and account routes calls `supabase.auth.getSession()` → redirects to `/account/login` if no session.
- Component-level: `<ProtectedRoute>` wrapper watches auth state → redirects if session expires after mount.

**Routes with `beforeLoad` auth guard:**
- `/checkout` → redirects to `/account/login?redirect=...`
- `/account` (index) → redirects to `/account/login`
- `/account/login` → redirects to `/account` if already authenticated
- `/account/register` → redirects to `/account` if already authenticated

**Routes with `<ProtectedRoute>` wrapper:**
- Checkout page wraps its content in `<ProtectedRoute>`.

**Code:** `Frontend_whole/storefront/src/routes/checkout.tsx:43-51`, `Frontend_whole/storefront/src/components/common/ProtectedRoute.tsx`

---

### 2.2 HOME PAGE

#### 2.2.1 What Loads

The homepage is **CMS-driven**. All sections are fetched via `useHomepage()` hook which calls `GET /cms/homepage`.

**Sections rendered (in order):**
1. `AnnouncementBar` — scrolling marquee with CMS messages or fallback: "Certified 92.5 Sterling Silver", "Return eligibility depends on the individual product", "Handcrafted in Visakhapatnam"
2. `Header` — sticky header with logo, navigation (mega menu by gender), search, account, wishlist, cart icons
3. `Hero` — CMS carousel with slides (image/video, headline, subheading, CTA buttons). Fallback slide exists if no CMS data.
4. `ShopByGender` — (referenced in homepage component)
5. `FeaturedCollection` — (referenced in homepage component)
6. `FeaturedProducts` — fetches `GET /products?is_featured=true&page_size=8` with 5min staleTime
7. `CraftsmanshipVideo`
8. `NewArrivals` — fetches `GET /products?is_new_arrival=true&page_size=8` with 5min staleTime
9. `ShopByCategory` — fetches `GET /collections` with 10min staleTime
10. `PromoBanner`
11. `Trending` — fetches `GET /products?is_best_seller=true&page_size=4` with 5min staleTime
12. `WhyChooseUs`
13. `Reviews`
14. `InstagramSection`
15. `Newsletter`
16. `Footer`

#### 2.2.2 Loading State

- Each section independently handles loading via TanStack Query `isLoading`.
- `FeaturedProducts`: Shows `ProductCardSkeleton` grid (8 skeletons) while loading.
- `Hero`: Uses CMS data; no explicit loading skeleton.
- `ShopByCategory`: No loading state shown; section hidden when empty.
- `NewArrivals`: No loading skeleton; section hidden when empty.
- `Trending`: No loading skeleton; section hidden when empty.

#### 2.2.3 Empty State

- All product/collection sections return `null` when data is empty (section not rendered).

#### 2.2.4 Error State

- No explicit error states shown for homepage sections. If API fails, sections silently don't render.

#### 2.2.5 Caching

- `FeaturedProducts`: `staleTime: 5 * 60_000` (5 minutes)
- `NewArrivals`: `staleTime: 5 * 60_000` (5 minutes)
- `Trending`: `staleTime: 5 * 60_000` (5 minutes)
- `ShopByCategory` (collections): `staleTime: 10 * 60_000` (10 minutes)
- Homepage CMS: staleTime from `useHomepage()` hook
- Backend: SWR cache with TTL constants per endpoint, cache warming at startup for 9 endpoints
- Global QueryClient: `staleTime: 60_000`, `gcTime: 5 min`, `refetchOnWindowFocus: false`

#### 2.2.6 Search

- `SearchOverlay` component triggered by header search icon.
- Opens overlay (UI state in `useUi` store).
- Search page at `/search` with trending tags and recent searches.

**Code:** `Frontend_whole/storefront/src/routes/index.tsx`, `Frontend_whole/storefront/src/components/site/AnnouncementBar.tsx`, `Frontend_whole/storefront/src/components/site/FeaturedProducts.tsx`, `Frontend_whole/storefront/src/components/site/ShopByCategory.tsx`, `Frontend_whole/storefront/src/components/site/NewArrivals.tsx`, `Frontend_whole/storefront/src/components/site/Trending.tsx`

---

### 2.3 PRODUCT LISTING

#### 2.3.1 Category Page (`/products`)

**API Call:** `GET /products` with query params.

**Search Params (validated via Zod):**
- `gender` — filter by gender (women/men/unisex/kids)
- `category` — filter by category slug
- `deals` — boolean, filter deals
- `sort` — sort option
- `q` — search query
- `page` — pagination page number

**Backend Implementation:**
- Repository uses `COUNT(*) OVER()` window function for pagination in single query.
- GIN-indexed `search_vector` for full-text search.
- CTE-based image hydration (2 images per product).

**Pagination:** Server-side, 24 items per page (`page_size: 24`).

**Loading State:** `ProductGridSkeleton` shown while loading.

**Empty State:** `EmptyState` component when no results.

#### 2.3.2 Collection Page (`/collections/$slug`)

**API Calls:**
- `GET /collections/{slug}` — collection detail (banner, description)
- `GET /products?collection_slug={slug}` + filter params

**Filters (client-side state):**
- Gender
- In Stock only
- Is New
- Is Bestseller
- Max Price

**Sorting:** Featured, Newest, Price Low→High, Price High→Low

**Mobile:** Filter drawer (slide-out panel).

**Active filter chips** with clear functionality.

#### 2.3.3 Sorting

Available sort options via API params:
- `sort_by` + `sort_dir` for backend sorting
- Frontend exposes: featured, newest, price-asc, price-desc

#### 2.3.4 Price Filtering

- Collection page has `maxPrice` filter in `FilterState`.
- No min price filter exposed in frontend.
- Backend accepts price range params.

#### 2.3.5 Stock Indicators

- `InventoryBadge` component shows stock status on product cards.
- Displays: "In Stock", "Low Stock" (≤5), "Out of Stock" / "Sold Out".

**Code:** `Frontend_whole/storefront/src/routes/products.index.tsx`, `Frontend_whole/storefront/src/routes/collections.$slug.tsx`, `Frontend_whole/storefront/src/components/site/InventoryBadge.tsx`

---

### 2.4 PRODUCT DETAILS (`/products/$slug`)

#### 2.4.1 Image Gallery

**Behaviour:**
- Custom `ProductImageViewer` component (not a library).
- Desktop: cursor-follow zoom, wheel-scale.
- Mobile: pinch-zoom, double-tap zoom, pan with non-passive touch handlers.
- Gallery thumbnails with active index state.

#### 2.4.2 Variant Selection

- Variants displayed as selectable options (size, weight, etc.).
- Selecting a variant updates: price (with adjustment), stock display, SKU.
- `selectedVariant` state tracks the chosen variant.
- `variantError` state for validation.

#### 2.4.3 Price Display

- Shows current price from variant or base product.
- Original price with strikethrough if discounted.
- Discount percentage badge.

#### 2.4.4 Stock Display

- `InventoryBadge` component shows: In Stock, Low Stock (≤5), Sold Out.
- Per-variant stock indicators in variant selector.
- Out-of-stock state shows "Sold Out" badge and disables Add to Cart.

#### 2.4.5 Quantity Selector

- `QuantityStepper` component with +/- buttons.
- `computeQuantityBounds` enforces: min=1, max=min(stock, max_order_qty).
- Updates dynamically based on selected variant stock.

#### 2.4.6 Add to Cart

- Calls `useCart.add(productId, qty, snapshot, variantId)`.
- Cart store adds/updates line in localStorage.
- Cart drawer opens automatically (`isOpen: true`).
- Snapshot includes: name, image, slug, sku, price, variantName.

#### 2.4.7 Buy It Now

- Calls `useBuyNowStore.setItems([{ productId, qty, snapshot, variantId }])`.
- Navigates directly to `/checkout`.
- Completely independent from cart store.
- Sets `isActive: true` in buyNow store.

#### 2.4.8 Wishlist

- Toggle button calls `useWishlist.toggle(item)`.
- `has(id)` checks product-level (any variant wishlisted).
- Stored in localStorage only (no backend API).

#### 2.4.9 Related Products

- Fetches `GET /products?page_size=5&is_featured=true`.
- Displayed as `ProductGrid` below product detail.

#### 2.4.10 Reviews

- Fetches `GET /reviews/products/{id}?limit=50` for review list.
- Fetches `GET /reviews/products/{id}/summary` for aggregate rating.
- Fetches `GET /reviews/products/{id}/my-status` if authenticated (to check if user can review).
- Reviews show: rating, text, author, verified purchase badge, images, date.
- "Write Review" modal (`WriteReviewModal`) for eligible users.
- `?review=1` deep-link support opens Reviews tab from email links.

#### 2.4.11 Live Stock Polling

- Every 60 seconds, fetches `GET /products/{slug}` for current stock.
- Query key: `queryKeys.products.stock(slug)`.

#### 2.4.12 Breadcrumbs

- `Breadcrumbs` component: Home → Category → Product name.

#### 2.4.13 Loading State

- Full page skeleton while loading.

#### 2.4.14 Error State

- `OopsPage` component for not-found products.

#### 2.4.15 Back Button

- No explicit back button component. Browser back button works naturally.

#### 2.4.16 Reservation Status

- No reservation status shown on product page.
- Only visible during checkout via `ReservationCountdown` component.

**Code:** `Frontend_whole/storefront/src/routes/products.$slug.tsx`, `Frontend_whole/storefront/src/components/site/InventoryBadge.tsx`, `Frontend_whole/storefront/src/components/site/QuantityStepper.tsx`

---

### 2.5 CART

#### 2.5.1 Frontend State

**Store:** `useCart` (Zustand with localStorage persist, key: `hadha-cart`)

**State:**
```ts
lines: CartEntry[]  // { productId, variantId?, qty, snapshot? }
isOpen: boolean
```

**Unique Key:** `${productId}::${variantId ?? ""}` — same product, different variant = different line.

#### 2.5.2 Cart Operations

| Action | UI | Store Update |
|--------|-----|--------------|
| Add product | ProductCard/Detail "Add to Cart" | `add()` → upsert line, open drawer |
| Increase qty | QuantityStepper + | `setQty()` → update line qty |
| Decrease qty | QuantityStepper - | `setQty()` → if qty≤0, remove line |
| Remove item | Remove button | `remove()` → filter out line |
| Clear cart | Not exposed in UI | `clear()` → empty lines array |

#### 2.5.3 What Happens on Each Event

**Add Product:**
1. `add(productId, qty, snapshot, variantId)` called.
2. If line exists (same key): increment qty, update snapshot.
3. If new line: append to lines.
4. Cart drawer opens automatically.
5. Subtotal recalculated from snapshots.

**Increase/Decrease Quantity:**
- `setQty(productId, qty, variantId)` called.
- If qty ≤ 0, line is removed.
- No backend API call — purely localStorage.
- No stock validation at cart page level until checkout.

**Remove Item:**
- `remove(productId, variantId)` filters out matching line.
- No backend API call.

**Clear Cart:**
- `clear()` sets lines to `[]`.
- Called explicitly on: logout (via `AuthCleanup`), payment success (via `verifyPaymentMutation.onSuccess`).

**Refresh Page:**
- Cart persists via Zustand `persist` middleware → localStorage.
- Cart state survives page refresh.
- Stock not revalidated until cart page loads or checkout.

**Logout:**
- `AuthCleanup` watches `!isAuthenticated` → calls `useCart.getState().clear()`.
- All user stores cleared: cart, checkout, buyNow, wishlist, recentlyViewed, recentSearches.

**Login:**
- No cart merge from guest to server. Cart remains in localStorage.
- Backend has guest→user cart merge capability (`POST /cart/merge`) but it's not called from the frontend login flow.

**Stock Changes:**
- Not reflected in cart until cart page loads (per-line stock validation via `GET /products/{slug}` polling every 60s).
- No real-time stock updates in cart.

**Price Changes:**
- Cart uses snapshot prices, not live prices. If admin changes price, cart shows stale price until next add/update.

**Discount Changes:**
- Coupon is validated server-side at checkout, not in cart.

**Product Deleted:**
- Cart still contains the deleted product. No validation until checkout.

**Variant Unavailable:**
- No validation in cart. Stock issues caught at checkout.

**Reservation Expires:**
- No cart update. Reservation is a checkout concern only.

#### 2.5.4 Cart Page (`/cart`)

**API Calls:**
- Per-line stock validation: `GET /products/{slug}` for each cart line (polls every 60s).
- Coupon validation: `POST /coupons/validate`.

**Stock Validation:**
- Each line validates current stock.
- Detects: qty exceeds cap, sold-out items.
- Checkout button disabled when stock issues exist.

**Coupon:**
- Input field with apply/clear.
- Calls `POST /coupons/validate` with code, order amount, cart product IDs.
- Shows discount amount, removes coupon if invalid.

**Order Summary:**
- Subtotal (from snapshots).
- Shipping: Free for orders > ₹999 (standard), ₹99 (standard under ₹999), ₹199 (express).
- Coupon discount.
- Total.

**Code:** `Frontend_whole/storefront/src/stores/cart.ts`, `Frontend_whole/storefront/src/routes/cart.tsx`, `Frontend_whole/storefront/src/components/site/CartDrawer.tsx`

---

### 2.6 RESERVATION SYSTEM

#### 2.6.1 When Reservation Starts

**Trigger:** User clicks "Place Order" on checkout page.

**Backend Flow:**
1. Frontend calls `POST /orders/create-payment`.
2. Backend `orders/service.py` `create_payment_intent()`:
   a. Validates cart items exist and have stock.
   b. Creates `Order` with status `pending`.
   c. Creates `OrderItem` for each cart line.
   d. Calls `inventory/reservation_service.py` `reserve_stock()`:
      - Uses `SELECT ... FOR UPDATE` row-level locking on inventory.
      - Creates `InventoryReservation` record with 10-minute expiry.
      - Decrements `reserved_quantity` in inventory.
   e. Creates `Payment` record with Razorpay order ID.
   f. Returns `CreatePaymentIntentResponse` with Razorpay order details.

**Frontend Flow:**
1. `createPaymentMutation.mutate(intentBody)` called.
2. Before API call: `DELETE /cart` + `POST /cart/items` per line (syncs local cart to server).
3. On success: `setReservationStartedAt(Date.now())`, `setCheckoutState("payment_open")`.
4. `ReservationCountdown` component starts 10-minute timer.

#### 2.6.2 Reservation Timer

**Component:** `ReservationCountdown`

**Behaviour:**
- Calculates remaining time: `RESERVATION_TTL_MS - (now - startedAt)`.
- Updates every second via `setInterval`.
- Shows countdown in MM:SS format.
- When ≤ 0: calls `onExpired` callback.

**When Expired:**
- `handleReservationExpired()` sets `checkoutState: "reservation_expired"`.
- `ReservationExpiredModal` shown with message.
- On dismiss: clears buyNow or cart, resets checkout, navigates to cart or product page.

**Code:** `Frontend_whole/storefront/src/components/site/ReservationCountdown.tsx`

#### 2.6.3 Reservation Owner

- Reservation is tied to the authenticated user (JWT user ID).
- Created in `orders/service.py` with `user_id` from `require_customer` dependency.

#### 2.6.4 Multiple Users / Concurrent Users

**Stock Calculation:**
- `reserved_quantity` in inventory tracks total reserved stock across all users.
- `available_quantity = total_quantity - reserved_quantity - quantity` (quantity is confirmed orders).

**What Another Customer Sees:**
- Product page shows stock from `GET /products/{slug}` which includes `available_quantity`.
- If User A reserves 5 units of a product with 10 total, User B sees 5 available.
- `InventoryBadge` shows "Low Stock" when ≤5 remaining.

#### 2.6.5 Reservation Release

**Automatic Expiry (Background Worker):**
- `reservation_expiry.py` runs every 60 seconds.
- Finds `InventoryReservation` records where `expires_at <= NOW()`.
- For each expired reservation:
  1. Releases reserved stock (increments `reserved_quantity`).
  2. Transitions order to `payment_expired` status.
  3. Restores coupon usage if coupon was applied.
  4. Updates Redis cache (`bust_product_list_cache`).

**Payment Success:**
- `verify_payment()` in `orders/service.py`:
  1. Verifies Razorpay signature.
  2. Captures payment.
  3. Calls `inventory/reservation_service.py` `complete_reservation()`:
     - Decrements `quantity` (actual stock reduction).
     - Sets `reserved_quantity` back (clears reservation).
     - Sets `InventoryReservation.status = "completed"`.
  4. Updates order status to `confirmed`.

#### 2.6.6 Background Workers

| Worker | Interval | Purpose |
|--------|----------|---------|
| `reservation_expiry` | 60s | Expire stale reservations, release stock, restore coupons |
| `cms_publish` | 60s | Promote scheduled CMS sections |
| `media_generation` | 5s | Process pending image variants |
| `notification_retry` | 30s | Retry failed notifications |
| `partition_manager` | Monthly | Create Postgres partitions |
| `admin_session_cleanup` | Hourly | Delete expired admin sessions |

#### 2.6.7 Frontend Updates

**Polling:** Product page polls stock every 60s. No WebSocket or real-time updates.

**Cache Invalidation:**
- On reservation creation: `bust_product_list_cache` invalidates product list caches.
- On reservation expiry: `bust_product_list_cache` called.
- On payment success: `queryClient.invalidateQueries` for orders, cart, products, inventory, collections, CMS, search.

**Code:** `Backend/app/modules/inventory/reservation_service.py`, `Backend/app/workers/reservation_expiry.py`, `Backend/app/modules/orders/service.py`

---

### 2.7 CHECKOUT

#### 2.7.1 Auth Guard

- `beforeLoad` checks `supabase.auth.getSession()`.
- If no session: redirects to `/account/login?redirect=/checkout`.
- `<ProtectedRoute>` wrapper handles session expiry during checkout.

#### 2.7.2 Address Selection

**Saved Addresses:**
- Fetches `GET /me/addresses`.
- Auto-selects default address or first address.
- Radio button selection.

**New Address:**
- "Use a new address" option shows form.
- Fields: firstName, lastName, phone, alternate phone, address, apt, landmark, city, state, pincode, country (locked to India).
- Phone validation: 10-digit Indian mobile.
- On submit: `POST /me/addresses` creates address, uses returned ID.

#### 2.7.3 Delivery Method

- Standard Delivery: Free above ₹999, else ₹99.
- Express Delivery: ₹199 (metro cities only, note says).

#### 2.7.4 Coupon

- Input field with apply/clear.
- Calls `POST /coupons/validate` with context: subtotal, product IDs, shipping method, delivery state/city/pincode.
- Applied coupon shows green success bar with discount amount.
- Remove button clears coupon.
- On checkout mount: coupon revalidated once (if previously applied).

#### 2.7.5 Cart Sync to Server

**Before Payment:**
1. `DELETE /cart` — clears server-side cart.
2. `POST /cart/items` per line — syncs local cart items to server.
3. `POST /orders/create-payment` — creates order with reservation.

#### 2.7.6 Payment (Razorpay)

**Flow:**
1. `loadRazorpayScript()` — dynamically loads Razorpay SDK.
2. Opens Razorpay modal with: key, amount, currency, order ID, prefill (name, email).
3. User completes payment in Razorpay modal.

**Success:**
- Razorpay `handler` callback fires.
- `isVerifyingRef` prevents double verification.
- Calls `POST /orders/verify-payment` with: order_id, razorpay_payment_id, razorpay_order_id, razorpay_signature.
- Backend verifies signature, captures payment, fulfills order.

**On Verify Success:**
1. Clears buyNow or cart store.
2. Resets checkout store.
3. Invalidates query caches: orders, cart, products, inventory, collections, CMS homepage, search.
4. If gift flag enabled and total ≥ ₹2000: shows gift popup.
5. Navigates to `/checkout/success?order=...&orderId=...`.

**On Verify Failure:**
- Sets `checkoutState: "payment_failed"`.
- Shows error toast: "Payment verification failed".
- User can retry with same payment intent.

**On Razorpay Modal Dismiss:**
- Toast: "Payment cancelled — your items are still reserved. Complete payment before the timer expires."
- State returns to `payment_open`.

#### 2.7.7 Payment Retry

- `retryPayment()` reuses `currentIntentRef.current` (same Razorpay order).
- Reloads Razorpay script if needed.
- Opens modal with same intent.

#### 2.7.8 Failed Payment

- UI shows: "Payment failed — No money was deducted. Your items are still reserved — retry before the timer expires."
- "Retry Payment" button calls `retryPayment()`.

#### 2.7.9 Cancelled Payment

- Same as modal dismiss: reservation remains active, user can retry.

#### 2.7.10 Refresh During Payment

- `checkoutStep` and `reservationStartedAt` are **transient** (not persisted to localStorage).
- On page refresh during checkout: `checkoutStep` resets to "idle", `reservationStartedAt` resets to null.
- Server-side reservation still exists (10-minute window) but frontend loses track of timer.
- Cart/buyNow items persist in localStorage (can re-enter checkout).
- Address selection, shipping method, coupon persist in localStorage.

#### 2.7.11 Back Button

- No explicit handler. Browser back button works naturally.
- If user goes back during payment: Razorpay modal closes, reservation remains active.

#### 2.7.12 Browser Close

- Server-side reservation continues until 10-minute expiry.
- Background worker will expire it after 10 minutes.
- Frontend state is lost (transient fields).

#### 2.7.13 Duplicate Payment

- Backend `verify_payment()` is idempotent (checks payment status before processing).
- Razorpay order can only be captured once.

#### 2.7.14 Complimentary Gift

- If `complimentary_gift_enabled` flag is true and order total ≥ ₹2000:
  - Gift popup shown after payment success.
  - Options: "Traditional Sweet", "Traditional Hot Snack".
  - `POST /orders/{id}/complimentary-gift` saves selection.
  - Then navigates to success page.

**Code:** `Frontend_whole/storefront/src/routes/checkout.tsx`, `Backend/app/modules/orders/service.py`, `Backend/app/modules/inventory/reservation_service.py`

---

### 2.8 ORDER SUCCESS (`/checkout/success`)

#### 2.8.1 What Happens After Successful Purchase

**Backend (in `verify_payment()`):**
1. Razorpay signature verified.
2. Payment captured.
3. Inventory reservation completed (stock decremented).
4. Order status updated to `confirmed`.
5. Payment status updated to `captured`.

**Frontend (in `verifyPaymentMutation.onSuccess`):**
1. Clears buyNow or cart store.
2. Resets checkout store.
3. Invalidates query caches.

**Success Page (`checkout_.success.tsx`):**
- Fetches order by `orderId` (UUID) or falls back to matching by `order_number` from recent orders.
- Displays: order timeline (placed → processing → shipped → delivered), items list, totals, gift selection.
- On mount: invalidates orders and cart query caches.

#### 2.8.2 What Does NOT Happen

- **No reservation release confirmation** — reservation is marked "completed" server-side but no explicit frontend confirmation.
- **No product cache invalidation** — products cache is invalidated but no explicit stock badge update on other users' screens.
- **No other-user notification** — no WebSocket/polling to update other customers' stock views in real-time.
- **No analytics event** — no explicit analytics tracking on success page (may exist in backend but not visible in frontend).
- **No push notification** — no push notification sent to user.
- **No email confirmation visible** — backend may send order confirmation email via notification system, but not visible in frontend code.

**Code:** `Frontend_whole/storefront/src/routes/checkout_.success.tsx`, `Backend/app/modules/orders/service.py`

---

### 2.9 ORDERS

#### 2.9.1 Account Dashboard Orders Tab

**API Call:** `GET /orders?page=1&page_size=20`

**Display:**
- Expandable order cards with: order number, date, status badge, item count, total.
- Expanded view: full items list, totals breakdown, order timeline, tracking info.

#### 2.9.2 Order List

- Paginated server-side (page, page_size params).
- Overview tab shows last 3 orders.

#### 2.9.3 Order Details

- `GET /orders/{orderId}` for full detail.
- Shows: items, quantities, prices, subtotal, discount, tax, shipping, total.
- Order status timeline.
- Shipment tracking (if shipped).

#### 2.9.4 Cancellation

- Backend has order cancellation endpoint but frontend account page doesn't show a cancel button (not visible in code).

#### 2.9.5 Refund

- Backend has refund processing but no customer-facing refund request UI in account dashboard.

#### 2.9.6 Invoice

- Backend has invoice generation. Frontend may have download capability but not explicitly shown in account page.

#### 2.9.7 Retry Payment

- `checkout_.payment-failed.tsx` has "Try Again" button navigating to `/checkout`.
- No retry payment from order details.

#### 2.9.8 Reorder

- No reorder functionality visible in frontend code.

**Code:** `Frontend_whole/storefront/src/routes/account.index.tsx` (Orders tab), `Backend/app/modules/orders/router.py`, `Backend/app/modules/orders/service.py`

---

### 2.10 INVENTORY SYNCHRONIZATION

#### 2.10.1 How Inventory Updates Travel

```
Purchase:
  Frontend → POST /orders/create-payment → Backend
  → InventoryReservation (reserve_stock with FOR UPDATE lock)
  → On verify: complete_reservation (stock decremented)
  → Redis cache busted (bust_product_list_cache)
  → Background: reservation_expiry worker (every 60s)

Admin Stock Change:
  Admin → PATCH /admin/inventory/{id} → Backend
  → Inventory model updated
  → Redis cache busted
  → Background: cache_warmer re-warms affected endpoints
```

#### 2.10.2 Timing

- **Immediate for the purchaser:** Cache invalidated on verify, query caches refreshed.
- **For other customers:** Polling only (product page polls every 60s). No WebSocket.
- **Backend Redis:** Cache busted immediately on stock changes.
- **Frontend cache:** React Query `staleTime` determines when data refreshes (5-10 minutes for homepage sections, 60s global default).

#### 2.10.3 Stale Cache Scenarios

- Product list cache on homepage: up to 5 minutes stale.
- Product detail stock: polled every 60s, up to 60s stale.
- Collection cache: up to 10 minutes stale.
- Cart page stock validation: per-line polling every 60s.
- No real-time stock updates anywhere in the frontend.

**Code:** `Backend/app/core/cache.py` (bust functions), `Backend/app/core/redis.py`, `Backend/app/core/cache_warmer.py`

---

### 2.11 WISHLIST

#### 2.11.1 Add/Remove

- Toggle: `useWishlist.toggle(item)` — adds if not present, removes if present.
- Remove: `useWishlist.remove(id, variantId)`.
- All in localStorage (`hadha-wishlist`).

#### 2.11.2 Login/Guest

- Wishlist is purely client-side (localStorage).
- No backend API for wishlist.
- No sync between devices or after login.

#### 2.11.3 Guest→Login Sync

- **Not implemented.** Guest wishlist stays in localStorage after login.
- Backend has wishlist CRUD (`/me/wishlist`) but frontend doesn't use it.

#### 2.11.4 Refresh

- Persists via Zustand `persist` middleware → survives refresh.

#### 2.11.5 Move to Cart

- `/wishlist` page has "Move to Cart" button.
- Calls `useCart.add()` then `useWishlist.remove()`.

**Code:** `Frontend_whole/storefront/src/stores/wishlist.ts`, `Frontend_whole/storefront/src/routes/wishlist.tsx`

---

### 2.12 PROFILE

#### 2.12.1 Overview Tab

- Stats: member since, order count, wishlist count, address count.
- Latest order status preview.
- Recent orders (last 3).
- Default address.
- Wishlist preview.

#### 2.12.2 Orders Tab

- Paginated order list with expandable details.

#### 2.12.3 Addresses Tab

- CRUD for addresses.
- Max 10 addresses (enforced server-side).
- Default address selection.
- Form: full_name, phone, line1, line2, landmark, city, state, postal_code, country, is_default.

#### 2.12.4 Wishlist Tab

- Grid display of wishlisted items with remove button.

#### 2.12.5 Profile Edit

- Avatar upload (drag/click, 5MB limit, FormData).
- Name and phone editing.
- `PATCH /me` for profile update.
- `PATCH /me/avatar` for avatar upload.

#### 2.12.6 Password Change

- Security tab with current/new/confirm password fields.
- Calls `supabase.auth.updateUser({ password })`.
- Show/hide toggle for password fields.

#### 2.12.7 Logout

- Clears all stores via `AuthCleanup`.
- No explicit logout button visible in account page code (may be in header dropdown).

**Code:** `Frontend_whole/storefront/src/routes/account.index.tsx`

---

### 2.13 ADMIN IMPACT ON CUSTOMER EXPERIENCE

#### 2.13.1 Changes Stock

- Admin updates inventory via `PATCH /admin/inventory/{id}`.
- Backend updates `Inventory` model.
- Redis cache busted immediately.
- **Customer sees change:** After React Query staleTime expires (5-10 min for lists, 60s for detail polling). No real-time push.

#### 2.13.2 Changes Price

- Admin updates product price via product CRUD.
- Redis cache busted.
- **Customer sees change:** After cache invalidation + React Query staleTime.
- **Cart issue:** Cart uses snapshot prices, not live prices. Existing cart items show old price.

#### 2.13.3 Deletes Product

- Admin soft-deletes product (via `deleted_at` timestamp).
- Redis cache busted.
- **Customer sees change:** Product disappears from listings after cache refresh.
- **Cart issue:** Deleted product remains in cart. Stock validation at checkout will fail.

#### 2.13.4 Publishes CMS

- `cms_publish` worker runs every 60 seconds.
- Promotes `scheduled` sections to `published` when `scheduled_at <= NOW()`.
- Invalidates homepage Redis cache.
- **Customer sees change:** Within 60 seconds of scheduled time + cache TTL.

#### 2.13.5 Adds Variants

- Admin adds variants via product CRUD.
- Redis cache busted.
- **Customer sees change:** After cache refresh. New variants appear on product detail page.

#### 2.13.6 Uploads Images

- `media_generation` worker runs every 5 seconds.
- Processes pending image variants (crop → encode → R2 upload).
- **Customer sees change:** After variant generation completes + cache refresh. Could be 5-30 seconds.

#### 2.13.7 Changes Collection

- Admin updates collection via collection CRUD.
- Redis cache busted.
- **Customer sees change:** After cache refresh (10min staleTime for collection list).

---

### 2.14 BACKGROUND WORKERS

| Worker | File | Interval | Customer Impact |
|--------|------|----------|-----------------|
| `reservation_expiry` | `Backend/app/workers/reservation_expiry.py` | 60s | Releases expired reservations, restores stock, transitions orders to `payment_expired`, restores coupon usage |
| `cms_publish` | `Backend/app/workers/cms_publish.py` | 60s | Publishes scheduled CMS sections, invalidates homepage cache |
| `media_generation` | `Backend/app/workers/media_generation.py` | 5s | Processes image variants (crop, resize, upload to R2) |
| `notification_retry` | `Backend/app/workers/notification_retry.py` | 30s | Retries failed email/WhatsApp notifications at [1, 5, 15] min intervals |
| `partition_manager` | `Backend/app/workers/partition_manager.py` | Monthly | Creates Postgres partitions for analytics/audit tables (no direct customer impact) |
| `admin_session_cleanup` | `Backend/app/workers/admin_session_cleanup.py` | Hourly | Deletes expired admin 2FA sessions (no direct customer impact) |

---

### 2.15 API FLOW (Per User Action)

#### Add to Cart

```
Frontend: useCart.add(productId, qty, snapshot, variantId)
  ↓ (Zustand store update, localStorage persist)
  ↓ (No API call)
  ↓ Cart drawer opens
  ↓ Subtotal recalculated from snapshots
```

#### Place Order (Checkout)

```
Frontend: placeOrder()
  ↓ Validate address / create new address
  ↓ POST /me/addresses (if new)
  ↓ createPaymentMutation.mutate()
    ↓ DELETE /cart (clear server cart)
    ↓ POST /cart/items (per line, sync to server)
    ↓ POST /orders/create-payment
      ↓ Backend: validate stock
      ↓ Backend: create Order (status=pending)
      ↓ Backend: create OrderItems
      ↓ Backend: reserve_stock() (FOR UPDATE lock)
      ↓ Backend: create Payment (status=pending)
      ↓ Backend: bust_product_list_cache
      ↓ Return CreatePaymentIntentResponse
  ↓ Load Razorpay script
  ↓ Open Razorpay modal
  ↓ User completes payment
  ↓ Razorpay handler callback
    ↓ verifyPaymentMutation.mutate()
      ↓ POST /orders/verify-payment
        ↓ Backend: verify Razorpay signature
        ↓ Backend: capture payment
        ↓ Backend: complete_reservation() (stock decremented)
        ↓ Backend: update order status to confirmed
      ↓ Frontend: clear cart/buyNow store
      ↓ Frontend: reset checkout store
      ↓ Frontend: invalidate query caches
      ↓ Navigate to /checkout/success
```

#### Search Products

```
Frontend: SearchOverlay or /search page
  ↓ User types query
  ↓ GET /products?q={query}&page_size=24
    ↓ Backend: PostgreSQL tsvector FTS with ILIKE fallback
    ↓ Backend: SWR cached response
  ↓ Display ProductGrid with results
```

---

### 2.16 STATE MANAGEMENT

#### React State (Component-level)

- Gallery active index, quantity, tab selection, form inputs, error states, modals.

#### Zustand Stores (Persisted to localStorage)

| Store | Key | Persisted Fields | Transient Fields |
|-------|-----|------------------|------------------|
| `useCart` | `hadha-cart` | lines, isOpen | — |
| `useCheckoutStore` | `hadha-checkout` | shippingMethod, billingSame, selectedAddressId, couponCode, appliedCoupon | checkoutStep, reservationStartedAt, phone, altPhone |
| `useBuyNowStore` | `hadha-buy-now` | items, isActive | — |
| `useWishlist` | `hadha-wishlist` | items | — |
| `useRecentSearches` | `hadha-recent-search` | recent | — |
| `useRecentlyViewed` | `hadha-recent` | ids | — |
| `useUi` | (not persisted) | — | searchOpen |

#### TanStack Query Cache

- Centralized QueryClient with `staleTime: 60_000`, `gcTime: 5 min`.
- `refetchOnWindowFocus: false`.
- Retry logic based on `isApiError.isRetryable`.
- Hierarchical query keys for precise invalidation.

#### Cache Invalidation

- On payment success: invalidates orders, cart, products, inventory, collections, CMS, search.
- On profile update: no explicit invalidation (profile is refetched on next access).
- On address CRUD: no explicit invalidation (addresses refetch on mount).
- On wishlist toggle: no backend call (localStorage only).

#### Optimistic Updates

- None implemented. All mutations wait for server response.

#### Rollback

- None implemented. Failed mutations show error toasts.

---

### 2.17 CACHE BEHAVIOUR

#### Browser Cache

- Standard HTTP caching via `Cache-Control` headers.
- Backend sets: `must-revalidate` for originals, `immutable` for variants.
- SWR cache with request coalescing prevents stampede.

#### Redis Cache

- Circuit breaker: CLOSED → OPEN (30s) → HALF_OPEN → CLOSED.
- SWR: serves stale data while revalidating in background.
- Transparent zlib compression for values >2KB.
- Cache warming at startup for 9 endpoints.

#### Query Cache (React Query)

- `staleTime: 60_000` (global default).
- Product lists: 5 minutes.
- Collections: 10 minutes.
- `gcTime: 5 minutes`.
- `refetchOnWindowFocus: false`.

#### Invalidation Triggers

- Product CRUD → `bust_product_list_cache()`.
- Reservation created/expired → `bust_product_list_cache()`.
- CMS publish → homepage cache busted.
- Payment success → multiple query invalidations.

#### CDN Cache

- Cloudflare R2 for media assets with `immutable` Cache-Control for variants.
- No explicit CDN cache invalidation logic visible.

---

### 2.18 FAILURE SCENARIOS

#### API Fails

- TanStack Query retries based on `isApiError.isRetryable` (network/timeout/5xx/408/429).
- Toast error displayed to user.
- Sections that fail to load simply don't render (no error UI on homepage).

#### Redis Unavailable

- Circuit breaker opens → falls through to database queries.
- Cache-aside pattern: `cache_get_or_fetch` tries cache first, falls back to DB.
- No user-visible impact (slower responses).

#### Payment Timeout

- Reservation timer continues counting down.
- User sees "Payment failed" state with retry option.
- Reservation expires after 10 minutes.

#### Stock Changed During Checkout

- `createPaymentMutation.onError` checks for "available" in error message.
- If stock insufficient: redirects to `/checkout/stock-changed`.
- `StockChangedOopsPage` shown with "Continue Shopping" link.

#### Reservation Expired During Checkout

- `ReservationCountdown` detects expiry.
- `ReservationExpiredModal` shown.
- On dismiss: clears appropriate store, navigates to cart or product page.

#### Network Lost

- No explicit offline handling.
- API calls fail → error toasts.
- Cart/wishlist remain in localStorage.
- Checkout state lost (transient fields reset on reload).

#### Browser Refresh

- Cart, wishlist, buyNow, recently viewed, recent searches persist (localStorage).
- Checkout transient state lost (step, timer).
- Server-side reservation still active for 10 minutes.

#### Double Click

- `isVerifyingRef` prevents double payment verification.
- `checkoutState !== "idle"` guard prevents double order creation.
- Button disabled during submission states.

#### Multiple Tabs

- Cart/wishlist/buyNow in localStorage → shared across tabs (same origin).
- Checkout state in localStorage → shared across tabs.
- BroadcastChannel syncs logout across tabs.
- No conflict resolution for concurrent cart edits.

#### Concurrent Purchase

- `FOR UPDATE` row-level locking on inventory prevents overselling.
- Second user gets "stock changed" error if first user completes purchase.
- `available_quantity` calculation accounts for reservations.

---

## 3. UX Flow Diagrams

### 3.1 Authentication Flow

```
                    ┌─────────────────┐
                    │   App Boot      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ getSession()    │
                    │ (Supabase)      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │ Session Found              │ No Session
              ▼                            ▼
     ┌────────────────┐          ┌─────────────────┐
     │ status =       │          │ status =        │
     │ "authenticated"│          │ "unauthenticated"│
     └────────┬───────┘          └────────┬────────┘
              │                           │
     ┌────────▼───────┐          ┌────────▼────────┐
     │ ProfileSyncer  │          │ Guest Browsing   │
     │ GET /me        │          │ (localStorage)   │
     └────────┬───────┘          └────────┬────────┘
              │                           │
     ┌────────▼───────┐          ┌────────▼────────┐
     │ Authenticated  │          │ Login/Register   │
     │ Experience     │          │ /account/login   │
     └────────────────┘          └────────┬────────┘
                                          │
                                 ┌────────▼────────┐
                                 │ Supabase Auth    │
                                 │ signIn/signUp    │
                                 └────────┬────────┘
                                          │
                                 ┌────────▼────────┐
                                 │ onAuthStateChange│
                                 │ status =         │
                                 │ "authenticated"  │
                                 └────────┬────────┘
                                          │
                                 ┌────────▼────────┐
                                 │ ProfileSyncer    │
                                 │ GET /me          │
                                 └────────┬────────┘
                                          │
                                 ┌────────▼────────┐
                                 │ Redirect to      │
                                 │ intended page    │
                                 └─────────────────┘
```

### 3.2 Shopping Flow

```
     ┌──────────────┐
     │ Browse        │
     │ (Home/Search) │
     └──────┬───────┘
            │
     ┌──────▼───────┐
     │ Product List  │
     │ /products     │
     └──────┬───────┘
            │
     ┌──────▼───────┐
     │ Product      │
     │ Detail       │
     │ /products/:slug│
     └──────┬───────┘
            │
     ┌──────┼──────────────┐
     │ Add to Cart         │ Buy It Now
     ▼                     ▼
┌────────────┐     ┌────────────┐
│ Cart Store │     │ BuyNow Store│
│ (localStorage)│  │ (localStorage)│
└──────┬─────┘     └──────┬─────┘
       │                   │
       ▼                   ▼
┌────────────┐     ┌────────────┐
│ Cart Drawer │     │ /checkout  │
│ or /cart    │     │ (direct)   │
└──────┬─────┘     └──────┬─────┘
       │                   │
       └───────┬───────────┘
               ▼
        ┌────────────┐
        │ /checkout  │
        └────────────┘
```

### 3.3 Reservation Flow

```
     ┌──────────────────┐
     │ User clicks       │
     │ "Place Order"     │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ validate address  │
     │ create if needed  │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ DELETE /cart      │
     │ POST /cart/items  │
     │ (sync to server)  │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ POST /orders/     │
     │ create-payment    │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Backend:          │
     │ - Validate stock  │
     │ - Create Order    │
     │ - Reserve Stock   │
     │   (FOR UPDATE)    │
     │ - Create Payment  │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ ReservationCount- │
     │ down starts       │
     │ (10 min timer)    │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Load Razorpay SDK │
     │ Open modal        │
     └────────┬─────────┘
              │
     ┌────────┼──────────────┐
     │ Success              │ Failure/Dismiss
     ▼                      ▼
┌────────────┐        ┌────────────┐
│ Verify     │        │ Payment    │
│ Payment    │        │ Failed     │
│ POST /orders│       │ Retry or   │
│ /verify    │        │ Wait       │
└──────┬─────┘        └────────────┘
       │
┌──────▼─────┐
│ Backend:   │
│ - Verify   │
│   signature│
│ - Capture  │
│ - Complete │
│   reservation│
│ - Stock    │
│   decremented│
└──────┬─────┘
       │
┌──────▼─────┐
│ Frontend:  │
│ - Clear    │
│   cart/BN  │
│ - Invalidate│
│   caches   │
│ - Navigate │
│   to success│
└────────────┘
```

### 3.4 Checkout Flow

```
     ┌──────────────────┐
     │ /checkout         │
     │ (auth required)   │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Load addresses    │
     │ GET /me/addresses │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Select/Create     │
     │ Address           │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Select Delivery   │
     │ Method            │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Apply Coupon      │
     │ (optional)        │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Place Order       │
     │ (form submit)     │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Sync cart to      │
     │ server            │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Create payment    │
     │ intent            │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Razorpay modal    │
     └────────┬─────────┘
              │
     ┌────────┼──────────────┐
     │ Success              │ Failure
     ▼                      ▼
┌────────────┐        ┌────────────┐
│ Verify     │        │ Show error │
│ Payment    │        │ Retry same │
└──────┬─────┘        │ intent     │
       │              └────────────┘
┌──────▼─────┐
│ Clear stores│
│ Invalidate │
│ caches     │
│ Navigate to│
│ success    │
└────────────┘
```

### 3.5 Inventory Synchronization Flow

```
     ┌──────────────────┐
     │ Event: Stock      │
     │ Change            │
     └────────┬─────────┘
              │
     ┌────────┼──────────────┐
     │ Purchase            │ Admin Change
     ▼                     ▼
┌────────────┐        ┌────────────┐
│ Reserve    │        │ Update     │
│ Stock      │        │ Inventory  │
│ (FOR UPDATE)│       └──────┬─────┘
└──────┬─────┘              │
       │              ┌─────▼──────┐
┌──────▼─────┐        │ Bust Redis │
│ Complete   │        │ Cache      │
│ Reservation│        └─────┬──────┘
│ (stock -)  │              │
└──────┬─────┘        ┌─────▼──────┐
       │              │ Cache      │
┌──────▼─────┐        │ Warmer     │
│ Bust Redis │        │ re-warms   │
│ Cache      │        └─────┬──────┘
└──────┬─────┘              │
       │              ┌─────▼──────┐
┌──────▼─────┐        │ Customer   │
│ Invalidate │        │ sees after │
│ Query Cache│        │ staleTime  │
└──────┬─────┘        └────────────┘
       │
┌──────▼─────┐
│ Customer   │
│ sees after │
│ query      │
│ invalidation│
└────────────┘
```

### 3.6 Order Completion Flow

```
     ┌──────────────────┐
     │ Payment Verified  │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Backend:          │
     │ - Capture payment │
     │ - Complete        │
     │   reservation     │
     │ - Order confirmed │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Frontend:         │
     │ - Clear cart/BN   │
     │ - Reset checkout  │
     │ - Invalidate:     │
     │   orders, cart,   │
     │   products,       │
     │   inventory,      │
     │   collections,    │
     │   CMS, search     │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Gift popup?       │
     │ (if eligible)     │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Navigate to       │
     │ /checkout/success │
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ Fetch order detail│
     │ Display timeline  │
     │ Show items/totals │
     └──────────────────┘
```

---

## 4. State Transition Tables

### 4.1 Cart

| State | Trigger | Next State |
|-------|---------|------------|
| Empty | Add item | Has items |
| Has items | Add same item (different variant) | Has items (new line) |
| Has items | Add same item (same variant) | Has items (qty incremented) |
| Has items | Remove item | Has items or Empty |
| Has items | Set qty ≤ 0 | Has items or Empty |
| Has items | Clear | Empty |
| Has items | Logout | Empty |
| Any | Payment success | Empty |
| Any | Page refresh | Same (localStorage) |

### 4.2 Reservation

| State | Trigger | Next State |
|-------|---------|------------|
| None | Create payment intent | Active (10 min) |
| Active | Payment success | Completed |
| Active | Payment failed | Active (can retry) |
| Active | Razorpay dismissed | Active (can retry) |
| Active | 10 min expired | Expired |
| Active | Server: reservation_expiry worker | Expired |
| Expired | User dismisses modal | None |
| Completed | — | Terminal |

### 4.3 Inventory

| State | Trigger | Next State |
|-------|---------|------------|
| In Stock (qty > 5) | Reserve | In Stock (reserved qty ↑) |
| In Stock | Complete reservation | In Stock (qty ↓, reserved ↓) |
| In Stock | Admin stock change | Updated stock |
| Low Stock (qty ≤ 5) | Reserve | Low Stock (reserved qty ↑) |
| Low Stock | Complete reservation | Low Stock or Out of Stock |
| Out of Stock (qty = 0) | Reserve | Error (insufficient stock) |
| Reserved | Expiry worker | Stock restored (reserved ↓) |

### 4.4 Order

| State | Trigger | Next State |
|-------|---------|------------|
| — | Create payment intent | Pending |
| Pending | Payment captured | Confirmed |
| Pending | Reservation expired | Payment Expired |
| Pending | Cancel | Cancelled |
| Confirmed | Shipped | Shipped |
| Shipped | Delivered | Delivered |
| Delivered | Return requested | Return Pending |
| Any | — | Terminal states: Cancelled, Delivered |

### 4.5 Payment

| State | Trigger | Next State |
|-------|---------|------------|
| — | Create intent | Pending |
| Pending | Captured | Captured |
| Pending | Failed | Failed |
| Pending | Refunded | Refunded |
| Captured | Refund initiated | Refunding |
| Refunding | Refund completed | Refunded |
| Refunding | Refund failed | Captured (reverted) |

### 4.6 User Session

| State | Trigger | Next State |
|-------|---------|------------|
| — | App boot | Loading |
| Loading | getSession() success | Authenticated |
| Loading | getSession() failure | Unauthenticated |
| Unauthenticated | Login success | Authenticated |
| Authenticated | Logout | Unauthenticated |
| Authenticated | Token expired | Loading (refresh) |
| Authenticated | Session cleared | Unauthenticated |
| Any (multi-tab) | Logout in other tab | Unauthenticated |

---

## 5. Functional Gaps

### 5.1 Cart Not Synced to Server on Login

**Observation:** When a guest user logs in, their localStorage cart is NOT merged with any server-side cart. The backend has `POST /cart/merge` capability but the frontend never calls it.

**Impact:** If a user added items on one device as guest, then logs in on another device, the cart is empty.

**Code:** `Backend/app/modules/cart/router.py` (merge endpoint exists), `Frontend_whole/storefront/src/routes/account.login.tsx` (no merge call)

### 5.2 Wishlist Not Synced to Server

**Observation:** Wishlist is purely localStorage. Backend has `/me/wishlist` CRUD but frontend never uses it.

**Impact:** Wishlist lost on device change, different browsers, or incognito mode.

**Code:** `Frontend_whole/storefront/src/stores/wishlist.ts`, `Backend/app/modules/wishlist/router.py`

### 5.3 Cart Uses Snapshot Prices, Not Live Prices

**Observation:** Cart stores `snapshot.price` at time of add. If admin changes price later, cart shows stale price.

**Impact:** User sees incorrect total until they remove and re-add the item.

**Code:** `Frontend_whole/storefront/src/stores/cart.ts:15` (CartProductSnapshot.price)

### 5.4 Cart Does Not Validate Product Existence

**Observation:** If a product is deleted by admin, it remains in the cart. Stock validation at checkout will fail, but no graceful handling on cart page.

**Impact:** User sees "product not found" errors at checkout for deleted items.

**Code:** `Frontend_whole/storefront/src/routes/cart.tsx` (per-line stock validation only checks stock, not existence)

### 5.5 Checkout Transient State Lost on Refresh

**Observation:** `checkoutStep` and `reservationStartedAt` are not persisted to localStorage. On page refresh during checkout, the timer resets and step returns to "idle".

**Impact:** Server-side reservation is still active but frontend loses track. User must re-initiate checkout. Reservation timer display is incorrect.

**Code:** `Frontend_whole/storefront/src/stores/checkout.ts:73-80` (partialize excludes transient fields)

### 5.6 No Real-Time Stock Updates

**Observation:** Stock is polled every 60s on product detail page only. No WebSocket or Server-Sent Events. Other pages (cart, collection) don't poll stock.

**Impact:** User may add out-of-stock item to cart, discover issue only at checkout.

**Code:** `Frontend_whole/storefront/src/routes/products.$slug.tsx` (60s polling), `Frontend_whole/storefront/src/routes/cart.tsx` (per-line polling)

### 5.7 No Reservation Visibility on Product Pages

**Observation:** When User A has an item reserved, User B sees stock reduced (available_quantity accounts for reservations). But there's no UI indication that items are "temporarily held" by another customer.

**Impact:** User B sees "Low Stock" but doesn't know it's due to an active reservation that may expire.

**Code:** `Backend/app/modules/inventory/reservation_service.py` (stock calculation), no frontend reservation visibility component

### 5.8 Reservation Expiry Does Not Refresh Other Users' Caches

**Observation:** When a reservation expires and stock is restored, `bust_product_list_cache` is called for product lists. But the product detail page cache is NOT explicitly invalidated.

**Impact:** Other users' product pages may show stale "Low Stock" for up to 60s (polling interval) after reservation expires.

**Code:** `Backend/app/workers/reservation_expiry.py` (calls `bust_product_list_cache` but not product detail cache)

### 5.9 No Cart Merge on Checkout

**Observation:** Checkout syncs local cart to server (`DELETE /cart` + `POST /cart/items`) right before payment. But if the user has items in a server-side cart from a previous session, those are lost.

**Impact:** Server-side cart from other sessions is overwritten.

**Code:** `Frontend_whole/storefront/src/routes/checkout.tsx:createPaymentMutation` (DELETE + POST pattern)

### 5.10 No Duplicate Tab Cart Conflict Resolution

**Observation:** Multiple tabs share the same localStorage cart. Concurrent edits (add in tab A, remove in tab B) can lead to inconsistent state.

**Impact:** Last write wins. No conflict resolution or synchronization between tabs.

**Code:** `Frontend_whole/storefront/src/stores/cart.ts` (Zustand persist, no cross-tab sync)

### 5.11 No Email Verification Check

**Observation:** Supabase may send verification emails, but the app never checks `email_confirmed_at` or similar fields.

**Impact:** User can use the app with unverified email.

**Code:** `Frontend_whole/packages/shared-api/src/providers/AuthProvider.tsx` (no email verification check)

### 5.12 No "Remember Me" Checkbox

**Observation:** Session persistence is always on (`persistSession: true`). No option for session-only (browser close clears session).

**Impact:** User stays logged in indefinitely unless explicitly logging out.

**Code:** `Frontend_whole/packages/shared-api/src/integrations/supabase/client.ts` (persistSession: true)

### 5.13 No Guest Checkout

**Observation:** Checkout requires authentication (`beforeLoad` guard redirects to login). No guest checkout option.

**Impact:** Forced account creation before purchase.

**Code:** `Frontend_whole/storefront/src/routes/checkout.tsx:43-51` (auth guard)

### 5.14 No Order Cancellation from Customer

**Observation:** Backend has cancellation endpoints but no customer-facing cancel button in the account dashboard.

**Impact:** Customer must contact support to cancel an order.

**Code:** `Frontend_whole/storefront/src/routes/account.index.tsx` (no cancel button in Orders tab)

### 5.15 No Refund Request from Customer

**Observation:** Backend has refund processing but no customer-facing refund request UI.

**Impact:** Customer must contact support for refunds.

**Code:** `Frontend_whole/storefront/src/routes/account.index.tsx` (no refund request in Orders tab)

### 5.16 No Reorder Functionality

**Observation:** No "Reorder" button on past orders.

**Impact:** Customer must manually re-add items to cart.

**Code:** `Frontend_whole/storefront/src/routes/account.index.tsx` (no reorder button)

### 5.17 No Invoice Download from Customer

**Observation:** Backend has invoice generation (`/orders/{id}/invoice`) but no download button in account dashboard.

**Impact:** Customer cannot download invoices.

**Code:** `Frontend_whole/storefront/src/routes/account.index.tsx` (no invoice download in Orders tab)

### 5.18 Cart Drawer Opens on Every Add

**Observation:** `useCart.add()` always sets `isOpen: true`, opening the cart drawer even when user wants to continue browsing.

**Impact:** Disruptive UX when adding multiple items rapidly.

**Code:** `Frontend_whole/storefront/src/stores/cart.ts:35` (set({ lines, isOpen: true }))

### 5.19 No Stock Validation Before Add to Cart

**Observation:** `useCart.add()` doesn't check stock. Stock is only validated on cart page (per-line polling) and at checkout.

**Impact:** User can add out-of-stock items to cart, only to discover at checkout.

**Code:** `Frontend_whole/storefront/src/stores/cart.ts:33-38` (add action, no stock check)

### 5.20 No Price Recalculation in Cart

**Observation:** Cart subtotal is calculated from snapshot prices. If a coupon discount or price change occurs, the cart page re-fetches stock but uses stored prices.

**Impact:** Potential price discrepancy between cart and checkout.

**Code:** `Frontend_whole/storefront/src/stores/cart.ts:55-56` (subtotal from snapshots)

### 5.21 No Push Notifications

**Observation:** No push notification implementation visible in frontend. Backend has notification system (email, WhatsApp) but no web push.

**Impact:** User not notified of order status changes, delivery updates, etc. via browser.

**Code:** No push notification code found in frontend or backend.

### 5.22 No Analytics Events on Frontend

**Observation:** Backend has analytics module but no frontend event tracking code visible (no `track()`, `analytics.event()`, etc.).

**Impact:** No user behavior tracking for conversion optimization.

**Code:** `Backend/app/modules/analytics/` exists but no frontend integration visible.

### 5.23 Hero Carousel Fallback Always Shows

**Observation:** If CMS homepage data doesn't include hero slides, a hardcoded fallback slide is shown. No empty state.

**Impact:** Users see generic content instead of "No hero configured" message.

**Code:** `Frontend_whole/storefront/src/components/site/Hero.tsx:46-62` (FALLBACK_SLIDES)

---

## 6. Code References

### 6.1 Authentication

| Component | File | Lines |
|-----------|------|-------|
| Auth Provider | `Frontend_whole/packages/shared-api/src/providers/AuthProvider.tsx` | 1-176 |
| Auth Context | `Frontend_whole/packages/shared-api/src/providers/auth-context.ts` | — |
| Supabase Auth Helpers | `Frontend_whole/packages/shared-api/src/lib/supabase/auth.ts` | — |
| Supabase Client | `Frontend_whole/packages/shared-api/src/integrations/supabase/client.ts` | — |
| Session Helpers | `Frontend_whole/packages/shared-api/src/lib/supabase/session.ts` | — |
| Login Page | `Frontend_whole/storefront/src/routes/account.login.tsx` | 1-138 |
| Register Page | `Frontend_whole/storefront/src/routes/account.register.tsx` | 1-121 |
| Forgot Password | `Frontend_whole/storefront/src/routes/account.forgot-password.tsx` | — |
| Reset Password | `Frontend_whole/storefront/src/routes/account.reset-password.tsx` | — |
| Protected Route | `Frontend_whole/storefront/src/components/common/ProtectedRoute.tsx` | 1-48 |
| Google Auth Button | `Frontend_whole/storefront/src/components/common/GoogleAuthButton.tsx` | 1-61 |
| Root Layout (AuthCleanup) | `Frontend_whole/storefront/src/routes/__root.tsx` | 1-251 |
| Backend Auth Router | `Backend/app/modules/auth/router.py` | 1-645 |
| Backend Auth Service | `Backend/app/modules/auth/service.py` | 1-771 |
| Backend Dependencies (JWT) | `Backend/app/core/dependencies.py` | 1-323 |
| Backend Security (JWT verify) | `Backend/app/core/security.py` | — |

### 6.2 Home Page

| Component | File | Lines |
|-----------|------|-------|
| Homepage Route | `Frontend_whole/storefront/src/routes/index.tsx` | 1-119 |
| Announcement Bar | `Frontend_whole/storefront/src/components/site/AnnouncementBar.tsx` | 1-36 |
| Hero | `Frontend_whole/storefront/src/components/site/Hero.tsx` | 1-379 |
| Featured Products | `Frontend_whole/storefront/src/components/site/FeaturedProducts.tsx` | 1-112 |
| Shop By Category | `Frontend_whole/storefront/src/components/site/ShopByCategory.tsx` | 1-68 |
| New Arrivals | `Frontend_whole/storefront/src/components/site/NewArrivals.tsx` | 1-93 |
| Trending | `Frontend_whole/storefront/src/components/site/Trending.tsx` | 1-35 |
| Header | `Frontend_whole/storefront/src/components/site/Header.tsx` | 1-491 |
| Homepage Hook | `Frontend_whole/packages/shared-api/src/hooks/cms/useHomepage.ts` | — |
| CMS Router | `Backend/app/modules/cms/router.py` | — |
| CMS Service | `Backend/app/modules/cms/service.py` | — |
| CMS Repository | `Backend/app/modules/cms/repository.py` | 1-352 |

### 6.3 Product Listing

| Component | File | Lines |
|-----------|------|-------|
| Products Index | `Frontend_whole/storefront/src/routes/products.index.tsx` | 1-142 |
| Collection Detail | `Frontend_whole/storefront/src/routes/collections.$slug.tsx` | 1-226 |
| Collections Index | `Frontend_whole/storefront/src/routes/collections.index.tsx` | — |
| Product Grid | `Frontend_whole/storefront/src/components/site/ProductGrid.tsx` | 1-12 |
| Product Card | `Frontend_whole/storefront/src/components/site/ProductCard.tsx` | 1-199 |
| Filter Panel | `Frontend_whole/storefront/src/components/site/FilterPanel.tsx` | 1-145 |
| Inventory Badge | `Frontend_whole/storefront/src/components/site/InventoryBadge.tsx` | 1-89 |
| Catalog Router | `Backend/app/modules/catalog/router.py` | 1-515 |
| Catalog Service | `Backend/app/modules/catalog/service.py` | 1-391 |
| Catalog Repository | `Backend/app/modules/catalog/repository.py` | 1-433 |
| Collections Router | `Backend/app/modules/collections/router.py` | — |
| Search Router | `Backend/app/modules/search/router.py` | 1-172 |
| Search Service | `Backend/app/modules/search/service.py` | 1-188 |

### 6.4 Product Details

| Component | File | Lines |
|-----------|------|-------|
| Product Detail | `Frontend_whole/storefront/src/routes/products.$slug.tsx` | 1-1156 |
| Product Card | `Frontend_whole/storefront/src/components/site/ProductCard.tsx` | 1-199 |
| Inventory Badge | `Frontend_whole/storefront/src/components/site/InventoryBadge.tsx` | 1-89 |
| Quantity Stepper | `Frontend_whole/storefront/src/components/site/QuantityStepper.tsx` | — |
| Reviews | `Frontend_whole/storefront/src/components/site/Reviews.tsx` | — |
| Write Review Modal | `Frontend_whole/storefront/src/components/site/WriteReviewModal.tsx` | — |
| Catalog Router | `Backend/app/modules/catalog/router.py` | 1-515 |
| Reviews Router | `Backend/app/modules/reviews/router.py` | — |

### 6.5 Cart

| Component | File | Lines |
|-----------|------|-------|
| Cart Store | `Frontend_whole/storefront/src/stores/cart.ts` | 1-94 |
| Cart Page | `Frontend_whole/storefront/src/routes/cart.tsx` | — |
| Cart Drawer | `Frontend_whole/storefront/src/components/site/CartDrawer.tsx` | — |
| Cart Router (backend) | `Backend/app/modules/cart/router.py` | 1-111 |
| Cart Service (backend) | `Backend/app/modules/cart/service.py` | 1-378 |
| Cart Repository (backend) | `Backend/app/modules/cart/repository.py` | 1-190 |
| Cart Models (backend) | `Backend/app/modules/cart/models.py` | 1-97 |

### 6.6 Reservation System

| Component | File | Lines |
|-----------|------|-------|
| Reservation Countdown | `Frontend_whole/storefront/src/components/site/ReservationCountdown.tsx` | — |
| Reservation Service (backend) | `Backend/app/modules/inventory/reservation_service.py` | 1-1015 |
| Reservation Expiry Worker | `Backend/app/workers/reservation_expiry.py` | 1-39 |
| Inventory Router | `Backend/app/modules/inventory/router.py` | 1-159 |
| Inventory Service | `Backend/app/modules/inventory/service.py` | 1-184 |
| Inventory Models | `Backend/app/modules/inventory/models.py` | 1-200 |

### 6.7 Checkout & Payment

| Component | File | Lines |
|-----------|------|-------|
| Checkout Page | `Frontend_whole/storefront/src/routes/checkout.tsx` | 1-1016 |
| Checkout Store | `Frontend_whole/storefront/src/stores/checkout.ts` | 1-90 |
| Buy Now Store | `Frontend_whole/storefront/src/stores/buyNow.ts` | 1-46 |
| Success Page | `Frontend_whole/storefront/src/routes/checkout_.success.tsx` | — |
| Stock Changed Page | `Frontend_whole/storefront/src/routes/checkout_.stock-changed.tsx` | — |
| Reservation Expired Page | `Frontend_whole/storefront/src/routes/checkout_.reservation-expired.tsx` | — |
| Payment Failed Page | `Frontend_whole/storefront/src/routes/checkout_.payment-failed.tsx` | — |
| Oops Pages | `Frontend_whole/storefront/src/components/site/OopsPage.tsx` | — |
| Orders Router (backend) | `Backend/app/modules/orders/router.py` | 1-200 |
| Orders Service (backend) | `Backend/app/modules/orders/service.py` | 1-919 |
| Orders Models (backend) | `Backend/app/modules/orders/models.py` | 1-233 |
| Payments Router (backend) | `Backend/app/modules/payments/router.py` | 1-65 |
| Payments Service (backend) | `Backend/app/modules/payments/service.py` | 1-154 |
| Payments Models (backend) | `Backend/app/modules/payments/models.py` | 1-150 |

### 6.8 Orders

| Component | File | Lines |
|-----------|------|-------|
| Account Dashboard | `Frontend_whole/storefront/src/routes/account.index.tsx` | 1-1569 |
| Order Tracking Section | `Frontend_whole/storefront/src/components/customer/OrderTrackingSection.tsx` | — |
| Orders Router (backend) | `Backend/app/modules/orders/router.py` | 1-200 |
| Orders Repository (backend) | `Backend/app/modules/orders/repository.py` | 1-172 |

### 6.9 Inventory Synchronization

| Component | File | Lines |
|-----------|------|-------|
| Reservation Service | `Backend/app/modules/inventory/reservation_service.py` | 1-1015 |
| Inventory Repository | `Backend/app/modules/inventory/repository.py` | 1-148 |
| Redis Cache | `Backend/app/core/redis.py` | 1-308 |
| SWR Cache | `Backend/app/core/cache.py` | 1-551 |
| Cache Warmer | `Backend/app/core/cache_warmer.py` | 1-518 |

### 6.10 Wishlist

| Component | File | Lines |
|-----------|------|-------|
| Wishlist Store | `Frontend_whole/storefront/src/stores/wishlist.ts` | 1-49 |
| Wishlist Page | `Frontend_whole/storefront/src/routes/wishlist.tsx` | 1-102 |
| Wishlist Router (backend) | `Backend/app/modules/wishlist/router.py` | 1-72 |
| Wishlist Service (backend) | `Backend/app/modules/wishlist/service.py` | 1-61 |
| Wishlist Repository (backend) | `Backend/app/modules/wishlist/repository.py` | 1-91 |

### 6.11 Profile

| Component | File | Lines |
|-----------|------|-------|
| Account Dashboard | `Frontend_whole/storefront/src/routes/account.index.tsx` | 1-1569 |
| useProfile Hook | `Frontend_whole/storefront/src/hooks/auth/useProfile.ts` | — |
| Profiles Router (backend) | `Backend/app/modules/profiles/router.py` | 1-250 |
| Profiles Service (backend) | `Backend/app/modules/profiles/service.py` | 1-185 |

### 6.12 Background Workers

| Worker | File | Lines |
|--------|------|-------|
| Queue Setup | `Backend/app/workers/queue.py` | — |
| Base Worker | `Backend/app/workers/base.py` | — |
| Reservation Expiry | `Backend/app/workers/reservation_expiry.py` | 1-39 |
| CMS Publish | `Backend/app/workers/cms_publish.py` | — |
| Media Generation | `Backend/app/workers/media_generation.py` | — |
| Notification Retry | `Backend/app/workers/notification_retry.py` | — |
| Partition Manager | `Backend/app/workers/partition_manager.py` | — |
| Admin Session Cleanup | `Backend/app/workers/admin_session_cleanup.py` | — |

### 6.13 State Management

| Component | File | Lines |
|-----------|------|-------|
| Cart Store | `Frontend_whole/storefront/src/stores/cart.ts` | 1-94 |
| Checkout Store | `Frontend_whole/storefront/src/stores/checkout.ts` | 1-90 |
| Buy Now Store | `Frontend_whole/storefront/src/stores/buyNow.ts` | 1-46 |
| Wishlist Store | `Frontend_whole/storefront/src/stores/wishlist.ts` | 1-49 |
| Search Store | `Frontend_whole/storefront/src/stores/search.ts` | 1-24 |
| Recently Viewed Store | `Frontend_whole/storefront/src/stores/recentlyViewed.ts` | 1-19 |
| UI Store | `Frontend_whole/storefront/src/stores/ui.ts` | — |
| Router Config | `Frontend_whole/storefront/src/router.tsx` | — |
| Query Keys | `Frontend_whole/packages/shared-api/src/lib/api/queryKeys.ts` | 1-197 |

### 6.14 API Layer

| Component | File | Lines |
|-----------|------|-------|
| API Client | `Frontend_whole/packages/shared-api/src/lib/api/client.ts` | — |
| API Errors | `Frontend_whole/packages/shared-api/src/lib/api/errors.ts` | — |
| API Mappers | `Frontend_whole/packages/shared-api/src/lib/api/mappers.ts` | — |
| API Interceptors | `Frontend_whole/packages/shared-api/src/lib/api/interceptors.ts` | — |
| Storefront API Client | `Frontend_whole/storefront/src/lib/api/client.ts` | — |
| Storefront Query Keys | `Frontend_whole/storefront/src/lib/api/queryKeys.ts` | — |

### 6.15 Cache & Events

| Component | File | Lines |
|-----------|------|-------|
| Redis | `Backend/app/core/redis.py` | 1-308 |
| SWR Cache | `Backend/app/core/cache.py` | 1-551 |
| Cache Warmer | `Backend/app/core/cache_warmer.py` | 1-518 |
| Event Bus | `Backend/app/core/events.py` | 1-205 |
| Notification Dispatcher | `Backend/app/modules/notifications/dispatcher.py` | 1-59 |
| Notification Event Registry | `Backend/app/modules/notifications/event_registry.py` | 1-265 |

---

*End of Audit*
