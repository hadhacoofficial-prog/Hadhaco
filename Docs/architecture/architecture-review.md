# Hadha Reservation System — Architecture Review

> **Review type**: Adversarial Principal/Staff Architect review.
> **Goal**: Challenge every decision. Prove it wrong first. Replace if better exists.
> **Reviewed document**: `reservation-system-architecture.md` (the "proposal").

---

## 1. Challenge Every Major Design Decision

### 1.1 CheckoutSession

**The proposal's claim**: CheckoutSession is the central coordination object that owns reservation lifetime, eliminating the order-reparenting bug.

**Challenge**: Is CheckoutSession actually a new concept, or is it an Order renamed?

The CheckoutSession accumulates: address snapshots, coupon code, coupon ID, notes, idempotency key. These are the same fields that exist on `orders`. The session is created, populated, then "converted" to an order on payment. This is exactly the Order lifecycle — just split into two tables with a state transition between them.

**The honest question**: Why not just make Orders support a `payment_pending` status where the order exists but is not yet confirmed? The current system already does this — `orders.status = 'stock_reserved'` or `'payment_pending'` before payment. The proposal's own data model shows the order gets a `session_id` FK and a `reservation_snapshot` JSONB field. At that point, the CheckoutSession is a pre-Order and the Order is a post-CheckoutSession. Two tables representing the same entity at different lifecycle stages.

**Alternative considered and rejected by the proposal**: Making the cart server-side. The proposal rejects this because "adds complexity and latency to every add-to-cart." This is correct for the general case, but let me stress-test it:

- **Jewellery e-commerce**: Low cart modification frequency. Customers add 1-3 items, maybe adjust quantity once, then checkout. This is not Amazon where customers have 50-item carts they modify daily. A server call per add-to-cart adds ~20-50ms. For a low-frequency operation on a luxury purchase, this is invisible.
- **Guest checkout**: The proposal's biggest unaddressed gap. The current cart is localStorage, which means guest users lose their cart on device change. A server-side cart with a session token (like Shopify's `cart_token`) solves this cleanly.

**Verdict**: CheckoutSession is **the correct choice given the constraint that carts remain client-side**. But that constraint itself is the wrong decision for this platform. See Section 14.2 for the recommended change.

**Industry comparison**:
- **Shopify**: No CheckoutSession. Cart is server-side. Reservation is implicit in inventory allocation at payment time.
- **Stripe**: PaymentIntent is the closest analogue. But Stripe does not manage inventory — that is the platform's job.
- **Medusa/Saleor**: Both use "swap" or "draft order" concepts similar to CheckoutSession. Both also support server-side carts.
- **Amazon**: Cart is server-side. "Reserve" happens at payment time, not at checkout initiation.

**Trade-off accepted**: The proposal accepts a two-table, two-phase architecture (CheckoutSession + Order) instead of a one-table, one-phase architecture (server-side Cart that becomes an Order). This adds migration complexity and a permanent dual-write concern.

### 1.2 Reservation Lines Table

**The proposal's claim**: Separate `reservation_lines` table with one row per product/variant per session.

**Challenge**: Is this table necessary, or should reservations be columns on the checkout session?

A single `reservation_lines` table with per-product rows is correct for multi-product carts. You cannot represent "2 of Product A and 3 of Product B" in a single row. The table is necessary.

**But**: The proposal adds partial unique indexes:
```sql
UNIQUE (user_id, product_id, variant_id) WHERE status = 'ACTIVE'
```

**This is the most dangerous constraint in the proposal.** It enforces exactly one ACTIVE reservation per user per product. Consider:

1. User has Session A with Product X (ACTIVE). Session A expires.
2. Expiry worker runs, sets Session A's reservation to EXPIRED.
3. User creates Session B for Product X.
4. But the expiry worker's transaction has not yet committed (it batches 500 rows).
5. Session B's reservation insert hits the unique constraint -> constraint violation -> checkout fails.

The `FOR UPDATE SKIP LOCKED` in the expiry worker means the worker holds a lock on Session A's reservation row until it commits. Session B's insert will wait for the lock. When the worker commits (setting status to EXPIRED), the unique index no longer applies (it only covers ACTIVE rows). Session B succeeds.

Actually, this is safe — the unique index only covers `WHERE status = 'ACTIVE'`, and the worker transitions the row to EXPIRED before committing. The constraint only fires if there are two ACTIVE rows for the same user+product. Since the worker sets EXPIRED before commit, there is only one ACTIVE row at constraint-check time.

**But there is still a real edge case**: Two concurrent checkout sessions from the same user (two tabs, same product). Tab A creates Session 1 and reserves Product X. Tab B creates Session 2 and tries to reserve Product X. The constraint blocks Tab B. Tab B must either: (a) find Session 1 and reconcile against it, or (b) fail with a confusing error.

The proposal says Tab B "reconciles against Tab A's existing reservation." But this means Tab B is modifying Tab A's reservation — which means Tab B has write access to a reservation it does not own. This is the same cross-session re-parenting problem the proposal was supposed to eliminate, just at the session level instead of the order level.

**Stronger alternative**: Remove the partial unique constraint entirely. Let the application layer handle deduplication via `SELECT FOR UPDATE` on existing reservations. The database constraint is a backstop that creates more edge cases than it prevents.

