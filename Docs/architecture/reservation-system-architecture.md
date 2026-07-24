# Hadha Reservation System — Production Architecture Blueprint

> **Status**: Design document. Not yet implemented.
> **Scope**: Complete redesign of the inventory reservation, checkout, order, payment,
> return, and refund lifecycle for a jewellery e-commerce platform on
> FastAPI + Postgres + Redis + Razorpay.
> **Goal**: Eliminate the four Critical bugs found in the v3 audit (reservation
> theft, refund/restock decoupling, returns not touching inventory, checkout
> hoarding) while preserving the existing proven concurrency layer.

---

## 1. Reservation Model

### Decision: Reservations belong to a Checkout Session, not an Order

**Current problem**: Reservations are keyed by `(user_id, product_id, variant_id)`
for reuse-matching but linked to Orders at creation time. This creates an
irreconcilable tension — the reservation doesn't know what quantity the customer
wants today (it only knows what they wanted when it was first created), and the
order doesn't know whether its backing reservation still exists (it can be silently
re-parented to a different order on retry).

**Proposed model**:

```
Cart (client-side localStorage or server-side)
  └── CheckoutSession (server-side, created when user clicks "Place Order")
        └── ReservationLine[] (one per product/variant in the cart)
              └── Links to inventory (FOR UPDATE, decrements reserved_quantity)
```

**Why Checkout Session, not Order:**

| Alternative | Why not |
|---|---|
| Reservation -> Cart | Cart is client-side localStorage today. Tying reservations to carts means either (a) server-side carts (adds complexity and latency to every add-to-cart) or (b) reservations that cannot be server-managed because the cart ID is not known until checkout. Neither is clean. |
| Reservation -> Cart Item | Same problem as Cart, plus now you need a server-side cart-item ID before checkout starts. |
| Reservation -> Order | **This is the current design and the source of the reservation-theft bug.** Orders are created *after* reservation succeeds. Linking them requires either creating the order first (wasting DB rows on failed checkouts) or linking after (the current re-parenting mess). |
| Reservation -> User | A user can have multiple active reservations for different products across different checkout attempts. User-scoping is correct for dedup, but not for lifecycle management. |
| Reservation -> Payment Intent | Razorpay payment intents are created *after* the reservation. You would need to create a payment intent before knowing if stock is available — wasteful and confusing for the customer. |
| **Reservation -> Checkout Session** | **A CheckoutSession is created server-side when the user initiates checkout. It owns the reservation lifetime. Orders are only created when payment succeeds. The session is the single source of truth for "what does this customer want right now."** |

**Key properties of the CheckoutSession approach:**

1. **Orders only exist after payment.** No more orphaned orders with zero reservations.
2. **Reservations reconcile against cart quantity on every checkout attempt**, not just the first.
3. **Multiple tabs/devices create separate CheckoutSessions**, each with its own reservation. The system deduplicates at the product level (only N total reservations allowed for a product) rather than at the user level.
4. **Session expiry is independent of reservation TTL.** The session can expire (user walks away) and the reservation can expire (TTL reached), but they are not conflated.

---

## 2. Reservation Lifecycle

### Complete State Machine

```
                        ┌──────────────┐
                        │     NONE     │  (item in cart, no reservation)
                        └──────┬───────┘
                               │
                    User clicks "Place Order"
                    create_checkout_session()
                               │
                               ▼
                    ┌──────────────────┐
                    │  SESSION_ACTIVE  │  (15-minute session TTL)
                    └──────┬──────────┘
                           │
              ┌────────────┼─────────────┐
              │            │             │
              ▼            ▼             ▼
    ┌─────────────┐ ┌──────────┐ ┌──────────────┐
    │  QUANTITY_  │ │ RELEASED │ │   EXPIRED    │
    │  CHANGED    │ │ (user    │ │ (TTL hit)    │
    │ (reconcile) │ │  cancelled)│              │
    └──────┬──────┘ └──────────┘ └──────────────┘
           │                         │
           │ click "Place Order"     │
           │ again                   │
           ▼                         ▼
    ┌──────────────┐          (inventory freed,
    │ RESERVATION_ │           session dead)
    │  ACTIVE      │
    │ (stock held) │
    └──────┬───────┘
           │
     ┌─────┼──────┬──────────────┐
     │     │      │              │
     ▼     ▼      ▼              ▼
  ┌──────┐ ┌────────┐ ┌──────────┐ ┌─────────┐
  │CHANGE│ │ PAYMENT│ │ EXPIRED  │ │RELEASED │
  │QTY   │ │ CAPTURED│ │ (TTL)   │ │(cancel) │
  └──┬───┘ └───┬────┘ └────┬─────┘ └─────────┘
     │         │            │
     ▼         ▼            ▼
  reconcile  ┌────────┐  (stock freed,
  existing   │COMPLETED│  session dead,
  reservation│         │  may be re-used
             └───┬────┘  by late payment)
                 │
           ┌─────┼─────────┐
           │     │         │
           ▼     ▼         ▼
        ┌──────┐ ┌────────┐ ┌──────────┐
        │RETURN│ │REFUND  │ │CANCELLED │
        │      │ │(partial│ │(restock) │
        │      │ │ or     │ │          │
        │      │ │ full)  │ │          │
        └──────┘ └────────┘ └──────────┘
```

### State Definitions

| State | Meaning | Duration | Exit Conditions |
|---|---|---|---|
| `NONE` | Item in cart, no server reservation | Indefinite | User clicks "Place Order" |
| `SESSION_ACTIVE` | Checkout session created, stock not yet reserved | <= 15 min | User proceeds to reserve / session expires |
| `RESERVATION_ACTIVE` | Stock physically held (reserved_quantity incremented) | <= 10 min from last activity (extendable up to 30 min cap) | Payment captured / TTL / user cancel |
| `PAYMENT_CAPTURED` | Razorpay confirmed payment | Terminal transition | Moves to COMPLETED |
| `COMPLETED` | Reserved -> Sold, order confirmed | Terminal (for reservation) | May be followed by RETURN / REFUND / CANCELLED |
| `RELEASED` | Stock freed (user cancelled or admin action) | Terminal | -- |
| `EXPIRED` | TTL reached without payment | Terminal (for this reservation) | Late payment may create new reservation |
| `RETURNED` | Customer returned item, stock restored | Terminal | -- |
| `REFUNDED` | Payment refunded, stock may or may not be restored | Terminal | -- |
| `CANCELLED` | Order cancelled, stock restored, refund issued | Terminal | -- |

### Key Transition Rules

1. **Quantity changes reconcile, not create.** When a user modifies their cart and re-initiates checkout, the system adjusts the existing reservation's quantity (up or down) rather than creating a new one. This is the core fix for the reservation-theft bug.

2. **Reservation belongs to the session, not the order.** The order is created after payment capture, when the reservation is already COMPLETED. There is never a window where an order exists but its reservation is unlinked.

