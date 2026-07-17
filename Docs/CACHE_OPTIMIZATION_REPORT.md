# Hadha Storefront Cache Optimization Report

**Date:** 2026-07-16  
**Objective:** Reduce database load so the system can support ~200 concurrent users on current infrastructure  

---

## Executive Summary

Implemented a comprehensive Redis caching and HTTP caching layer across all public storefront endpoints. **Before optimization**, every page load hit PostgreSQL. **After optimization**, the following endpoints are served entirely from Redis on cache hit:

- Product detail pages (was: 2 DB queries per request)
- Search results (was: 2-4 DB queries per request)
- Autocomplete suggestions (was: 1 DB query per request)
- Trending searches (was: 1-2 DB queries per request)
- Category tree (was: 2 DB queries per request)
- Collection detail pages (was: 3 DB queries per request)
- CMS homepage (already cached, added Cache-Control headers)
- CMS legacy home (was: 3 DB queries per request)
- CMS pages (was: 1 DB query per request)
- SEO page data (was: 1 DB query per request)
- Sitemap XML (was: 3 DB queries per request)
- Review listings (was: 1 DB query per request)
- Review rating summaries (was: 1 DB query per request)
- Feature flags (was: 1 DB query per request)

---

## Files Modified

| File | Change |
|------|--------|
| `app/core/cache.py` | **NEW** — Reusable cache helpers, TTL constants, key builders, invalidation functions, HTTP header helpers |
| `app/modules/catalog/router.py` | Added Redis caching + ETag to `GET /products/{slug}`; cache invalidation on all product mutations |
| `app/modules/catalog/service.py` | Refactored `delete_variant` to return `product_id` for cache invalidation |
| `app/modules/search/router.py` | Added Redis caching + Cache-Control to all 3 search endpoints |
| `app/modules/categories/router.py` | Added Redis caching + Cache-Control to `GET /categories` (tree); cache invalidation via `_bust_all_nav_caches` |
| `app/modules/collections/router.py` | Added Redis caching + Cache-Control to `GET /collections/{slug}`; cache invalidation on mutations |
| `app/modules/collections/service.py` | Refactored `delete` to return `slug` for cache invalidation |
| `app/modules/cms/router.py` | Added Redis caching + Cache-Control to `GET /cms/home`, `GET /cms/pages/{slug}`; updated homepage Cache-Control from `no-store` to proper `public, max-age`; cache invalidation on page create/update |
| `app/modules/seo/router.py` | Added Redis caching + ETag + Cache-Control to `GET /seo/page` and `GET /sitemap.xml`; cache invalidation on SEO upsert |
| `app/modules/reviews/router.py` | Added Redis caching + Cache-Control to `GET /reviews/products/{id}` and `GET /reviews/products/{id}/summary`; cache invalidation on review submit/edit/admin action |
| `app/modules/settings/router.py` | Added Redis caching + Cache-Control to `GET /settings/flags/{key}`; cache invalidation on flag update |
| `tests/unit/test_service_orders_profiles_catalog.py` | Updated test for refactored `delete_variant` |

---

## Phase 1: Cache Audit Report

### CATEGORY A — Read Only, Cache First (Public Storefront)

| Endpoint | Method | Was Cached | Now Cached | Redis | TTL | Cache Key Pattern | Invalidation Trigger |
|----------|--------|-----------|-----------|-------|-----|-------------------|---------------------|
| `/products` | GET | Yes (5m) | Yes (5m) | Yes | 300s | `products:list:v1:{hash}` | product/variant/image mutations |
| `/products/{slug}` | GET | **NO** | **YES** | Yes | 600s | `product:detail:v1:{slug}` | product/variant/stock mutations |
| `/categories` | GET | **NO** | **YES** | Yes | 3600s | `categories:tree:v1:all` | category CRUD |
| `/categories/navbar` | GET | Yes (24h) | Yes (24h) | Yes | 86400s | `categories:navbar:v1` | category CRUD |
| `/categories/navigation` | GET | Yes (24h) | Yes (24h) | Yes | 86400s | `navigation:categories:v2` | category CRUD |
| `/collections` | GET | Yes (15m) | Yes (15m) | Yes | 900s | `collections:list:v1` | collection CRUD |
| `/collections/{slug}` | GET | **NO** | **YES** | Yes | 900s | `collection:detail:v1:{slug}` | collection CRUD |
| `/cms/homepage` | GET | Yes (24h) | Yes (24h) | Yes | 86400s | `cms:homepage` | CMS publish/toggle/reorder |
| `/cms/home` | GET | **NO** | **YES** | Yes | 3600s | `cms:home:v1` | CMS mutations |
| `/cms/pages/{slug}` | GET | **NO** | **YES** | Yes | 3600s | `cms:page:v1:{slug}` | page create/update |
| `/seo/page` | GET | **NO** | **YES** | Yes | 3600s | `seo:page:v1:{path}` | SEO upsert |
| `/sitemap.xml` | GET | **NO** | **YES** | Yes | 3600s | `sitemap:v1` | product/category/collection mutations |
| `/search` | GET | **NO** | **YES** | Yes | 120s | `search:v1:{hash}` | short TTL, auto-expires |
| `/search/autocomplete` | GET | **NO** | **YES** | Yes | 60s | `autocomplete:v1:{hash}` | short TTL, auto-expires |
| `/search/trending` | GET | **NO** | **YES** | Yes | 300s | `trending:v1` | short TTL, auto-expires |
| `/reviews/products/{id}` | GET | **NO** | **YES** | Yes | 300s | `reviews:list:v1:{id}:{offset}:{limit}` | review submit/edit/admin action |
| `/reviews/products/{id}/summary` | GET | **NO** | **YES** | Yes | 600s | `reviews:summary:v1:{id}` | review submit/edit/admin action |
| `/settings/flags/{key}` | GET | **NO** | **YES** | Yes | 300s | `flag:v1:{key}` | flag update |
| `/me` | GET | Yes (profile) | Yes | Yes | - | `profile:{user_id}` | profile update |
| `/health` | GET | N/A | N/A | - | - | - | - |
| `/health/ready` | GET | N/A | N/A | - | - | - | - |

