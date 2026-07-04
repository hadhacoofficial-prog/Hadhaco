# Hadha.co Database Architecture & Performance Audit

**Date:** 2026-07-03
**Scope:** Full PostgreSQL/SQLAlchemy audit — schema, migrations, repositories, transactions, inventory concurrency, CMS/cart/checkout query flow.
**Method:** Read-only static analysis of `Backend/app/modules/*` (23 modules), `Backend/alembic/versions/*` (19-20 migrations), `Backend/supabase/sql/*`. No code was modified.

---

## Executive summary

| Area | Critical | High | Medium | Low |
|---|---|---|---|---|
| Schema & migrations | 8 | 16 | 13 | 12 |
| Repository query performance | 5 | 6 | 16 | 17 |
| Transactions & inventory concurrency | 1 | 3 | 5 | 2 |
| CMS / cart / checkout query flow | 5 | 7 | 7 | 3 |

### Architectural finding that reframes the whole schema section

A third independent schema pass converged on the same root cause as the first two, but sharpened it: the live Postgres schema (`supabase/sql/*.sql`) is genuinely well-built — proper FKs, CHECK constraints, triggers, partitioning, indexes — but the **SQLAlchemy ORM models substantially under-declare that reality**, and in a few cases actively diverge from it in ways that break at runtime (not just "missing docs"). Concretely: `analytics_events` and `audit_logs` are range-partitioned by `created_at` in production (`PRIMARY KEY (id, created_at)`), but both ORM models declare `id` alone as the primary key — meaning `session.get()` by id and any ORM-level identity/merge logic against these two tables operates on a false premise. Separately, `audit_logs` has six live columns (`actor_email`, `actor_role`, `old_value`, `new_value`, `request_id`, `source`) with zero representation in the ORM model, so ORM-driven audit writes can never populate them. And the monthly partition-creation worker calls a Postgres function that only exists via manual `supabase/sql/022_triggers.sql` — no Alembic migration creates it, so any environment stood up purely via `alembic upgrade head` (fresh CI, disaster recovery) is missing it and the worker crashes monthly. See Section 1, findings C5-C8, for detail.

### Top 10 issues to fix first (ranked by blast radius × ease)