3. **Late payments get a fresh reservation attempt.** If a payment arrives after reservation expiry, the system checks available stock and either completes the sale (if stock is available) or flags for manual reconciliation (if stock was resold). This replaces the current unconditional oversell path.

4. **Refund and restock are one atomic operation.** A refund on a confirmed order always triggers inventory restock. A cancellation of a paid order always triggers a refund. There is no path where one happens without the other.

---

## 3. Data Model

### Entity Relationship Diagram

```
┌─────────────┐     ┌─────────────────┐     ┌────────────────────┐
│   products   │────<│ product_variants │     │  checkout_sessions │
│              │     │                  │     │                    │
│ stock_qty    │     │ stock_qty        │     │ id (PK)            │
│ reserved_qty │     │ reserved_qty     │     │ user_id (FK)       │
│ sold_qty     │     │ sold_qty         │     │ status             │
│              │     │                  │     │ expires_at         │
└─────────────┘     └─────────────────┘     │ idempotency_key    │
       │                    │                └─────────┬──────────┘
       │                    │                          │
       │              ┌─────┴──────────────┐           │
       │              │ reservation_lines   │<──────────┘
       │              │                    │
       │              │ session_id (FK)    │
       │              │ product_id (FK)    │
       │              │ variant_id (FK)    │
       │              │ quantity           │
       │              │ status             │
       │              └─────────┬──────────┘
       │                        │
       │              ┌─────────┴──────────┐
       │              │ inventory_         │
       │              │ transactions       │
       │              │                    │
       │              │ reservation_line_id│
       │              │ order_id           │
       │              │ transaction_type   │
       │              └────────────────────┘
       │
┌──────┴──────┐     ┌────────────────┐     ┌──────────────┐
│   orders    │────<│  order_items   │     │   payments   │
│             │     │                │     │              │
│ status      │     │ order_id (FK)  │     │ order_id(FK) │
│ payment_    │     │ product_id     │     │ status       │
│  status     │     │ quantity       │     │ amount       │
│ session_id  │     │ unit_price     │     │ razorpay_*   │
└──────┬──────┘     └────────────────┘     └──────┬───────┘
       │                                   ┌──────┴───────┐
       │                                   │   refunds    │
       │                                   └──────────────┘
       │
┌──────┴──────┐     ┌────────────────┐
│   returns   │────<│ return_items   │
│             │     │                │
│ order_id    │     │ return_id(FK)  │
│ status      │     │ order_item_id  │
│ refund_id   │     │ quantity       │
└─────────────┘     │ received_qty   │
                    └────────────────┘
```

### Table: checkout_sessions

```sql
CREATE TABLE checkout_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_number  VARCHAR(30) NOT NULL UNIQUE,
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,
    status          VARCHAR(30) NOT NULL DEFAULT 'active',
    idempotency_key VARCHAR(64) UNIQUE,
    shipping_address_snapshot JSONB,
    billing_address_snapshot  JSONB,
    coupon_code      VARCHAR(50),
    coupon_id        UUID REFERENCES coupons(id),
    notes            TEXT,
    expires_at       TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Why this table exists**: Separates the "customer is deciding" phase from the "stock is held" phase. A session can exist without reservations (user opened checkout but hasn't confirmed). This avoids wasting reserved_quantity slots on abandoned checkout attempts that never reached the reservation step.

### Table: reservation_lines

```sql
CREATE TABLE reservation_lines (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    line_number       VARCHAR(30) NOT NULL UNIQUE,
    session_id        UUID NOT NULL REFERENCES checkout_sessions(id) ON DELETE CASCADE,
    order_id          UUID REFERENCES orders(id) ON DELETE SET NULL,
    user_id           UUID NOT NULL REFERENCES profiles(id),
    product_id        UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    variant_id        UUID REFERENCES product_variants(id) ON DELETE SET NULL,
    quantity          INTEGER NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    original_quantity INTEGER NOT NULL,
    extends_count     INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT rl_quantity_positive CHECK (quantity > 0),
    CONSTRAINT rl_original_quantity_positive CHECK (original_quantity > 0)
);

CREATE UNIQUE INDEX idx_rl_active_user_product
    ON reservation_lines(user_id, product_id, COALESCE(variant_id, '00000000-0000-0000-0000-000000000000'))
    WHERE status = 'ACTIVE';

CREATE UNIQUE INDEX idx_rl_active_order_product
    ON reservation_lines(order_id, product_id, COALESCE(variant_id, '00000000-0000-0000-0000-000000000000'))
    WHERE status = 'ACTIVE' AND order_id IS NOT NULL;
