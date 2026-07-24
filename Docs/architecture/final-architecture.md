# Hadha Reservation System — Final Architecture

> **Author**: Principal Architect (sign-off)
> **Date**: July 2026
> **Status**: DEFINITIVE — Engineering team implements this. No further architecture debates.
> **Predecessor**: `reservation-system-architecture.md` (proposal), `architecture-review.md` (adversarial review)

---

# Part A: Decisions

Each decision below is binary or singular. There is no "alternative A vs B" — there is the chosen path and the rejected path.

---

## Decision 1: Cart — Server-Side, Persistent

### Final Decision

**Server-side cart.** Replace the current localStorage-only frontend cart with a persistent `carts` + `cart_items` table that already exists in the database schema but is unused by the backend.

### Why This Is the Best Choice

The `carts` and `cart_items` tables already exist (`Backend/app/modules/cart/models.py`) with the correct schema:
- `carts`: user_id (nullable for guests), session_id, coupon_code, discount, expires_at
- `cart_items`: cart_id, product_id, variant_id, quantity, unit_price
- Unique constraint: `(cart_id, product_id, variant_id)`

The infrastructure is built. The decision is whether to use it.

**Business justification**:
1. **Guest checkout** (~30-40% of e-commerce traffic per Baymard Institute). localStorage carts are lost on device change. Server carts persist via session token.
2. **Cross-device sync**. Customer adds items on mobile, completes on desktop. Required for high-value jewellery purchases where customers research on phone, buy on laptop.
3. **Abandoned cart recovery**. Server-side carts enable email reminders for abandoned carts. This is a direct revenue recovery tool (5-15% of abandoned carts convert with a reminder email).
4. **Server-side stock validation**. Cart shows real-time availability. Customer sees "only 2 left" before reaching checkout, not at checkout when it is too late.
5. **Cart merge after login**. Guest adds items, creates account, cart merges automatically. Zero friction.

### Why the Alternatives Were Rejected

**localStorage (current approach)**:
- Lost on device switch, browser clear, incognito mode.
- No server-side stock validation until checkout (customer discovers "out of stock" at the worst moment).
- No abandoned cart recovery.
- No guest checkout.
- Cart data is invisible to the business (no analytics on cart behavior).

