// k6 shared — API endpoint ranking and performance report generator
// Generates a ranked list of all tested endpoints by latency

import { group } from "k6";

/**
 * Expected API performance rankings based on codebase analysis.
 *
 * Tiers:
 * - Tier 1 (Critical): <200ms p95 — Product list, search, cart, homepage
 * - Tier 2 (Important): <400ms p95 — Product detail, category, collection
 * - Tier 3 (Moderate): <800ms p95 — Checkout, payment, order creation
 * - Tier 4 (Background): <2000ms p95 — Reports, analytics, admin
 */
export const API_RANKINGS = {
  // ── Tier 1: Critical read paths (heavily cached) ─────────────────────────
  tier1_critical: {
    description: "Heavily cached, must be sub-200ms",
    endpoints: [
      { method: "GET", path: "/cms/homepage", cache: "Redis 5min", criticality: "CRITICAL" },
      { method: "GET", path: "/categories/navbar", cache: "Redis 24h", criticality: "CRITICAL" },
      { method: "GET", path: "/categories/navigation", cache: "Redis 24h", criticality: "CRITICAL" },
      { method: "GET", path: "/collections", cache: "Redis 15min", criticality: "CRITICAL" },
      { method: "GET", path: "/search/trending", cache: "DB query", criticality: "HIGH" },
      { method: "GET", path: "/settings/flags/:key", cache: "DB query", criticality: "MEDIUM" },
    ],
  },

  // ── Tier 2: Product browsing ──────────────────────────────────────────────
  tier2_browsing: {
    description: "Core browsing — Redis cached with query param hashing",
    endpoints: [
      { method: "GET", path: "/products", cache: "Redis 5min (param hash)", criticality: "CRITICAL" },
      { method: "GET", path: "/products/:slug", cache: "DB query", criticality: "CRITICAL" },
      { method: "GET", path: "/categories", cache: "Redis 24h", criticality: "HIGH" },
      { method: "GET", path: "/collections/:slug", cache: "DB query", criticality: "HIGH" },
      { method: "GET", path: "/search", cache: "DB full-text", criticality: "CRITICAL" },
      { method: "GET", path: "/search/autocomplete", cache: "DB query", criticality: "HIGH" },
      { method: "GET", path: "/reviews/products/:id", cache: "DB query", criticality: "MEDIUM" },
      { method: "GET", path: "/reviews/products/:id/summary", cache: "DB aggregation", criticality: "MEDIUM" },
      { method: "GET", path: "/seo/page", cache: "DB query", criticality: "LOW" },
    ],
  },

  // ── Tier 3: Cart & Checkout (write operations) ────────────────────────────
  tier3_checkout: {
    description: "Write operations — Redis cache invalidation, DB locks",
    endpoints: [
      { method: "GET", path: "/cart", cache: "DB query", criticality: "CRITICAL" },
      { method: "POST", path: "/cart/items", cache: "None (write)", criticality: "CRITICAL" },
      { method: "PATCH", path: "/cart/:id/items/:id", cache: "None (write)", criticality: "HIGH" },
      { method: "DELETE", path: "/cart/:id/items/:id", cache: "None (write)", criticality: "HIGH" },
      { method: "DELETE", path: "/cart", cache: "None (write)", criticality: "MEDIUM" },
      { method: "POST", path: "/coupons/validate", cache: "DB query", criticality: "HIGH" },
      { method: "POST", path: "/orders/create-payment", cache: "SELECT FOR UPDATE", criticality: "CRITICAL" },
      { method: "POST", path: "/orders/verify-payment", cache: "SELECT FOR UPDATE", criticality: "CRITICAL" },
      { method: "POST", path: "/cart/merge", cache: "None (write)", criticality: "MEDIUM" },
    ],
  },

  // ── Tier 4: Authenticated user operations ─────────────────────────────────
  tier4_account: {
    description: "Authenticated — profile caching in Redis 60s",
    endpoints: [
      { method: "GET", path: "/me", cache: "Redis 60s", criticality: "HIGH" },
      { method: "PATCH", path: "/me", cache: "None (write)", criticality: "MEDIUM" },
      { method: "GET", path: "/me/addresses", cache: "DB query", criticality: "MEDIUM" },
      { method: "POST", path: "/me/addresses", cache: "None (write)", criticality: "LOW" },
      { method: "GET", path: "/me/wishlist", cache: "DB query", criticality: "MEDIUM" },
      { method: "POST", path: "/me/wishlist/toggle", cache: "None (write)", criticality: "MEDIUM" },
      { method: "GET", path: "/orders", cache: "DB query", criticality: "HIGH" },
      { method: "GET", path: "/orders/:id", cache: "DB query", criticality: "HIGH" },
      { method: "GET", path: "/orders/active-reservations", cache: "DB query", criticality: "MEDIUM" },
      { method: "POST", path: "/dev/login", cache: "None (auth)", criticality: "CRITICAL" },
      { method: "GET", path: "/auth/verify-token", cache: "JWKS cache", criticality: "CRITICAL" },
    ],
  },

  // ── Tier 5: Background/async operations ───────────────────────────────────
  tier5_background: {
    description: "Notification preferences, support, returns — lower priority",
    endpoints: [
      { method: "GET", path: "/notifications/preferences", cache: "DB query", criticality: "LOW" },
      { method: "POST", path: "/enquiries", cache: "None (write)", criticality: "LOW" },
      { method: "POST", path: "/returns", cache: "None (write)", criticality: "LOW" },
      { method: "GET", path: "/returns", cache: "DB query", criticality: "LOW" },
      { method: "POST", path: "/support/tickets", cache: "None (write)", criticality: "LOW" },
      { method: "GET", path: "/support/tickets", cache: "DB query", criticality: "LOW" },
    ],
  },
};

