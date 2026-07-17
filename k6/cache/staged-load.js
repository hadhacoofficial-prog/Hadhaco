// k6 cache-aware staged load test
// Measures Redis hit rates, pool utilization, SQL queries, and latency
// at progressive load stages.  Polls /health/metrics between stages.
//
// Usage:
//   k6 run cache/staged-load.js
//   k6 run cache/staged-load.js --env STAGES=2,5,10,20,50
//   k6 run cache/staged-load.js --summary-export=cache/results.json

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Trend, Counter, Rate } from "k6/metrics";
import { apiGet, apiPost, think } from "../helpers/http.js";
import { devLogin, generateSessionId } from "../helpers/auth.js";

// ── Custom metrics ────────────────────────────────────────────────────────────

const cacheHitLatency = new Trend("cache_hit_latency", true);
const cacheMissLatency = new Trend("cache_miss_latency", true);
const poolWaitTime = new Trend("pool_wait_ms", true);

// ── Config ────────────────────────────────────────────────────────────────────

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const STAGE_DURATION = __ENV.STAGE_DURATION || "2m";
const STAGES = (__ENV.STAGES || "2,5,10,20,50").split(",").map(Number);
const WARMUP_SECONDS = 15;

// Build ramping stages: for each target, ramp up, hold, ramp down to next
function buildStages() {
  const result = [];
  let prev = 0;
  for (const target of STAGES) {
    result.push({ duration: "30s", target: prev }); // ramp
    result.push({ duration: STAGE_DURATION, target: target }); // hold
    prev = target;
  }
  result.push({ duration: "30s", target: 0 }); // ramp down
  return result;
}

export const options = {
  scenarios: {
    staged_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: buildStages(),
      exec: "userJourney",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<800", "p(99)<2000", "max<5000"],
    http_req_failed: ["rate<0.02"],
  },
};

// ── Data ──────────────────────────────────────────────────────────────────────

let allProducts = [];
let allSlugs = [];
let allCategories = [];

export function setup() {
  // Load product data
  const { body: pBody } = apiGet(
    "/products",
    { query: { page: 1, page_size: 50, include_collections: false } },
    { name: "cache_setup_products" }
  );
  if (pBody && pBody.data && pBody.data.items) {
    allProducts = pBody.data.items.filter((p) => p.stock_quantity > 0);
    allSlugs = allProducts.map((p) => p.slug);
  }

  // Load categories
  const { body: cBody } = apiGet("/categories/navbar", {}, {
    name: "cache_setup_categories",
  });
  if (cBody && cBody.data) {
    allCategories = cBody.data;
  }

  // Warm up caches
  console.log("Warming caches...");
  apiGet("/products", { query: { page: 1, page_size: 20 } }, { name: "warmup_products" });
  apiGet("/categories", {}, { name: "warmup_categories" });
  apiGet("/categories/navbar", {}, { name: "warmup_navbar" });
  apiGet("/collections", {}, { name: "warmup_collections" });
  apiGet("/cms/homepage", {}, { name: "warmup_homepage" });
  apiGet("/search", { query: { q: "silver" } }, { name: "warmup_search" });
  apiGet("/search/trending", {}, { name: "warmup_trending" });

  if (allSlugs.length > 0) {
    apiGet(`/products/${allSlugs[0]}`, {}, { name: "warmup_detail" });
  }

  // Capture initial metrics
  const initialMetrics = getMetrics();
  console.log("Initial metrics: " + JSON.stringify(initialMetrics));

  return {
    products: allProducts,
    slugs: allSlugs,
    categories: allCategories,
    metricsSnapshots: [],
    initialMetrics: initialMetrics,
  };
}

// ── Metrics collection ────────────────────────────────────────────────────────

function getMetrics() {
  const res = http.get(`${BASE}/health/metrics`, { timeout: "5s" });
  try {
    return JSON.parse(res.body);
  } catch {
    return null;
  }
}

function getPoolStatus() {
  const res = http.get(`${BASE}/health/ready`, { timeout: "5s" });
  try {
    const data = JSON.parse(res.body);
    return data.pool || {};
  } catch {
    return {};
  }
}

// ── User journey (mixed traffic) ─────────────────────────────────────────────

export function userJourney(data) {
  const products = data.products || allProducts;
  const slugs = data.slugs || allSlugs;
  const categories = data.categories || allCategories;

  if (products.length === 0) return;

  const userType = Math.random();
  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  if (userType < 0.35) {
    browserReads(data, headers);
  } else if (userType < 0.6) {
    searchBrowsing(data, headers);
  } else if (userType < 0.8) {
    productDeepDive(data, headers);
  } else {
    cartInteraction(data, headers);
  }
}

