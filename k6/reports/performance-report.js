// k6 shared — Performance report generator
// Produces structured JSON output for post-processing

import { group } from "k6";

/**
 * Performance score calculator based on k6 metric results.
 *
 * Scoring methodology:
 * - API Score: Based on p95 latency vs targets per tier
 * - Database Score: Based on query-heavy endpoint performance
 * - Caching Score: Based on cache hit indicators
 * - Infrastructure Score: Based on error rates and throughput
 * - Overall Grade: Weighted average
 */

export const PERFORMANCE_TARGETS = {
  // Response time targets (ms)
  latency: {
    homepage: { p95: 300, p99: 600, max: 2000 },
    product_list: { p95: 400, p99: 800, max: 3000 },
    product_detail: { p95: 300, p99: 600, max: 2000 },
    search: { p95: 500, p99: 1000, max: 3000 },
    autocomplete: { p95: 200, p99: 400, max: 1000 },
    cart_operations: { p95: 300, p99: 600, max: 2000 },
    checkout: { p95: 1000, p99: 2000, max: 5000 },
    auth: { p95: 500, p99: 1000, max: 3000 },
    categories: { p95: 300, p99: 500, max: 1500 },
    collections: { p95: 300, p99: 500, max: 1500 },
  },

  // Throughput targets (req/s)
  throughput: {
    minimum: 10,
    target: 25,
    peak: 50,
  },

  // Error rate targets
  errors: {
    maximum: 0.01,      // 1% max
    target: 0.001,       // 0.1% target
    checkout_max: 0.005, // 0.5% max for checkout
  },

  // Availability targets
  availability: {
    target: 0.999,       // 99.9%
    minimum: 0.99,       // 99%
  },
};

/**
 * Expected infrastructure sizing based on codebase analysis.
 */
export const INFRASTRUCTURE_SIZING = {
  development: {
    description: "Local Docker Compose",
    backend: "2 vCPU, 2GB RAM (uvicorn, pool_size=3, max_overflow=1)",
    redis: "1 vCPU, 512MB RAM",
    database: "Supabase Free/Pro (shared, max 60 connections)",
    expected_rps: "10-25",
    expected_concurrent_users: "10-20",
  },
  production: {
    description: "Docker Compose with Nginx reverse proxy",
    backend: "1 vCPU, 768MB RAM (resource limit)",
    storefront: "0.75 vCPU, 384MB RAM",
    redis: "0.5 vCPU, 300MB RAM",
    database: "Supabase Pro (dedicated, max 60 connections)",
    nginx: "0.5 vCPU, 128MB RAM (Brotli compression)",
    expected_rps: "25-50",
    expected_concurrent_users: "30-80",
    notes: [
      "Backend pool_size=3, max_overflow=1 = max 4 connections per worker",
      "2 uvicorn workers = 8 max backend DB connections",
      "Remaining connections for workers, migrations, admin tools",
      "Redis max_connections=20, 0.3s timeout per operation",
    ],
  },
  scale_up: {
    description: "Horizontal scaling with multiple backend instances",
    backend: "Multiple instances behind Nginx load balancer",
    expected_rps: "100-200",
    expected_concurrent_users: "200-500",
    notes: [
      "Must increase Supabase connection pool",
      "Add Redis Cluster for distributed caching",
      "Implement connection pooling (PgBouncer)",
      "Consider read replicas for product listing queries",
    ],
  },
};

/**
 * Top 20 bottlenecks identified from codebase analysis.
 */