```

**Why `original_quantity`**: Enables the cumulative-hold-time cap. Even if `expires_at` is bumped on every retry, the system can enforce a maximum total hold time.

**Why `extends_count`**: Anomaly detection. A reservation with `extends_count > 10` is suspicious and should be surfaced to FraudService.

### Table: orders (modification)

```sql
ALTER TABLE orders ADD COLUMN session_id UUID REFERENCES checkout_sessions(id);
ALTER TABLE orders ADD COLUMN reservation_snapshot JSONB;
```

**Why `reservation_snapshot`**: When an order is created, snapshot the reservation quantities. This provides an immutable audit record.

---

## 4. Inventory Ledger

### The Six Dimensions

```
stock_quantity      = Physical items in the warehouse
reserved_quantity   = Items held for active checkout reservations (not yet paid)
sold_quantity       = Items confirmed sold (payment captured)
available_stock     = stock_quantity - reserved_quantity - sold_quantity
returned_stock      = Items returned by customers (tracked via return_items.received_qty)
damaged_stock       = Items damaged in warehouse (tracked via adjustments with damage reason)
```

### How Every Movement is Recorded

| Action | stock_qty | reserved_qty | sold_qty | Transaction Type |
|---|---|---|---|---|
| Admin receives new stock | +N | -- | -- | RESTOCK |
| Customer reserves (checkout) | -- | +N | -- | RESERVE |
| Reservation quantity increase | -- | +delta | -- | RESERVE (delta) |
| Reservation quantity decrease | -- | -delta | -- | RELEASE (delta) |
| Reservation expired | -- | -N | -- | RELEASE |
| Payment captured | -- | -N | +N | SALE |
| Customer cancels pre-payment | -- | -N | -- | RELEASE |
| Customer cancels post-payment (confirmed order) | -N | -- | -N | RETURN (cancel restock) |
| Customer returns item | -N | -- | -N | RETURN |
| Admin stock correction | +-/delta | -- | -- | ADJUSTMENT |
| Item damaged | -1 | -- | -- | DAMAGE |

### Returned Stock Tracking

When a return is marked as "received" in the warehouse:
1. For each ReturnItem with `received_qty > 0`, call `ReservationService.record_return()` to decrement `sold_quantity`.
2. Log an `InventoryTransaction` with type `RETURN`.

This is the fix for returns not touching inventory — the code already exists (`record_return`), it just needs to be called from the returns module.

---

## 5. Reservation Reconciliation

This section defines the **exact behaviour** for every scenario where a reservation
might need to change. There must never be ambiguity.

### 5.1 Cart Quantity Increases

**Trigger**: Customer has an active reservation for Product X, qty=2. They go back to the cart, increase qty to 4, and click "Place Order" again.

**Behaviour**:
1. System finds the existing ACTIVE reservation for this user + product.
2. System reads the current cart quantity: 4.
3. Delta = 4 - 2 = +2.
4. Inside the product row lock: check `available_stock >= delta`. If not, reject with "Only N more available."
5. Increment `reserved_quantity` by delta on the product row.
6. Update `reservation_lines.quantity` from 2 to 4.
7. Reset `expires_at` to `now + 10 minutes` (subject to 30-minute hard cap).
8. Increment `extends_count`.
9. Log an `InventoryTransaction` with `RESERVE` type and `quantity = delta`.

### 5.2 Cart Quantity Decreases

**Trigger**: Customer has active reservation for Product X, qty=4. They decrease to 2.

**Behaviour**:
1. System finds the existing ACTIVE reservation for this user + product.
2. System reads the current cart quantity: 2.
3. Delta = 4 - 2 = -2 (release 2 units).
4. Inside the product row lock: decrement `reserved_quantity` by 2.
5. Update `reservation_lines.quantity` from 4 to 2.
6. Reset `expires_at` to `now + 10 minutes` (subject to 30-minute hard cap).
7. Increment `extends_count`.
8. Log an `InventoryTransaction` with `RELEASE` type and `quantity = 2`.

### 5.3 Item Removed from Cart

**Trigger**: Customer has active reservation for Product X. They remove it from cart.

**Behaviour**:
1. System finds the existing ACTIVE reservation for this user + product.
2. Release the entire reservation: decrement `reserved_quantity` by the reservation quantity.
3. Set `reservation_lines.status = 'RELEASED'`.
4. Log an `InventoryTransaction` with `RELEASE` type.

### 5.4 Browser Refresh

**Trigger**: Customer is on checkout page, browser refreshes.

**Behaviour**:
- Server-side: Nothing changes. The CheckoutSession and its reservation lines are still active and counting down.
- Client-side: The checkout page re-mounts and calls `GET /checkout/{session_id}` to retrieve the current session state, including active reservation lines. The user sees exactly where they left off.
- No duplicate reservation: The session ID is stored in `sessionStorage` (not `localStorage`), so it persists across refreshes within the same tab but not across new tabs.

### 5.5 Retry Checkout (Same Tab)

**Trigger**: Customer clicks "Place Order", gets an error, tries again.

**Behaviour**:
1. If the existing CheckoutSession is still active (not expired), reuse it.
2. Reconcile reservation quantities against current cart.
3. If the existing session expired, create a new session.

**Idempotency**: The `idempotency_key` on `checkout_sessions` prevents duplicate session creation.

### 5.6 Multiple Tabs (Same User)

**Trigger**: Tab A and Tab B both click "Place Order" for the same product.

**Behaviour**:
1. Each tab creates its own CheckoutSession (different `session_id`).
2. Tab A's reservation succeeds.
3. Tab B's reservation attempts to reserve the same product. It hits the product row lock, waits for Tab A's transaction to commit, then reads the updated `reserved_quantity`.
4. If stock remains, Tab B gets its own reservation (separate session).
5. If stock is insufficient, Tab B gets a clean "insufficient stock" error.

**Same-user multi-tab**: The partial unique index means only one ACTIVE reservation line per `(user_id, product_id, variant_id)`. Tab B's attempt to create a second one hits the unique index; the system reconciles Tab B's quantity against Tab A's existing reservation. This is correct: the customer has one intent per product, regardless of how many tabs they use.

**Different-user multi-tab**: Each user gets their own reservation line. The product row lock serializes them.

### 5.7 Multiple Devices

Same as 5.6. The CheckoutSession is server-side and identified by `session_id`. Different devices get different sessions, but the same user is deduplicated by the partial unique index.

### 5.8 Payment Retry

**Trigger**: Customer's payment fails or times out. They try again.

**Behaviour**:
1. If the existing CheckoutSession is still active, reuse it. Reconcile quantities.
2. If the session expired (reservation released), create a new session and new reservation.
3. The old failed order remains in `payment_failed` status. A new order is created for the new session.

**Key rule**: Payment retries never modify an existing order's reservation. They create a fresh session and reservation. This eliminates the order-reparenting bug entirely.

### 5.9 Late Webhook (Payment After Reservation Expiry)

**Trigger**: Reservation expired, stock was released. Razorpay webhook arrives confirming payment.

**Behaviour**:
1. Find the order (created at payment-intent time, status = `payment_expired`).
2. Check if the order's items are still in the ledger with `sold_quantity` covering them. (They won't be — the reservation expired and stock was released.)
3. Attempt to re-reserve: Lock the product row, check `available_stock >= item.quantity`.
   - If available: Complete the sale (reserved -> sold). The customer gets their item.
   - If NOT available: Flag the order for **manual reconciliation**. Do NOT silently oversell.
4. Log the outcome. If manual reconciliation is needed, emit a `PaymentReconciliationRequired` event for the admin dashboard.

### 5.10 Admin Changes Stock

**Trigger**: Admin adjusts `stock_quantity` while reservations are active.

**Behaviour**:
1. Admin adjustment goes through `ReservationService.record_adjustment()` (locked, validated).
2. The adjustment validates: `new_stock >= reserved_quantity + sold_quantity`.
3. If the adjustment would make available stock negative, it is rejected with a clear error.
4. No reservation is affected — reservations hold their own `reserved_quantity` slots.

---

## 6. Checkout Session

### Should Checkout Create a Dedicated Session?

**Yes.** The CheckoutSession is the central coordination point for the entire checkout flow.

### Trade-offs: Sessions vs Orders vs Payment Intents

| Approach | Pros | Cons |
|---|---|---|
| Session -> Reservation -> Order -> Payment (proposed) | Clean separation of concerns. Session = customer intent. Reservation = stock hold. Order = financial commitment. Payment = gateway interaction. | One more table. Slightly more complex data model. |
| Reservation -> Order -> Payment (current) | Fewer tables. Simpler data model. | Orders exist before payment. Reservation ownership is ambiguous. |
| Cart -> Reservation -> Order -> Payment | Cart acts as the session. | Requires server-side carts. Adds latency to every add-to-cart. |

### Why Orders Only Exist After Payment

Creating orders only after payment capture means:
- No orphaned orders from abandoned checkouts.
- No "payment_expired" orders cluttering the order table.
- Order status is always meaningful (it represents a real commitment).
- Admin order list only shows real orders, not checkout attempts.

The trade-off is that you need a separate way to track abandoned sessions (the `checkout_sessions` table handles this). But this is strictly better than littering the orders table with phantom orders.

---

## 7. Idempotency Strategy

### Create Payment (POST /checkout/{session_id}/payment)

- **Key**: `idempotency_key` on `checkout_sessions`, generated client-side.
- **Behaviour**: If a session with this key already exists and is in `reserved` status, return the existing session's payment details instead of creating a new order.
- **Edge case**: If the session expired between the first and second call, create a new session with the same key (use a composite of key + attempt counter).

### Verify Payment (POST /checkout/{session_id}/verify)

- **Key**: `razorpay_payment_id` (unique index on `payments` table).
- **Behaviour**: If a payment row with this ID already exists, return the existing order confirmation. The `begin_nested()` + `IntegrityError` pattern already handles this correctly.

### Webhook (/webhooks/razorpay)

- **Key**: Razorpay's own event ID or `razorpay_payment_id`.
- **Behaviour**: The webhook handler already deduplicates via the payments table unique index. Add the same `begin_nested()` pattern for the refund webhook path.

### Reservation Creation (inside reserve)

- **Key**: Partial unique index on `(user_id, product_id, variant_id) WHERE status = 'ACTIVE'`.
- **Behaviour**: If an ACTIVE reservation already exists for this user+product, reconcile quantity instead of creating a duplicate. The DB index is the hard backstop.

### Reservation Extension (inside reserve, existing reservation found)

- **Key**: The existing reservation row itself (SELECT FOR UPDATE).
- **Behaviour**: Update `expires_at` and `quantity` on the existing row. Idempotent by construction.

### Refund (POST /admin/orders/{id}/refund)

- **Key**: `razorpay_refund_id` (unique index on `refunds` table).
- **Behaviour**: Already handled via `begin_nested()` + `IntegrityError` catch.

### Return (POST /admin/returns/{id}/receive)

- **Key**: Return + ReturnItem IDs (already created when the return was requested).
- **Behaviour**: When marking a return as received, check if `received_qty` has already been set. If so, skip the restock step. The `ReturnItem.received_qty` column serves as the idempotency marker.

### Shipment (POST /admin/orders/{id}/ship)

- **Key**: `order_id` + `fulfillment_status` transition guard.
- **Behaviour**: The validator checks current status before allowing transition. An already-shipped order cannot be shipped again.

---

## 8. Concurrency Model

### Database Locking Strategy

**Pessimistic locking (SELECT FOR UPDATE)** on all inventory mutations. This is the correct choice for a reservation system because:

1. The critical section is short (validate + update one row).
2. Contention is concentrated on hot SKUs during flash sales.
3. The cost of a failed optimistic lock (retry loop) is higher than waiting for a brief row lock.
4. Postgres READ COMMITTED re-reads committed values after acquiring the lock, so no stale reads.

### Lock Hierarchy

```
Level 1: product_variants (FOR UPDATE OF v)   — per-variant stock
Level 2: products (FOR UPDATE)                — per-product stock
Level 3: reservation_lines (FOR UPDATE)       — per-reservation state
Level 4: checkout_sessions (FOR UPDATE)       — per-session state
```

Lock ordering: Always acquire in Level 1 to Level 4 order. Within Level 2, sort by `(product_id, variant_id)` — the existing deadlock-safe ordering, preserved from the current implementation.

### Optimistic Locking for Admin Operations

Admin stock adjustments can use optimistic locking (version column) since contention is low and the retry cost is negligible.

```sql
UPDATE products
SET stock_quantity = :new_val, version = version + 1
WHERE id = :pid AND version = :expected_version;
-- If rowcount = 0, someone else modified it — re-read and retry
```

### Isolation Level

**READ COMMITTED** (Postgres default). This is correct because:
- `SELECT FOR UPDATE` serializes concurrent writes to the same row.
- We never need to see uncommitted reads from other transactions.
- Higher isolation levels add unnecessary overhead and deadlock risk for this workload.

### Deadlock Prevention

1. **Fixed lock acquisition order**: Products are always locked in `(product_id, variant_id)` sort order, regardless of cart iteration order.
2. **Lock timeout**: Set `lock_timeout = '3s'` at the session level. If a lock cannot be acquired in 3 seconds, fail fast with a retryable error.
3. **Retry strategy**: For transient deadlocks (Postgres error code 40P01), retry up to 3 times with exponential backoff (100ms, 200ms, 400ms).

### Row Lock Scope

**Critical fix**: Release the product row lock as soon as the reservation write is durable, before doing unrelated work (order creation, address handling, Razorpay API call).

```
Current (too broad):
  LOCK product -> reserve stock -> create order -> link reservations -> COMMIT

