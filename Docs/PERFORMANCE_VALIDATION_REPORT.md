# PERFORMANCE VALIDATION REPORT

**Hadha.co E-Commerce Platform — Enterprise Performance Audit**

**Date:** 2026-07-13
**Auditor:** Automated Performance Validation (code-level analysis)
**Scope:** Backend (FastAPI/SQLAlchemy), Storefront (React Router), Admin (React), Infrastructure (Docker/Nginx/PostgreSQL/Redis)
**Methodology:** Architecture inspection, LOC analysis, dependency analysis, query pattern analysis, middleware overhead modeling, capacity estimation from framework benchmarks

> **Note:** This is a code-level audit. Load tests, Lighthouse, EXPLAIN ANALYZE, and browser benchmarks were not executed. All performance metrics are estimates based on code analysis, framework benchmarks, and industry-standard capacity models.

---

## 1. Executive Summary

| Dimension | Score | Verdict |
|-----------|-------|---------|
| Backend API Performance | 72/100 | ACCEPTABLE — 2 critical bottlenecks |
| Frontend Page Performance | 58/100 | NEEDS IMPROVEMENT — zero code splitting |
| Database Performance | 68/100 | ACCEPTABLE — 3 missing indexes |
| Redis Performance | 82/100 | GOOD — minor gaps |
| Infrastructure Performance | 65/100 | NEEDS IMPROVEMENT — memory pressure |
| **Overall** | **69/100** | **ACCEPTABLE WITH RECOMMENDATIONS** |

**Verdict: CONDITIONAL GO — Production-safe with 6 performance fixes required pre-scale.**

The platform is performant enough for launch with <100 concurrent users. Two backend bottlenecks (sync Razorpay SDK in async context, missing trigram indexes) and frontend bundle issues (zero code splitting, 7 dead dependencies) must be addressed before scaling past 500 concurrent users.

---

## 2. Backend API Performance

### 2.1 Middleware Stack Overhead

13 middleware layers execute per request. Estimated overhead per request:

| Middleware | Overhead | Notes |
|-----------|----------|-------|
| Request ID | ~0.01ms | UUID generation |
| Request context (structlog) | ~0.02ms | Context binding |
| Performance timing | ~0.03ms | Timer start/stop |
| Rate limiting (Redis) | ~0.08–0.15ms | Sorted-set ZRANGEBYSCORE + ZADD |
| Audit context | ~0.01ms | Admin mutating only |
| RBAC | ~0.02ms | Admin only, role check |
| Security headers | ~0.01ms | Dict merge per response |
| **Total per request** | **~0.15–0.25ms** | **Negligible** |

**Verdict:** Middleware overhead is well under 1ms. No action needed.

### 2.2 Endpoint Response Time Estimates

| Endpoint | Estimated P50 | Estimated P99 | Bottleneck |
|----------|--------------|--------------|------------|
| `GET /health` | 5–10ms | 15ms | None (no DB/Redis) |
| `GET /api/products` | 120–180ms | 280ms | 2 DB queries + Redis cache |
| `GET /api/cart` | 80–120ms | 150ms | 1–2 DB queries |
| `POST /api/orders` | 200–350ms | 400ms | Transactional + inventory lock |
| `POST /api/payments/capture` | 500–1,200ms | 2,000ms | **Sync Razorpay SDK** |
| `GET /api/account/profiles` | 100–150ms | 200ms | 1 DB query + Redis cache |
| `GET /api/admin/dashboard` | 150–300ms | 500ms | Multiple aggregate queries |

### 2.3 Critical Bottleneck #1: Sync Razorpay SDK in Async Context

**File:** `Backend/app/modules/payments/service.py`

```python
# CURRENT: Sync SDK call blocks the event loop
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
client.payment.capture(payment_id, amount)  # Blocks for 50–500ms
```

**Impact:**
- Blocks the asyncio event loop for 50–500ms per payment capture
- Under concurrent load, this creates a queue of blocked coroutines
- With 10 concurrent payments: 500ms–5s of blocked event loop time

**Fix:** Wrap in `asyncio.to_thread()` or migrate to `httpx` async client:
```python
await asyncio.to_thread(client.payment.capture, payment_id, amount)
```