/**
 * Database dependencies per endpoint (from codebase analysis).
 */
export const DB_DEPENDENCIES = {
  "/products": {
    tables: ["products", "product_variants", "product_attributes", "images", "product_collections"],
    query_type: "Paginated SELECT with optional JOINs",
    index_usage: "category_id, collection_id, status, gender, metal_type, base_price",
    cache: "Redis — SHA256 hash of all params, 5min TTL",
    concern: "Slug→ID resolution adds extra query when category_slug/collection_slug used",
  },
  "/products/:slug": {
    tables: ["products", "product_variants", "product_attributes", "images", "reviews"],
    query_type: "Single SELECT with JOINs",
    index_usage: "slug (unique)",
    cache: "None (per-product cache not implemented)",
    concern: "N+1 risk if variants/images loaded separately",
  },
  "/search": {
    tables: ["products", "search_queries"],
    query_type: "Full-text search (to_tsvector/to_tsquery)",
    index_usage: "GIN index on tsvector column",
    cache: "None",
    concern: "Fire-and-forget search recording adds async write",
  },
  "/orders/create-payment": {
    tables: ["carts", "cart_items", "products", "product_variants", "inventory_reservations", "inventory_transactions", "orders", "order_items"],
    query_type: "SELECT FOR UPDATE (row locks)",
    index_usage: "Primary keys, (product_id, variant_id) for lock ordering",
    cache: "Redis invalidation after reservation",
    concern: "Row-level locks serialize concurrent checkouts on same SKU",
  },
  "/cart/items": {
    tables: ["carts", "cart_items", "products", "product_variants"],
    query_type: "INSERT/UPDATE with upsert logic",
    index_usage: "Primary keys, user_id/session_id indexes",
    cache: "None",
    concern: "Cart merging on login can cause contention",
  },
  "/cms/homepage": {
    tables: ["landing_sections", "landing_section_items", "banners"],
    query_type: "SELECT active sections with config",
    index_usage: "section_key, is_active, sort_order",
    cache: "Redis — 'cms:homepage' key, configurable TTL",
    concern: "Heavy JSON config serialization",
  },
};

/**
 * Redis key patterns and their TTLs.
 */
export const REDIS_KEY_PATTERNS = {
  "products:list:v1:{hash}": { ttl: "300s (5min)", description: "Product listing cache — SHA256 of query params" },
  "cms:homepage": { ttl: "Configurable", description: "Homepage CMS data" },
  "profile:v1:{user_id}": { ttl: "60s", description: "User profile cache (dependency injection)" },
  "rl:{prefix}:{ip}:{path}": { ttl: "60s", description: "Rate limiter sliding window" },
  "admin:2fa_lockout:{user_id}": { ttl: "900s (15min)", description: "2FA brute-force lockout" },
  "admin:session_tracked:{session_id}": { ttl: "43200s (12h)", description: "Session activity dedup" },
  "admin:login_logged:{session_id}": { ttl: "43200s (12h)", description: "Login audit dedup" },
};

/**
 * Background workers and their intervals.
 */
export const WORKER_SCHEDULES = {
  reservation_expiry: { interval: "60s", description: "Expires ACTIVE reservations past TTL, releases stock" },
  cms_publish: { interval: "60s", description: "Promotes scheduled CMS sections to published" },
  media_generation: { interval: "5s", description: "Image variant processing (async + periodic)" },
  notification_retry: { interval: "30s", description: "Retries failed notifications" },
  partition_manager: { interval: "Monthly (1st, 00:10 UTC)", description: "Creates next month's DB partitions" },
  admin_session_cleanup: { interval: "Hourly", description: "Deletes expired AdminSession rows" },
};