**Verdict**: The partial unique index is **correct in theory but creates subtle coupling between sessions that undermines the "each session is independent" design goal**. The application-level reconciliation (which already works correctly with row locking) is sufficient. The index should be removed.

### 1.3 Inventory Ledger (Counters vs. Pure Append-Only)

**The proposal's claim**: Keep `stock_quantity`, `reserved_quantity`, `sold_quantity` as mutable counters on the product row, backed by an append-only `inventory_transactions` table.

**Challenge**: Should counters be derived from the transaction log instead?

**Pure append-only approach**:
```
inventory_ledger: (product_id, variant_id, delta, reason, timestamp, reference)
available_stock = SUM(delta) GROUP BY product, variant WHERE timestamp <= now()
```

**Advantages over mutable counters**:
- Impossible for counters to drift from the transaction history.
- Perfect temporal queries ("what was stock at 2pm?").
- Naturally supports multi-warehouse (add a `warehouse_id` column).
- Simpler mental model: one source of truth (the ledger), multiple projections.

**Disadvantages**:
- Every read requires a SUM query over potentially millions of rows (mitigated by materialized views or periodic snapshots).
- The current approach with mutable counters is faster for reads (single row lookup).
- The current approach already has the transaction table as an audit trail.

**The honest assessment**: For a jewellery e-commerce platform at current scale (thousands of SKUs, not millions), the mutable-counter-with-audit-log approach is correct. The performance advantage of direct column reads outweighs the theoretical purity of a derived ledger. The CHECK constraints (`stock_quantity >= reserved_quantity + sold_quantity`) enforce the invariant at the database level, which is equivalent to a derived ledger for correctness purposes.

**However**: The proposal does NOT add the composite CHECK constraint in Phase 1. It defers it to Phase 2. This means the system ships with only individual non-negativity checks, not the composite invariant. **This is a mistake.** The composite constraint should be added in Phase 1 with a `NOT VALID` + `VALIDATE` approach (safe, non-blocking).

**Verdict**: Mutable counters with audit log are **correct for this scale**. The composite CHECK constraint must be added in Phase 1, not Phase 2.

### 1.4 Reservation Reconciliation

**The proposal's claim**: Cart quantity changes reconcile against existing reservations (up or down) on every checkout attempt.

**Challenge**: Is bidirectional reconciliation actually safe?

**Quantity increase**: Customer has reservation for 2, increases to 4. System checks `available_stock >= 2` (the delta), increments `reserved_quantity` by 2, updates reservation to 4.

**This is correct.** The delta check ensures we only reserve what is newly available.

**Quantity decrease**: Customer has reservation for 4, decreases to 2. System decrements `reserved_quantity` by 2, updates reservation to 2.

**This is also correct.** The released stock becomes available to other customers immediately.

**But there is a subtle issue with the decrease path**: Between the customer decreasing quantity and the system committing the release, another customer might have already reserved those 2 units. This is fine — the release and the other customer's reservation are serialized by the product row lock. The release happens first (reducing reserved_quantity), and the other customer's reservation reads the updated value. No oversell.

**The real concern is UX, not correctness**: If the customer decreases from 4 to 2, but between the decrease and the commit, another customer reserves the 2 freed units, the customer sees "2 reserved for you" — which is correct. But if the customer then increases back to 4, they need those 2 units again. If another customer already took them, the increase check fails with "only 2 available." The customer is confused: "I just had 4, why can I only get 2 now?"

**This is inherent to any reservation system and is not a bug.** The alternative (holding the released units for a grace period) adds complexity for a rare edge case. The proposal's approach is correct.

### 1.5 Event Architecture

**The proposal's claim**: In-process `asyncio.create_task` event bus, with Redis pub/sub for SSE.

**Challenge**: This does not work across multiple application servers.

The proposal acknowledges this in Section 14 ("Replace in-process event bus with Redis Streams for horizontal scaling") but defers it to Phase 3. **This is the wrong sequencing.** If the system needs to scale to even 2-3 app servers (which it will, as soon as traffic grows), the in-process event bus becomes a silent failure mode: events published on Server A are invisible to Server B. SSE connections on Server B receive no inventory updates.

**Stronger approach**: Migrate to Redis Streams in Phase 2, not Phase 3. Redis is already in the stack. The migration is straightforward:
- Replace `asyncio.create_task` with Redis Stream `XADD`.
- Replace in-process listeners with consumer groups.
- The existing Redis pub/sub for SSE can remain as-is (it already works cross-instance).

**Verdict**: The event architecture migration is **underprioritized**. It should be Phase 2, not Phase 3.

### 1.6 Session Expiration

**The proposal's claim**: 10-minute TTL, extendable to 30-minute hard cap, 3 extensions max.

**Challenge**: Is 30 minutes enough? Too much?

For jewellery (high-consideration purchase), 30 minutes is aggressive. A customer comparing gold necklaces might take 45 minutes to decide. Forcing them to restart checkout after 30 minutes is frustrating.

**For flash sales**, 30 minutes is too long. Scarce items should be held for 5-10 minutes max.

**The correct approach**: Make the TTL configurable per-product or per-category:
- Flash sale items: 5-minute TTL, 10-minute hard cap.
- Regular items: 10-minute TTL, 30-minute hard cap.
- High-value items: 15-minute TTL, 60-minute hard cap.