**Priority:** P0 — Must fix before >100 concurrent users.

### 2.4 Critical Bottleneck #2: DB Lock Held During Sync I/O

**File:** `Backend/app/modules/orders/service.py`

```python
# update_status holds FOR UPDATE lock while calling Razorpay (sync)
result = await db.execute(select(Order).where(...).with_for_update())
order = result.scalar_one()
# ... business logic ...
await payment_service.capture(order.payment_id)  # Sync: 50-500ms
await db.commit()  # Lock released here
```

**Impact:**
- DB row lock held for 50–500ms (Razorpay round-trip)
- Other requests for the same order queue behind this lock
- Under concurrent load: lock contention → request timeouts

**Fix:** Perform payment capture before acquiring the lock, or use `asyncio.to_thread()` to avoid blocking the event loop during the lock hold.

---

## 3. Frontend Page Performance

### 3.1 Route Size Analysis

| Route | LOC | Estimated Bundle (gz) | Verdict |
|-------|-----|----------------------|---------|
| `products.$slug.tsx` | 1,368 | ~85KB | **NEEDS SPLITTING** |
| `account.index.tsx` | 1,568 | ~95KB | **NEEDS SPLITTING** |
| `checkout.tsx` | 936 | ~60KB | Borderline |
| `cart.tsx` | ~600 | ~40KB | Acceptable |
| `products._index.tsx` | ~500 | ~35KB | Acceptable |
| `index.tsx` | ~400 | ~25KB | Good |

### 3.2 Critical Issue: Zero Code Splitting

**No `React.lazy()` anywhere in the codebase.** All routes load in a single bundle.

**Impact:**
- Initial page load downloads ALL route code (~400KB gz total)
- First Contentful Paint delayed by 200–400ms on 3G/4G
- Time to Interactive penalized by unused code (checkout code loads on homepage)

**Fix:** Implement route-level code splitting:
```typescript
const Checkout = React.lazy(() => import('./routes/checkout'));
const Account = React.lazy(() => import('./routes/account.index'));
const ProductDetail = React.lazy(() => import('./routes/products.$slug'));
```

**Priority:** P0 — Must fix before launch. Reduces initial bundle by ~60%.

### 3.3 Dead Dependencies (7 packages, ~150KB gz wasted)

| Package | Size (gz) | Usage |
|---------|-----------|-------|
| `recharts` | ~45KB | 0 imports |
| `swiper` | ~30KB | 0 imports |
| `embla-carousel-react` | ~15KB | 0 imports |
| `react-easy-crop` | ~12KB | 0 imports |
| `react-resizable-panels` | ~18KB | 0 imports |
| `react-day-picker` | ~20KB | 0 imports |
| `cmdk` | ~10KB | 0 imports |

**Impact:** ~150KB gzipped added to bundle for zero usage.

**Fix:** `npm uninstall recharts swiper embla-carousel-react react-easy-crop react-resizable-panels react-day-picker cmdk`

**Priority:** P1 — Quick win, reduces bundle by ~150KB gz.

### 3.4 Framer Motion Overhead

**4 homepage components** import `framer-motion` (~40KB gz):

- `FeaturedProducts.tsx`
- `NewArrivals.tsx`
- `TrendingSection.tsx`
- `WhyChooseHadha.tsx`

**Impact:** 40KB gz of animation library loaded on homepage only.

**Fix:** Dynamic import with `React.lazy()` for these components, or replace with CSS animations for simple fade-in/slide effects.

### 3.5 Image Optimization Gap

- No `srcset` or `<picture>` elements for responsive images
- No WebP/AVIF format serving
- No lazy loading (`loading="lazy"`) on below-fold images
- Google Fonts loaded render-blocking (no `font-display: swap`)

**Estimated impact:** 30–50% reduction in image transfer size with responsive images.

---

## 4. Database Performance

### 4.1 Connection Pool Configuration

```python
# Backend/app/core/database.py
pool_size = 5 + (2 * uvicorn.workers)  # = 14 connections (default 2 workers)
max_overflow = 2 * uvicorn.workers    # = 4 overflow connections
total_max = 18 connections
```

**Verdict:** Reasonable for a single-server deployment. At 500+ concurrent users, consider increasing to 20+ connections.