1. **Duplicate/divergent payment-verification path** (`payments/service.py::verify_and_capture`) can confirm+pay an order without completing its inventory reservation, risking oversold stock and status corruption on paid orders. *(Transactions #5 — Critical)*
2. **Admin reviews list is a 151-query N+1** (`reviews/service.py::list_all_reviews` re-fetches every row individually after an already-complete batched query). *(Repo #2 / CMS-flow #12 — Critical)*
3. **Checkout order-number generation race** (`COUNT ... LIKE 'prefix%'` then format) can produce duplicate order numbers or mid-checkout `IntegrityError` after stock is already reserved. *(Transactions #1, Schema H8/H9, Repo #7 — High/Critical, found independently by 3 agents)*
4. **Checkout holds row locks + DB transaction open across the Razorpay HTTP call**, and across N sequential product-lookup/lock round trips per cart item — the single highest lock-contention risk in the codebase, worst exactly during flash-sale-style concurrent demand. *(Transactions #2, CMS-flow #1/#2/#10 — High/Critical)*
5. **Redis `KEYS` (not `SCAN`) inside the per-item reservation loop** — up to ~45 blocking full-keyspace scans on a 5-item checkout, contending with every other Redis consumer. *(Repo #1, CMS-flow #2/#10 — Critical/High)*
6. **No non-negative CHECK constraints on any money or stock-quantity column schema-wide** — negative price/stock is prevented only by application code, nowhere in the database. *(Schema C4 / M6/M7 — Critical)*
7. **Coupon usage-limit and per-user-limit checks have a TOCTOU race** — concurrent redemptions can exceed a hard usage cap or let a user redeem a "one-time" coupon twice. *(Transactions #8 — High)*
8. **`updated_at` never actually updates on 11+ tables** (CMS, notifications, returns, support, reviews) because `onupdate=` was omitted — column silently freezes at creation time forever. *(Schema M4 — Medium but high-value quick fix)*
9. **Missing GIN/trigram indexes**: product search (`ILIKE` on name/sku/description) ignores the existing `search_vector` GIN index entirely; coupon JSONB eligibility columns have no GIN index at all. *(Repo #4, CMS-flow #5, Schema M8 — Critical/Medium)*
10. **Homepage/CMS section builder N+1**: ~13 sequential queries (1 + 1-per-section) on every cache-miss homepage render, hitting hardest exactly during cache-stampede after an admin publish. *(CMS-flow #3/#11, Repo #15 — Critical/High)*

---

## Section 1 — Schema & Migrations

*Two independent audits were run against the schema/migrations; findings below are merged and deduplicated. Where both audits independently found the same issue, that is noted (it raises confidence).*

**Key structural fact:** the initial ~15 tables are NOT created by Alembic — they come from raw SQL in `Backend/supabase/sql/*.sql` (`setup.sql` + numbered includes), with `0001_baseline` as an intentional Alembic no-op that must be `alembic stamp`-ed onto a DB provisioned by those SQL files. Alembic only governs incremental schema changes from `0002` onward. This dual-ownership setup is itself the root cause of several findings below (model/DB drift, constraints declared in only one place).

**A third independent pass confirmed and sharpened this: the live Postgres schema (via `supabase/sql/`) is comprehensive — proper FKs, CHECK constraints, triggers, partitioning — but the SQLAlchemy ORM models substantially under-declare that reality.** Read the findings below with that lens: several "missing index/FK" items likely already exist in the live database; the ORM's ignorance of them is itself the bug (type-unsafe queries, `session.get()` failures, autogenerate hazards, spurious `DROP CONSTRAINT` proposals). The newly surfaced items below (C5-C8) are additive, not duplicates.

**C5. `analytics_events` and `audit_logs` are range-partitioned by `created_at` in the live schema (`PRIMARY KEY (id, created_at)`), but the ORM models declare `id` as the sole primary key**
`supabase/sql/011_analytics.sql:23`, `supabase/sql/013_audit_logs.sql:22` vs. `app/modules/analytics/models.py:15-17`, `app/modules/audit/models.py:14-16`. Postgres requires the partition key in every unique/PK constraint on a partitioned table — the ORM's false belief that `id` alone is unique means `session.get(AuditLog, id)`/`session.get(AnalyticsEvent, id)` generates a query with no partition-pruning hint (scans all partitions), and any ORM-level identity-map/merge/upsert logic built against these models operates on an incorrect key shape.
*Fix:* add `created_at` to the ORM PK declaration on both models, or explicitly document/enforce these two tables as insert-only from the ORM with a repository-layer guard against single-column lookups.

**C6. `audit_logs` — six live columns are entirely absent from the ORM model, and `source` has a NOT-NULL CHECK-constrained default the ORM can't set correctly**
`supabase/sql/013_audit_logs.sql:5-23` (`actor_email`, `actor_role`, `old_value` JSONB, `new_value` JSONB, `request_id`, `source TEXT NOT NULL DEFAULT 'api' CHECK (source IN ('api','webhook','system','worker'))`) vs. `app/modules/audit/models.py:11-33` — model has only `actor_id`, `action`, `resource_type`, `resource_id`, `meta`, `ip_address`, `user_agent`, `created_at`. Also `resource_id`/`actor_id` are `UUID` with a real FK in SQL but `String(36)` with no FK in the model.
*Impact:* ORM-driven audit writes can never populate `old_value`/`new_value`/`request_id`, defeating the point of an audit trail; every ORM insert silently mislabels `source='api'` even for worker/webhook-originated writes, since the ORM doesn't know the column exists to set it correctly.
*Fix:* regenerate `AuditLog` from the live schema; fix `actor_id`/`resource_id` types to native `UUID`.

**C7. The monthly partition-creation worker depends on a Postgres function that no Alembic migration creates — `alembic upgrade head` alone cannot stand up a working environment**
`app/workers/partition_manager.py:27` (`SELECT create_analytics_partition(:d)`) — the function is defined only in `supabase/sql/022_triggers.sql:44`; no Alembic migration creates it, the `create_analytics_partition` function, or the partitioned `analytics_events`/`audit_logs` tables themselves.
*Impact:* any environment provisioned purely via `alembic upgrade head` (fresh CI database, disaster-recovery restore that only replays Alembic) is missing these tables/function entirely — the worker crashes monthly with `function create_analytics_partition(date) does not exist`, and any ORM write to `AnalyticsEvent`/`AuditLog` fails with `relation "analytics_events" does not exist`.
*Fix:* either formally adopt `supabase/sql/` as sole source of truth with a scripted, documented bootstrap (not manual), or port the partitioned-table DDL and function into a real Alembic migration.

**C8. `coupon_usages.order_id` has zero FK constraint despite participating in a real relational unique constraint (confirms H2 from the first schema pass, independently re-derived)**
Same finding as the first audit's H6, re-confirmed independently — see above.

### Critical

**C1. Dual schema ownership — no single source of truth**
`alembic/versions/0001_baseline.py`. Two independently-evolving definitions of the schema exist (`supabase/sql/*.sql` and `app/modules/*/models.py`); nothing enforces they stay in sync, and Alembic autogenerate can never be trusted against the ~15-table baseline.
*Impact:* new-environment bootstrap depends on manually running `setup.sql` then `alembic stamp 0001_baseline` in the right order; schema drift between SQL and models is undetectable by tooling.
*Fix:* generate a real Alembic baseline reflecting true initial DDL and retire the manual SQL step, or add a CI check diffing `alembic autogenerate` output against `setup.sql`.

**C2. `returns`/`return_items`/`support_tickets`/`support_messages` FKs have no `ondelete`**
`app/modules/returns/models.py:18-23,62-63`, `app/modules/support/models.py:19-24,56-58`. `returns.order_id`, `returns.customer_id`, `return_items.order_item_id`, `support_tickets.customer_id`/`order_id`, `support_messages.sender_id` all default to Postgres `NO ACTION`, unlike every other order/profile-adjacent FK in the schema which explicitly declares `RESTRICT`/`CASCADE`/`SET NULL`.
*Impact:* deleting an order/profile that has an associated return or support ticket fails with a raw, uncontrolled FK-violation error instead of a clean 409/422; blocks GDPR-style profile erasure wherever a support ticket exists.
*Fix:* add explicit `ondelete="RESTRICT"` (orders/profiles → matches existing convention) or `SET NULL` (order_id on tickets) via a new migration; these tables live only in `setup.sql` and have never been touched by an Alembic migration, compounding C1.

**C3. `coupons_status_check` CHECK constraint declared in the ORM model but never created in the database**
`app/modules/coupons/models.py:135-138` vs `alembic/versions/0017_coupon_rule_engine.py` (adds the `status` column but never issues `create_check_constraint`). Genuine model/DB drift — nothing stops `coupons.status` from holding an arbitrary string in production today, despite the model appearing to guarantee otherwise.
*Fix:* new migration: `op.create_check_constraint("coupons_status_check", "coupons", "status IN ('active','inactive','draft')")`.

**C4. No non-negative CHECK constraints on any money or quantity column, schema-wide**
Confirmed by both schema audits across `products` (`base_price`, `stock_quantity`, `reserved_quantity`, `sold_quantity`), `product_variants`, `orders`/`order_items` (`subtotal`, `total`, `unit_price`, `quantity`), `cart_items`, `payments`/`refunds` (`amount`). Only `coupons.value` has a `> 0` check anywhere in the schema; `order_items.quantity > 0` and `orders_payment_status_check` exist in the live DB via `setup.sql` but are **invisible to the ORM model** (so `Base.metadata.create_all()` — used in tests / fresh dev DBs — won't recreate them, and any future model-driven migration risks silently dropping them).
*Impact:* a service-layer arithmetic bug (e.g. reservation double-decrement, refund exceeding payment) can write negative stock or negative money with zero DB-level backstop — the `available_stock = max(..., 0)` clamp in `Product` is itself a signal this has already been a known risk.
*Fix:* add `CheckConstraint(... >= 0)` to every money/quantity column in a dedicated migration; add the two DB-only constraints (`order_items.quantity`, `orders.payment_status`) to the ORM model to close the drift.

### High

- **H1.** `coupons_percentage_max` CHECK (`coupon_type != 'percentage' OR value <= 100`) exists in `supabase/sql/009_coupons.sql` but has no counterpart in the ORM model — same drift pattern as C3/C4.
- **H2.** `fulfillment_timeline.actor_id` FK (`profiles.id`, `SET NULL`) has no supporting index; every "actions by admin X" query and every profile-delete cascade scans the whole table.
- **H3.** `support_tickets.customer_id`, `support_tickets.order_id`, `support_messages.sender_id` — confirmed **not indexed** in either the model or the live DB. `returns`/`return_items` FK columns *are* indexed in `setup.sql` but the ORM model doesn't declare it (model-only drift).
- **H4.** Three overlapping indexes lead with `orders.user_id` (`idx_orders_user_id`, `idx_orders_user_created(user_id, created_at)`, `idx_orders_user_status(user_id, status)`) — the single-column index is fully redundant once either composite exists; triples write-amplification on the highest-value, highest-write table in the schema for no read benefit.
- **H5.** `returns.status` CHECK constraint exists in `setup.sql` but is missing from the model; model also uses Python-side `default=` instead of `server_default=`, meaning raw-SQL/bulk inserts bypass the default entirely.
- **H6.** `returns.refund_id` is a bare UUID column with **no FK** to `refunds.id` — an unconstrained reference to financial reconciliation data. `coupon_usages.order_id` has the same gap despite participating in a `UniqueConstraint("coupon_id", "order_id")`.
- **H7.** `products.average_rating`/`review_count` are denormalized cache columns recalculated only by specific service-layer code paths, with no DB trigger and no scheduled reconciliation against the authoritative `product_rating_summary` VIEW — silent staleness risk if any code path (bulk admin op, direct SQL fix, partial-commit failure) bypasses the exact service method.
- **H8/H9.** `orders.status`/`fulfillment_status`/`shipping_provider` enforcement lives entirely in migration-only raw-SQL CHECK constraints (rewritten twice — `0006` then `0007`, because the first list was incomplete) with **zero trace in the model** of what values are legal; high risk of the next status-migration forgetting an in-use value, as already happened once.
- **H10.** `cms_section_items.section_id` / `cms_version_history.section_id` — migration creates a real `ForeignKey(..., ondelete="CASCADE")`, but the ORM model declares them as bare UUID with no `ForeignKey`/`relationship()` at all — DB enforces integrity correctly, ORM has no knowledge of it (breaks cascade-aware loading, causes spurious autogenerate diffs).
- **H11.** `analytics_events`, `fraud_signals`, `notification_logs` — `user_id`/`product_id`/`order_id`-shaped columns with zero FK constraints anywhere; may be an intentional volume tradeoff but is undocumented as such.
- **H12.** ORM models are broadly missing CHECK constraints that the live `supabase/sql` schema enforces — confirmed by spot-check on `Product` (`base_price>0`, `stock_quantity>=0`, `gender IN (...)`, `status IN (...)` all present in `002_catalog.sql` but absent from the model), `Return.status`, `SupportTicket.category/status/priority`, `FraudSignal.signal_type/severity`. Same drift category as C3/C4/H1, confirmed independently by a third pass across a different set of tables — treat as a systemic pattern, not isolated incidents.
- **H13.** ORM models are broadly missing `Index()` declarations that the live schema has — confirmed by spot-check on `Review` (no index on `product_id`/`user_id`/`order_id`/`is_approved` despite `idx_reviews_product_approved` existing live), `Return`/`ReturnItem`, `SupportTicket`/`SupportMessage`, `AnalyticsEvent`, `FraudSignal`, `NotificationLog`. Same impact class as H2/H3: any ORM-driven schema build (tests, ephemeral CI) is materially slower and less correct than production, and the model actively hides which indexes are safe to assume exist.
- **H14.** Seven FK columns have no `ondelete=` in *both* the ORM model and the live SQL (a genuine DB-level gap, not just ORM drift, cross-checked directly against `supabase/sql`): `categories.parent_id` (self-referential), `returns.order_id`/`customer_id`, `return_items.order_item_id`, `support_tickets.customer_id`/`order_id`, `support_messages.sender_id`. All default to Postgres `NO ACTION`. Since `profiles.id` is CASCADE-configured from many other tables, a customer-deletion workflow will fail unpredictably depending on which of these tables happens to hold rows for that customer.
- **H15.** `inventory_reservations.variant_id` and `inventory_movements.created_by` — the only two FK columns on these two hot-path tables without an index, while every sibling FK column (`product_id`, `order_id`, `user_id`, `reservation_id`) is indexed. Breaks "how much of variant X is reserved" and "show all stock adjustments by admin Y" queries as the tables grow.
- **H16.** `orders.coupon_id` has no index despite `orders` being the highest-traffic table in the system and having 6 other indexed columns in `__table_args__` — any "orders that used coupon X" / coupon-performance query scans the full table.

### Medium (highlights — see full detail in source agent transcripts if needed)

- **M1.** `company_config` is the only Integer-PK table in a 100%-UUID-PK schema (singleton config table — defensible but undocumented).
- **M2/M3.** Inconsistent enum-enforcement strategy: `inventory_*` uses real Postgres ENUM types; `orders`/`coupons` use CHECK constraints; `returns`/`support_tickets`/`fraud_signals`/`payments`/`refunds`/`webhook_events` status columns have **no DB-level protection at all**.
- **M4. `updated_at` never actually updates on 11+ tables** — `cms_*`, `notifications_*`, `returns`, `support_tickets`, `reviews` all use `default=lambda: datetime.now(UTC)` with **no `onupdate=`**, meaning the column is stamped once at creation and frozen forever despite the name implying it tracks last modification. This is a functional bug, not just style — admin UIs/audit trails showing "last updated" for reviews, tickets, returns, or CMS content are reading stale data unconditionally. **Cheapest high-value fix in this entire audit.**
- **M5.** No GIN indexes on any of `coupons`' 13 JSONB eligibility columns despite them being the obvious target of checkout-time containment queries; `webhook_events.payload` stored as `Text` instead of `JSONB`.
- **M6.** `Product.gender`/`metal_type` are free-text with no CHECK, despite the frontend enforcing a fixed literal union for gender elsewhere in the codebase (per project convention).
- **M7.** `0017_coupon_rule_engine` downgrade drops columns without reconciling `is_active` for coupons whose `status` became `'draft'` post-upgrade — a rollback data-loss bug (low practical likelihood, real if exercised).
- **M8.** No cross-row invariant (trigger/reconciliation) prevents `SUM(refunds.amount) > payments.amount` for a given payment — a double-refund race has zero DB-level backstop.
- **M9.** `updated_at` on `cms`/`notifications`/`fraud`/`analytics`/`returns`/`support`/`settings`/`reviews` models uses a Python-side `default=` with no `onupdate=` (matches Section 1's M4 finding) — but a third pass found the live SQL for several of these tables (`024_returns.sql`, `017_support.sql`, `002_catalog.sql`) actually maintains `updated_at` via a Postgres trigger (`set_updated_at()`). So the mechanism likely works correctly in production, but the ORM model **documents it incorrectly** — reads as a plain client-side default, hiding that a DB trigger is doing the real work. Anyone reasoning about update semantics from the model alone will draw the wrong conclusion. Recommend adding a comment noting trigger-backed columns explicitly, or removing the misleading Python default.
- **M10.** No partial unique index prevents multiple `is_default = true` addresses per user (`user_addresses.is_default`) — a race between two concurrent "set as default" requests can leave two default addresses for one user, and any `.filter(is_default=True).one()` call will raise `MultipleResultsFound`.
- **M11.** `products.max_order_quantity` has `server_default="0"` — a semantically dangerous default for a "max quantity" column unless `0` is deliberately special-cased as "unlimited" everywhere it's read (verify in `orders/service.py`/`cart/service.py`); if not, every new product is unpurchasable until an admin manually sets a real value.
- **M12.** `Review.images`/`Review.votes`, `Return.items`, `SupportTicket.messages` relationships have no `cascade="all, delete-orphan"` (unlike `Cart.items`, `Order.items`, `Wishlist.items`, `Product.variants`, `Shipment.events`, which all specify it). The DB-level `ON DELETE CASCADE` on the child FK covers raw deletes, but in-memory collection manipulation (`review.images.remove(img)`) won't delete the DB row without the ORM-level cascade — silent orphan risk from ORM-only code paths.
- **M13.** `fulfillment_timeline.details` uses plain `JSON` instead of `JSONB`, inconsistent with every other JSON-typed column in the codebase (coupons' 13 restriction columns, CMS config/snapshot, support attachments, analytics/fraud metadata all use `JSONB`) — not indexable, no containment-query support.

### Low

- Naming conventions (plural snake_case tables, `<table>_id` FK columns) are consistent schema-wide — no issues found.
- `AuditLog.actor_id`/`resource_id` stored as `String(36)` instead of native `UUID` (inconsistent, possibly intentional for non-UUID resource refs).
- `metadata`-equivalent columns use four different Python aliases across modules (`event_metadata`, `metadata_`, `extra_meta`, `meta`) for the same underlying pattern — pure ergonomics.
- Migration `0008` bundles an unrelated Alembic-internals fix (`alembic_version.version_num` widened to VARCHAR(255)) inside a "add tracking_url to shipments" migration — works, but hurts discoverability.
- `0002_profiles_fk` downgrade re-points FKs to `auth.users`, which will fail outside the original Supabase environment.
- `product_variants.sku` (and `invoices.order_id`, `wishlists.user_id`) each declare both `unique=True` and a separate explicit `Index(...)` on the same column — Postgres materializes two redundant indexes per column (the unique constraint already creates one).
- `orders` has three composite indexes all leading with `user_id` or `created_at` created across two different sources (Alembic `0003` and `supabase/sql/020_indexes.sql`) — worth a `pg_stat_user_indexes` check on the live DB to confirm all three are actually chosen by the planner before assuming they're all needed.
- `profiles.email` is unbounded `String` with no length cap, inconsistent with every other `String(...)` column in the codebase which specifies an explicit length.

### FK columns confirmed to lack an index (ORM-level; live-DB status noted where cross-checked)

| Table | Column | Target | Indexed in ORM? | Indexed live (supabase/sql)? |
|---|---|---|---|---|
| orders | coupon_id | coupons.id | No | Not confirmed — verify |
| inventory_reservations | variant_id | product_variants.id | No | Not confirmed — verify |
| inventory_movements | created_by | profiles.id | No | Not confirmed — verify |
| cms_section_items / cms_version_history | section_id | landing_sections.id (no FK declared at all in ORM) | No | **Yes** — ORM lacks both the FK and the index |
| returns | order_id, customer_id | orders.id, profiles.id | No | Yes |
| return_items | order_item_id | order_items.id | No | Yes |
| support_tickets | customer_id, order_id | profiles.id, orders.id | No | customer_id/created_at/status yes; order_id not confirmed |
| support_messages | sender_id | profiles.id | No | Not confirmed |
| coupon_usages | order_id | orders.id (no FK at all) | No | Not confirmed |
| analytics_events | user_id, product_id, category_id, order_id | (none FK'd in ORM) | No | user_id/product_id yes; category_id/order_id not confirmed |
| fraud_signals | user_id, resolved_by | profiles.id (neither FK'd in ORM) | No | user_id yes; resolved_by not confirmed |
| notification_logs | user_id | profiles.id (no FK in ORM) | No | Yes |

*Follow-up recommended: a dedicated pass diffing every `app/modules/*/models.py` column-by-column against its corresponding `supabase/sql/0NN_*.sql` file — every module spot-checked by this audit turned up real drift, so unchecked modules likely have more.*

---

## Section 2 — Repository Query Performance

*Scope: all 23 `app/modules/*/repository.py` files.*

### Critical

**R1. Redis `KEYS` pattern scan inside the per-item checkout/reservation loop**
`inventory/reservation_service.py` — `reserve_items`, `complete_order_reservations`, `release_order_reservations`, `expire_stale_reservations` → `_invalidate_inventory_cache`. `redis.keys(pattern)` is O(N) over the entire keyspace and **blocks the Redis server**; called ~9 times per line item. A 5-item checkout issues ~45 blocking `KEYS` scans plus 5 `SELECT FOR UPDATE` + 5 `UPDATE` + 5 flushes, repeated again at fulfillment.
*Fix:* `scan_iter()` instead of `keys()`; collect affected product/variant IDs and invalidate cache once per checkout, not once per item.

**R2. Admin review list — raw-SQL fetch, then per-row ORM refetch (151 queries for 50 rows)**
`reviews/repository.py::list_all` (raw SQL, returns full rows + `product_name`) followed by `reviews/service.py::list_all_reviews` looping and calling `get_by_id` per row (which itself triggers 2 more `selectin` batched queries for images+votes). `1 + 50×3 ≈ 151` queries per admin page load; scales linearly with page size, up to 200 at max page size.
*Fix:* single ORM query with `.join(Product)` for `product_name` and `.options(selectinload(Review.images))`; delete the refetch loop entirely.

**R3. Non-sargable `created_at::date` predicate across all 4 analytics dashboard queries**
`analytics/repository.py::get_dashboard`, `get_revenue_by_day`, `get_orders_by_status`, `get_top_products` all cast the indexed `created_at` column (`WHERE created_at::date BETWEEN ...`), defeating any btree index and forcing a sequential scan on `orders`, run sequentially (not concurrently) on every dashboard load.
*Fix:* rewrite as sargable range predicates (`created_at >= :from AND created_at < :to + interval '1 day'`); run the 4 independent queries via `asyncio.gather`.

**R4. Product search ignores the existing `search_vector` GIN index, uses 3-column leading-wildcard `ILIKE` instead**
`catalog/repository.py::list_paginated` — `or_(Product.name.ilike(term), Product.sku.ilike(term), Product.description.ilike(term))`, run twice per request (once for count, once for data). The model already has `search_vector` (TSVECTOR) with a GIN index that this method never uses.
*Fix:* `Product.search_vector.match(search)` against the existing index. Expected 10-100x improvement at 10k+ products.

**R5. Webhook handler swallows exceptions after partial writes, then commits everything together**
`webhooks/service.py::handle_razorpay`/`_record_event`/`_mark_failed` — if payment-captured processing fails partway (e.g. after payment update succeeds but reservation completion throws), the exception is caught, `_mark_failed` runs in the *same still-open transaction*, and both partial-success and failure-record commit together. Webhook returns HTTP 200 regardless, so Razorpay never retries — a payment can be marked "captured" while order confirmation/reservation completion silently never happened.
*Fix:* wrap per-branch processing in `db.begin_nested()` (SAVEPOINT) so a failed handler's partial writes roll back before the failure record commits.

### High

- **R6.** `collections/repository.py::add_products`/`reorder_products` — one INSERT/UPDATE per product ID in a loop instead of a single multi-row statement (~200 round trips for 200 products).
- **R7. COUNT-then-increment ID generators race under concurrency** — `orders/repository.py::generate_order_number`, `payments/repository.py::generate_invoice_number`, `support/repository.py::next_ticket_number` all read a `COUNT(...)` then format `+1`; two concurrent requests can read the same count and collide. `next_ticket_number` additionally has no year-scoping — full-table COUNT on every single ticket, forever. *(Independently confirmed by the transactions audit, see Section 3 #1.)*
- **R8.** Coupon checkout path re-fetches the same coupon row by code twice — once inside `validate()`, once again immediately after in `validate_with_email_check`/`apply_and_reserve` purely to read fields already available on the first result.
- **R9. Systemic UPDATE-then-full-reSELECT pattern** across `orders`, `payments`, `shipping`, `addresses`, `profiles`, `catalog` repositories' `update()` methods — every mutation does `UPDATE` then a full re-`SELECT` (with eager loads re-triggered in orders/shipping/catalog). Callers frequently already hold the loaded entity from moments earlier. **This is the single highest-frequency issue in the codebase** — it touches nearly every state-transition endpoint (order status change, payment capture, shipment update, address/profile edit, product edit).
  *Fix:* adopt `UPDATE ... RETURNING` (native in SQLAlchemy 2.0) project-wide, or mutate the already-loaded entity and `flush()`.
- **R10.** Review image upload holds the DB transaction open across up to 5 sequential external storage HTTP calls before committing — ties up a DB connection for the full upload duration under the project's constrained 8-slot connection budget.
- **R11.** `notifications/repository.py::get_pending_retries` — no `LIMIT`, no index on `(status, next_retry_at)`; sequential scan on every worker poll cycle, unbounded batch size on a provider-outage backlog spike.

### Medium (selected — 16 total findings)

- Cart mutation methods (`add_item`/`update_item`/`remove_item`/`clear`/`merge_guest_cart`) reload the *entire* cart after every single write — 2 extra SELECTs beyond the mutation itself on the hottest storefront endpoint (add-to-cart).
- `cart/repository.py::merge_guest_into_user` — N+1 upsert loop over guest cart items at login-merge time; should be one bulk `INSERT ... ON CONFLICT ... DO UPDATE`.
- Order-item insert loop during checkout — one `INSERT`+`flush()` per line item instead of `db.add_all()` + one flush.
- CMS `list_sections_with_items` (admin, **uncached**) pays the same N+1 as the homepage builder on *every single request*, not just cache-miss.
- `shipping/repository.py` unconditionally eager-loads `Shipment.events` on every read, even for call sites that never touch it.
- `catalog/repository.py::_base_query` always loads images+variants+attributes even for pure existence checks (`add_variant`, `upsert_attribute`, `delete`, `adjust_stock`).
- `categories/repository.py::list_admin` aggregates product counts over the *entire* products table on every admin page load, regardless of page size.
- `collections/repository.py::get_products_in_collection` — **correctness bug**: the COUNT query omits the `deleted_at IS NULL` filter that the data query applies, overcounting pagination totals whenever a linked product is soft-deleted.
- `payments`/`shipping` `create()` calls `db.refresh()` after `flush()` even when no server-generated field is consumed downstream — 1 avoidable round trip in the checkout hot path.
- `notifications/service.py::retry_pending` refetches the notification template once per log instead of once per distinct `(event_type, channel)` pair — 200 queries where 3 would do.
- `notifications/repository.py::upsert_preferences` — SELECT-then-branch instead of native `INSERT ... ON CONFLICT`, despite a `unique=True` constraint that supports it directly.
- `wishlist/service.py` — every add/remove/toggle fetches the full wishlist+items twice within one request.
- `reviews/service.py::vote`/`admin_action`/`admin_delete` — full entity load triggers 2 unused `selectin` relationships (images, votes) when only status fields are needed.
- `returns/repository.py::list_for_customer` — unbounded result set, no supporting index on `customer_id`/`created_at`.
- `audit/repository.py::list_paginated` — exact `COUNT(*)` + OFFSET on an ever-growing append-only table; switch to keyset pagination.
- `support/repository.py::list_all`, `returns/repository.py::list_all` — OFFSET pagination with no supporting index on `created_at`.

### Low (17 findings — full list retained for reference)
Style-only local imports; `cart::upsert_item` loading a full entity just to increment quantity; admin order search using leading-wildcard ILIKE on `order_number`; unbounded `inventory::get_low_stock` raw-SQL view query; unvalidated `sort_by` via `getattr()` in catalog/profiles list endpoints (permits sorting on unindexed columns); `categories::has_children` using `COUNT(*)` instead of `EXISTS`; `webhooks::_record_event` loading a full row (including a `payload` Text column) just for an idempotency check; `wishlist::get_or_create` doing an extra SELECT-after-refresh round trip on first-ever creation; `reviews::upsert_vote`/`_sync_helpful_count` at 4 round trips per vote (acceptable tradeoff, flagged for completeness).

### Positive patterns confirmed (no action needed)
`orders::get_by_id` correctly uses `selectinload`; `catalog::get_collections_for_products` correctly batches via `IN` clause; `catalog::adjust_stock` is a correct atomic `UPDATE ... RETURNING`; `settings::upsert_flag` uses correct native upsert; `support` model's `lazy="selectin"` on `messages` correctly batches; `notifications::send_email`/`send_sms` correctly commits *before* the external I/O call (contrast with R10); session handling (flush vs. commit/rollback ownership) is consistently correct across all 23 repository files — no leaks or premature commits found anywhere except the webhook handler (R5).

---

## Section 3 — Transactions, Inventory Concurrency & Payment Safety

*Scope: `inventory/{service,reservation_service,repository,models}.py`, `orders/{service,repository,models}.py`, `cart/{service,repository}.py`, `payments/{service,router}.py`, `coupons/{service,repository,models}.py`, `app/workers/*`, `app/core/database.py`.*

**Isolation level:** no explicit `isolation_level` is set on either engine — both use Postgres's default **READ COMMITTED**. This is the correct choice *given* the codebase's reliance on explicit `SELECT ... FOR UPDATE` pessimistic locking, but it means every new read-then-write on a shared counter must remember to take a row lock — READ COMMITTED provides no automatic protection against lost updates (this is the root cause of findings #1 and #4 below).

### Critical

**T1. Duplicate/divergent payment-verification path skips inventory reservation completion**
`payments/service.py::verify_and_capture` marks an order `confirmed`/`paid` and fires `PaymentCapturedEvent`, but **never calls `_reservation_svc.complete_order_reservations`** — unlike the parallel, correct implementation in `orders/service.py::verify_and_fulfill`. If both endpoints are reachable in the live checkout flow (needs confirmation against router wiring), a paid order's stock reservation stays in `ACTIVE` status, the 10-minute expiry worker will forcibly release it and flip the order to `payment_expired` — corrupting an already-paid order and freeing its inventory for the next customer to buy (double-sell risk).
*Fix:* remove/deprecate this duplicate path if unused, or make it delegate to `verify_and_fulfill` rather than reimplementing the same critical state transition.

### High

**T2. Order-number generation race (count-then-format, not atomic)**
`orders/repository.py::generate_order_number` — `SELECT COUNT(...) WHERE order_number LIKE 'prefix%'` then `seq+1`. Two concurrent checkouts in the same period can both read the same count and generate identical order numbers, either producing silent duplicates or an `IntegrityError` deep inside `create_payment_intent` *after* stock has already been reserved — leaving a reservation orphaned until the 10-minute expiry. *(Independently found by the repository audit, Section 2 R7 — three total confirmations across audits.)*
*Fix:* Postgres `SEQUENCE` or `SELECT ... FOR UPDATE` against a dedicated counter row.

**T3. Checkout holds row locks + open transaction across the Razorpay HTTP call**
`orders/service.py::create_payment_intent` — `reserve_items` takes `FOR UPDATE` locks on every cart line item's product/variant row and never commits before the outbound Razorpay HTTP call executes (hundreds of ms to seconds, or a hang on timeout). Any other concurrent checkout or admin stock adjustment touching the *same* product blocks for the full external-call duration — worst exactly during flash-sale-style contention on hot SKUs, and risks exhausting the project's small (~8-slot) connection pool.
*Fix:* split into (a) commit reservation + order in `stock_reserved` status (releasing locks), (b) call Razorpay outside any open transaction, (c) short second transaction to attach the Razorpay order id.

**T4. Coupon usage-limit and per-user-limit checks have a TOCTOU race**
`coupons/service.py::validate`/`apply_and_reserve` — the `usage_count >= usage_limit` check and `get_user_usage_count` (for one-time-per-customer coupons) both read a plain unlocked `SELECT`. Two concurrent checkouts can both pass the check before either commits, oversubscribing a capped promo or letting a user redeem a "one time" coupon twice — no unique constraint on `(coupon_id, user_id)` prevents the second case (the existing `UniqueConstraint("coupon_id", "order_id")` doesn't help since `order_id` is `NULL` at apply time for both racing rows).
*Fix:* `SELECT ... FOR UPDATE` on the coupon row before checking `usage_count` (mirroring the inventory locking pattern); add a partial unique index `(coupon_id, user_id) WHERE order_id IS NULL` for the per-user case.

### Medium

- **T5.** Reservation release-on-Razorpay-failure (`create_payment_intent`'s exception handler) is not explicitly committed before the `ValidationError` is raised — if the outer `get_db` dependency's generic rollback fires first, the release itself can be undone, leaving stock locked for the full 10-minute TTL after a failed checkout the customer was told to retry.
- **T6.** No idempotency guard on the `payments` table insert inside `verify_and_fulfill` — a double-submit/retry race (frontend retry racing a webhook) can insert two payment rows for one order, since the inner reservation-completion guard is idempotent but the payment insert is not.
- **T7. No consistent lock ordering across products in multi-item checkouts** — `reserve_items` locks rows in cart-iteration order with no sort; two customers whose carts share 2+ products in reversed order can deadlock (Postgres detects and aborts one side after ~1s, surfacing as a checkout 500).
  *Fix:* one-line sort by `(product_id, variant_id)` before the locking loop.
- **T8. `finalize_usage`'s coupon-usage `UPDATE` has no rowcount check and can silently stamp multiple rows** if the TOCTOU race in T4 has already created two pending usage rows for the same coupon+user — data-integrity risk for usage-limit reporting.
- **T9.** Connection pool is small (documented 8-slot budget across 2 workers) — this materially raises the stakes of T3; a handful of slow/hung Razorpay calls can exhaust the pool entirely.

### Low / Informational

- **T10.** The reservation service's core locking pattern (`_lock_stock_target`, `reserve_items`, `complete_order_reservations`, `expire_stale_reservations` using `FOR UPDATE SKIP LOCKED`) is **correctly implemented** and should be treated as the reference pattern for any new stock-mutating code — this is the strongest part of the codebase from a concurrency standpoint.
- **T11.** Isolation-level choice (READ COMMITTED + explicit locking) is appropriate but undocumented; recommend a code comment near `engine = create_async_engine(...)` codifying the "any counter mutation needs `FOR UPDATE`" rule as a review checklist item.

---

## Section 4 — CMS / Homepage / Cart / Checkout / Catalog Query Flow

*Scope: request-flow tracing from router → service → repository for CMS homepage, cart, checkout/orders, and catalog/categories/collections/search.*

### Critical

**F1. N+1 raw-SQL query per cart line item during checkout**
`orders/service.py::_resolve_line_items` loops over every cart item issuing one raw query (with a correlated image subquery) per item. A 5-item cart = 5 sequential round trips here alone, plus 5 more in reservation locking (F2) = 10+ round trips before any write happens.
*Fix:* batch fetch with `WHERE p.id = ANY(:pids)`, replace the correlated image subquery with a window-function join.

**F2. N+1 row-lock loop in stock reservation** — see Section 3 T3 and Section 2 R1 (same root cause, confirmed independently by three audits: sequential per-item locking plus the Redis `KEYS` scan issue).

**F3. CMS homepage builder N+1 across ~12 sections (cache-miss path)**
`cms/service.py::_build_homepage` loops over active sections calling `get_items_for_section` once per section — 1 + ~12 = 13 sequential round trips on every cache miss, which is exactly when concurrent homepage requests are likely to hit a cold cache simultaneously (thundering herd after any admin publish/toggle/reorder).
*Fix:* single query with `section_id.in_([...])`, group in Python.

**F4. Unbounded `list_collections` — no pagination, no cache, on a public storefront endpoint**
`collections/router.py` → `service.py::list_active` → `repository.py::list_active` has no `LIMIT` at all and, unlike `/products` and `/categories/navbar`, no Redis caching layer — the weakest-protected high-QPS endpoint found in this audit.

**F5. Missing trigram indexes — every `ILIKE '%term%'` search is a sequential scan**
`pg_trgm` extension is enabled but no `gin_trgm_ops` indexes exist anywhere. Affects `catalog::list_paginated`, `search::full_text_search` fallback and `autocomplete`, `categories::list_admin`, `collections::list_admin`. Autocomplete fires per keystroke — the highest-QPS path hitting the unindexed scan. *(Same root issue as Section 2 R4.)*

### High

- **F6.** Product pricing/stock is fetched via 3-4 independently maintained raw-SQL copies across cart-add → checkout (`cart::_fetch_product_price`/`_fetch_available_stock`, `orders::_resolve_line_items`, reservation locking) — these can and do drift (e.g. `tax_rate` only exists in the orders copy).
- **F7.** Homepage rails (featured/new-arrival/best-seller) each independently call `/products`, tripling to up to 9 queries + 3 uncoordinated Redis lookups on cache miss where 1 aggregate call would do; the 3 underlying boolean flag columns (`is_featured` etc.) have no index.
- **F8.** `get_collections_for_products` join runs unconditionally on every `/products` call, including the lightweight homepage rails that never render collection badges.
- **F9.** Product detail page does 5 sequential round trips for one entity (base query + 3 selectinloads + a hand-rolled 5th query for collections) — collapsible to 2-3 with `joinedload` for small relations and folding collections into the main relationship load.
- **F10.** Redis `KEYS` in the reservation loop — see F2/T3/R1.
- **F11.** CMS admin `list_sections_with_items` has the identical N+1 as F3, but **uncached** — pays it on every single admin request, not just cache miss.
- **F12.** Admin `list_all_reviews` — see Section 2 R2 (same finding, confirmed by 2 independent audits: up to 200 extra per-row queries on a single admin page load).

### Medium

- Coupon row is re-fetched a second time inside checkout total computation purely to read `coupon_type`, duplicating T4/R8's already-loaded data.
- Cart and Orders compute tax via two independently maintained formulas (`cart` uses a flat 3% fallback constant; `orders` uses real per-item `tax_rate`) — a correctness/consistency risk, not just performance: the cart-displayed total can visibly disagree with the final order total.
- Order line-item insert loop — one `INSERT`+`flush()` per item (same as Section 2 finding).
- Admin `update()` methods across categories/collections/catalog each do 3-4 lookups for one write (existence check, optional slug-conflict check, blind UPDATE, re-fetch) — same root pattern as Section 2 R9.
- Correlated `primary_image` subquery per row in category/collection product listings scans all of a product's images per row because `product_images.is_primary` has no partial index.
- Catalog list view eager-loads full variant rows (all columns) solely to sum stock in a Python model property — should be a SQL `SUM()` aggregate instead.
- Legacy `/cms/home` endpoint fires 2 sequential near-duplicate banner queries where one unfiltered query partitioned in Python would do (verify this endpoint isn't dead code first).

### Low

- `generate_order_number`'s scan cost is currently low (small table) but carries the T2/R7 race regardless.
- `/categories` (plain tree endpoint) isn't cached while its sibling `/categories/navbar` is, despite querying the identical underlying data.
- Cart items carry only a price/quantity snapshot with no batched product display-data hydration — the frontend must resolve name/image per item separately; fixable via an `IN`-clause batch fetch already used elsewhere in `catalog/repository.py`.

### Verified — good patterns, no action needed
`orders::list_for_user`/`list_all` (correct pagination + correlated subquery for item counts, no N+1); `orders::get_by_id` (single clean `selectinload`, no unrelated joins); `categories::_build_tree` (single flat query + in-memory tree build, correctly avoids the recursive-CTE-vs-N+1 tradeoff entirely); `reviews` rating aggregation (SQL `AVG()`/`COUNT() FILTER`, not Python summation); `catalog::list_products` collections hydration is batched via `IN` (see F8 for "is it needed at all," not an N+1 concern).

---

## Cross-cutting recommendations, ranked by leverage

1. **Adopt `UPDATE ... RETURNING` project-wide** for the near-universal `update()` = UPDATE-then-reSELECT pattern (orders, payments, shipping, addresses, profiles, catalog). Highest-frequency fix in the whole audit — touches nearly every state-transition endpoint in the app.
2. **Fix the Redis `KEYS`-in-loop and per-item row-locking pattern in `reservation_service.py`.** Most severe single finding — sits directly in the synchronous checkout path, confirmed independently by 3 of the 4 audits.
3. **Replace COUNT-then-increment ID generators** (order numbers, invoice numbers, ticket numbers) with Postgres sequences or `SELECT ... FOR UPDATE` — confirmed independently by 3 audits as a real concurrency bug, not a theoretical one.
4. **Route product/coupon search through existing GIN indexes** (`search_vector` for products, add new GIN for coupon JSONB columns) instead of leading-wildcard `ILIKE` — single biggest raw-query-time win as the catalog grows.
5. **Split checkout's Razorpay call out of the reservation transaction** — reduces lock hold time from "one external HTTP round trip" to "near zero," directly reducing flash-sale contention risk.
6. **Add non-negative CHECK constraints on every money/quantity column** — cheap, mechanical, closes a real integrity gap flagged as Critical in the schema audit.
7. **Fix `updated_at` `onupdate=` on the 11+ affected tables** — trivial one-line-per-column fix, currently silently produces wrong "last modified" data across CMS/notifications/returns/support/reviews.
8. **Resolve or delete the duplicate `payments::verify_and_capture` path** — Critical severity pending confirmation of live routing; investigate router wiring first as the very next step.
9. **Eliminate the reviews-admin N+1** (confirmed by 2 independent audits, up to 151-200 extra queries per page load) — small, contained fix with an outsized win.
10. **Batch the CMS homepage/admin section-item fetch** — turns a 13-query cold path (worst exactly during cache-stampede after a publish) into 1-2 queries.