// 35% — Pure reads (homepage + browse + detail)
function browserReads(data, headers) {
  apiGet("/cms/homepage", {}, { name: "cache_homepage" });
  think(2);

  apiGet("/categories", {}, { name: "cache_categories" });
  think(1);

  apiGet("/products", { query: { page: 1, page_size: 20 } }, { name: "cache_products" });
  think(3);

  if (data.slugs && data.slugs.length > 0) {
    const slug = data.slugs[Math.floor(Math.random() * data.slugs.length)];
    apiGet(`/products/${slug}`, {}, { name: "cache_product_detail" });
    think(4);
  }

  apiGet("/collections", {}, { name: "cache_collections" });
  think(1);
}

// 25% — Search-heavy (search + autocomplete + trending)
function searchBrowsing(data, headers) {
  const terms = ["ring", "necklace", "bracelet", "earring", "silver", "gold"];
  const term = terms[Math.floor(Math.random() * terms.length)];

  apiGet("/search", { query: { q: term, page: 1 } }, { name: "cache_search" });
  think(2);

  apiGet("/search/autocomplete", { query: { q: term.substring(0, 3), limit: 8 } }, {
    name: "cache_autocomplete",
  });
  think(1);

  apiGet("/search/trending", {}, { name: "cache_trending" });
  think(1);

  if (data.slugs && data.slugs.length > 0) {
    const slug = data.slugs[Math.floor(Math.random() * data.slugs.length)];
    apiGet(`/products/${slug}`, {}, { name: "cache_search_product" });
    think(3);
  }
}

// 20% — Product deep-dive (detail + reviews + related)
function productDeepDive(data, headers) {
  if (data.slugs && data.slugs.length > 0) {
    const slug = data.slugs[Math.floor(Math.random() * data.slugs.length)];
    apiGet(`/products/${slug}`, {}, { name: "cache_pd_detail" });
    think(3);

    if (data.products && data.products.length > 0) {
      const pid = data.products[0].id;
      apiGet(`/reviews/products/${pid}/summary`, {}, { name: "cache_pd_reviews" });
      think(2);
    }
  }

  apiGet("/categories/navbar", {}, { name: "cache_pd_navbar" });
  think(1);

  apiGet("/products", { query: { page: 1, page_size: 5 } }, { name: "cache_pd_related" });
  think(2);

  apiGet("/cms/homepage", {}, { name: "cache_pd_homepage" });
  think(1);
}

// 20% — Cart interaction (browse + add to cart + view cart)
function cartInteraction(data, headers) {
  apiGet("/products", { query: { page: 1, page_size: 20 } }, { name: "cache_cart_browse" });
  think(2);

  if (data.products && data.products.length > 0) {
    const product = data.products[Math.floor(Math.random() * data.products.length)];

    // Add to cart
    apiPost(
      "/cart/items",
      { product_id: product.id, variant_id: product.variant_id || null, quantity: 1 },
      { headers },
      { name: "cache_cart_add" }
    );
    think(1);

    // View cart
    apiGet("/cart", { headers }, { name: "cache_cart_view" });
    think(2);
  }

  apiGet("/categories/navbar", {}, { name: "cache_cart_navbar" });
  think(1);
}

// ── Teardown: final metrics snapshot ──────────────────────────────────────────

export function teardown(data) {
  const finalMetrics = getMetrics();
  console.log("\n=== FINAL METRICS ===");
  console.log(JSON.stringify(finalMetrics, null, 2));

  if (data && data.initialMetrics && finalMetrics) {
    const pBefore = data.initialMetrics.pool || {};
    const pAfter = finalMetrics.pool || {};
    const sBefore = data.initialMetrics.sql || {};
    const sAfter = finalMetrics.sql || {};
    const rBefore = data.initialMetrics.redis || {};
    const rAfter = finalMetrics.redis || {};

    console.log("\n=== DELTA ===");
    console.log(`Pool peak: ${pBefore.peak_checked_out || 0} -> ${pAfter.peak_checked_out || 0} (cap=${pAfter.capacity || "?"})`);
    console.log(`Pool waits: ${pAfter.total_checkout_waits || 0} (max_wait=${pAfter.max_wait_ms || 0}ms)`);
    console.log(`SQL queries: ${sBefore.total_queries || 0} -> ${sAfter.total_queries || 0} (delta=${(sAfter.total_queries || 0) - (sBefore.total_queries || 0)})`);
    console.log(`SQL avg: ${sAfter.avg_ms || 0}ms, slow: ${sAfter.slow_queries || 0}`);
    console.log(`Redis calls: ${rBefore.total_calls || 0} -> ${rAfter.total_calls || 0} (delta=${(rAfter.total_calls || 0) - (rBefore.total_calls || 0)})`);
    console.log(`Redis avg: ${rAfter.avg_ms || 0}ms, max: ${rAfter.max_ms || 0}ms, errors: ${rAfter.errors || 0}`);
  }
}