Proposed (tight):
  LOCK product -> reserve stock -> COMMIT (lock released)
  -> create order -> link reservation to order -> COMMIT
  -> call Razorpay API
```

This requires splitting the flow into two transactions:
1. **Transaction 1** (locked): Validate stock, adjust `reserved_quantity`, create reservation lines. Commit. Lock released.
2. **Transaction 2** (unlocked): Create CheckoutSession to Order, link reservation to order. Commit.
3. **Outside any transaction**: Call Razorpay API.

---

## 9. Reservation Expiry

### Extension Policy

- Each reservation starts with a 10-minute TTL from creation.
- On every cart reconciliation, `expires_at` is bumped forward by 10 minutes from now.
- **Hard cap**: `expires_at` can never exceed `created_at + 30 minutes`. After 30 minutes of total hold time, the reservation expires regardless of retry frequency.
- `extends_count` is incremented on each extension and logged.

### Maximum Lifetime

```
max_hold_duration = 30 minutes (configurable)
ttl_per_extension = 10 minutes (configurable)
max_extensions = floor(max_hold_duration / ttl_per_extension) = 3
```

A customer can retry up to 3 times (every 10 minutes) before the reservation permanently expires.

### Background Cleanup

The existing expiry worker pattern is correct and should be preserved:
1. Every 60 seconds, query `reservation_lines WHERE status = 'ACTIVE' AND expires_at < now()`.
2. For each candidate: `FOR UPDATE SKIP LOCKED`, release stock, set status = `EXPIRED`.
3. Commit the batch atomically.
4. Emit events after commit (commit-before-publish pattern).

### Heartbeat (Optional Future Enhancement)

For very long-lived sessions:
- The frontend sends a heartbeat `POST /checkout/{session_id}/heartbeat` every 60 seconds while the checkout page is open.
- The server bumps `expires_at` by the TTL on each heartbeat, subject to the 30-minute hard cap.
- This replaces the client-side countdown with a server-validated one.

### User Activity

- When the user navigates away from the checkout page, the frontend stops the heartbeat.
- The reservation continues to count down based on the last `expires_at`.
- When the user returns, the frontend re-fetches the session state and resumes.

### Checkout Activity

- If the session reaches `status = 'expired'`, the frontend shows a "Session expired" modal and offers to create a new session.
- The expired reservation lines are left in `EXPIRED` state for audit trail.

---

## 10. UI Behaviour

### Product Page

```
+---------------------------------------------+
|  Gold Necklace — INR 24,999                  |
|                                              |
|  Available: 3                                |
|  Reserved by you: 2 (08:41 left)             |
|                                              |
|  [Add to Cart]                               |
+---------------------------------------------+
```

- **Available**: `available_stock` (includes your own reservation as "not available").
- **Reserved by you**: Only shown if the user has an ACTIVE reservation for this product. Shows quantity and countdown.
- **Message**: "2 units reserved for you. Complete checkout within 08:41 to secure them."

### Collection / Search / Wishlist Pages

```
+------------------+
|  Gold Necklace   |
|  INR 24,999      |
|  3 available     |  <-- just the available count
|  [Add to Cart]   |
+------------------+
```

- Show `available_stock` only. No reservation details (too cluttered for list views).
- If `available_stock == 0` and user has an active reservation, show "Reserved by you" instead of "Out of stock".

### Cart Page

```
+-----------------------------------------------------+
|  Gold Necklace (Size: 18")                          |
|  INR 24,999 x 2 = INR 49,998                       |
|                                                     |
|  [-] 2 [+]          [Remove]                        |
|                                                     |
|  Stock: 3 available                                 |
|  Your reservation: 2 units (08:41 left)             |
|                                                     |
|  -------------------------------------------------  |
|                                                     |
|  Silver Bangle (Size: 6")                           |
|  INR 4,999 x 1 = INR 4,999                         |
|                                                     |
|  [-] 1 [+]          [Remove]                        |
|                                                     |
|  Stock: 12 available                                |
|  (Not reserved — will be reserved at checkout)      |
+-----------------------------------------------------+
```

- **Quantity stepper**: Always visible (replaces current bug where it is hidden when "Sold Out").
- **Stock badge**: Shows `available_stock` (excluding the user's own reservation).
- **Reservation banner**: Only shown for items with active reservations.
- **"Sold Out" flag**: Replaced with a more accurate message. If `available_stock == 0` but the user has an active reservation, show "Reserved for you — complete checkout to secure."

### Checkout Page

```
+-----------------------------------------------------+
|  Checkout                                           |
|                                                     |
|  +-----------------------------------------------+  |
|  |  Reservation active: 08:41 remaining          |  |
|  |  2x Gold Necklace reserved for you            |  |
|  |  1x Silver Bangle reserved for you            |  |
|  +-----------------------------------------------+  |
|                                                     |
|  Shipping Address: [dropdown]                       |
|  Billing Address:  [dropdown]                       |
|  Coupon: [input] [Apply]                            |
|  Notes: [textarea]                                  |
|                                                     |
|  Subtotal:     INR 54,997                           |
|  Shipping:     INR 0 (Free)                         |
|  Discount:     -INR 0                               |
|  Total:        INR 54,997                           |
|                                                     |
|  [Place Order & Pay]                                |
+-----------------------------------------------------+
```

- **Reservation banner**: Sticky at top, always visible, shows countdown.
- **"Place Order" button**: Disabled if reservation has expired. Shows "Reservation expired — click to retry" if expired.
- **On page load**: Frontend calls `GET /checkout/{session_id}` to reconcile reservation state. If the session expired, shows a modal.

### Order Details Page (Post-Payment)

```
+-----------------------------------------------------+
|  Order #HAD-000123                                  |
|  Status: Confirmed                                  |
|  Payment: Paid (INR 54,997)                         |
|                                                     |
|  Items:                                             |
|  - 2x Gold Necklace — INR 24,999 each              |
|  - 1x Silver Bangle — INR 4,999 each               |
|                                                     |
|  [Cancel Order]  [Track Shipment]                   |
+-----------------------------------------------------+
```

- No reservation countdown (reservation is completed).
- "Cancel Order" available only while order is in cancellable status.

### Admin Dashboard

```
+-----------------------------------------------------+
|  Product: Gold Necklace                             |
|                                                     |
|  Physical stock:    10                              |
|  Reserved:           3 (2 active reservations)      |
|  Sold:               4                              |
|  Available:          3                              |
|                                                     |
|  [Adjust Stock]  [View Reservations]  [History]     |
|                                                     |
|  Recent Transactions:                               |
|  - 14:32  RESERVE   +2  (Session CS-XXX, User A)   |
|  - 14:28  SALE      -1  (Order #HAD-000123)        |
|  - 14:15  RESTOCK   +5  (Admin: restock supplier)   |
+-----------------------------------------------------+
```

- **All six inventory dimensions visible**: Physical, Reserved, Sold, Available, Returned, Damaged.
- **Active reservation count**: Shows how many users have active holds.
- **Real-time updates**: SSE or polling. Admin sees stock changes within seconds.
- **Transaction history**: Full audit trail, filterable.

---

## 11. Event Architecture

### Events

| Event | Trigger | Payload | Listeners |
|---|---|---|---|
| CheckoutSessionCreated | Session created | session_id, user_id | -- |
| CheckoutSessionReserved | Reservation lines created | session_id, reservation_line_ids | InventoryChanged |
| CheckoutSessionExpired | Session TTL reached | session_id, user_id | Release reservation lines |
| ReservationLineCreated | New reservation line | line_id, user_id, product_id, quantity | InventoryChanged |
| ReservationLineUpdated | Quantity reconciled | line_id, old_qty, new_qty, delta | InventoryChanged |
| ReservationLineReleased | Released (cancel/expiry) | line_id, product_id, quantity | InventoryChanged |
| ReservationLineCompleted | Payment captured | line_id, order_id | InventoryChanged |
| InventoryChanged | Any stock movement | product_ids[] | Cache invalidation, SSE broadcast |
| OrderCreated | Order confirmed (post-payment) | order_id, user_id, total | Notifications, analytics |
| PaymentCaptured | Razorpay confirms payment | order_id, payment_id, amount | Notifications, analytics |
| PaymentFailed | Payment failed | order_id, reason | Notifications, restore coupon |
| RefundInitiated | Refund created | order_id, refund_id, amount | Notifications, inventory restock |
| RefundCompleted | Refund processed | order_id, refund_id | Notifications |
| ReturnReceived | Warehouse confirms return | return_id, order_id, items[] | Inventory restock |
| ShipmentCreated | Shipment dispatched | order_id, tracking_number | Notifications |
| PaymentReconciliationRequired | Late payment cannot be fulfilled | order_id, reason | Admin alert |
| ReservationAnomalyDetected | Suspicious reservation pattern | user_id, anomaly_type | Fraud alert |

### Event Flow: Complete Checkout

```
User clicks "Place Order"
  -> CheckoutSessionCreated

User confirms, clicks "Reserve & Pay"
  -> CheckoutSessionReserved
    -> InventoryChanged (cache bust + SSE)
  -> ReservationLineCreated (for each item)

Razorpay payment confirmed (webhook or verify)
  -> ReservationLineCompleted
    -> InventoryChanged (cache bust + SSE)
  -> OrderCreated
    -> NotificationEmail
    -> AnalyticsEvent
  -> PaymentCaptured
    -> NotificationEmail
    -> AnalyticsEvent
```

### Event Flow: Reservation Expiry

```
Background worker finds expired reservation
  -> ReservationLineReleased
    -> InventoryChanged (cache bust + SSE)
  -> CheckoutSessionExpired

Late webhook arrives
  -> PaymentReconciliationRequired (if stock no longer available)
    -> AdminDashboardAlert
```

### Event Flow: Return

```
Customer requests return
  -> ReturnCreated (status: requested)

Admin approves return
  -> ReturnApproved

Warehouse receives item
  -> ReturnReceived
    -> ReservationService.record_return() (decrements sold_quantity)
    -> InventoryChanged (cache bust + SSE)
    -> RefundInitiated (if refund not yet issued)

Refund processed
  -> RefundCompleted
    -> NotificationEmail
```

---

## 12. API Design

### Checkout Endpoints

```
POST   /checkout/sessions
  Creates a new checkout session from the user's current cart.
  Input:  { idempotency_key, shipping_address_id, billing_address_id?,
            coupon_code?, notes? }
  Output: { session_id, session_number, expires_at, items[] }
  Idempotency: idempotency_key (returns existing session if found)
  Transaction: Creates session record. No stock changes yet.
  Failure: 400 if cart empty, 409 if idempotency_key conflict.

GET    /checkout/{session_id}
  Returns current session state including reservation lines.
  Output: { session_id, status, reservation_lines[], expires_at, total }
  Transaction: Read-only.

POST   /checkout/{session_id}/reserve
  Locks stock and creates/updates reservation lines.
  Input:  { items: [{ product_id, variant_id, quantity }] }
  Output: { reservation_lines[], expires_at }
  Idempotency: Session status check (already reserved -> reconcile)
  Transaction: Stock lock + reservation write. Commit before returning.
  Failure: 409 if insufficient stock. 410 if session expired.
  Retry: Safe to retry — reconciles existing reservation.

POST   /checkout/{session_id}/payment
  Creates Razorpay order and links to a new Order record.
  Input:  { }
  Output: { razorpay_order_id, amount, currency, key }
  Idempotency: Session status check (already payment_pending -> return existing)
  Transaction: Order creation. Commit before Razorpay API call.
  Failure: 502 if Razorpay unreachable. Releases reservation on failure.

POST   /checkout/{session_id}/verify
  Verifies Razorpay payment and fulfills order.
  Input:  { razorpay_order_id, razorpay_payment_id, razorpay_signature }
  Output: { order_id, order_number, success }
  Idempotency: Payment razorpay_payment_id unique index.
  Transaction: Reservation completion + order confirmation + payment record.
  Failure: 400 if signature invalid. 409 if already verified.
```

### Order Endpoints (mostly unchanged)

```
GET    /orders                          List user's orders
GET    /orders/{id}                     Get order details
POST   /orders/{id}/cancel              Cancel order (pre-shipment)
GET    /orders/active-reservations      Get user's active reservations
```

### Admin Endpoints

```
POST   /admin/products/{id}/stock/adjust
  Input:  { delta: int, reason: string }
  Output: { stock_quantity, reserved_quantity, sold_quantity, available_stock }
  Transaction: FOR UPDATE + validated adjustment + commit.
  Failure: 409 if adjustment would make available negative.

DELETE /admin/checkout-sessions/{id}
  Input:  { reason: string }
  Output: { session_id, status: 'released' }
  Transaction: Release reservations + commit.

POST   /admin/returns/{id}/receive
  Input:  { items: [{ return_item_id, received_qty }] }
  Output: { return_id, status: 'received', restocked_items[] }
  Transaction: For each item with received_qty > 0:
    ReservationService.record_return() + commit atomically.
  Idempotency: received_qty already set -> skip restock.
```

### Webhook Endpoints (unchanged)

```
POST   /webhooks/razorpay
```

### Inventory Query Endpoints

```
GET    /inventory/{product_id}/status
  Output: { stock_quantity, reserved_quantity, sold_quantity, available_stock,
            active_reservations: [{ user_id, quantity, expires_at }] }

GET    /inventory/{product_id}/transactions
  Output: { transactions[], total }
```

### Rate Limiting

```
POST   /checkout/sessions              5 per user per minute, 10 per IP per minute
POST   /checkout/{id}/reserve          10 per user per minute, 20 per IP per minute
POST   /checkout/{id}/payment          5 per user per minute, 10 per IP per minute
POST   /checkout/{id}/verify           10 per user per minute
```

---

## 13. Failure Recovery

### Server Restart

- **No data loss**: All reservation state is in Postgres. Sessions and reservation lines survive restarts.
- **In-flight transactions**: Any uncommitted transaction is rolled back by Postgres. The next API call creates a new transaction.
- **Background worker**: APScheduler restarts the expiry worker. The first tick picks up any reservations that expired during downtime.

### Redis Restart

- **No reservation impact**: Reservations are Postgres-only.
- **Cache impact**: All Redis cache keys are lost. The next product page load repopulates from Postgres. SSE subscriptions reconnect within ~5 seconds.
- **Rate limit impact**: Rate limit counters reset. Acceptable — temporary degradation, not a correctness issue.

### Worker Restart

- **Expiry worker**: APScheduler restarts it. The first tick processes all overdue reservations (the query finds `expires_at < now()`, which is always true for anything that expired during downtime).
- **No duplicate processing**: `FOR UPDATE SKIP LOCKED` ensures each reservation is processed by exactly one worker instance.

### Payment Timeout (Customer Browser Times Out)

- Frontend has a 20s client timeout on the payment-intent call and a 30s UI safety-timeout on the verify-payment call.
- If the customer's browser times out but Razorpay actually captured the money:
  - The new reconciliation job (§7.4 fix) polls Razorpay's API for orders in `payment_pending` status.
  - For each, it checks the Razorpay order status. If captured, it calls the verify/fulfill flow.
  - This is the **safety net** that replaces the current zero-reconciliation approach.

### Lost Webhook

- The reconciliation job (above) also handles lost webhooks. It queries orders in `payment_pending` status older than 5 minutes and checks their status against Razorpay.
- Idempotency ensures processing the same payment twice is safe (unique index on `razorpay_payment_id`).

### Duplicate Webhook

- Idempotent by construction: the `begin_nested()` + `IntegrityError` pattern on the payments table's unique `razorpay_payment_id` index means a duplicate webhook is a no-op.

### Database Rollback

- All reservation state is in Postgres transactions. A rollback returns everything to the pre-transaction state.
- The expiry worker's batch processing with a single commit means a mid-batch crash rolls back the entire tick atomically.

### Queue Failure (Event Bus)

- The in-process event bus (currently `asyncio.create_task`) has no queue to fail.
- For future horizontal scaling (multiple app instances), events would need an external queue (Redis Streams, RabbitMQ). The current in-process bus would become a local-only fallback.
- SSE events via Redis pub/sub are already cross-instance.

---

## 14. Scaling

### 100 Users (Current Scale)

- Single Postgres instance, single Redis instance, single app server.
- Row-level locking on product rows is more than sufficient.
- The expiry worker runs in-process via APScheduler.
- No changes needed from current infrastructure.

### 10,000 Users

- **Database**: Still single Postgres, but consider read replicas for analytics/admin queries. Reservation writes go to primary.
- **Redis**: Single instance for cache + pub/sub + rate limiting. Sufficient for this scale.
- **App servers**: 2-3 instances behind a load balancer. The in-process event bus becomes insufficient — migrate to Redis Streams for cross-instance event delivery.
- **Worker**: Move expiry worker to a separate process (not in-process APScheduler) to avoid contention with request-handling event loops.
- **Connection pool**: Each app server needs its own pool. Monitor `pg_stat_activity` for connection exhaustion under peak load.

### 100,000 Users

- **Database**: Primary + 2 read replicas. Reservation writes still go to primary. Product listing reads go to replicas.
- **Redis**: Cluster mode for cache. Dedicated Redis instance for pub/sub (separate from cache).
- **App servers**: 5-10 instances. Horizontal scaling is trivial because all state is in Postgres.
- **Workers**: Dedicated worker fleet for expiry, reconciliation, notifications. Use a proper task queue (Celery with Redis broker, or ARQ).
- **Connection pooling**: PgBouncer in front of Postgres. Pool per app server, not per connection.

### Flash Sales

Flash sales create extreme contention on a small number of SKUs. The row-level locking approach is correct but has a latency concern: under 10,000 concurrent requests for 2 units, the 9,998 losers each wait behind the full transaction duration of whichever request currently holds the lock.

**Mitigations** (in priority order):

1. **Tighten the lock scope** (§8): Release the product row lock as soon as the reservation write is durable, before doing order creation. This reduces lock hold time from ~100ms to ~5ms.
2. **Queue with a short timeout**: Set `lock_timeout = '3s'`. Requests that cannot acquire the lock within 3 seconds get a fast "busy, try again" response instead of queuing indefinitely.
3. **Pre-reserve for flash sales**: For announced flash sales, allow users to "register interest" (no stock held). At sale time, batch-reserve for a random subset of registrants. This avoids the thundering-herd problem entirely.
4. **Circuit breaker on product**: If a product receives more than 100 concurrent reserve attempts in 10 seconds, temporarily reject new attempts with a "high demand, please retry" message. This protects the database connection pool.

### Multiple Application Servers

- All state is in Postgres (no in-memory reservation state). Horizontal scaling is safe.
- The in-process event bus must be replaced with Redis Streams or a message broker.
- Rate limiting must use Redis (already does — the sliding-window implementation is Redis-backed).
- APScheduler must be replaced with a distributed scheduler (Celery Beat, or a Postgres-backed advisory lock pattern).

### Multiple Workers

- The expiry worker uses `FOR UPDATE SKIP LOCKED`, which is already safe for multi-instance execution. Each instance picks up different rows from the candidate batch.
- The reconciliation job (new) should also use `FOR UPDATE SKIP LOCKED` on the orders it processes.
- SSE event deduplication: multiple workers may expire reservations for the same product simultaneously. Each emits an `InventoryChanged` event, but the frontend handles redundant events gracefully (React Query deduplicates cache invalidations).

---

## 15. Database Constraints

### CHECK Constraints

```sql
-- Products: individual column non-negativity (already exists)
ALTER TABLE products ADD CONSTRAINT products_stock_quantity_check
    CHECK (stock_quantity >= 0);
ALTER TABLE products ADD CONSTRAINT products_reserved_quantity_check
    CHECK (reserved_quantity >= 0);
ALTER TABLE products ADD CONSTRAINT products_sold_quantity_check
    CHECK (sold_quantity >= 0);

-- Products: composite invariant (NEW — currently not enforced)
-- This is the most important constraint in the entire system.
ALTER TABLE products ADD CONSTRAINT products_composite_stock_check
    CHECK (stock_quantity >= reserved_quantity + sold_quantity);

-- Same for variants
ALTER TABLE product_variants ADD CONSTRAINT pv_composite_stock_check
    CHECK (stock_quantity >= reserved_quantity + sold_quantity);

-- Reservation lines
ALTER TABLE reservation_lines ADD CONSTRAINT rl_quantity_positive
    CHECK (quantity > 0);
ALTER TABLE reservation_lines ADD CONSTRAINT rl_original_quantity_positive
    CHECK (original_quantity > 0);
```

### UNIQUE Indexes

```sql
-- Partial unique: one ACTIVE reservation per user per product
CREATE UNIQUE INDEX CONCURRENTLY idx_rl_active_user_product
    ON reservation_lines(user_id, product_id,
        COALESCE(variant_id, '00000000-0000-0000-0000-000000000000'))
    WHERE status = 'ACTIVE';

-- Partial unique: one ACTIVE reservation per order per product
CREATE UNIQUE INDEX CONCURRENTLY idx_rl_active_order_product
    ON reservation_lines(order_id, product_id,
        COALESCE(variant_id, '00000000-0000-0000-0000-000000000000'))
    WHERE status = 'ACTIVE' AND order_id IS NOT NULL;
```

### Foreign Keys

```sql
-- Checkout sessions -> profiles
ALTER TABLE checkout_sessions ADD CONSTRAINT fk_cs_user
    FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE RESTRICT;

-- Reservation lines -> checkout sessions
ALTER TABLE reservation_lines ADD CONSTRAINT fk_rl_session
    FOREIGN KEY (session_id) REFERENCES checkout_sessions(id) ON DELETE CASCADE;

-- Reservation lines -> orders (nullable, set after payment)
ALTER TABLE reservation_lines ADD CONSTRAINT fk_rl_order
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL;

-- Orders -> checkout sessions (NEW)
ALTER TABLE orders ADD CONSTRAINT fk_orders_session
    FOREIGN KEY (session_id) REFERENCES checkout_sessions(id);
```

### Trigger-Based Validation

```sql
-- Ensure an order in 'confirmed' status always has at least one COMPLETED reservation
-- (DEFERRABLE INITIALLY DEFERRED so it checks at COMMIT time, not per-statement)
CREATE CONSTRAINT TRIGGER trg_order_has_reservation
    AFTER INSERT OR UPDATE ON orders
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    WHEN (NEW.status = 'confirmed')
    EXECUTE FUNCTION check_order_has_reservation();

-- The function:
CREATE OR REPLACE FUNCTION check_order_has_reservation()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM reservation_lines
        WHERE order_id = NEW.id AND status = 'COMPLETED'
    ) THEN
        RAISE EXCEPTION 'Order % has no completed reservation', NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### Migration Safety

1. **Audit first**: Before adding `products_composite_stock_check`, query for existing violations:
   ```sql
   SELECT id, stock_quantity, reserved_quantity, sold_quantity
   WHERE stock_quantity < reserved_quantity + sold_quantity;
   ```
2. **Clean up violations**: Fix any rows where the invariant is already broken.
3. **Add as NOT VALID**: `ALTER TABLE ... ADD CONSTRAINT ... NOT VALID` (skips scanning existing rows).
4. **Validate**: `ALTER TABLE ... VALIDATE CONSTRAINT` (scans rows but does not lock the table for writes).

---

## 16. Migration Plan

### Phase 1: Critical Fixes (Week 1-2)

**Risk: Low. Target: Fix the four Critical bugs without changing the data model.**

| Fix | What Changes | Risk |
|---|---|---|
| Reservation quantity reconciliation (fix for reservation-theft) | Modify `reserve_items` reuse branch: instead of freezing quantity, compute delta and adjust. Add quantity diff check. | Low — modifies one code path, preserves the locking layer. |
| Refund triggers restock | Modify `PaymentService.initiate_refund` to call `record_return` for each item when full refund on a confirmed order. | Low — adds a call to an existing, tested method. |
| Returns touch inventory | Modify `ReturnService` to call `record_return` when a return is marked received. | Low — the method already exists and works. |
| Rate limiting on checkout | Add `rate_limit_checkout` dependency to the orders router. | Low — the rate-limiting infrastructure already exists. |
| Cache-before-publish fix | Generalize the commit-before-publish pattern from `expire_stale_reservations` to all other write paths. | Low — mechanical change, same pattern everywhere. |

**Verification**: Run the full test suite. Add specific test cases for each fix. Verify with `black`, `ruff`, `mypy`.

### Phase 2: Architecture Improvements (Week 3-6)

**Risk: Medium. Introduces new tables and modifies the checkout flow.**

| Change | What Changes | Risk |
|---|---|---|
| Create `checkout_sessions` table | New Alembic migration. No existing code affected yet. | Very low — additive only. |
| Create `reservation_lines` table | New Alembic migration. Existing `inventory_reservations` table kept for backward compatibility. | Very low — additive only. |
| Dual-write to both tables | New checkout flow writes to both `inventory_reservations` (old) and `reservation_lines` (new). Old code reads from old table. | Medium — two code paths to maintain. |
| Migrate checkout flow | Update `create_payment_intent` to use `CheckoutSession` + `reservation_lines`. | Medium — core checkout path changes. |
| Add composite CHECK constraint | `stock_quantity >= reserved_quantity + sold_quantity`. Audit violations first. | Low after audit. |
| Add partial unique indexes | On `reservation_lines`. | Low — additive. |
| Delete legacy admin stock-adjust endpoints | Remove `/admin/products/{id}/inventory/adjust` and the dead-code `catalog/repository.py adjust_stock`. | Low — no callers. |

**Verification**: Run full test suite. Shadow-mode both old and new paths for 1 week before cutting over.

### Phase 3: Scaling Improvements (Week 7-10)

**Risk: Medium. Infrastructure changes.**

| Change | What Changes | Risk |
|---|---|---|
| Split lock scope | Two transactions in checkout flow instead of one. | Medium — requires careful testing of edge cases. |
| Add payment reconciliation job | New background job that polls Razorpay for pending/expired orders. | Low — additive, non-critical path. |
| Move expiry worker to separate process | From in-process APScheduler to standalone worker. | Low — same logic, different execution context. |
| Replace in-process event bus with Redis Streams | For horizontal scaling. | Medium — new infrastructure dependency. |

**Verification**: Load test with simulated flash-sale contention. Measure lock-hold times and p99 latency.

### Phase 4: Observability (Week 11-14)

**Risk: Low. Monitoring and alerting, no data model changes.**

| Change | What Changes | Risk |
|---|---|---|
| Wire reservation signals to FraudService | Log reservation count, extension count, per-user active reservations. | Very low — additive logging. |
| Admin dashboard SSE integration | Connect admin app to the same SSE stream as storefront. | Low — frontend-only change. |
| Admin inventory visibility | Show reserved/sold/available alongside stock in admin UI. | Low — frontend-only change. |
| CDN cache headers | Mark stock-sensitive endpoints as `Cache-Control: private` or add Cloudflare purge-on-write. | Low — configuration change. |
| Alert on payment reconciliation failures | PagerDuty/Slack alert when `PaymentReconciliationRequired` event fires. | Very low — additive. |

### Phase 5: Future Enhancements (Week 15+)

**Risk: Varies. Feature additions, not critical path.**

| Enhancement | Description |
|---|---|
| Guest cart sync | Server-side carts for guests, merged on login. |
| Pre-reserve for flash sales | "Register interest" flow that batch-reserves at sale time. |
| Exchange flow | Return item A + ship item B as one atomic operation. |
| Heartbeat-based reservation extension | Server-validated countdown instead of client-side timer. |
| Loyalty points integration | Deduct on purchase, refund on return. |
| Multi-warehouse inventory | Per-warehouse stock tracking with location-aware reservation. |

---

## Summary: What Changes, What Stays

### Preserve As-Is (Already Production-Grade)

- Row-level locking with `SELECT FOR UPDATE`
- Deadlock-safe lock ordering by `(product_id, variant_id)`
- `GREATEST(..., 0)` defense-in-depth on stock decrements
- Append-only audit trail (no DELETEs on reservation/transaction tables)
- Redis circuit breaker (fail-open on Redis outage)
- `begin_nested()` + `IntegrityError` pattern for duplicate webhook/payment handling
- Postgres-only reservation state (no in-memory state)
- The existing `record_return`, `record_restock`, `record_adjustment` methods

### Fix (Critical, Phase 1)

- Reservation quantity reconciliation on retry (the root cause of reservation-theft)
- Refund triggers restock (and vice versa)
- Returns module calls `record_return` on receipt
- Rate limiting on checkout endpoint
- Commit-before-publish generalized across all write paths

### Build (Architecture, Phase 2)

- `checkout_sessions` table (reservations belong to sessions, not orders)
- `reservation_lines` table (with partial unique indexes as DB backstops)
- Composite CHECK constraint (`stock_quantity >= reserved_quantity + sold_quantity`)
- Dual-write migration path

### Add (Operations, Phase 3-4)

- Payment reconciliation background job
- FraudService integration for reservation anomaly detection
- Admin dashboard real-time sync
- CDN cache control for stock-sensitive endpoints