This is not a fundamental architectural change — it is a configuration layer on top of the existing TTL mechanism.

**Verdict**: The fixed 30-minute cap is **too rigid**. The TTL should be configurable per product.

### 1.7 API Boundaries

**The proposal's claim**: Four checkout endpoints (create session, reserve, payment, verify).

**Challenge**: This creates 4 HTTP round trips before the customer sees a Razorpay popup. Each round trip adds latency and a failure mode.

**Alternative**: Collapse into 2 endpoints:
1. `POST /checkout` — Creates session + reserves stock + creates Razorpay order. Returns Razorpay order ID.
2. `POST /checkout/verify` — Verifies payment + fulfills order.

This is the pattern used by Shopify, Medusa, and most commerce platforms. The "create session" and "reserve" steps are one atomic operation because the session is meaningless without a reservation.

**Why the proposal separates them**: To allow the customer to review their reservation before committing. But the reservation is already committed (stock is held) after the "reserve" step. The separation creates a window where stock is held but no order exists — the exact problem the proposal was supposed to eliminate.

**Stronger approach**: Single `POST /checkout` that atomically creates session + reserves + creates Razorpay order. The session is the coordination object, but it does not need to be a separate API call.

**Verdict**: The four-endpoint checkout is **over-decomposed**. Collapse to two endpoints (checkout + verify) for simplicity and reduced failure surface.

---

## 2. Concurrency Model Stress Test

### 2.1 SELECT FOR UPDATE with SKIP LOCKED

**The proposal's claim**: `SELECT FOR UPDATE SKIP LOCKED` on the product row prevents two concurrent checkouts from overselling the last unit.

**Challenge**: SKIP LOCKED means both transactions proceed — but the second one skips the row and does not see the lock. What does it actually read?

The flow:
1. Transaction A locks `products WHERE id = X FOR UPDATE`. Holds the lock.
2. Transaction B starts, runs the same query with `SKIP LOCKED`. The row is locked, so B skips it. B reads nothing. B's reservation insert fails because `available_stock < requested_qty` (B did not decrement anything, it still sees the old value).
3. Transaction A commits (decrements stock).
4. Transaction B retries. Now the row is unlocked. B reads the updated stock. If stock is sufficient, B succeeds.

**This is correct.** SKIP LOCKED is the right pattern here because:
- It prevents deadlocks (no waiting for locks).
- It forces a retry (fast failure, not blocking).
- The retry reads the committed value from Transaction A.

**Edge case**: What if Transaction A rolls back after locking? The lock is released, stock is unchanged. Transaction B retries and sees the original stock. Correct.

**Edge case**: What if Transaction A commits but the subsequent order creation fails? Stock was decremented but no order exists. The proposal handles this with a compensating `restock_cancelled_order()` in the order creation failure path. This is correct — but it is the same compensating transaction pattern the proposal criticizes the current system for using.

**Honest assessment**: The proposal uses compensating transactions for the order-creation failure path, which is the same pattern it criticizes in the current system. The difference is that the proposal's compensating path is well-defined (fail the entire checkout) while the current system's is ad-hoc (cancel the order, hope the stock restock works). Both are compensating; the proposal's version is simply more disciplined.

### 2.2 Concurrent Checkout for Same Product (Flash Sale)

**Stress test**: 500 customers simultaneously attempt to buy the last 100 units of a product.

**Scenario**:
1. All 500 transactions start within a 10ms window.
2. Each runs `SELECT FROM products WHERE id = X FOR UPDATE SKIP LOCKED`.
3. One transaction gets the lock. The other 499 skip the row.
4. The locking transaction decrements stock from 100 to 99 (or to 0 if buying all 100), commits.
5. The next transaction gets the lock, reads the updated stock, decrements if possible.
6. This cascades until all 100 units are reserved.

**Total time**: ~100 serial lock acquisitions. Each takes ~1-5ms (Postgres row lock + commit). Total: ~100-500ms. For 500 concurrent users, this is acceptable — most will see "out of stock" within 500ms.

**Problem**: The 499 skipped transactions each execute their full checkout flow (create session, check stock, attempt reservation) only to find 0 stock on retry. This is wasted work. 499 database round trips that achieve nothing.

**Proposal's mitigation**: None explicitly stated. The proposal relies on the frontend retry loop, which is implicit.

**Stronger approach**: A Redis stock pre-check before the database transaction:
```
available = redis.decr(f"stock:{product_id}")
if available < 0:
    redis.incr(f"stock:{product_id}")  # roll back
    return "out_of_stock"
```

This reduces the 500 database connections to ~100 (only customers who pass the Redis check hit Postgres). The Redis check is O(1) and handles contention internally with much lower overhead.

**Verdict**: The pure-database locking model **works correctly but scales poorly under flash-sale contention**. A Redis pre-check should be added in Phase 2.

---

## 3. Scalability Review

### 3.1 Database Write Amplification

The current system writes to `products` (stock decrement), `inventory_reservations` (new row), `orders` (new row), `order_items` (new rows), and `inventory_movements` (new row) on every successful checkout. That is at least 5 table writes per checkout.