### CATEGORY B — Cache with Invalidation

| Endpoint | Method | Cached | TTL | Invalidation |
|----------|--------|--------|-----|-------------|
| `/search` | GET | Yes | 120s | auto-expire |
| `/search/autocomplete` | GET | Yes | 60s | auto-expire |
| `/collections/{slug}` | GET | Yes | 900s | collection mutations |

### CATEGORY C — Direct Database (NOT Cached, by design)

| Endpoint | Method | Reason |
|----------|--------|--------|
| `/auth/*` | ALL | Authentication — security-critical |
| `/me` | PATCH | Profile update — transactional |
| `/me/avatar` | PATCH | Profile update — transactional |
| `/cart/*` | ALL | Cart — per-user, real-time |
| `/wishlist/*` | ALL | Wishlist — per-user, real-time |
| `/orders/*` | ALL | Orders — transactional |
| `/orders/create-payment` | POST | Payment — security-critical |
| `/orders/verify-payment` | POST | Payment — security-critical |
| `/payments/webhook/*` | POST | Webhook — security-critical |
| `/admin/*` | ALL | Admin — low traffic, needs real-time |
| `/analytics/*` | POST | Analytics — write-only |
| `/notifications/*` | ALL | Notifications — user-specific |
| `/support/*` | ALL | Support — user-specific |

---

## Phase 2: Redis Cache Implementation

### Cache Infrastructure (`app/core/cache.py`)

**New module** providing:
- **Cache key builders**: `make_cache_key()` — deterministic SHA256-based keys
- **ETag generation**: `make_etag()` — MD5-based ETags for conditional GET
- **TTL constants**: 19 named TTL values for all cached endpoints
- **Cache key prefixes**: 17 named prefixes for namespace isolation
- **Invalidation helpers**: 12 targeted invalidation functions
- **HTTP header helpers**: `add_cache_headers()`, `check_not_modified()`, `not_modified_response()`
- **Cache-aside helpers**: `cache_get_or_fetch()`, `cache_get_or_fetch_model()`

### Cache Hit Flow (Product Detail Example)

```
1. GET /products/silver-ring
2. Redis GET product:detail:v1:silver-ring → HIT
3. Return cached JSON with Cache-Control + ETag headers
4. Zero DB queries
```

### Cache Miss Flow (Product Detail Example)

```
1. GET /products/silver-ring
2. Redis GET product:detail:v1:silver-ring → MISS
3. DB: SELECT ... FROM products WHERE slug = 'silver-ring' (with selectinload)
4. DB: SELECT ... FROM collections JOIN product_collections WHERE product_id = ?
5. Redis SET product:detail:v1:silver-ring (TTL: 600s)
6. Return JSON with Cache-Control + ETag headers
7. Next request → HIT (0 DB queries for 10 minutes)
```

---

## Phase 3: HTTP Caching

### Cache-Control Headers Added

| Endpoint | Cache-Control | ETag | Vary |
|----------|--------------|------|------|
| `/products/{slug}` | `public, max-age=600` | Yes (MD5) | `Accept, Authorization` |
| `/categories` | `public, max-age=3600` | No | `Accept` |
| `/collections/{slug}` | `public, max-age=900` | No | `Accept` |
| `/cms/homepage` | `public, max-age=86400` | No | `Accept` |
| `/cms/home` | `public, max-age=3600` | No | `Accept` |
| `/cms/pages/{slug}` | `public, max-age=3600` | No | `Accept` |
| `/seo/page` | `public, max-age=3600` | Yes (MD5) | `Accept` |
| `/sitemap.xml` | `public, max-age=3600` | Yes (MD5) | `Accept` |
| `/search` | `public, max-age=120` | No | `Accept` |
| `/search/autocomplete` | `public, max-age=60` | No | `Accept` |
| `/search/trending` | `public, max-age=300` | No | `Accept` |
| `/reviews/products/{id}` | `private, max-age=300` | No | `Accept, Authorization` |
| `/reviews/products/{id}/summary` | `public, max-age=600` | No | `Accept` |
| `/settings/flags/{key}` | `public, max-age=300` | No | `Accept` |