**localStorage + server sync hybrid** (like the current proposal's implicit model):
- Adds sync complexity (conflict resolution when local and server differ).
- localStorage becomes the source of truth, server is a mirror — defeats the purpose.
- Two sources of truth is worse than one.

### Long-Term Trade-offs

| Concern | Impact | Mitigation |
|---|---|---|
| Every add-to-cart is a DB write | ~20-50ms per operation | Redis cache for cart reads; writes are infrequent (jewellery: 2-5 items per cart) |
| Guest cart cleanup | Orphaned carts accumulate | TTL-based cleanup worker (expire carts after 7 days of inactivity) |
| Cart table bloat | High-traffic periods create many carts | Partition by `created_at` quarterly; vacuum old partitions |
| Rate limiting on cart ops | Adds latency | Cart operations are low-frequency; rate limit at 30 req/min per user (not per IP) |

### Migration Impact

- **Backend**: Activate the existing `carts` module. Add endpoints: `GET/POST/PUT/DELETE /cart/items`, `POST /cart/merge`.
- **Frontend**: Replace localStorage cart with API calls. Wrap in React Query with optimistic updates.
- **Data**: Migrate existing localStorage carts to server on first login (one-time, client-side migration script).
- **Timeline**: Phase 1 (first 2 weeks).

### Operational Impact

- One new Redis cache layer for cart reads (key: `cart:{user_id}` or `cart:{session_id}`).
- One new background worker for cart TTL cleanup (runs daily, deletes carts older than 7 days).
- No new infrastructure. Postgres and Redis are already in the stack.

---

## Decision 2: CheckoutSession — Eliminated. Cart Becomes the Session.

### Final Decision

**No CheckoutSession.** The cart IS the checkout session. When a customer clicks "Checkout," the cart transitions from `BROWSING` to `CHECKOUT` status. Stock is reserved at this point. The cart holds the reservation until payment succeeds (cart → order) or fails (cart → release stock, revert to `BROWSING`).

### Why This Is the Best Choice

The adversarial review identified that CheckoutSession is an Order at a different lifecycle stage. Two tables representing the same entity at different stages is architectural overhead. The cart already holds everything a CheckoutSession would hold:
- Product references + quantities (cart_items)
- Address snapshots (can be added to cart as JSONB)
- Coupon code (already on cart)
- Price snapshots (unit_price on cart_items)

The only thing missing from the cart that CheckoutSession adds is address snapshots. This is a single JSONB column addition.

**The flow**:
1. Customer browses, adds items to cart (`CART` status).
2. Customer clicks "Checkout" → cart transitions to `CHECKOUT` status → stock is reserved → address is captured.
3. Customer confirms → Razorpay popup appears.
4. Payment succeeds → cart converts to Order → stock moves from reserved to sold.
5. Payment fails → cart reverts to `CART` status → stock is released.

**Why this works**: One entity (Cart) with clear status transitions. No dual-write between CheckoutSession and Order. No orphaned sessions. No reconciliation logic between two tables.

### Why the Alternatives Were Rejected

**CheckoutSession + Order (the proposal's model)**:
- Two tables for one entity at different lifecycle stages.
- Requires reconciliation between session and order.
- Session must be "converted" to order — a complex transaction that the proposal already acknowledges is error-prone.
- The proposal's own Section 5.3 recommends collapsing session creation and reservation into one call, which eliminates the value of having a separate session.

**Order with `payment_pending` status** (existing pattern):
- Orders are financial records. Creating an order before payment means a financial record exists for a non-transaction. This pollutes the order table with unpaid entries.
- Refunding an unpaid order is semantically wrong — there is nothing to refund.
- Order IDs are used in accounting. Unpaid orders create noise in financial reports.

### Long-Term Trade-offs

| Concern | Impact | Mitigation |
|---|---|---|
| Cart table grows with address snapshots | Cart row becomes wider | JSONB compression; address snapshot only added at CHECKOUT status |
| Cart status transitions are complex | 4 states (BROWSING, CHECKOUT, CONVERTED, EXPIRED) | Simple state machine; enforce with CHECK constraint |
| Cart→Order conversion is a multi-table transaction | Latency under contention | Keep conversion transaction under 50ms (only insert order + order_items, no heavy computation) |

### Migration Impact

- **New column on `carts`**: `status` (VARCHAR, CHECK: `BROWSING`, `CHECKOUT`, `CONVERTED`, `EXPIRED`), `address_snapshot` (JSONB, nullable), `razorpay_order_id` (VARCHAR, nullable), `payment_status` (VARCHAR, nullable).
- **Remove**: The `checkout_sessions` table (if it was created per the proposal — it was never implemented, so nothing to remove).
- **Timeline**: Phase 1 (first 2 weeks, alongside cart activation).

### Operational Impact

- One fewer table to maintain (no checkout_sessions).
- Simpler migration story (extend existing carts table, no new table).
- Order table stays clean — only paid orders appear.

---

## Decision 3: Reservation Ownership — Inventory Bounded Context

### Final Decision

**Reservations are owned by the Inventory bounded context.** The `inventory_reservations` table (which already exists) is the source of truth for reservation state. The Cart holds a reference to the reservation (via a new `reservation_id` FK column on `carts`), but does not own the reservation's lifecycle.

### Why This Is the Best Choice

Reservations are an inventory concern, not a cart concern. The cart says "I want these items." The inventory system says "I will hold these items for you." The cart does not need to know HOW to reserve stock — it delegates to the inventory service.

**Existing infrastructure**: `Backend/app/modules/inventory/reservation_service.py` (1,079 lines) already implements:
- `reserve_items()` — reserves stock with FOR UPDATE locking
- `complete_order_reservations()` — transitions reserved → sold
- `release_order_reservations()` — frees reserved stock
- `expire_stale_reservations()` — background TTL enforcement
- `record_return()`, `record_restock()`, `record_adjustment()` — inventory lifecycle

This service is production-ready and correctly implements the stock formula: `available = stock - reserved - sold`.

**The cart's role**: The cart references a reservation ID. When the cart transitions from `CART` → `CHECKOUT`, it calls `reservation_service.reserve_items()`. When payment succeeds, the cart calls `reservation_service.complete_order_reservations()`. When payment fails, the cart calls `reservation_service.release_order_reservations()`.

**The reservation's role**: The reservation tracks: which user, which product/variant, quantity, expiry time, status. It does not know about the cart or the order — it only knows about inventory.

### Why the Alternatives Were Rejected

**Cart owns reservations**:
- The cart is a UI concern (what the customer sees). Reservations are a business concern (what the warehouse holds). Mixing them violates separation of concerns.
- If the cart is deleted (customer abandons), the reservation should NOT be automatically deleted — it should expire on TTL. If the cart owns the reservation, deleting the cart deletes the reservation, and stock is released prematurely.

**CheckoutSession owns reservations**:
- We eliminated CheckoutSession (Decision 2). This is moot.

**Order owns reservations**:
- Orders are created AFTER payment. Reservations are created BEFORE payment. The order cannot own something that predates it.
- The current system has this problem (reservation.order_id is set AFTER order creation), which is the root cause of the order-reparenting bug.

### Long-Term Trade-offs

| Concern | Impact | Mitigation |
|---|---|---|
| Cross-context dependency (Cart → Inventory) | Cart service must call Inventory service | Use domain events: cart publishes `CheckoutStarted`, inventory subscribes and creates reservation |
| Reservation TTL is independent of cart TTL | Cart can exist without reservation (expired) | Cart status reflects this: if reservation expired, cart reverts to BROWSING |
| Multiple reservations per user (if user has multiple carts) | Stock is held by multiple reservations | Partial unique constraint REMOVED (Decision from review); application-level dedup via SELECT FOR UPDATE |

### Migration Impact

- **New column on `carts`**: `reservation_id` (UUID FK → inventory_reservations, nullable). Set when cart transitions to CHECKOUT status.
- **No changes to `inventory_reservations`**. The table and service are already correct.
- **Timeline**: Phase 1 (first 2 weeks, alongside cart activation).

### Operational Impact

- None beyond what already exists. The reservation service and background expiry worker are already operational.

---

## Decision 4: Inventory Model — Mutable Counters + Append-Only Transaction Log

### Final Decision

**Mutable counters with an append-only transaction log.** Keep the existing `stock_quantity`, `reserved_quantity`, `sold_quantity` columns on `products` and `product_variants`. Keep the existing `inventory_transactions` table as the immutable audit log. Add the composite CHECK constraint as a safety net.

### Why This Is the Best Choice

The current implementation is correct and battle-tested. The `ReservationService` (1,079 lines) already implements all mutations with `SELECT FOR UPDATE` locking and transaction logging. The stock formula `available = stock - reserved - sold` is enforced consistently across:
- `products.available_stock` property
- `product_variants.available_stock` property
- `ReservationService._lock_stock_target()` (raw SQL)
- `InventoryTransaction` before/after snapshots

**Performance**: A single `SELECT ... FOR UPDATE` on the products row returns stock values in O(1). A pure event-sourced ledger would require `SUM(delta) GROUP BY product_id` over potentially millions of rows — O(n) on every stock check.

**Scale**: For a jewellery e-commerce platform with thousands of SKUs (not millions), the mutable counter approach is correct. The append-only transaction log provides the audit trail and temporal query capability that event sourcing offers, without the read performance penalty.

**Simplicity**: The team already understands this model. The `ReservationService` is well-documented and tested. Switching to event sourcing would require rewriting 1,079 lines of production code with a fundamentally different paradigm.

### Why the Alternatives Were Rejected

**Pure event-sourced ledger** (no mutable counters):
```
inventory_ledger: (product_id, variant_id, delta, reason, timestamp)
available = SUM(delta) WHERE timestamp <= now()
```
- O(n) reads on every stock check. At 100K transactions per SKU, this is a full table scan.
- Requires materialized views or periodic snapshots to be performant — which is just mutable counters with extra steps.
- The team has no event-sourcing experience. The learning curve is a project risk.
- Overkill for thousands of SKUs. Event sourcing is designed for systems with millions of entities and complex temporal queries (banks, ledgers, audit-heavy domains).

**Pure append-only with no counters**:
- Same O(n) read problem.
- Cannot enforce the `stock >= reserved + sold` invariant at the database level (must be derived from the ledger).
- CHECK constraints cannot reference a derived value from another table.

### Long-Term Trade-offs

| Concern | Impact | Mitigation |
|---|---|---|
| Counter drift from bugs | Stock values could diverge from reality | Composite CHECK constraint (Decision 7) catches drift at the DB level |
| No built-in temporal queries | "What was stock at 2pm?" requires scanning the transaction log | The `inventory_transactions` table already stores `before_available` / `after_available` — temporal queries are O(1) per row |
| Single-row contention under flash sales | Product row is locked for the duration of the mutation | Redis pre-check (Decision 6) reduces contention; row lock is <5ms |
| Audit log grows unboundedly | `inventory_transactions` table bloat | Partition by `created_at` quarterly; retain 2 years online, archive to cold storage |

### Migration Impact

- **New constraint**: `ALTER TABLE products ADD CONSTRAINT chk_inventory_invariant CHECK (stock_quantity >= reserved_quantity + sold_quantity) NOT VALID; ALTER TABLE products VALIDATE CONSTRAINT chk_inventory_invariant;`
- **Same constraint on `product_variants`**.
- **Timeline**: Phase 1 (first week — safe, non-blocking migration).

### Operational Impact

- Zero runtime impact. The constraint is checked on every UPDATE to the stock columns. If the invariant holds (which it should, given correct application logic), the constraint adds ~0.1ms per write.
- The `VALIDATE` step scans all rows but takes a `SHARE UPDATE EXCLUSIVE` lock (allows concurrent reads and writes). Safe for production.

---

## Decision 5: Event Architecture — Redis Streams (with Outbox for Critical Events)

### Final Decision

**Redis Streams** for cross-instance event delivery. **Transactional outbox pattern** for critical financial events (payment captured, order created, refund processed). The current in-process `asyncio.create_task` event bus is replaced entirely.

### Why This Is the Best Choice

The current in-process event bus (`Backend/app/core/events.py`) works for a single server but fails silently across multiple instances:
- Server A publishes `OrderCreatedEvent`. Server B never sees it.
- SSE connections on Server B receive no real-time updates for that order.
- The email notification listener on Server B never fires.

This is not a theoretical concern — it is a current production bug that will manifest the moment a second app server is deployed.

**Redis Streams** solve this because:
1. Events are stored in Redis (shared across all instances).
2. Consumer groups ensure each event is processed by exactly one consumer.
3. The existing Redis pub/sub for SSE can remain (it already works cross-instance).
4. No new infrastructure — Redis is already in the stack.
5. Persistent events — unlike pub/sub, events are not lost if no consumer is listening.

**Outbox pattern** for critical events:
- Financial events (payment captured, refund processed) are written to an `outbox_events` table within the same transaction as the business data.
- A background worker polls the outbox and publishes to Redis Streams.
- This guarantees at-least-once delivery even if Redis is temporarily unavailable.
- Non-critical events (product updated, collection changed) can skip the outbox and publish directly to Redis Streams.

### Why the Alternatives Were Rejected

**In-process asyncio.create_task (current)**:
- Does not scale to multiple instances. This is a non-starter for production.

**RabbitMQ**:
- Adds a new infrastructure component (RabbitMQ server).
- Requires ops expertise the team does not have.
- Overkill for the event volume (hundreds of events/day, not thousands/second).
- Redis Streams covers the same use case with zero additional infrastructure.

**Kafka**:
- Massively overkill for this scale. Kafka is designed for millions of events per second.
- Requires a Kafka cluster (3+ brokers minimum for production).
- Operational complexity is 10x that of Redis Streams.
- The team has no Kafka experience.

**Plain Redis pub/sub (current SSE layer)**:
- Fire-and-forget — events are lost if no consumer is listening.
- No consumer groups — every instance receives every event (no work distribution).
- No persistence — events vanish after delivery.
- Already used for SSE (which is fine for real-time UI updates), but not suitable for business logic events.

### Long-Term Trade-offs

| Concern | Impact | Mitigation |
|---|---|---|
| Redis becomes a critical dependency | Redis outage stops event delivery | Outbox pattern ensures events are persisted in Postgres; worker retries on Redis recovery |
| Consumer group lag | Events may be delayed under high load | Monitor consumer lag via `XINFO GROUPS`; alert if lag > 100 events |
| At-least-once delivery | Listeners must be idempotent | All listeners already use idempotency keys (razorpay_order_id, order_id uniqueness) |
| Redis memory for event streams | Streams grow unboundedly | `XTRIM MAXLEN ~10000` on each stream; retain last 10K events |

### Migration Impact

- **New table**: `outbox_events` (id, aggregate_type, aggregate_id, event_type, payload JSONB, created_at, published_at nullable).
- **New Redis streams**: `hadha:events:orders`, `hadha:events:inventory`, `hadha:events:payments`, `hadha:events:notifications`.
- **Replace**: `event_bus.publish()` calls with `redis.xadd()` for non-critical events, or insert into `outbox_events` for critical events.
- **New worker**: `OutboxPublisher` — polls `outbox_events` every 5 seconds, publishes unpublished events to Redis Streams, marks as published.
- **New worker**: `EventConsumer` — reads from Redis Streams, dispatches to domain handlers.
- **Timeline**: Phase 2 (weeks 3-4). The in-process bus continues to work for single-instance during Phase 1.

### Operational Impact

- Redis memory: ~10MB for 10K events per stream × 4 streams = ~40MB total. Negligible.
- One new Postgres table (`outbox_events`) with low write volume (only critical events).
- Two new background workers (outbox publisher + event consumer). Lightweight, <10MB RAM each.
- Monitoring: Redis `XINFO GROUPS` for consumer lag, outbox table row count for backlog.

---

## Decision 6: Concurrency Strategy — Redis Pre-Check + SELECT FOR UPDATE SKIP LOCKED

### Final Decision

**Two-layer concurrency control**:
1. **Redis stock pre-check** (fast path): Before entering a database transaction, check stock availability in Redis. If stock is zero, reject immediately without touching Postgres.
2. **SELECT FOR UPDATE SKIP LOCKED** (slow path): Inside the database transaction, lock the product row, verify stock, decrement `reserved_quantity`, insert reservation.

This is the Shopify/Medusa pattern. It handles flash sales (hundreds of concurrent users per SKU) without overwhelming the database.

### Why This Is the Best Choice

**The problem with pure database locking**:
Under flash-sale conditions (200+ concurrent users per SKU), `SELECT FOR UPDATE SKIP LOCKED` serializes all checkouts for that product. Each takes ~5ms (lock + read + write + commit). At 200 concurrent users, the last user waits ~1 second. At 1000 users, ~5 seconds. This is acceptable for normal traffic but becomes a bottleneck for flash sales.

**The Redis pre-check solves this**:
```
available = redis.get(f"stock:{product_id}:{variant_id}")
if available <= 0:
    return HTTP 409 "Out of stock"
# Proceed to database transaction
```

Redis `GET` is O(1) and handles 100K+ operations per second on a single instance. The pre-check eliminates ~80% of database contention under flash-sale conditions — only customers who pass the Redis check hit Postgres.

**Why not Redis-only (no database lock)?**
Redis is an in-memory cache. It can lose data on crash (depending on persistence config). The database is the source of truth. The Redis pre-check is an optimization, not a replacement. The `SELECT FOR UPDATE` in the database is the final safety net.

### Why the Alternatives Were Rejected

**Pure database locking (current approach)**:
- Works correctly but scales poorly above ~200 concurrent users per SKU.
- The proposal's own review identified this as a scalability ceiling.
- For a jewellery flash sale (limited edition pieces, high demand), this ceiling will be hit.

**Redis-only with no database lock**:
- Redis can lose data on crash (even with AOF persistence, there is a window).
- No audit trail (Redis does not have transaction logs).
- Cannot enforce the composite CHECK constraint (Redis does not support SQL constraints).
- Risk of oversell if Redis crashes between decrement and order creation.

**Optimistic locking (version column)**:
- Requires retry loop on conflict. Under high contention, retry storms waste CPU.
- Worse than `SKIP LOCKED` for write-heavy workloads (SKIP LOCKED avoids the retry entirely).
- Better for read-heavy workloads with occasional writes (not the case here).

### Long-Term Trade-offs

| Concern | Impact | Mitigation |
|---|---|---|
| Redis stock counter can drift from Postgres | Redis shows 0 stock, Postgres shows 2 | Periodic reconciliation job (every 5 minutes: sync Redis counter from Postgres `available_stock`) |
| Redis crash loses stock counters | Temporary oversell risk | Reconciliation job restores from Postgres; database lock prevents actual oversell |
| Two systems to monitor | Operational complexity | Dashboard showing Redis vs Postgres stock divergence; alert if divergence > 0 |
| Added latency for Redis call | ~2ms per checkout | Negligible; the database transaction is 10-50ms |

### Migration Impact

- **New Redis keys**: `stock:{product_id}` (integer, decremented on reserve, incremented on release/expire).
- **New utility**: `check_stock_redis(product_id, variant_id) -> int` — returns available stock from Redis.
- **New utility**: `sync_stock_redis()` — reconciliation job that reads Postgres `available_stock` and sets Redis counters.
- **Modification to `ReservationService.reserve_items()`**: Add Redis pre-check before the database transaction.
- **New worker**: `StockSyncWorker` — runs every 5 minutes, syncs Redis counters from Postgres.
- **Timeline**: Phase 2 (weeks 3-4). Phase 1 uses pure database locking (sufficient for pre-launch traffic).

### Operational Impact

- Redis memory: ~1 byte per SKU × 10K SKUs = ~10KB. Negligible.
- One new background worker (stock sync). Lightweight, runs every 5 minutes.
- Monitoring: Redis counter vs Postgres available_stock divergence. Alert threshold: >0 for any SKU.

---

## Decision 7: Checkout API — Two Endpoints

### Final Decision

**Two endpoints**:
1. `POST /checkout` — Validates cart, reserves stock, captures address, creates Razorpay order. Returns Razorpay order ID.
2. `POST /checkout/verify` — Verifies Razorpay payment signature, converts cart to order, fulfils stock (reserved → sold), sends confirmation.

### Why This Is the Best Choice

The four-endpoint model (create session → reserve → payment → verify) is over-decomposed. Each endpoint is an HTTP round trip with its own failure mode. Collapsing session creation and reservation into one call eliminates 25% of the failure surface and reduces pre-payment latency from ~500ms to ~250ms.

**The flow in detail**:

```
POST /checkout
  Input: { cart_id, address_snapshot, coupon_code? }
  Steps:
    1. Load cart + cart_items
    2. Validate cart is non-empty, all items are ACTIVE products
    3. Calculate totals (subtotal, tax, discount, total)
    4. If coupon_code: validate coupon, apply discount
    5. Call reservation_service.reserve_items(cart.items)
       → FOR UPDATE on products, decrement reserved_quantity, insert inventory_reservations
    6. Save address_snapshot on cart
    7. Create Razorpay order (razorpay.order.create)
    8. Save razorpay_order_id on cart
    9. Transition cart status: BROWSING → CHECKOUT
  Response: { razorpay_order_id, amount, currency }

POST /checkout/verify
  Input: { razorpay_order_id, razorpay_payment_id, razorpay_signature }
  Steps:
    1. Verify signature (HMAC SHA256)
    2. Load cart by razorpay_order_id
    3. Verify cart.status == CHECKOUT (idempotency: if CONVERTED, return existing order)
    4. Create order from cart (snapshot all data)
    5. Create order_items from cart_items
    6. Call reservation_service.complete_order_reservations(cart.reservation_id)
       → reserved_quantity -= qty, sold_quantity += qty
    7. Transition cart status: CHECKOUT → CONVERTED
    8. Publish OrderCreatedEvent
  Response: { order_id, order_number, status }
```

**Failure paths**:
- Step 5 fails (stock insufficient): Return 409. Cart stays BROWSING. No reservation created.
- Step 7 fails (Razorpay down): Return 500. Reservation exists but is held for 10 min TTL. Customer retries → cart is already CHECKOUT → skip to step 7.
- Step 2 in verify fails (invalid signature): Return 400. Cart stays CHECKOUT. Reservation held. Customer retries.
- Step 4 in verify fails (DB error): Return 500. Razorpay payment was captured but order not created. **Reconciliation job** (Decision 8) catches this.

### Why the Alternatives Were Rejected

**Four endpoints (proposal's original model)**:
- 4 HTTP round trips before Razorpay popup. Latency: ~500ms.
- Each endpoint is a separate failure mode.
- The "create session" step has no business value — a session without a reservation is meaningless.
- The proposal's own Section 5.3 recommends collapsing steps 1-2, which admits the four-endpoint model is over-decomposed.

**Single endpoint (checkout + payment in one call)**:
- The Razorpay popup is a client-side redirect/popup. The server cannot "include" the Razorpay popup in a single call.
- The server must return the Razorpay order ID first, then the frontend initializes the popup.
- Two calls are the minimum: one to prepare, one to verify.

### Long-Term Trade-offs

| Concern | Impact | Mitigation |
|---|---|---|
| Single endpoint does everything | Harder to test individual steps | Unit test each step in isolation; integration test the full flow |
| Address validation happens at checkout, not earlier | Customer sees address errors late | Add address validation endpoint (optional, Phase 2) |
| Coupon validation happens at checkout, not earlier | Customer sees coupon errors late | Validate coupon on apply (in cart), re-validate at checkout |

### Migration Impact

- **New endpoints**: `POST /checkout`, `POST /checkout/verify` (replacing the proposal's 4 endpoints).
- **New Pydantic schemas**: `CheckoutRequest`, `CheckoutResponse`, `CheckoutVerifyRequest`, `CheckoutVerifyResponse`.
- **New service method**: `CheckoutService.checkout(cart_id, address, coupon_code)`, `CheckoutService.verify(razorpay_order_id, payment_id, signature)`.
- **Timeline**: Phase 1 (first 2 weeks).

### Operational Impact

- Two new API routes. No new infrastructure.
- Rate limiting: `POST /checkout` at 10 req/min per user. `POST /checkout/verify` at 20 req/min per user (webhook retries increase volume).

---

## Decision 8: Database Constraints — Composite CHECK, Rate Limiting, Reconciliation

### Final Decision

**Mandatory constraints before production** (all Phase 1):

| Constraint | Table | Definition | Purpose |
|---|---|---|---|
| `chk_inventory_invariant` | `products` | `CHECK (stock_quantity >= reserved_quantity + sold_quantity)` | Prevents oversell at DB level |
| `chk_inventory_invariant` | `product_variants` | `CHECK (stock_quantity >= reserved_quantity + sold_quantity)` | Same, for variants |
| `chk_cart_status` | `carts` | `CHECK (status IN ('BROWSING','CHECKOUT','CONVERTED','EXPIRED'))` | Enforces cart state machine |
| `chk_reservation_status` | `inventory_reservations` | `CHECK (status IN ('ACTIVE','COMPLETED','RELEASED','EXPIRED'))` | Enforces reservation lifecycle |
| `uq_cart_razorpay_order` | `carts` | `UNIQUE (razorpay_order_id) WHERE razorpay_order_id IS NOT NULL` | Prevents duplicate payment |
| `uq_order_razorpay_order` | `orders` | `UNIQUE (razorpay_order_id)` | Prevents duplicate order creation |
| `uq_order_razorpay_payment` | `orders` | `UNIQUE (razorpay_payment_id)` | Prevents double-fulfillment |

**Rate limiting** (also Phase 1):

| Endpoint | Limit | Window | Purpose |
|---|---|---|---|
| `POST /checkout` | 10 | 60s | Prevent inventory hoarding |
| `POST /checkout/verify` | 20 | 60s | Accommodate webhook retries |
| `POST /cart/items` | 30 | 60s | Prevent cart manipulation abuse |

**Reconciliation** (Phase 1):

| Job | Frequency | Purpose |
|---|---|---|
| `PaymentReconciler` | Every 15 min | Compare Razorpay payments against fulfilled orders. Flag mismatches. |
| `StockReconciler` | Every 5 min (Phase 2) | Sync Redis stock counters with Postgres. |

### Why This Is the Best Choice

The composite CHECK constraint is the single most important safety net in the entire system. Without it, any application bug that sets `reserved_quantity > stock_quantity` silently corrupts data. With it, the database rejects the corrupt write and the application logs an error.

**The constraint MUST be Phase 1** — not Phase 2 as the original proposal suggested. The constraint is the database-level guarantee that the business logic is correct. Deferring it means shipping to production without the safety net.

**Rate limiting on checkout** is equally critical. Without it, a script can call `POST /checkout` 1000 times per second, reserving stock for 1000 carts, and holding all inventory hostage for 10 minutes. This is the inventory hoarding attack identified in the original audit.

**Payment reconciliation** is a financial compliance requirement. Without it, there is no way to detect and fix mismatched payments (paid but not fulfilled, fulfilled but not paid). This must be in production from day one.

### Why the Alternatives Were Rejected

**Deferring composite CHECK to Phase 2** (proposal's original plan):
- Ships to production without the safety net.
- Any application bug during Phase 1 can corrupt inventory data.
- The constraint is zero-cost to add (NOT VALID + VALIDATE is safe, non-blocking).

**No rate limiting on checkout** (current state):
- Inventory hoarding attack is trivially executable.
- A single script can hold all stock hostage for 10 minutes per run.
- This is the #1 attack vector for a limited-quantity e-commerce platform.

**Deferred reconciliation** (proposal's original plan):
- Financial mismatches accumulate during the deferral period.
- Manual reconciliation is error-prone and time-consuming.
- Automated reconciliation runs daily in most production systems; 15-minute intervals are conservative.

### Migration Impact

- **7 new constraints** (all NOT VALID + VALIDATE — safe, non-blocking).
- **3 new rate limit policies** in `Backend/app/middleware/rate_limit.py`.
- **1 new table**: `outbox_events` (for reconciliation events).
- **1 new worker**: `PaymentReconciler` (runs every 15 minutes).
- **Timeline**: All Phase 1 (first 2 weeks).

### Operational Impact

- Constraint validation: ~1-2 minutes on a table with 10K rows. Safe for production (SHARE UPDATE EXCLUSIVE lock).
- Rate limiter: Uses existing Redis sliding window. No new infrastructure.
- Reconciliation worker: ~10MB RAM, runs every 15 minutes. Negligible resource usage.

---

## Decision 9: Priority Matrix — What to Build When

### Phase 1: Foundation (Weeks 1-2) — BEFORE PRODUCTION

These are non-negotiable. The system cannot go live without them.

| # | Task | Rationale | Owner |
|---|---|---|---|
| 1 | Activate server-side cart (carts + cart_items) | Foundation for everything else | Backend |
| 2 | Add `status`, `address_snapshot`, `reservation_id`, `razorpay_order_id` columns to `carts` | Cart state machine + checkout flow | Backend |
| 3 | Implement `POST /checkout` endpoint | Core checkout flow | Backend |
| 4 | Implement `POST /checkout/verify` endpoint | Payment verification + order creation | Backend |
| 5 | Add composite CHECK constraints (products + product_variants) | Database safety net | Backend |
| 6 | Add rate limiting on checkout endpoints | Prevent inventory hoarding | Backend |
| 7 | Implement `PaymentReconciler` worker | Financial compliance | Backend |
| 8 | Add `cart_status` CHECK constraint | Enforce state machine | Backend |
| 9 | Replace localStorage cart with API calls | Frontend uses server cart | Frontend |
| 10 | Implement cart merge on login | Guest → authenticated transition | Frontend |
| 11 | Add optimistic cart UI (show "reserved" badge) | UX for reservation feedback | Frontend |

### Phase 2: Hardening (Weeks 3-4) — FIRST MONTH

These improve reliability and performance. Not blocking for launch, but should be done before the first flash sale.

| # | Task | Rationale | Owner |
|---|---|---|---|
| 12 | Migrate event bus to Redis Streams | Cross-instance event delivery | Backend |
| 13 | Implement outbox pattern for critical events | Guaranteed delivery | Backend |
| 14 | Add Redis stock pre-check | Flash sale readiness | Backend |
| 15 | Implement `StockSyncWorker` | Redis/Postgres stock reconciliation | Backend |
| 16 | Add guest checkout flow | ~30-40% of traffic | Backend + Frontend |
| 17 | Add product status check at fulfilment time | Prevent fulfilling discontinued products | Backend |
| 18 | Make reservation TTL configurable per product | Flash sale vs high-consideration items | Backend |
| 19 | Add cart TTL cleanup worker | Prevent orphaned cart accumulation | Backend |
| 20 | Add coupon locking during checkout | Prevent one-time coupon abuse | Backend |

### Phase 3: Scale (Months 2-3) — GROWTH

These are needed as traffic grows. Not needed at launch.

| # | Task | Rationale | Owner |
|---|---|---|---|
| 21 | Add exchange flow | Customer service improvement | Backend + Frontend |
| 22 | Add shipment splitting | Multi-item order fulfilment | Backend + Frontend |
| 23 | Add partial chargeback support | Financial operations | Backend |
| 24 | Add price change notification at payment time | Transparency for price fluctuations | Backend + Frontend |
| 25 | Add abandoned cart email recovery | Revenue recovery (5-15% conversion) | Backend + Marketing |
| 26 | Add cart analytics (add-to-cart rate, abandonment rate) | Business intelligence | Backend + Analytics |

### Phase 4: Future (Months 4+) — SCALE

These are needed at >10K orders/month or >100K products.

| # | Task | Rationale | Owner |
|---|---|---|---|
| 27 | Multi-warehouse inventory | Expansion to multiple warehouses | Backend |
| 28 | Inventory forecasting | Demand planning | Data |
| 29 | Sharded database (by region or product category) | Horizontal scale | Infrastructure |
| 30 | CDN for product catalog (edge caching) | Global latency | Infrastructure |

---

# Part B: Final Recommended Architecture

---

## High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CLIENT (React + Zustand)                       │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  Product  │  │   Cart   │  │ Checkout │  │  Orders  │  │ Account  │ │
│  │  Browser  │  │  (API)   │  │  (API)   │  │  (API)   │  │  (API)   │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │              │              │              │              │       │
│       └──────────────┴──────────────┴──────┬───────┴──────────────┘       │
│                                            │                            │
│                                    SSE (Real-time)                       │
└────────────────────────────────────────────┼────────────────────────────┘
                                             │
┌────────────────────────────────────────────┼────────────────────────────┐
│                         API GATEWAY (FastAPI + Nginx)                   │
│                                             │                            │
│  ┌──────────────────────────────────────────┴──────────────────────────┐│
│  │                        Rate Limiter (Redis)                         ││
│  │  checkout: 10/min │ cart: 30/min │ auth: 60/min │ verify: 20/min   ││
│  └──────────────────────────────────────────┬──────────────────────────┘│
│                                             │                            │
│  ┌──────────────────────────────────────────┴──────────────────────────┐│
│  │                     Authentication (JWT + Supabase)                 ││
│  └──────────────────────────────────────────┬──────────────────────────┘│
└─────────────────────────────────────────────┼───────────────────────────┘
                                              │
┌─────────────────────────────────────────────┼───────────────────────────┐
│                    APPLICATION SERVER (FastAPI)                         │
│                                              │                           │
│  ┌──────────────────────────────────────────┴──────────────────────────┐│
│  │                         ROUTER LAYER                                ││
│  │                                                                     ││
│  │  /products  /cart  /checkout  /orders  /payments  /returns  /admin  ││
│  └──────┬──────────┬──────────┬──────────┬──────────┬─────────────────┘│
│         │          │          │          │          │                     │
│  ┌──────┴───┐ ┌────┴────┐ ┌──┴───┐ ┌────┴────┐ ┌──┴──────┐           │
│  │ Catalog  │ │  Cart   │ │Check-│ │ Orders  │ │Inventory│           │
│  │ Service  │ │ Service │ │out   │ │ Service │ │ Service │           │
│  │          │ │         │ │Serv. │ │         │ │         │           │
│  └──────┬───┘ └────┬────┘ └──┬───┘ └────┬────┘ └──┬──────┘           │
│         │          │         │          │          │                     │
│  ┌──────┴──────────┴─────────┴──────────┴──────────┴──────────────────┐│
│  │                    DOMAIN EVENT BUS                                ││
│  │  Phase 1: asyncio.create_task (single instance)                    ││
│  │  Phase 2: Redis Streams (cross-instance)                           ││
│  │  Critical events: Transactional outbox → Postgres → Redis Streams  ││
│  └───────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────┬─────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                   │
              ┌─────┴─────┐   ┌──────┴──────┐   ┌──────┴──────┐
              │  POSTGRES  │   │    REDIS     │   │  RAZORPAY   │
              │            │   │              │   │             │
              │ orders     │   │ cache        │   │ orders      │
              │ carts      │   │ sessions     │   │ payments    │
              │ products   │   │ stock:SKU    │   │ refunds     │
              │ inventory  │   │ rate limits  │   │             │
              │ payments   │   │ events (S2)  │   │             │
              │ returns    │   │ cart cache   │   │             │
              │ outbox (S2)│   │              │   │             │
              └───────────┘   └──────────────┘   └─────────────┘
```

---

## Aggregate Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRODUCT CATALOG CONTEXT                       │
│                                                                  │
│  Aggregates:                                                     │
│    Product (root)                                                │
│      ├── ProductVariant (entity)                                 │
│      ├── ProductMedia (value object)                             │
│      ├── ProductAttribute (value object)                         │
│      └── Category (reference)                                    │
│                                                                  │
│  Tables: products, product_variants, product_attributes,         │
│          product_images, categories                              │
│                                                                  │
│  Ownership: Stock counters (stock_quantity, reserved_quantity,   │
│             sold_quantity) live on Product/Variant but are       │
│             mutated by the Inventory context.                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    INVENTORY CONTEXT                             │
│                                                                  │
│  Aggregates:                                                     │
│    InventoryReservation (root)                                   │
│      └── lifecycle: ACTIVE → COMPLETED | RELEASED | EXPIRED     │
│                                                                  │
│    InventoryTransaction (value object, append-only)              │
│      └── records every stock mutation with before/after snapshot │
│                                                                  │
│  Tables: inventory_reservations, inventory_transactions          │
│                                                                  │
│  Services: ReservationService                                    │
│    ├── reserve_items()                                           │
│    ├── complete_order_reservations()                             │
│    ├── release_order_reservations()                              │
│    ├── expire_stale_reservations() (background worker)           │
│    ├── record_return()                                           │
│    ├── record_restock()                                          │
│    └── record_adjustment()                                       │
│                                                                  │
│  External state: Stock counters on products/product_variants     │
│  (mutated by this context, owned by Catalog context)             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       CART CONTEXT                               │
│                                                                  │
│  Aggregates:                                                     │
│    Cart (root)                                                   │
│      ├── CartItem (entity)                                       │
│      ├── AddressSnapshot (value object, JSONB)                   │
│      └── CouponRef (value object)                                │
│                                                                  │
│  Tables: carts, cart_items                                       │
│                                                                  │
│  Status machine:                                                 │
│    BROWSING → CHECKOUT → CONVERTED                               │
│       ↓         ↓                                                 │
│    EXPIRED    EXPIRED (reservation TTL)                          │
│                                                                  │
│  Services: CartService                                           │
│    ├── get_or_create_cart()                                      │
│    ├── add_item() / update_item() / remove_item()                │
│    ├── apply_coupon() / remove_coupon()                          │
│    ├── start_checkout() → calls Inventory.reserve_items()        │
│    ├── complete_checkout() → calls Inventory.complete_*()        │
│    └── release_checkout() → calls Inventory.release_*()          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      ORDER CONTEXT                               │
│                                                                  │
│  Aggregates:                                                     │
│    Order (root)                                                  │
│      ├── OrderItem (entity, snapshot of product at purchase)     │
│      ├── OrderTimelineEntry (value object)                       │
│      └── OrderStatusHistory (value object)                       │
│                                                                  │
│  Tables: orders, order_items, order_status_history,              │
│          order_timeline_entries                                   │
│                                                                  │
│  Services: OrderService                                          │
│    ├── create_order_from_cart()                                  │
│    ├── update_order_status()                                     │
│    ├── cancel_order() → calls Inventory.release_*()              │
│    └── get_order_history()                                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     PAYMENT CONTEXT                              │
│                                                                  │
│  Aggregates:                                                     │
│    Payment (root)                                                │
│    Refund (entity)                                               │
│    Invoice (value object)                                        │
│                                                                  │
│  Tables: payments, refunds, invoices                             │
│                                                                  │
│  Services: PaymentService                                        │
│    ├── create_razorpay_order()                                   │
│    ├── verify_payment()                                          │
│    ├── initiate_refund()                                         │
│    └── reconcile_payments() (background worker)                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     RETURN CONTEXT                               │
│                                                                  │
│  Aggregates:                                                     │
│    Return (root)                                                 │
│      └── ReturnItem (entity)                                     │
│                                                                  │
│  Tables: returns, return_items                                   │
│                                                                  │
│  Services: ReturnService                                         │
│    ├── request_return()                                          │
│    ├── approve_return()                                          │
│    ├── receive_return() → calls Inventory.record_return()        │
│    └── process_refund() → calls Payment.initiate_refund()        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Cart → Reservation → Payment → Order → Fulfillment → Return → Refund

### Step 1: Add to Cart

```
Customer clicks "Add to Cart"
  │
  ├── Frontend: POST /cart/items { product_id, variant_id, quantity }
  │
  ├── CartService.add_item()
  │     ├── Check if cart exists for user (or create new)
  │     ├── Check if item already in cart (increment quantity)
  │     ├── Validate product is ACTIVE
  │     ├── Fetch current price from product
  │     └── INSERT cart_items (cart_id, product_id, variant_id, quantity, unit_price)
  │
  └── Response: { cart_id, items_count, subtotal }
```

### Step 2: Start Checkout

```
Customer clicks "Checkout"
  │
  ├── Frontend: POST /checkout { cart_id, address_snapshot, coupon_code? }
  │
  ├── CheckoutService.checkout()
  │     │
  │     ├── 1. Load cart + cart_items (FOR UPDATE)
  │     │
  │     ├── 2. Validate all items are ACTIVE products
  │     │
  │     ├── 3. [Redis pre-check] Check stock for each item
  │     │     └── redis.get(f"stock:{product_id}:{variant_id}")
  │     │         └── If <= 0: return 409 "Out of stock"
  │     │
  │     ├── 4. Calculate totals (subtotal, tax, discount, total)
  │     │
  │     ├── 5. If coupon_code: validate coupon, apply discount
  │     │
  │     ├── 6. reservation_service.reserve_items()
  │     │     │
  │     │     ├── FOR UPDATE on products WHERE id IN (product_ids)
  │     │     │   └── Lock order: sorted by (product_id, variant_id) to prevent deadlocks
  │     │     │
  │     │     ├── For each item:
  │     │     │   ├── Check: available_stock >= requested_qty
  │     │     │   ├── UPDATE products SET reserved_quantity += qty
  │     │     │   ├── INSERT inventory_reservations (user_id, product_id, variant_id, qty, expires_at)
  │     │     │   └── INSERT inventory_transactions (RESERVE, before/after snapshots)
  │     │     │
  │     │     └── Return: reservation_ids[]
  │     │
  │     ├── 7. Save address_snapshot on cart (JSONB)
  │     │
  │     ├── 8. razorpay_service.create_order(total_amount)
  │     │     └── POST https://api.razorpay.com/v1/orders
  │     │
  │     ├── 9. Save razorpay_order_id on cart
  │     │
  │     ├── 10. UPDATE carts SET status = 'CHECKOUT', reservation_id = ?, address_snapshot = ?
  │     │
  │     └── 11. Redis: decrement stock counter for each item
  │
  └── Response: { razorpay_order_id, amount, currency }
```

### Step 3: Payment (Razorpay Popup)

```
Frontend initializes Razorpay popup with razorpay_order_id
  │
  ├── Customer completes payment in Razorpay
  │
  └── Razorpay redirects to /checkout/verify with payment details
```

### Step 4: Verify Payment + Create Order

```
POST /checkout/verify { razorpay_order_id, razorpay_payment_id, razorpay_signature }
  │
  ├── CheckoutService.verify()
  │     │
  │     ├── 1. Verify signature: HMAC SHA256(order_id + "|" + payment_id, secret)
  │     │     └── If invalid: return 400 "Invalid payment signature"
  │     │
  │     ├── 2. Load cart by razorpay_order_id
  │     │     └── If cart.status == 'CONVERTED': return existing order (idempotent)
  │     │
  │     ├── 3. BEGIN TRANSACTION
  │     │     │
  │     │     ├── 4. Create order from cart
  │     │     │     ├── INSERT orders (user_id, status='confirmed', payment_status='paid',
  │     │     │     │   shipping_* fields from address_snapshot, subtotal, tax, discount, total,
  │     │     │     │   razorpay_order_id, razorpay_payment_id, coupon_code, coupon_id)
  │     │     │     └── RETURNING id, order_number
  │     │     │
  │     │     ├── 5. Create order_items from cart_items
  │     │     │     └── INSERT order_items (order_id, product_id, variant_id,
  │     │     │         product_name, product_sku, unit_price, quantity, tax_rate, tax_amount, line_total)
  │     │     │
  │     │     ├── 6. reservation_service.complete_order_reservations(order_id)
  │     │     │     ├── FOR UPDATE on inventory_reservations WHERE order_id = ? AND status = 'ACTIVE'
  │     │     │     ├── For each reservation:
  │     │     │     │   ├── UPDATE inventory_reservations SET status = 'COMPLETED'
  │     │     │     │   ├── UPDATE products SET reserved_quantity -= qty, sold_quantity += qty
  │     │     │     │   └── INSERT inventory_transactions (SALE, before/after)
  │     │     │     └── Return: completed reservation count
  │     │     │
  │     │     ├── 7. UPDATE carts SET status = 'CONVERTED'
  │     │     │
  │     │     ├── 8. Redis: increment sold counter for each item
  │     │     │
  │     │     └── 9. COMMIT
  │     │
  │     ├── 10. Publish OrderCreatedEvent
  │     │     └── [Phase 1: asyncio.create_task] [Phase 2: Redis Stream XADD]
  │     │
  │     └── 11. Return: { order_id, order_number, status }
  │
  └── Response: { order_id, order_number }
```

### Step 5: Fulfillment

```
Admin updates order status
  │
  ├── PUT /admin/orders/{order_id}/status { status: 'packed' }
  │
  ├── OrderService.update_order_status()
  │     ├── Validate status transition (pending → packed → dispatched → delivered)
  │     ├── UPDATE orders SET status = ?, packed_at = NOW()
  │     ├── INSERT order_status_history
  │     ├── INSERT fulfillment_timeline
  │     └── Publish OrderStatusChangedEvent
  │
  └── SSE: Real-time status update to customer
```

### Step 6: Return Request

```
Customer requests return
  │
  ├── POST /orders/{order_id}/returns { items: [{ order_item_id, quantity, reason }] }
  │
  ├── ReturnService.request_return()
  │     ├── Validate order is DELIVERED
  │     ├── Validate return window (30 days from delivered_at)
  │     ├── Validate requested qty <= purchased qty
  │     ├── INSERT returns (order_id, customer_id, reason, status='requested')
  │     └── INSERT return_items (return_id, order_item_id, quantity, reason)
  │
  └── Response: { return_id, status: 'requested' }
```

### Step 7: Return Processing (Admin)

```
Admin approves return and processes refund
  │
  ├── PUT /admin/returns/{return_id}/approve
  │
  ├── ReturnService.approve_return()
  │     ├── UPDATE returns SET status = 'approved'
  │     └── INSERT fulfillment_timeline
  │
  ├── Customer ships item back
  │
  ├── PUT /admin/returns/{return_id}/receive { received_qty: 2 }
  │
  ├── ReturnService.receive_return()
  │     ├── UPDATE return_items SET received_qty = 2
  │     ├── UPDATE returns SET status = 'received', received_at = NOW()
  │     │
  │     ├── FOR EACH returned item:
  │     │   └── reservation_service.record_return(product_id, variant_id, qty)
  │     │       ├── FOR UPDATE on products WHERE id = product_id
  │     │       ├── UPDATE products SET sold_quantity -= qty, stock_quantity += qty
  │     │       └── INSERT inventory_transactions (RETURN, before/after)
  │     │
  │     └── Publish ReturnReceivedEvent
  │
  ├── Admin processes refund
  │
  ├── POST /admin/returns/{return_id}/refund { amount, reason }
  │
  ├── ReturnService.process_refund()
  │     ├── payment_service.initiate_refund(payment_id, amount, reason)
  │     │   └── POST https://api.razorpay.com/v1/refunds
  │     ├── UPDATE refunds SET status = 'processed', razorpay_refund_id = ?
  │     ├── UPDATE orders SET payment_status = 'partially_refunded'
  │     └── Publish RefundProcessedEvent
  │
  └── SSE: Real-time refund status to customer
```

---

## Transaction Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRANSACTION 1: Reserve Stock                  │
│                                                                  │
│  BEGIN                                                           │
│    SELECT ... FROM products WHERE id IN (...) FOR UPDATE         │
│    UPDATE products SET reserved_quantity += qty                  │
│    INSERT INTO inventory_reservations (...)                      │
│    INSERT INTO inventory_transactions (...)                      │
│  COMMIT                                                          │
│                                                                  │
│  Duration: ~10-30ms                                              │
│  Lock: Product row (FOR UPDATE, exclusive)                       │
│  Contention: Serialized per product                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    TRANSACTION 2: Create Order                    │
│                                                                  │
│  BEGIN                                                           │
│    INSERT INTO orders (...)                                      │
│    INSERT INTO order_items (...)                                 │
│    SELECT ... FROM inventory_reservations WHERE order_id = ?     │
│      AND status = 'ACTIVE' FOR UPDATE                            │
│    UPDATE inventory_reservations SET status = 'COMPLETED'        │
│    UPDATE products SET reserved_quantity -= qty, sold += qty     │
│    INSERT INTO inventory_transactions (...)                      │
│    UPDATE carts SET status = 'CONVERTED'                         │
│  COMMIT                                                          │
│                                                                  │
│  Duration: ~20-50ms                                              │
│  Lock: Reservation rows (FOR UPDATE) + Product row (FOR UPDATE)  │
│  Contention: Low (each reservation is unique)                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    TRANSACTION 3: Release Stock (on failure)     │
│                                                                  │
│  BEGIN                                                           │
│    SELECT ... FROM inventory_reservations WHERE order_id = ?     │
│      AND status = 'ACTIVE' FOR UPDATE                            │
│    UPDATE inventory_reservations SET status = 'RELEASED'         │
│    UPDATE products SET reserved_quantity -= qty                   │
│    INSERT INTO inventory_transactions (...)                      │
│  COMMIT                                                          │
│                                                                  │
│  Duration: ~5-15ms                                               │
│  Lock: Reservation rows + Product row                            │
│  Contention: Low                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    TRANSACTION 4: Process Return                  │
│                                                                  │
│  BEGIN                                                           │
│    SELECT ... FROM inventory_reservations WHERE ... FOR UPDATE   │
│    UPDATE products SET sold_quantity -= qty, stock_quantity += qty│
│    INSERT INTO inventory_transactions (...)                      │
│  COMMIT                                                          │
│                                                                  │
│  Duration: ~5-15ms                                               │
│  Lock: Product row                                               │
│  Contention: Low (returns are infrequent)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Event Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 1: In-Process Events                    │
│                                                                  │
│  ReservationService.reserve_items()                              │
│    └── publish(ReservationCreatedEvent)                          │
│          ├── Listener: SendSSE(user_id, "reservation_created")   │
│          └── Listener: LogAnalytics("checkout_started")          │
│                                                                  │
│  CheckoutService.verify()                                        │
│    └── publish(OrderCreatedEvent)                                │
│          ├── Listener: SendSSE(user_id, "order_created")         │
│          ├── Listener: SendEmail(order_confirmation)             │
│          └── Listener: UpdateSearchIndex(order)                  │
│                                                                  │
│  ReturnService.receive_return()                                  │
│    └── publish(ReturnReceivedEvent)                              │
│          ├── Listener: SendSSE(user_id, "return_received")       │
│          └── Listener: NotifyAdmin("return_received")            │
│                                                                  │
│  ReturnService.process_refund()                                  │
│    └── publish(RefundProcessedEvent)                             │
│          ├── Listener: SendSSE(user_id, "refund_processed")      │
│          └── Listener: SendEmail(refund_confirmation)            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 2: Redis Streams                         │
│                                                                  │
│  [Same events as Phase 1, but delivered via Redis Streams]       │
│                                                                  │
│  Stream: hadha:events:orders                                     │
│    ├── Consumer Group: order-email-workers (1 consumer)          │
│    ├── Consumer Group: order-analytics-workers (1 consumer)      │
│    └── Consumer Group: order-sse-workers (N consumers)           │
│                                                                  │
│  Stream: hadha:events:inventory                                  │
│    ├── Consumer Group: inventory-cache-workers (N consumers)     │
│    └── Consumer Group: inventory-sse-workers (N consumers)       │
│                                                                  │
│  Stream: hadha:events:payments                                   │
│    ├── Consumer Group: payment-reconciliation (1 consumer)       │
│    └── Consumer Group: payment-sse-workers (N consumers)         │
│                                                                  │
│  Critical events (payment captured, refund processed):           │
│    ├── Write to outbox_events table (same transaction as business│
│    │   data write)                                               │
│    ├── OutboxPublisher polls every 5s, publishes to Redis Stream │
│    └── Guarantees at-least-once delivery even if Redis is down   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Database Ownership

| Table | Context | Purpose |
|---|---|---|
| `products` | Catalog | Product data + stock counters |
| `product_variants` | Catalog | Variant data + stock counters |
| `product_attributes` | Catalog | Product specifications |
| `categories` | Catalog | Category hierarchy |
| `carts` | Cart | Shopping cart + checkout state |
| `cart_items` | Cart | Cart line items |
| `inventory_reservations` | Inventory | Stock reservations with TTL |
| `inventory_transactions` | Inventory | Immutable audit log of all stock mutations |
| `orders` | Order | Confirmed orders (paid) |
| `order_items` | Order | Order line items (snapshots) |
| `order_status_history` | Order | Status change audit trail |
| `order_timeline_entries` | Order | Admin action history |
| `payments` | Payment | Razorpay payment records |
| `refunds` | Payment | Razorpay refund records |
| `invoices` | Payment | Invoice generation |
| `returns` | Return | Return requests |
| `return_items` | Return | Return line items |
| `fulfillment_timeline` | Fulfillment | Shipping/packing history |
| `outbox_events` | Infrastructure | Transactional outbox (Phase 2) |

---

## Cache Ownership

| Cache Key | TTL | Owner | Purpose |
|---|---|---|---|
| `product:{slug}` | 1 hour | Catalog | Product detail page |
| `products:list:{filters}` | 15 min | Catalog | Product listing |
| `stock:{product_id}:{variant_id}` | Real-time | Inventory | Flash sale pre-check |
| `cart:{user_id}` | 30 min | Cart | Cart data (read) |
| `cart:{session_id}` | 30 min | Cart | Guest cart data |
| `rate_limit:{ip}:{path}` | 60s | Infrastructure | Rate limiting |
| `session:{user_id}` | 24 hours | Auth | JWT session data |

---

## Worker Responsibilities

| Worker | Frequency | Purpose | Phase |
|---|---|---|---|
| `ReservationExpiryWorker` | Every 30s | Expire stale reservations, release stock | 1 |
| `PaymentReconciler` | Every 15 min | Compare Razorpay payments vs orders, flag mismatches | 1 |
| `CartCleanupWorker` | Daily | Delete carts older than 7 days | 1 |
| `StockSyncWorker` | Every 5 min | Sync Redis stock counters from Postgres | 2 |
| `OutboxPublisher` | Every 5s | Publish outbox events to Redis Streams | 2 |
| `EventConsumer` | Real-time | Process Redis Stream events, dispatch to handlers | 2 |
| `EmailWorker` | Real-time | Send transactional emails (order confirmation, refund) | 1 |
| `SSEBroadcaster` | Real-time | Push real-time updates to connected clients | 1 |

---

## Failure Recovery Strategy

### Reservation Expiry (TTL)

**Scenario**: Customer starts checkout, stock is reserved, but customer abandons checkout.

**Recovery**: `ReservationExpiryWorker` runs every 30 seconds. Finds reservations where `expires_at < NOW()` and `status = 'ACTIVE'`. Transitions to `EXPIRED`, decrements `reserved_quantity`, publishes `ReservationExpiredEvent`. Cart reverts to `BROWSING` status.

**Guarantee**: Stock is held for at most 10 minutes (configurable per product). No manual intervention needed.

### Payment Captured, Order Not Created

**Scenario**: Razorpay payment succeeds, but `POST /checkout/verify` fails (DB error, server crash).

**Recovery**: `PaymentReconciler` runs every 15 minutes. Queries Razorpay for captured payments in the last hour. Checks if each `razorpay_order_id` has a corresponding order. If not:
1. Sends alert to ops team.
2. Attempts to create the order from the cart data.
3. If cart data is unavailable, flags for manual resolution.

**Guarantee**: No payment is lost. Mismatches are detected within 15 minutes.

### Stock Counter Drift

**Scenario**: Redis stock counter shows 0, but Postgres shows 2 (Redis crash lost a decrement).

**Recovery**: `StockSyncWorker` runs every 5 minutes. Reads `available_stock` from Postgres for all active products. Sets Redis counters to match. Logs any divergence.

**Guarantee**: Stock counters are accurate within 5 minutes. The database lock prevents actual oversell even if Redis is wrong.

### Order Cancellation After Payment

**Scenario**: Customer pays, order is created, but item is out of stock (race condition).

**Recovery**: This should not happen with the two-phase approach (reserve → pay → convert). But if it does:
1. Admin cancels order via admin panel.
2. `OrderService.cancel_order()` calls `reservation_service.release_order_reservations()`.
3. Stock is released (reserved → available).
4. `PaymentService.initiate_refund()` processes full refund.
5. Customer receives refund within 5-7 business days.

**Guarantee**: Stock is always released on cancellation. Refund is always processed.

### Redis Outage

**Scenario**: Redis crashes. No cache, no rate limiting, no SSE, no event delivery.

**Recovery**: Application falls back to:
1. **Cart**: Direct Postgres reads (slower, but functional).
2. **Rate limiting**: Fails open (no rate limiting during outage).
3. **SSE**: No real-time updates (polling fallback).
4. **Events**: In-process asyncio.create_task continues (single-instance fallback).
5. **Stock pre-check**: Skipped (database lock handles contention).

**Guarantee**: Application remains functional during Redis outage. No data loss. Performance degrades but does not fail.

### Database Outage

**Scenario**: Postgres crashes. No reads, no writes.

**Recovery**: Application returns 503 Service Unavailable. No data loss (all transactions are committed before response). Recovery is automatic when Postgres restarts.

**Guarantee**: No data corruption. Application is unavailable during outage but recovers cleanly.

### Razorpay Outage

**Scenario**: Razorpay API is down. Cannot create orders or verify payments.

**Recovery**: `POST /checkout` fails at step 8 (Razorpay order creation). Reservation exists but is held for 10-minute TTL. Customer sees "Payment service temporarily unavailable. Please try again in a few minutes." If customer retries within 10 minutes, the existing reservation is reused (idempotent via `razorpay_order_id`).

**Guarantee**: Stock is held during the outage (not released prematurely). Customer can retry without losing their reservation.

---

# Part C: Production Readiness Checklist

---

## Must Implement Before Production (Phase 1)

These are non-negotiable. The system cannot go live without them. Every item in this list is a blocking requirement.

### Checkout Flow

- [ ] **Activate server-side cart** — `carts` + `cart_items` tables exist but are unused. Build the CartService and API endpoints (`GET/POST/PUT/DELETE /cart/items`).
- [ ] **Add cart state machine** — Add `status` column to `carts` with CHECK constraint: `BROWSING`, `CHECKOUT`, `CONVERTED`, `EXPIRED`.
- [ ] **Add `address_snapshot` JSONB column to `carts`** — Captures shipping address at checkout time.
- [ ] **Add `reservation_id` FK column to `carts`** — Links cart to inventory reservation.
- [ ] **Add `razorpay_order_id` column to `carts`** — Links cart to Razorpay order for idempotency.
- [ ] **Implement `POST /checkout`** — Validates cart, reserves stock, captures address, creates Razorpay order. Returns `razorpay_order_id`.
- [ ] **Implement `POST /checkout/verify`** — Verifies payment signature, creates order from cart, converts reservation to sale.
- [ ] **Implement idempotency** — If `razorpay_order_id` already exists on a CONVERTED cart, return the existing order (do not create a duplicate).
- [ ] **Implement retry logic** — If `POST /checkout` fails at Razorpay step, cart stays CHECKOUT. Customer retries → reuse existing reservation.

### Inventory Safety

- [ ] **Add composite CHECK constraint on `products`** — `CHECK (stock_quantity >= reserved_quantity + sold_quantity)` using `NOT VALID` + `VALIDATE`.
- [ ] **Add same constraint on `product_variants`** — Identical invariant for variants.
- [ ] **Add rate limiting on `POST /checkout`** — 10 requests per minute per user. Prevents inventory hoarding.
- [ ] **Add rate limiting on `POST /cart/items`** — 30 requests per minute per user.
- [ ] **Add rate limiting on `POST /checkout/verify`** — 20 requests per minute per user (webhook retries).

### Payment Integrity

- [ ] **Implement `PaymentReconciler` worker** — Runs every 15 minutes. Compares Razorpay captured payments against orders. Flags mismatches. Attempts auto-recovery.
- [ ] **Add UNIQUE constraint on `carts.razorpay_order_id`** (partial: WHERE razorpay_order_id IS NOT NULL).
- [ ] **Add UNIQUE constraint on `orders.razorpay_order_id`**.
- [ ] **Add UNIQUE constraint on `orders.razorpay_payment_id`**.
- [ ] **Add payment failure handling** — If verification fails, cart stays CHECKOUT. Reservation held. Customer can retry.

### Frontend

- [ ] **Replace localStorage cart with API calls** — All cart operations go through the server-side cart API.
- [ ] **Implement cart merge on login** — When guest logs in, merge anonymous cart into user cart.
- [ ] **Show reservation status in cart UI** — "Reserved for 8:42" countdown timer.
- [ ] **Handle out-of-stock at checkout** — Show clear error message, suggest alternatives.
- [ ] **Handle payment failure gracefully** — Show retry button, preserve cart state.

### Background Workers

- [ ] **`ReservationExpiryWorker`** — Runs every 30 seconds. Expires stale reservations. Releases stock. Publishes `ReservationExpiredEvent`.
- [ ] **`CartCleanupWorker`** — Runs daily. Deletes carts older than 7 days with status `BROWSING` or `EXPIRED`.
- [ ] **`EmailWorker`** — Sends order confirmation, refund confirmation, return status emails.

### Monitoring

- [ ] **Checkout success rate** — Alert if <95% over 5-minute window.
- [ ] **Reservation expiry rate** — Alert if >20% of reservations expire (indicates high abandonment or slow checkout).
- [ ] **Payment reconciliation mismatches** — Alert on any mismatch detected by `PaymentReconciler`.
- [ ] **Stock divergence** — Log when Redis counter differs from Postgres (Phase 2, but logging should be in place from Phase 1).

---

## Should Implement Within First 3 Months (Phase 2)

These improve reliability, performance, and user experience. Not blocking for launch, but should be done before the first flash sale or marketing push.

### Event Architecture

- [ ] **Migrate event bus to Redis Streams** — Replace `asyncio.create_task` with Redis Stream `XADD` for cross-instance event delivery.
- [ ] **Implement outbox pattern** — Critical events (payment captured, refund processed) written to `outbox_events` table within the same transaction. `OutboxPublisher` polls and publishes to Redis Streams.
- [ ] **Implement `EventConsumer` worker** — Reads from Redis Streams, dispatches to domain handlers. Consumer groups ensure each event is processed by exactly one consumer.

### Flash Sale Readiness

- [ ] **Add Redis stock pre-check** — Before entering database transaction, check `redis.get(f"stock:{product_id}")`. If <=0, reject immediately.
- [ ] **Implement `StockSyncWorker`** — Runs every 5 minutes. Syncs Redis stock counters from Postgres `available_stock`. Logs divergence.
- [ ] **Make reservation TTL configurable per product** — Add `checkout_ttl_minutes` column to `products` (default: 10). Flash sale items: 5 min. High-value items: 15 min.

### Guest Checkout

- [ ] **Implement `POST /checkout/guest`** — Guest provides email. System creates anonymous session. After payment, creates user account with email.
- [ ] **Guest cart persistence** — Cart stored by `session_id` (UUID cookie). Merges on account creation.

### Coupon Integrity

- [ ] **Add coupon locking** — When coupon is applied at checkout, decrement usage count. Restore on session expiry or cancellation.
- [ ] **Re-validate coupon at payment time** — If coupon expired between cart and payment, remove discount and notify customer.

### Product Safety

- [ ] **Add product status check at fulfilment** — In `POST /checkout/verify`, check `product.status`. If discontinued, fail verification and refund payment.
- [ ] **Add price change notification** — In `POST /checkout`, compare reservation price with current price. If different, return warning to frontend.

### Cart Analytics

- [ ] **Track add-to-cart events** — Product, quantity, user, timestamp.
- [ ] **Track cart abandonment** — Cart created but not converted within 24 hours.
- [ ] **Track checkout funnel** — Cart → Checkout → Payment → Conversion rates.

---

## Future Scalability Improvements (Phase 3+)

These are needed as the business grows. Not needed at launch.

### Operations

- [ ] **Abandoned cart email recovery** — Send reminder email 1 hour and 24 hours after abandonment. Include direct link to restored cart.
- [ ] **Exchange flow** — Customer returns item A, exchanges for item B. Reserve item B, process return for A, adjust refund for price difference.
- [ ] **Shipment splitting** — Multi-item orders where items ship from different locations. Separate tracking per shipment.
- [ ] **Partial chargeback support** — Chargeback on individual items, not full order. Restock returned items.

### Scale

- [ ] **Multi-warehouse inventory** — Add `warehouse_id` to inventory tables. Allocation logic selects optimal warehouse.
- [ ] **Inventory forecasting** — Use historical sales data to predict stock needs. Auto-reorder triggers.
- [ ] **Sharded database** — Split by product category or region when >100K products or >10K orders/month.
- [ ] **CDN for product catalog** — Edge caching for product images and static data. Reduces origin load.

### Intelligence

- [ ] **Dynamic pricing** — Adjust prices based on demand, time of day, inventory levels.
- [ ] **Personalized recommendations** — "Customers who bought this also bought..." powered by purchase history.
- [ ] **Fraud detection** — ML model to detect fraudulent orders before fulfilment.

---

# End of Architecture Document

> **This document is the definitive blueprint.** Engineering implements this. No further architecture debates.
>
> **Questions?** Reference Part A (Decisions) for rationale. Reference Part B (Architecture) for implementation details. Reference Part C (Checklist) for what to build and when.
>
> **Sign-off**: Principal Architect, July 2026.