export const IDENTIFIED_BOTTLENECKS = [
  {
    rank: 1,
    area: "Inventory",
    description: "SELECT FOR UPDATE row locks serialize concurrent checkouts on same SKU",
    impact: "HIGH",
    file: "reservation_service.py:56,86",
    mitigation: "Items sorted by (product_id, variant_id) for deadlock prevention",
  },
  {
    rank: 2,
    area: "Database",
    description: "Backend pool_size=3, max_overflow=1 limits concurrent DB operations to 4",
    impact: "HIGH",
    file: "database.py",
    mitigation: "Increase pool_size for higher concurrency",
  },
  {
    rank: 3,
    area: "Cache",
    description: "Product detail pages have NO Redis caching — every view hits DB",
    impact: "MEDIUM",
    file: "catalog/router.py:144",
    mitigation: "Add per-product Redis caching with invalidation on update",
  },
  {
    rank: 4,
    area: "Cache",
    description: "Product list cache uses SHA256 of ALL params — unique params create cache misses",
    impact: "MEDIUM",
    file: "catalog/router.py:38-42",
    mitigation: "Implement cache warming for common filter combinations",
  },
  {
    rank: 5,
    area: "Search",
    description: "Full-text search on every request with fire-and-forget recording",
    impact: "MEDIUM",
    file: "search/router.py:27-41",
    mitigation: "Consider Elasticsearch/Meilisearch for high-volume search",
  },
  {
    rank: 6,
    area: "Cache",
    description: "Redis SCAN-based cache invalidation on checkout can stall under high keyspace",
    impact: "MEDIUM",
    file: "reservation_service.py:110-157",
    mitigation: "Use direct key deletion instead of pattern scan when possible",
  },
  {
    rank: 7,
    area: "Checkout",
    description: "Cart→Order flow involves 3+ sequential DB transactions",
    impact: "MEDIUM",
    file: "orders/service.py:215+",
    mitigation: "Optimize to fewer round-trips where possible",
  },
  {
    rank: 8,
    area: "Workers",
    description: "Media generation worker processes one image at a time (5s interval)",
    impact: "LOW",
    file: "workers/media_generation.py",
    mitigation: "Batch processing, parallel image variant generation",
  },
  {
    rank: 9,
    area: "Database",
    description: "Category tree loads entire hierarchy on every /categories request",
    impact: "LOW",
    file: "categories/router.py:48",
    mitigation: "Redis caching already in place (24h TTL)",
  },
  {
    rank: 10,
    area: "API",
    description: "Slug→ID resolution adds extra query per product list request when filtering by slug",
    impact: "LOW",
    file: "catalog/router.py:78-92",
    mitigation: "Cache slug→ID mappings in Redis",
  },
  {
    rank: 11,
    area: "Auth",
    description: "JWKS cache refreshes every 10 minutes — cold start penalty",
    impact: "LOW",
    file: "jwks.py",
    mitigation: "Pre-warm JWKS cache on startup",
  },
  {
    rank: 12,
    area: "Rate Limiting",
    description: "Redis-backed rate limiter adds ~1ms per request",
    impact: "LOW",
    file: "middleware/rate_limit.py",
    mitigation: "Already well-optimized with sliding window",
  },
  {
    rank: 13,
    area: "CMS",
    description: "Homepage JSON config serialization is CPU-intensive for large sections",
    impact: "LOW",
    file: "cms/service.py",
    mitigation: "Already cached in Redis",
  },
  {
    rank: 14,
    area: "Notifications",
    description: "Notification retry worker polls every 30s — may delay retries",
    impact: "LOW",
    file: "workers/notification_retry.py",
    mitigation: "Use event-driven notifications instead of polling",
  },
  {
    rank: 15,
    area: "Inventory",
    description: "Reservation expiry worker uses SKIP LOCKED — safe but may miss under heavy load",
    impact: "LOW",
    file: "reservation_service.py:662",
    mitigation: "Increase worker frequency during high traffic",
  },
  {
    rank: 16,
    area: "Checkout",
    description: "Razorpay order creation is offloaded to thread pool — adds latency",
    impact: "MEDIUM",
    file: "orders/service.py:316",
    mitigation: "Use async HTTP client instead of sync thread pool",
  },
  {
    rank: 17,
    area: "Database",
    description: "53 Alembic migrations suggest complex schema — potential index fragmentation",
    impact: "LOW",
    file: "alembic/versions/",
    mitigation: "Regular VACUUM and REINDEX on production",
  },
  {
    rank: 18,
    area: "API",
    description: "Product listing endpoint returns heavy response (images, variants, attributes)",
    impact: "MEDIUM",
    file: "catalog/schemas.py",
    mitigation: "Already has include_collections=false option for lightweight listings",
  },
  {
    rank: 19,
    area: "Checkout",
    description: "Payment verification involves HMAC + DB lock + cache invalidation",
    impact: "MEDIUM",
    file: "orders/service.py:377+",
    mitigation: "Already optimized with SAVEPOINT for race condition handling",
  },
  {
    rank: 20,
    area: "Search",
    description: "Autocomplete runs query on every keystroke (debounced on frontend)",
    impact: "LOW",
    file: "search/router.py:49",
    mitigation: "Frontend debounce already in place",
  },
];