At 100 concurrent checkouts per second, this is 500 writes/second across 5 tables. Postgres handles this easily (single-node Postgres can do ~10,000 writes/second on modest hardware). The bottleneck is not write volume — it is lock contention on the `products` table.

**The real bottleneck**: Every checkout locks the `products` row for the duration of the transaction (session creation + reservation + stock decrement). If the transaction takes 50ms, the product row is locked for 50ms. During that window, all other checkouts for the same product are blocked (or skip-locked).

**At 100 concurrent checkouts for the same product**: The serial lock acquisition takes ~5 seconds total (100 × 50ms). This is the throughput ceiling for a single product.

**At 1000 concurrent checkouts**: ~50 seconds. Unacceptable for a flash sale.

**Mitigation**: Redis stock pre-check (see Section 2.2). Also: reduce transaction duration by moving the Razorpay order creation outside the reservation transaction (the proposal already does this in Section 5.3).

### 3.2 Horizontal Scaling

The proposal's architecture is horizontally scalable with one caveat: the in-process event bus (Section 1.5). Everything else (Postgres, Redis, Razorpay) is external and shared.

**Caveat**: SSE connections are sticky-session dependent. If the server that holds a user's SSE connection restarts, the user loses real-time updates. The proposal's Section 14 notes this but defers the fix to Phase 3.

**Scaling ceiling**: Without Redis Streams for events, the system is effectively single-server for real-time updates. This is fine for <1000 concurrent users but becomes a hard limit at higher traffic.

### 3.3 Read Scaling

Product catalog reads can be served from Redis cache (already implemented). Order history can be paginated with cursor-based pagination (already implemented). The read path is well-scaled.

**The weak spot**: `GET /cart` currently reads from localStorage (client-side). If migrated to server-side (Section 14.2), every page load would hit the database for cart data. This is a new read load that must be cached.

**Mitigation**: Cache cart data in Redis with a short TTL (5 minutes). Cart reads are frequent but not latency-critical (a 10ms Redis read is acceptable).

---

## 4. Database Review

### 4.1 Composite CHECK Constraint

**The proposal's claim**: Add `CHECK (stock_quantity >= reserved_quantity + sold_quantity)` in Phase 2.

**Challenge**: This should be Phase 1.

The current system has:
- `stock_quantity >= 0` (individual non-negativity)
- `reserved_quantity >= 0` (individual non-negativity)
- `sold_quantity >= 0` (individual non-negativity)

But no composite invariant. This means:
- `stock_quantity = 0, reserved_quantity = 5, sold_quantity = 0` passes all individual checks but represents an impossible state (5 reserved units with 0 stock).
- The composite constraint catches this.

**Why it must be Phase 1**: The composite constraint is the database-level safety net that prevents the core business logic bug (overselling). Without it, any application-level bug that sets `reserved_quantity > stock_quantity` silently corrupts the data. The constraint does not block writes (it only fires on update), so it has zero performance impact on normal operations.

**Implementation**: Use `NOT VALID` + `VALIDATE CONSTRAINT`:
```sql
ALTER TABLE products
ADD CONSTRAINT chk_inventory_invariant
CHECK (stock_quantity >= reserved_quantity + sold_quantity)
NOT VALID;

ALTER TABLE products
VALIDATE CONSTRAINT chk_inventory_invariant;
```

The `NOT VALID` step is instant (no row scan). The `VALIDATE` step scans all rows but does not hold an exclusive lock (it takes a `SHARE UPDATE EXCLUSIVE` lock, which allows concurrent reads and writes). This is safe for production.

### 4.2 Partial Unique Index Cross-Session Coupling

**The proposal's claim**: `UNIQUE (user_id, product_id, variant_id) WHERE status = 'ACTIVE'` prevents duplicate reservations.

**Challenge**: This constraint couples all of a user's sessions. If Session A has an ACTIVE reservation for Product X and Session B tries to create one, Session B's insert is blocked by the constraint.

**The proposal's mitigation**: Session B "reconciles against Session A." But this means Session B must:
1. Detect the constraint violation.
2. Query for Session A's reservation.
3. Decide whether to merge, replace, or fail.

This is application-level logic that duplicates the session ownership model. The constraint is supposed to simplify the model, but it actually adds a new code path (cross-session reconciliation) that must be tested and maintained.

**Stronger approach**: Remove the partial unique constraint. The application already handles this correctly:
1. Session B tries to reserve Product X.
2. `SELECT FOR UPDATE` on existing ACTIVE reservation for this user+product.
3. If found: reconcile (increase/decrease as needed) within Session B's transaction.
4. If not found: create new reservation.

This is the same logic, but without the database constraint creating an exception path. The row-level lock (`FOR UPDATE`) provides the same mutual exclusion without the cross-session coupling.

**Verdict**: Remove the partial unique constraint. The application-level row locking is sufficient and avoids the cross-session reconciliation complexity.

### 4.3 Reservation Snapshot on Order

**The proposal's claim**: Store a JSONB `reservation_snapshot` on the order row to capture what was reserved.

**Challenge**: JSONB snapshots are not queryable. If you need to find "all orders that included Product X," you must scan every order's JSONB field.

**Alternative**: The `order_items` table already stores `product_snapshot` (JSONB). Adding a `reservation_id` FK on `order_items` pointing to the reservation row is queryable and maintains the link without duplicating data.

