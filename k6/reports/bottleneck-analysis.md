# Hadha.co Performance Bottleneck Analysis
# Generated from k6 benchmark: 80 VUs, 9 min, 5543 requests

## Executive Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Avg latency | 4.50s | <500ms | CRITICAL |
| P95 latency | 7.90s | <2000ms | CRITICAL |
| Max latency | 14.52s | <5000ms | CRITICAL |
| Request timeouts | 83 (14.7%) | <1% | CRITICAL |
| API success rate | 89.70% | >99% | CRITICAL |
| 5xx errors | 0 | 0 | PASS |
| Check pass rate | 93.94% | >95% | WARN |

---

## Root Cause #1: DB Connection Pool Starvation (PRIMARY)

### Evidence
- pool_size=3, max_overflow=1 → **max 4 concurrent DB connections**
- 80 VUs generating 9.82 req/s → 4 connections cannot serve 80 concurrent requests
- All endpoint latencies spike from ~500ms (low VUs) to 5-10s (50+ VUs)
- 83 timeouts at 10s k6 default timeout
- Pool checkout event listener already warns: `pool_near_capacity` at capacity-1

### Code References
- `Backend/app/core/config.py:127-129`: `DATABASE_POOL_SIZE=3, DATABASE_MAX_OVERFLOW=1`
- `Backend/app/core/database.py:25-36`: Engine creation with pool settings
- `Backend/app/core/database.py:73-83`: Pool checkout listener confirms pressure

### Impact
Every request holds a DB connection for the full duration of its transaction (including serialization). With 4 connections and 80 concurrent VUs, 76 requests queue in SQLAlchemy's `pool_timeout` (30s), causing cascading latency.

### Fix
```python
# Backend/app/core/config.py
DATABASE_POOL_SIZE: int = 10      # was 3
DATABASE_MAX_OVERFLOW: int = 5    # was 1
DATABASE_POOL_TIMEOUT: int = 60   # was 30
```
Supabase free tier allows 15 session-mode connections. With 2 uvicorn workers: (10+5) * 2 = 30 > 15. 
**Recommendation**: Use pool_size=5, max_overflow=2 → (5+2)*2 = 14 connections. Or switch to transaction mode (pooler) for higher limits.

---

## Root Cause #2: No Response Caching (SECONDARY)

### Evidence
- Every category/collection/product list request hits the DB directly
- Categories: 4 top-level, 16 total — changes rarely, cached everywhere in production
- Collections: 13 active — same pattern
- Homepage products, featured products — same queries repeated thousands of times
- No `Cache-Control` headers on any endpoint

### Code References
- `Backend/app/modules/catalog/repository.py:26-30`: `list_all_active()` — raw DB query every time
- `Backend/app/modules/categories/repository.py:26-30`: `list_all_active()` — same
- `Backend/app/modules/collections/repository.py:32-37`: `list_active()` — same

### Impact
N requests × 1 DB query each = N DB roundtrips for identical data. At 80 VUs, this multiplies DB pressure unnecessarily.

### Fix
- Add in-memory TTL cache (e.g., `cachetools.TTLCache`) for category/collection/product-list endpoints
- Add `Cache-Control: max-age=60` headers to product listing responses
- Consider Redis caching with 5-minute TTL for homepage/featured data

---

## Root Cause #3: Missing Eager Loading (TERTIARY)

### Evidence
- `list_paginated()` loads Product.images + Product.variants but OMITS Product.attributes
- Category and Collection repos have ZERO `.options()` calls
- Product serializer may access lazy relationships → N+1 queries per list page

### Code References
- `Backend/app/modules/catalog/repository.py:162-166`: Missing `selectinload(Product.attributes)`
- `Backend/app/modules/categories/repository.py:26-30`: No `.options()` on any Category query
- `Backend/app/modules/collections/repository.py:32-37`: No `.options()` on any Collection query

### Impact
Each product in a list page triggers additional DB queries for missing relationships. 24 products per page × 3 N+1 patterns = ~72 extra queries per product listing.

### Fix
```python
# catalog/repository.py list_paginated() — add missing attribute loading
base_q = select(Product).where(and_(*filters)).options(
    selectinload(Product.images).selectinload(Image.variants),
    selectinload(Product.variants),
    selectinload(Product.attributes),  # ADD THIS
)
```

---

## Root Cause #4: Supabase Session-Mode Limits

### Evidence
- Supabase free tier: 15 session-mode connections max
- With 2 uvicorn workers, each holding pool_size connections, total = (pool_size + max_overflow) * workers
- Current: (3+1)*2 = 8 connections used by API alone
- With fix pool_size=5, max_overflow=2: (5+2)*2 = 14 — only 1 connection left for admin/migrations

### Recommendation
- Switch Supabase to **transaction-mode** pooler (PgBouncer) for 100+ connection limit
- Or reduce uvicorn workers to 1 for development/testing
- Monitor `get_pool_status()` via `/health/ready` endpoint

---

## Endpoint Latency Breakdown

| Endpoint | Avg | P95 | Max | Root Cause |
|----------|-----|-----|-----|------------|
| Products List | 5.08s | 8.06s | 10.00s | DB pool starvation + N+1 |
| Categories | 4.90s | 7.97s | 10.00s | DB pool starvation |
| Homepage | 4.86s | 7.97s | 10.00s | DB pool starvation |
| Collections | 4.78s | 7.86s | 10.00s | DB pool starvation |
| Cart (add/view) | 4.85s | 7.75s | 14.52s | DB pool starvation + locking |
| Search | 4.60s | 7.34s | 10.00s | DB pool starvation + full-text |
| Checkout | 15.2ms | 61.7ms | 615.5ms | Fast (fails fast with 401) |

All endpoints show identical latency patterns because they all share the same 4-connection pool. Checkout is fast only because it rejects immediately (no auth).

---

## Priority Fix Order

1. **DB Pool** (config change only, immediate impact): pool_size=5, max_overflow=2
2. **Eager Loading** (1 file change): Add `selectinload(Product.attributes)` to `list_paginated()`
3. **Category/Collection Caching** (new module): Add TTL cache for rarely-changing data
4. **Cache-Control Headers** (middleware): Add to product/category/collection responses
5. **Supabase Pool Mode** (infra): Switch to transaction-mode for production scaling

---

## Expected Impact After Fixes

| Metric | Current | After Pool Fix | After Full Optimization |
|--------|---------|----------------|------------------------|
| Avg latency | 4.50s | ~2.0s | <500ms |
| P95 latency | 7.90s | ~4.0s | <1500ms |
| Timeouts | 83 (14.7%) | ~20 (3%) | 0 |
| Max VUs sustainable | ~20 | ~50 | ~100+ |
