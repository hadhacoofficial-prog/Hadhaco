# Hadha.co Performance Optimization Recommendations

## 1. Database Connection Pool Tuning (IMMEDIATE — config change only)

**File**: `Backend/app/core/config.py:127-129`

```python
# CURRENT (causes pool starvation at 20+ VUs)
DATABASE_POOL_SIZE: int = 3
DATABASE_MAX_OVERFLOW: int = 1
DATABASE_POOL_TIMEOUT: int = 30

# RECOMMENDED (supports ~50 VUs on Supabase session-mode)
DATABASE_POOL_SIZE: int = 5
DATABASE_MAX_OVERFLOW: int = 2
DATABASE_POOL_TIMEOUT: int = 60
```

**Rationale**: Supabase free tier allows 15 session-mode connections. With 2 uvicorn workers: (5+2)*2 = 14 connections. Leaves 1 for admin/migrations.

**Expected impact**: Avg latency drops from 4.5s to ~2.0s. Timeouts drop from 14.7% to ~3%.

---

## 2. Fix Missing Eager Loading (IMMEDIATE — 1 line change)

**File**: `Backend/app/modules/catalog/repository.py:162-166`

```python
# CURRENT (missing attributes)
base_q = select(Product).where(and_(*filters)).options(
    selectinload(Product.images).selectinload(Image.variants),
    selectinload(Product.variants),
)

# FIXED
base_q = select(Product).where(and_(*filters)).options(
    selectinload(Product.images).selectinload(Image.variants),
    selectinload(Product.variants),
    selectinload(Product.attributes),  # ADD THIS
)
```

**Impact**: Eliminates N+1 queries on product listing pages. ~72 fewer DB queries per page load.

---

## 3. Category/Collection In-Memory Cache (SHORT-TERM)

**File**: `Backend/app/modules/categories/service.py`, `collections/service.py`

Add `cachetools.TTLCache` (maxsize=128, ttl=300) for rarely-changing data:

```python
from cachetools import TTLCache

_category_cache = TTLCache(maxsize=128, ttl=300)  # 5-min TTL

async def list_active_categories(self, db: AsyncSession) -> list[Category]:
    cache_key = "active_categories"
    if cache_key in _category_cache:
        return _category_cache[cache_key]
    result = await self.repo.list_all_active(db)
    _category_cache[cache_key] = result
    return result
```

Same pattern for collections. Categories change maybe once a month; collections weekly. 5-minute TTL is safe.

**Impact**: Reduces DB load by ~30% for homepage/catalog traffic.

---

## 4. HTTP Cache-Control Headers (SHORT-TERM)

**File**: `Backend/app/main.py` or new middleware

```python
from fastapi import Response

@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/v1/products") or path.startswith("/api/v1/categories"):
        response.headers["Cache-Control"] = "public, max-age=60"
    elif path.startswith("/api/v1/collections"):
        response.headers["Cache-Control"] = "public, max-age=120"
    return response
```

**Impact**: Reduces repeat requests from browser/CDN. ~40% fewer backend hits for catalog pages.

---

## 5. Supabase Transaction-Mode Pooler (PRODUCTION)

Switch from session-mode to transaction-mode (PgBouncer) in Supabase dashboard:
- Session-mode: 15 connections max (current)
- Transaction-mode: 100+ connections (recommended for production)

With transaction-mode, increase pool safely:
```python
DATABASE_POOL_SIZE: int = 15
DATABASE_MAX_OVERFLOW: int = 10
```

**Impact**: Supports 100+ concurrent VUs without connection pressure.

---

## 6. Redis Response Cache (PRODUCTION)

Implement Redis-based caching for hot endpoints:
- Product listings: 2-min TTL
- Category/Collection trees: 10-min TTL
- Homepage data: 5-min TTL
- Search suggestions: 1-hour TTL

```python
import redis.asyncio as redis
from app.core.config import settings

redis_client = redis.from_url(settings.REDIS_URL)

async def get_cached_or_fetch(key: str, ttl: int, fetch_fn):
    cached = await redis_client.get(key)
    if cached:
        return json.loads(cached)
    result = await fetch_fn()
    await redis_client.setex(key, ttl, json.dumps(result))
    return result
```

**Impact**: Reduces DB load by 80%+ for read-heavy traffic. Supports 200+ VUs.

---

## 7. N+1 Query Audit (MEDIUM-TERM)

Audit all repository methods for missing `.options()` calls:

| Repository | Method | Issue | Fix |
|-----------|--------|-------|-----|
| catalog | `get_by_sku()` | No `.options()` | Add image/variant/attribute loading |
| categories | All public methods | No `.options()` | Add child category loading if needed |
| collections | All public methods | No `.options()` | Add product count subquery |
| orders | `list_for_user()` | No `_with_items()` | Add `selectinload(Order.items)` |
| cart | `upsert_item()` | No product loading | Add if needed downstream |

---

## 8. Connection Pool Monitoring (PRODUCTION)

The existing `get_pool_status()` in `database.py:86-94` already exposes pool metrics. Wire it into:
- Prometheus metrics: `db_pool_checked_out`, `db_pool_overflow`
- Alerting: warn at 80% capacity, critical at 95%
- Grafana dashboard: real-time pool utilization

---

## Implementation Priority

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| P0 | DB Pool tuning | 5 min | HIGH |
| P0 | Eager loading fix | 5 min | MEDIUM |
| P1 | In-memory TTL cache | 2 hours | HIGH |
| P1 | Cache-Control headers | 1 hour | MEDIUM |
| P2 | Supabase transaction-mode | 30 min | HIGH |
| P2 | Redis response cache | 4 hours | VERY HIGH |
| P3 | N+1 audit | 2 hours | MEDIUM |
| P3 | Pool monitoring | 2 hours | LOW |

---

## Expected Results After Full Optimization

| Metric | Current | Target | With All Fixes |
|--------|---------|--------|----------------|
| Avg latency | 4.50s | <500ms | ~200ms |
| P95 latency | 7.90s | <2000ms | ~800ms |
| Timeouts | 83 (14.7%) | <1% | 0 |
| Max sustainable VUs | ~20 | 100+ | 200+ |
| API success rate | 89.70% | >99% | ~99.5% |
| DB queries per page | ~75 | ~5 | ~3 |