**Verdict**: The `reservation_snapshot` JSONB field is redundant with `order_items.product_snapshot`. The link should be a FK, not a snapshot.

---

## 5. API Review

### 5.1 Checkout Flow Latency

The proposal's four-endpoint checkout has these latency contributors:
1. `POST /checkout/sessions` — ~50ms (create session row)
2. `POST /checkout/sessions/{id}/reserve` — ~100ms (SELECT FOR UPDATE + stock decrement + reservation insert)
3. `POST /checkout/sessions/{id}/payment` — ~200ms (Razorpay API call)
4. `POST /checkout/verify` — ~150ms (verify signature + create order + fulfill)

**Total**: ~500ms before the customer sees a Razorpay popup. After payment: another ~150ms for verification.

**The proposal's own Section 5.3 recommends collapsing steps 1-2 into a single call**, which reduces to:
1. `POST /checkout` — ~150ms (create session + reserve + create Razorpay order)
2. `POST /checkout/verify` — ~150ms (verify + fulfill)

**Total**: ~300ms. A 40% reduction in pre-payment latency.

**The proposal should adopt its own recommendation.** The four-endpoint model is over-engineered for this use case.

### 5.2 Error Handling

The proposal's Section 15.5 defines HTTP status codes for each error type. This is good. But there is a gap: what happens if `POST /checkout` succeeds (session created, stock reserved) but the Razorpay order creation fails?

The proposal says "return error to frontend, customer retries." But stock is already reserved. The reservation holds stock for 10 minutes. If the customer retries within 10 minutes, the reservation is reused (reconciliation). If they retry after 10 minutes, the reservation expires and stock is released.

**The gap**: If Razorpay is down for 30 minutes, every customer who attempted checkout has a reservation holding stock but no order. The reservation expires after 10 minutes, but during those 10 minutes, the stock is unavailable to other customers.

**Mitigation**: The proposal's TTL mechanism handles this — reservations expire after 10 minutes regardless. But for a Razorpay outage lasting 30 minutes, 30 minutes worth of reservations are created and expired, each holding stock for 10 minutes. The effective stock availability is reduced by the number of concurrent reservations.

**Stronger approach**: If Razorpay order creation fails, immediately expire the reservation (do not wait for TTL). This releases stock instantly and allows other customers to proceed.

---

## 6. Failure Recovery

### 6.1 Reservation Expiry Worker

**The proposal's claim**: A background worker polls every 30 seconds for expired reservations, releases stock, and sends SSE notifications.

**Challenge**: What happens if the worker crashes mid-batch?

The proposal says the worker uses `FOR UPDATE SKIP LOCKED` and processes in batches of 500. If the worker crashes after processing 250 of 500 rows:
- The 250 processed rows are committed (status changed to EXPIRED, stock released).
- The 250 unprocessed rows remain ACTIVE.
- When the worker restarts, it picks up the remaining 250 rows.

**This is correct.** The worker is idempotent — processing a row twice has no effect (EXPIRED status is a no-op). The `SKIP LOCKED` ensures no rows are lost.

**Edge case**: What if the worker crashes AFTER decrementing `reserved_quantity` on the product row but BEFORE updating the reservation status? The product row has less reserved stock, but the reservation is still ACTIVE. A new customer sees more available stock than actually exists.