/**
 * Top 20 optimizations recommended.
 */
export const RECOMMENDED_OPTIMIZATIONS = [
  { priority: 1, area: "Cache", action: "Add Redis caching for product detail pages (/products/:slug)", effort: "LOW", impact: "HIGH" },
  { priority: 2, area: "Pool", action: "Increase backend pool_size from 3 to 10, max_overflow from 1 to 5", effort: "LOW", impact: "HIGH" },
  { priority: 3, area: "Cache", action: "Cache slug→ID mappings for category_slug and collection_slug filters", effort: "LOW", impact: "MEDIUM" },
  { priority: 4, area: "Search", action: "Add Redis caching for search results (1min TTL, key by search term hash)", effort: "LOW", impact: "MEDIUM" },
  { priority: 5, area: "Cache", action: "Implement cache warming for product listing on cache miss", effort: "MEDIUM", impact: "MEDIUM" },
  { priority: 6, area: "Async", action: "Replace Razorpay sync thread pool with httpx async client", effort: "MEDIUM", impact: "MEDIUM" },
  { priority: 7, area: "Cache", action: "Cache autocomplete suggestions in Redis (30s TTL)", effort: "LOW", impact: "MEDIUM" },
  { priority: 8, area: "Inventory", action: "Batch Redis cache invalidation instead of SCAN-based pattern deletion", effort: "MEDIUM", impact: "MEDIUM" },
  { priority: 9, area: "Pool", action: "Add PgBouncer connection pooler for production", effort: "HIGH", impact: "HIGH" },
  { priority: 10, area: "Search", action: "Introduce Meilisearch/Elasticsearch for full-text search", effort: "HIGH", impact: "HIGH" },
  { priority: 11, area: "Cache", action: "Add response compression (Brotli/gzip) for API responses", effort: "LOW", impact: "MEDIUM" },
  { priority: 12, area: "CDN", action: "Use CDN for product images instead of direct R2/S3 URLs", effort: "MEDIUM", impact: "MEDIUM" },
  { priority: 13, area: "Workers", action: "Parallelize media generation worker for batch processing", effort: "MEDIUM", impact: "LOW" },
  { priority: 14, area: "DB", action: "Add database read replica for product listing queries", effort: "HIGH", impact: "HIGH" },
  { priority: 15, area: "API", action: "Implement API response pagination limits (max 100 items)", effort: "LOW", impact: "LOW" },
  { priority: 16, area: "Cache", action: "Add HTTP cache headers (Cache-Control) for static-like endpoints", effort: "LOW", impact: "MEDIUM" },
  { priority: 17, area: "Monitoring", action: "Add APM (Application Performance Monitoring) for query tracing", effort: "MEDIUM", impact: "MEDIUM" },
  { priority: 18, area: "Workers", action: "Convert notification retry from polling to event-driven", effort: "MEDIUM", impact: "LOW" },
  { priority: 19, area: "Pool", action: "Monitor and alert on connection pool exhaustion", effort: "LOW", impact: "MEDIUM" },
  { priority: 20, area: "Cache", action: "Implement cache stampede protection (singleflight pattern)", effort: "MEDIUM", impact: "MEDIUM" },
];