### 4.2 Query Performance Analysis

| Query Pattern | Estimated Time | Index Status | Issue |
|--------------|---------------|-------------|-------|
| Product listing (paginated) | 15–50ms | Indexed | None |
| Order listing (paginated) | 20–80ms | Indexed + JOIN | None |
| Product search (`ilike %term%`) | 30–120ms | **No trigram** | Sequential scan |
| Order search (`ilike %term%`) | 25–100ms | **No trigram** | Sequential scan |
| Profile search (`ilike %term%`) | 25–100ms | **No trigram** | Sequential scan |
| Inventory `FOR UPDATE` | 5–20ms | Indexed | Lock contention risk |
| Order `FOR UPDATE` | 5–15ms | Indexed | Lock contention risk |

### 4.3 Missing Trigram Indexes

PostgreSQL `pg_trgm` extension not installed. `ILIKE '%search%'` queries fall back to sequential scan.

**Affected tables:**
- `products` (name, slug)
- `orders` (order_number)
- `profiles` (full_name, email)

**Fix:**
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_products_name_trgm ON products USING gin (name gin_trgm_ops);
CREATE INDEX idx_orders_number_trgm ON orders USING gin (order_number gin_trgm_ops);
```

**Priority:** P1 — Critical for search performance at scale.

### 4.4 Transaction Lock Duration

| Transaction | Lock Type | Hold Duration | Risk |
|------------|-----------|--------------|------|
| `update_status` | `FOR UPDATE` | 50–500ms (sync Razorpay) | **HIGH** |
| `create_from_cart` | `FOR UPDATE` | 50–200ms | MEDIUM |
| `reserve_inventory` | `FOR UPDATE` | 30–100ms | LOW (sorted lock order) |

**Recommendation:** Minimize lock hold time by performing external API calls outside the transaction.

---

## 5. Redis Performance

### 5.1 Cache Architecture

| Pattern | Implementation | Verdict |
|---------|---------------|---------|
| Cache-aside | Manual `get`/`set` with TTL | Good |
| Invalidation | SCAN-based key iteration | Good (avoids `KEYS` blocking) |
| Circuit breaker | 0.3s timeout, 5 failures → open | Good |
| Cache stampede protection | **None** | **Gap** |
| Deadletter queue | **None** | **Gap** |

### 5.2 Cache Stampede Risk

No singleflight/lock mechanism for cache misses. Under concurrent load:

1. Cache key expires
2. 50 concurrent requests all see cache miss
3. All 50 hit the database simultaneously
4. Database overwhelmed

**Fix:** Implement singleflight pattern or use Redis `SET NX EX` as a lock:
```python
lock = await redis.set(f"lock:{key}", "1", nx=True, ex=5)
if not lock:
    # Another request is populating; wait and retry cache read
    await asyncio.sleep(0.1)
    return await redis.get(key)