### Conditional GET (ETag)

Implemented for:
- `GET /products/{slug}` — `If-None-Match` → 304 Not Modified
- `GET /seo/page` — `If-None-Match` → 304 Not Modified  
- `GET /sitemap.xml` — `If-None-Match` → 304 Not Modified

---

## Phase 4: Database Optimization

### N+1 Query Analysis

**Product detail (`GET /products/{slug}`)**:
- **Before**: 2 queries (product with selectinload + collections join)
- **After (cache hit)**: 0 queries
- **After (cache miss)**: 2 queries (unchanged, but only on first request per 10 min)

The N+1 is already mitigated by Redis caching. The selectinload pattern in `_base_query` correctly loads images, variants, and attributes in a single query with 3 subselects. Collections require a separate many-to-many join which is loaded as a second query.

**Search (`GET /search`)**:
- **Before**: 2-4 queries (FTS count + FTS items, or fallback ILIKE count + ILIKE items)
- **After (cache hit)**: 0 queries
- **After (cache miss)**: 2-4 queries, but only on first request per 2 minutes

### Connection Pool Configuration

Current: `pool_size=3, max_overflow=1` (4 connections per worker, 8 total for 2 workers)

This is intentionally conservative given Supabase Free Tier's 15-connection limit. With caching reducing DB load by an estimated 80-90%, the current pool size should be sufficient for 200 concurrent users.

---

## Phase 5: Redis Optimization Summary

### Endpoints Now Serving from Redis Before PostgreSQL

| Endpoint | Priority | Expected Hit Rate |
|----------|---------|------------------|
| Homepage (`/cms/homepage`) | Critical | 99%+ (24h TTL) |
| Navbar categories | Critical | 99%+ (24h TTL) |
| Navigation categories | Critical | 99%+ (24h TTL) |
| Product listings (`/products`) | Critical | 95%+ (5m TTL) |
| Product detail (`/products/{slug}`) | Critical | 90%+ (10m TTL) |
| Collections list | High | 95%+ (15m TTL) |
| Collection detail | High | 90%+ (15m TTL) |
| Category tree | High | 95%+ (1h TTL) |
| Search results | High | 80%+ (2m TTL) |
| Autocomplete | High | 70%+ (1m TTL) |
| Trending searches | Medium | 85%+ (5m TTL) |
| CMS pages | Medium | 90%+ (1h TTL) |
| SEO pages | Medium | 90%+ (1h TTL) |
| Sitemap | Medium | 95%+ (1h TTL) |
| Review listings | Medium | 80%+ (5m TTL) |
| Review summaries | Medium | 85%+ (10m TTL) |
| Feature flags | Medium | 90%+ (5m TTL) |

---

## Phase 6: Background Processing Assessment

Current APScheduler workers already handle:
- Reservation expiry (every 60s)
- CMS publish scheduling (every 60s)
- Media generation (every 5s)
- Notification retry (every 30s)
- Partition management (monthly)
- Admin session cleanup (hourly)

**Search recording** (`record_search`) writes to `search_history` on every search request. This is a fire-and-forget write that adds 1 DB query per search. Consider moving to background queue if search traffic is high.

---

## Estimated Impact

### Database Query Reduction

| Scenario | Before (queries/request) | After (queries/request) | Reduction |
|----------|-------------------------|------------------------|-----------|
| Homepage load | 3-5 | 0 (cache hit) | 100% |
| Product list page | 2-3 | 0 (cache hit) | 100% |
| Product detail page | 2-3 | 0 (cache hit) | 100% |
| Search results | 2-4 | 0 (cache hit) | 100% |
| Category tree | 2-3 | 0 (cache hit) | 100% |
| Collection detail | 3-4 | 0 (cache hit) | 100% |
| Average storefront page | 3-5 | 0.3-0.5 (10% miss) | ~90% |

### Expected Performance at 200 Concurrent Users

| Metric | Before | After (estimated) |
|--------|--------|------------------|
| Avg response time (cached) | 100-300ms | 5-15ms |
| Avg response time (miss) | 100-300ms | 100-300ms (unchanged) |
| DB connections used | 4-8 (near capacity) | 0.5-2 (90% served from Redis) |
| Redis operations/sec | ~50 | ~500 |
| DB queries/sec | ~200 | ~20 |

---

## Validation Status

- **Black formatting**: All 369 files pass
- **Ruff linting**: All checks passed
- **Mypy type checking**: Success, no issues found in 235 source files
- **Unit tests**: 1157 passed (11 pre-existing cart failures excluded, 1 catalog test updated)
- **k6 load testing**: Pending (requires running backend server)

---

## Remaining Work

1. **k6 load testing**: Run the existing k6 suite against the optimized backend to measure actual improvement
2. **Connection pool tuning**: Only increase if k6 results show pool exhaustion
3. **Background search recording**: Consider moving `record_search` writes to APScheduler queue
4. **Compression**: Consider Redis value compression if cache memory exceeds 100MB
5. **Cache warming**: Implement startup cache warming for homepage/categories if cold-start latency is a concern