**This cannot happen** if both operations are in the same transaction (which they are — the proposal's Section 8.1 wraps both in a single transaction). If the transaction rolls back, both the stock decrement and the status change are undone.

**Verdict**: The expiry worker is **correctly designed**. No changes needed.

### 6.2 Payment Verification Failure

**The proposal's claim**: If Razorpay verification fails (signature mismatch), the order is not created and the reservation remains ACTIVE for the customer to retry.

**Challenge**: What if the signature is invalid because of a webhook race condition? Razorpay sends both a redirect (sync) and a webhook (async). If the redirect fails (network timeout) but the webhook succeeds, the customer sees "payment failed" but the webhook creates the order.

**The proposal handles this**: The idempotency key (`razorpay_order_id` uniqueness) prevents duplicate order creation. If the webhook arrives first, the order is created. If the redirect arrives later, the idempotency check finds the existing order and returns it instead of creating a duplicate.

**But**: The idempotency key is on `checkout_sessions.razorpay_order_id`. If the redirect creates the session without a Razorpay order ID (because the Razorpay call failed), the webhook cannot match the session.

**Mitigation**: The Razorpay order ID is created in `POST /checkout` (step 3 of the proposal). If the Razorpay call fails, no order ID exists, no session is created, and the webhook has nothing to match. This is correct — a failed Razorpay call means no session, no reservation, no order.

**Verdict**: Payment verification is **correctly handled** with idempotency keys. No changes needed.

---

## 7. Security Review

### 7.1 CSRF Protection

The proposal's Section 15.4 recommends sameSite cookies for CSRF protection. This is the correct approach for cookie-based auth. But the proposal does not mention what happens for API key authentication (server-to-server webhooks).

**Gap**: Razorpay webhooks use a signature header (`X-Razorpay-Signature`), not cookies. CSRF is not applicable to webhooks (they are server-to-server). But the proposal should explicitly state this to avoid confusion during implementation.

### 7.2 Stock Manipulation

**Threat**: A malicious user sends `POST /checkout` with `variant_id: null` to target the product-level stock instead of a specific variant, potentially reserving stock for all variants simultaneously.

**The proposal's mitigation**: Validate that `variant_id` matches a valid variant of the product. If the product has no variants, `variant_id` must be null.

**Challenge**: What if the product has variants but the user sends `variant_id: null`? The system should reject this (you cannot reserve product-level stock when variants exist). The proposal does not explicitly state this validation.

**Stronger approach**: If `product.has_variants == true` and `variant_id is null`, reject with 400. If `product.has_variants == false` and `variant_id is not null`, reject with 400. This ensures the reservation always targets the correct stock level.

### 7.3 Idempotency Key Reuse

**Threat**: A user sends multiple `POST /checkout` requests with the same idempotency key. The first creates a session. The subsequent ones should return the existing session (idempotent behavior).

**The proposal's Section 15.4 handles this**: "If `idempotency_key` exists in `checkout_sessions`, return existing session (idempotent)."

**Challenge**: What if the existing session is in `FAILED` status (Razorpay order creation failed)? The user retries with the same key. Should the system return the failed session or create a new one?

**Stronger approach**: If the session is in `FAILED` status, create a new session with a new idempotency key. The old session is dead (no Razorpay order to retry against). The user needs a fresh attempt.

---

## 8. Domain Model Review

### 8.1 DDD Bounded Contexts

The proposal identifies four bounded contexts: Product Catalog, Inventory, Orders, Payments. This is correct.

**Missing bounded context**: Cart. The proposal keeps the cart client-side (localStorage), so it does not exist as a bounded context. If the cart is migrated server-side (Section 14.2), it becomes a new bounded context with its own aggregate root (Cart), value objects (CartItem, CartItemVariant), and domain events (ItemAdded, ItemRemoved, QuantityChanged).

**The proposal correctly defers this** to a future decision point. But the recommendation is clear: the cart should be server-side for this platform.

### 8.2 Aggregate Boundaries

The proposal's aggregates:
- **Product**: Product + ProductVariant + ProductMedia + ProductAttribute. This is correct — all are entity/value objects within the Product aggregate.
- **Inventory**: InventoryReservation + InventoryMovement. Correct — these are entities owned by the Inventory aggregate.
- **Order**: Order + OrderItem + OrderTimelineEntry + OrderStatusHistory. Correct.
- **Payment**: Payment + PaymentTimelineEntry. Correct.

**Missing aggregate**: CheckoutSession (proposed as a new aggregate). This is correct — CheckoutSession is an aggregate root with its own lifecycle, independent of Order.

**Concern**: The CheckoutSession aggregate holds `address_snapshot` (JSONB) and `coupon_code`. If the coupon is per-user (one-time use), the session must "lock" the coupon when it reserves stock. Otherwise, a user could create multiple sessions with the same one-time coupon. The proposal does not address coupon locking.

**Stronger approach**: When a session is created with a coupon, decrement the coupon's usage count immediately (within the reservation transaction). If the session expires or is cancelled, restore the usage count. This is the same reservation pattern applied to coupons.

---

## 9. Missing Edge Cases

### 9.1 Guest Checkout

The proposal assumes authenticated users (JWT-based). Guest users cannot checkout.

**Impact**: This is a significant UX limitation. ~30-40% of e-commerce checkouts are guest (Baymard Institute data). For a jewellery platform, this may be lower (customers often create accounts for high-value purchases), but it is still a non-trivial segment.

**Stronger approach**: Add a guest checkout flow in Phase 2:
1. Guest provides email at checkout.
2. System creates an anonymous session (no JWT required).
3. After payment, system creates a user account with the email and links the order.
4. Guest receives an email to set a password.

This requires a new endpoint (`POST /checkout/guest`) and a session model that supports both authenticated and anonymous sessions.

### 9.2 Product Discontinuation During Checkout

**Scenario**: Customer reserves Product X. Admin discontinues Product X. Customer proceeds to payment. Payment succeeds. Order is created with a discontinued product.

**Impact**: The order contains a product that no longer exists. Fulfilment may fail (supplier cannot source the product). Customer support must handle the exception.

**The proposal does not address this.** The `product_status` is checked at reservation time but not at fulfilment time.

**Stronger approach**: Check `product.status` at order creation time (in `POST /checkout/verify`). If the product is discontinued, fail the verification and refund the payment. This is a single additional check in the verify flow.

### 9.3 Price Changes During Checkout

**Scenario**: Customer reserves Product X at ₹10,000. Admin changes price to ₹12,000. Customer proceeds to payment at ₹10,000. Payment succeeds.

**Impact**: The customer paid the old price. The order reflects the old price. The admin loses ₹2,000.

**The proposal's reservation snapshot** (Section 5.2) captures the price at reservation time. The order uses this snapshot. This means the customer pays the old price, which is correct from the customer's perspective but incorrect from the business perspective.

**Stronger approach**: Two options:
1. **Lock price at reservation time** (proposal's approach): Customer pays the price they saw. Business absorbs price changes. This is standard for e-commerce (price protection).
2. **Lock price at payment time**: Customer pays the current price at the moment of payment. If the price changed, the customer sees the new price before confirming payment.

**Recommendation**: Option 1 (lock at reservation time) is correct for this platform. The proposal's approach is correct. But the proposal should explicitly state this as a design decision, not an implicit behavior.

### 9.4 Coupon Expiry During Checkout

**Scenario**: Customer applies a coupon with 1-hour expiry. Customer takes 30 minutes to checkout. Coupon expires. Customer pays without the discount.

**The proposal does not address this.**

**Stronger approach**: At payment time (`POST /checkout`), verify the coupon is still valid. If expired, recalculate the total without the discount and inform the customer. Do not fail the checkout — just remove the discount and show the updated total.

### 9.5 Partial Refund with Partial Return

**Scenario**: Customer returns 2 of 5 items. Partial refund is issued. Inventory is restocked for 2 items. The order status remains `DELIVERED` (not all items returned).

**The proposal's Section 12.2 handles this**: "Partial returns trigger partial refunds. Inventory is restocked. Order status remains DELIVERED."

**Challenge**: What about the `sold_quantity` on the product? When 2 items are returned, `sold_quantity` should decrease by 2 and `stock_quantity` should increase by 2.

**The proposal's `record_return()` method handles this** (Section 8.1.2). It decrements `sold_quantity` and increments `stock_quantity`. Correct.

**But**: The proposal does not address the case where a partial return is requested AFTER a partial refund on the same order. For example:
1. Customer returns Item A (partial refund issued, inventory restocked).
2. Customer returns Item B (another partial refund, more inventory restocked).
3. Customer disputes the second refund (chargeback).

**The proposal's chargeback handling** (Section 12.3) does not address partial chargebacks. A chargeback is typically for the full order amount, not individual items.

**Stronger approach**: Support full and partial chargebacks:
- Full chargeback: Reverse the entire order, restock all items, mark as `CHARGEBACK`.
- Partial chargeback: Reverse specific items, restock those items, mark order as `PARTIAL_CHARGEBACK`.

### 9.6 Exchange with Different SKU

**Scenario**: Customer returns a gold necklace (SKU: GLN-001) and exchanges for a silver bracelet (SKU: SBR-002).

**The proposal does not address exchanges.** The `Return` model supports returns and refunds, not exchanges.

**Stronger approach**: Add an exchange flow:
1. Customer initiates a return for GLN-001.
2. Customer selects SBR-002 as the exchange item.
3. System checks stock for SBR-002.
4. If stock available: reserve SBR-002, process return for GLN-001, adjust the refund amount (price difference).
5. If no stock: offer refund only.

This is a Phase 3 feature. The current proposal's return model is sufficient for Phase 1 (returns + refunds only).

### 9.7 Shipment Split

**Scenario**: Customer orders 3 items. Item A is in stock. Items B and C are backordered. The order is split into two shipments.

**The proposal does not address shipment splitting.** The `FulfillmentTimeline` model tracks a single shipment per order.

**Stronger approach**: Add a `shipments` table:
```
shipments: (id, order_id, status, tracking_number, carrier, shipped_at, delivered_at)
order_items: (..., shipment_id FK)
```

Each shipment has its own status and tracking. Order items are linked to specific shipments. This allows partial fulfilment and separate tracking.

This is a Phase 3 feature. For Phase 1, the single-shipment model is sufficient.

### 9.8 Cart Merge After Login

**Scenario**: Guest user adds items to cart. Creates an account (or logs in). Guest cart is lost.

**The proposal does not address cart merging** because the cart is client-side.

**If the cart is migrated server-side** (Section 14.2), cart merge is straightforward:
1. On login, merge the anonymous session's cart into the user's cart.
2. If both carts have the same product, take the higher quantity.
3. If stock is insufficient for the merged cart, notify the user.

This is a Phase 2 feature, only relevant if the cart is migrated server-side.

---

## 10. Production Readiness

### Critical (Phase 1 — Must Fix Before Implementation)

**C1. Composite CHECK constraint must be Phase 1**

The proposal defers `CHECK (stock_quantity >= reserved_quantity + sold_quantity)` to Phase 2. This is the database-level safety net that prevents the core business logic bug (overselling). Without it, any application-level bug that sets `reserved_quantity > stock_quantity` silently corrupts data.

**Action**: Add the constraint in Phase 1 with `NOT VALID` + `VALIDATE` (safe, non-blocking).

**C2. Payment reconciliation must be Phase 1**

The proposal defers Razorpay payment reconciliation to Phase 3. Without reconciliation, there is no way to detect and fix mismatched payments (paid but not fulfilled, fulfilled but not paid). This is a financial compliance requirement, not a nice-to-have.

**Action**: Add a reconciliation job in Phase 1 that runs every 15 minutes and compares Razorpay payments against fulfilled orders.

**C3. Remove partial unique constraint**

The proposal's `UNIQUE (user_id, product_id, variant_id) WHERE status = 'ACTIVE'` creates cross-session coupling. The application-level row locking is sufficient for correctness. The constraint adds complexity without proportional benefit.

**Action**: Remove the partial unique index from the reservation_lines table.

### High (Phase 1-2 — Should Fix Before Launch)

**H1. Migrate event bus to Redis Streams in Phase 2**

The in-process event bus does not scale to multiple app servers. Redis is already in the stack. The migration is straightforward and should be done before the system needs horizontal scaling.

**Action**: Move from Phase 3 to Phase 2. Replace `asyncio.create_task` with Redis Stream `XADD`. Replace in-process listeners with consumer groups.

**H2. Add Redis stock pre-check for flash sales**

The pure-database locking model (SELECT FOR UPDATE SKIP LOCKED) handles contention correctly but scales poorly above ~200 concurrent users per product. A Redis pre-check reduces the database load by ~80% under flash-sale conditions.

**Action**: Add a Redis stock counter as an optional layer in Phase 2. Not required for launch, but required before the first flash sale.

**H3. Make TTL configurable per product**

The fixed 30-minute hard cap is too aggressive for high-consideration jewellery purchases and too lenient for flash sales. A per-product TTL configuration (5-60 minutes) accommodates both scenarios.

**Action**: Add a `checkout_ttl_minutes` column to `products` (default: 10). Use this value for reservation TTL instead of a global constant.

**H4. Add product status check at fulfilment time**

The proposal checks `product.status` at reservation time but not at fulfilment time. If a product is discontinued between reservation and fulfilment, the order contains a dead product.

**Action**: Add a `product.status` check in `POST /checkout/verify` (before creating the order). If discontinued, fail verification and refund payment.

**H5. Collapse checkout to two endpoints**

The four-endpoint checkout (create session, reserve, payment, verify) is over-decomposed. The proposal's own Section 5.3 recommends collapsing steps 1-2. The recommendation should be adopted.

**Action**: Replace the four endpoints with `POST /checkout` (create session + reserve + Razorpay order) and `POST /checkout/verify` (verify + fulfil).

### Medium (Phase 2-3 — Nice to Have)

**M1. Add guest checkout flow**

~30-40% of e-commerce checkouts are guest. The current system requires authentication. This limits conversion.

**Action**: Add `POST /checkout/guest` in Phase 2. Create anonymous sessions. Link orders to email after payment.

**M2. Add coupon locking during checkout**

A user can apply the same one-time coupon to multiple checkout sessions. The coupon is not "locked" until payment.

**Action**: Decrement coupon usage count at reservation time. Restore on session expiry or cancellation.

**M3. Add price change notification at payment time**

If a product's price changes between reservation and payment, the customer should be notified before confirming payment.

**Action**: In `POST /checkout`, compare reservation price with current price. If different, return a warning. Let the frontend display the discrepancy.

**M4. Add shipment splitting support**

The current model tracks a single shipment per order. Multi-shipment support is needed for backordered items.

**Action**: Add a `shipments` table in Phase 3. Link `order_items` to `shipments`.

**M5. Add exchange flow**

The current model supports returns and refunds, not exchanges. Exchanges are a common customer request.

**Action**: Add exchange logic in Phase 3. Reserve the exchange item, process the return, adjust the refund amount.

### Low (Phase 3+ — Future Consideration)

**L1. Add cart merge after login**

Only relevant if the cart is migrated server-side. Merge anonymous cart into user cart on login.

**L2. Add partial chargeback support**

Support chargebacks on individual items, not just the full order. Restock returned items.

**L3. Add Redis Streams for events**

Already covered in H1. Listed here as a reminder that it is a Phase 2 item, not Phase 3.

### Nice-to-Have (Phase 4+)

**N1. Add multi-warehouse inventory**

The current model assumes a single warehouse. Multi-warehouse requires a `warehouse_id` on inventory tables and allocation logic.

**N2. Add inventory forecasting**

Use historical sales data to predict stock needs. This is a data science feature, not an engineering feature.

---

## 11. Final Verdict

### Architecture Quality: 8/10

The proposal is **significantly better** than the current system. It fixes all 4 Critical bugs and introduces a disciplined two-phase architecture (reservation → payment → fulfilment) that is standard in modern e-commerce.

### What Must Change Before Implementation

1. **Add composite CHECK constraint in Phase 1** (C1).
2. **Add payment reconciliation in Phase 1** (C2).
3. **Remove partial unique constraint on reservation_lines** (C3).
4. **Collapse checkout to two endpoints** (H5).
5. **Make reservation TTL configurable per product** (H3).

### What Should Change But Can Wait

1. Migrate event bus to Redis Streams in Phase 2 (H1).
2. Add Redis stock pre-check before first flash sale (H2).
3. Add product status check at fulfilment time (H4).
4. Add guest checkout in Phase 2 (M1).
5. Add coupon locking in Phase 2 (M2).

### What Is Correct as Proposed

1. CheckoutSession as the central coordination object (given client-side cart constraint).
2. Reservation Lines table with per-product rows.
3. Inventory Ledger with mutable counters + audit log (correct for this scale).
4. Reservation reconciliation (bidirectional, on every checkout attempt).
5. Session expiration with 10-minute TTL + 30-minute hard cap.
6. Two-transaction checkout flow (locked write then unlocked read).
7. Payment verification with idempotency keys.
8. SSE notifications for real-time updates.
9. Optimistic concurrency with version columns on orders.
10. Background worker for reservation expiry.

### Overall Recommendation

**Proceed with implementation.** The architecture is sound. The 5 changes listed in "What Must Change" are implementation-level adjustments, not architectural rethinks. The proposal is ready for Phase 1 development.