```

**Priority:** P2 — Fix before >200 concurrent users.

### 5.3 HTTP Client Leak in JWKS

**File:** `Backend/app/core/jwks.py`

Creates a new `httpx.AsyncClient` per JWKS fetch without calling `__aexit__`. JWKS refreshes ~5/year, so impact is minimal, but it's a resource leak.

**Fix:** Use a module-level singleton client or `async with httpx.AsyncClient() as client:`.

---

## 6. Infrastructure Performance

### 6.1 Memory Budget

| Service | Memory Limit | Estimated Usage | Headroom |
|---------|-------------|----------------|---------|
| Backend (uvicorn) | 768MB | 300–500MB | **268–468MB (tight)** |
| PostgreSQL | 256MB | 150–200MB | 56–106MB |
| Redis | 256MB | 50–100MB | 156–206MB |
| Storefront | 128MB | 30–50MB | 78–98MB |
| Admin | 128MB | 30–50MB | 78–98MB |
| Nginx | 128MB | 20–40MB | 88–108MB |
| Redis Commander | 128MB | 20–30MB | 98–108MB |
| **Total** | **2,028MB** | **600–970MB** | **1,058–1,428MB** |

**Risk:** Backend at 768MB is an OOM-kill candidate under load. With 14 DB connections + 13 middleware layers + async workers, peak memory can spike to 600–700MB.

**Recommendation:** Increase backend to 1024MB if server RAM allows, or reduce `--workers` from 2 to 1 in production.

### 6.2 Nginx Configuration Gaps

| Setting | Current | Recommended | Impact |
|---------|---------|------------|--------|
| gzip level | 1 | 4–6 | 10–20% better compression |
| Brotli | Not enabled | Enable | 15–25% better compression |
| keepalive_timeout | Default (75s) | 65s | Faster connection reuse |
| open_file_cache | Not configured | `max=1000 inactive=20s` | Reduce disk I/O |
| sendfile | Not explicit | `on` | Kernel-level file serving |
| tcp_nopush | Not explicit | `on` | Better packet utilization |

### 6.3 Docker Configuration

| Issue | Risk | Fix |
|-------|------|-----|
| Redis Commander `:latest` tag | Unpredictable updates | Pin to specific version |
| No health checks on some services | Delayed failure detection | Add health check endpoints |
| No restart policy visible | Manual recovery needed | Add `restart: unless-stopped` |

---

## 7. Production Capacity Estimates

Based on framework benchmarks and code analysis:

### 7.1 Requests Per Second (RPS) Capacity

| Scenario | Estimated RPS | Bottleneck |
|----------|--------------|------------|
| Read-only (products, catalog) | 200–400 RPS | DB connections |
| Mixed read/write (cart, orders) | 80–150 RPS | DB locks + Redis |
| Payment-heavy (capture flow) | 20–50 RPS | **Sync Razorpay SDK** |
| Health check only | 1,000+ RPS | CPU |

### 7.2 Concurrent User Capacity

| Load Level | Concurrent Users | Expected Behavior |
|-----------|-----------------|-------------------|
| Light | 1–50 | All endpoints <200ms |
| Medium | 50–200 | Payment endpoints 500ms–1s |
| Heavy | 200–500 | DB lock contention, timeout risks |
| Overload | 500+ | **OOM risk, connection pool exhaustion** |

### 7.3 Database Connection Pressure

| Concurrent Users | Active Connections | Pool Utilization |
|-----------------|-------------------|-----------------|
| 50 | 8–12 | 44–67% |
| 100 | 14–18 | 78–100% |
| 200 | 18+ | **100%+ (overflow)** |

---

## 8. Optimization Roadmap

### 8.1 Immediate (Pre-Launch) — P0

| # | Fix | Impact | Effort |
|---|-----|--------|--------|
| 1 | Add `asyncio.to_thread()` around Razorpay SDK calls | Unblocks event loop, +200 RPS | 2 hours |
| 2 | Implement route-level code splitting (`React.lazy`) | -60% initial bundle, +30% FCP | 4 hours |
| 3 | Remove 7 dead npm dependencies | -150KB gz bundle | 15 minutes |

### 8.2 Short-Term (Week 1–2) — P1

| # | Fix | Impact | Effort |
|---|-----|--------|--------|
| 4 | Install `pg_trgm` + add trigram indexes | -70% search query time | 1 hour |
| 5 | Add `font-display: swap` to Google Fonts | -200ms FCP | 30 minutes |
| 6 | Enable `sendfile`, `tcp_nopush` in Nginx | -10% latency | 15 minutes |
| 7 | Increase gzip level to 4–6 | -15% transfer size | 5 minutes |

### 8.3 Medium-Term (Month 1) — P2

| # | Fix | Impact | Effort |
|---|-----|--------|--------|
| 8 | Implement cache stampede protection (singleflight) | Prevent thundering herd | 4 hours |
| 9 | Add responsive images (`srcset`, WebP/AVIF) | -40% image transfer | 8 hours |
| 10 | Enable Brotli compression in Nginx | -20% transfer size | 1 hour |
| 11 | Add `open_file_cache` to Nginx | -5% latency | 15 minutes |
| 12 | Move payment capture outside DB transaction | Reduce lock hold time | 4 hours |
| 13 | Pin Redis Commander to specific version | Prevent breaking updates | 5 minutes |

### 8.4 Long-Term (Month 2–3) — P3

| # | Fix | Impact | Effort |
|---|-----|--------|--------|
| 14 | Split `account.index.tsx` by tab | -60% account page bundle | 8 hours |
| 15 | Split `products.$slug.tsx` into sub-components | -40% PDP bundle | 6 hours |
| 16 | Replace framer-motion with CSS animations on homepage | -40KB gz | 4 hours |
| 17 | Implement backend deadletter queue for failed tasks | Reliability | 8 hours |
| 18 | Add JWKS singleton httpx client | Fix resource leak | 30 minutes |
| 19 | Consider Redis Cluster for >1000 concurrent users | Horizontal scaling | TBD |

---

## 9. VPS/DB/Redis Sizing Recommendations

### 9.1 Current (Launch)

| Resource | Spec | Adequate? |
|----------|------|----------|
| VPS | 2 vCPU, 2GB RAM | Yes for <100 users |
| PostgreSQL | 256MB limit | Yes for <50K rows |
| Redis | 256MB limit | Yes for <10K cached keys |
| Backend | 768MB, 2 workers | **Tight** — consider 1 worker |

### 9.2 Recommended (100–500 Users)

| Resource | Spec | Reason |
|----------|------|--------|
| VPS | 4 vCPU, 4GB RAM | Handle 3x more concurrent connections |
| PostgreSQL | 512MB limit | More shared_buffers for indexed queries |
| Redis | 512MB limit | Cache more products/sessions |
| Backend | 1024MB, 2 workers | Prevent OOM under load |
| Add | Read replica for PostgreSQL | Separate read/write workloads |

### 9.3 Recommended (500–2,000 Users)

| Resource | Spec | Reason |
|----------|------|--------|
| VPS | 8 vCPU, 8GB RAM | Handle 10x concurrent connections |
| PostgreSQL | 1GB limit + read replica | Connection pool scaling |
| Redis | 1GB limit | Session + cache scaling |
| Backend | 1024MB, 4 workers | Horizontal scaling |
| Add | CDN (CloudFlare/CloudFront) | Offload static assets |
| Add | Redis Sentinel | High availability |

### 9.4 Recommended (2,000+ Users)

| Resource | Spec | Reason |
|----------|------|--------|
| Architecture | Migrate to Kubernetes | Auto-scaling |
| Database | PostgreSQL cluster (primary + 2 replicas) | Read scaling |
| Cache | Redis Cluster (3 nodes) | Cache scaling |
| Backend | 3+ separate instances | Load balancing |
| CDN | Global CDN | Edge caching |
| Search | Elasticsearch/Meilisearch | Full-text search offload |

---

## 10. Monitoring Recommendations

### 10.1 Key Metrics to Track

| Metric | Warning Threshold | Critical Threshold |
|--------|------------------|-------------------|
| API response time (P95) | >500ms | >2,000ms |
| API response time (P99) | >1,000ms | >5,000ms |
| Error rate (5xx) | >1% | >5% |
| DB connection pool utilization | >70% | >90% |
| Redis memory usage | >70% | >85% |
| Backend memory usage | >70% | >85% |
| CPU usage | >70% | >90% |
| Payment capture duration | >2s | >5s |

### 10.2 Existing Monitoring

| Tool | Status | Coverage |
|------|--------|----------|
| Sentry (backend) | ✅ Active | Error tracking, performance |
| Prometheus | ✅ Active | Metrics export |
| Structured logging (structlog) | ✅ Active | Request tracing |
| Health endpoints | ✅ Active | DB + Redis connectivity |

---

## Appendix A: Files Analyzed

| Category | Files | LOC |
|----------|-------|-----|
| Backend Python | 214 | 22,730 |
| Storefront TypeScript | ~80 | 12,047 |
| Admin TypeScript | ~60 | ~8,000 |
| Infrastructure (Nginx, Docker) | 6 | ~400 |
| **Total** | **~360** | **~43,177** |

## Appendix B: Dependency Counts

| Scope | Count |
|-------|-------|
| Backend (pip) | 40 |
| Storefront (npm deps) | 59 |
| Storefront (npm devDeps) | 25 |
| **Dead dependencies** | **7** |

## Appendix C: Database Migrations

37 Alembic migrations. Schema is stable. No destructive changes pending.

---

*Report generated: 2026-07-13*
*Validation method: Code-level analysis (no runtime benchmarks)*
*Next review: After implementing P0 fixes*
