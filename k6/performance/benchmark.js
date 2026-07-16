// k6 performance benchmark — Comprehensive API performance profiling
// Profiles every storefront endpoint with custom metrics collection
// Generates JSON summary for report generation
//
// Usage:
//   k6 run performance/benchmark.js
//   k6 run --out json=results/benchmark-raw.json performance/benchmark.js

import { check, group } from "k6";
import { Counter } from "k6/metrics";
import { apiGet, apiPost, apiDelete, think } from "../helpers/http.js";
import { generateSessionId } from "../helpers/auth.js";
import {
  recordResponse,
  cartAddSuccessRate,
  searchSuccessRate,
  productViewSuccessRate,
  businessCheck,
} from "../helpers/metrics.js";

export const options = {
  scenarios: {
    read_heavy: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 10 },
        { duration: "2m", target: 25 },
        { duration: "3m", target: 50 },
        { duration: "2m", target: 50 },
        { duration: "1m", target: 0 },
      ],
      exec: "readProfile",
      tags: { scenario: "read_heavy" },
    },
    write_mixed: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 5 },
        { duration: "2m", target: 15 },
        { duration: "3m", target: 30 },
        { duration: "2m", target: 30 },
        { duration: "1m", target: 0 },
      ],
      exec: "writeProfile",
      tags: { scenario: "write_mixed" },
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<2000", "p(99)<5000"],
    http_req_failed: ["rate<0.15"],
    api_success_rate: ["rate>0.80"],
    status_5xx: ["count<50"],
  },
};

let products = [];
let slugs = [];

const results = { endpoints: {} };

export function setup() {
  const { raw, body } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "setup_products" });
  recordResponse(raw, "/products");

  if (body && body.data && body.data.items) {
    products = body.data.items.filter((p) => p.stock_quantity > 0);
    slugs = products.map((p) => p.slug);
  }
  return { products, slugs };
}

// ── READ PROFILE ──────────────────────────────────────────────────────────────

export function readProfile(data) {
  const prods = data.products || products;
  const sl = data.slugs || slugs;
  if (prods.length === 0) return;

  group("Read — Products List", () => {
    const { raw } = apiGet("/products", {
      query: { page: 1, page_size: 20, include_collections: false },
    }, { name: "bench_products" });
    recordResponse(raw, "/products");
    check(raw, { "products list 2xx": (r) => r.status >= 200 && r.status < 300 });
  });
  think(0.5);

  group("Read — Product Detail", () => {
    const slug = sl[Math.floor(Math.random() * sl.length)];
    const { raw, body } = apiGet(`/products/${slug}`, {}, { name: "bench_product_detail" });
    recordResponse(raw, "/products");
    const ok = check(raw, { "product detail 2xx": (r) => r.status >= 200 && r.status < 300 });
    businessCheck("product_view", () => ok, (v) => productViewSuccessRate.add(v));
  });
  think(0.5);

  group("Read — Search", () => {
    const queries = ["ring", "silver", "bracelet", "gold", "necklace"];
    const q = queries[Math.floor(Math.random() * queries.length)];
    const { raw } = apiGet("/search", {
      query: { q: q, page: 1 },
    }, { name: "bench_search" });
    recordResponse(raw, "/search");
    const ok = check(raw, { "search 2xx": (r) => r.status >= 200 && r.status < 300 });
    businessCheck("search", () => ok, (v) => searchSuccessRate.add(v));
  });
  think(0.5);

  group("Read — Homepage", () => {
    const { raw } = apiGet("/cms/homepage", {}, { name: "bench_homepage" });
    recordResponse(raw, "/cms/homepage");
    check(raw, { "homepage 2xx": (r) => r.status >= 200 && r.status < 300 });
  });
  think(0.5);

  group("Read — Categories", () => {
    const { raw } = apiGet("/categories/navbar", {}, { name: "bench_categories" });
    recordResponse(raw, "/categories");
    check(raw, { "categories 2xx": (r) => r.status >= 200 && r.status < 300 });
  });
  think(0.3);

  group("Read — Collections", () => {
    const { raw } = apiGet("/collections", {}, { name: "bench_collections" });
    recordResponse(raw, "/collections");
    check(raw, { "collections 2xx": (r) => r.status >= 200 && r.status < 300 });
  });
  think(0.5);

  group("Read — Filtered Products", () => {
    const { raw } = apiGet("/products", {
      query: { page: 1, page_size: 12, metal_type: "925 Silver", include_collections: false },
    }, { name: "bench_products_filtered" });
    recordResponse(raw, "/products");
    check(raw, { "filtered products 2xx": (r) => r.status >= 200 && r.status < 300 });
  });
  think(0.3);

  group("Read — Featured Products", () => {
    const { raw } = apiGet("/products", {
      query: { page: 1, page_size: 8, is_featured: true, include_collections: false },
    }, { name: "bench_products_featured" });
    recordResponse(raw, "/products");
    check(raw, { "featured products 2xx": (r) => r.status >= 200 && r.status < 300 });
  });
  think(0.5);
}

// ── WRITE PROFILE ─────────────────────────────────────────────────────────────

export function writeProfile(data) {
  const prods = data.products || products;
  if (prods.length === 0) return;

  const product = prods[Math.floor(Math.random() * prods.length)];
  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  group("Write — Add to Cart", () => {
    const { raw } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id || null,
      quantity: 1,
    }, { headers }, { name: "bench_cart_add" });
    recordResponse(raw, "/cart");
    const ok = check(raw, {
      "cart add — 200 or 409": (r) => r.status === 200 || r.status === 409,
    });
    businessCheck("cart_add", () => ok, (v) => cartAddSuccessRate.add(v));
  });
  think(0.5);

  group("Write — View Cart", () => {
    const { raw } = apiGet("/cart", { headers }, { name: "bench_cart_view" });
    recordResponse(raw, "/cart");
    check(raw, { "cart view 2xx": (r) => r.status >= 200 && r.status < 300 });
  });
  think(0.5);

  group("Write — Attempt Checkout (no auth)", () => {
    const { raw } = apiPost("/orders/create-payment", {
      shipping_address_id: null,
      billing_address_id: null,
      notes: "benchmark test",
    }, { headers }, { name: "bench_checkout" });
    recordResponse(raw, "/orders/create-payment");
    check(raw, {
      "checkout — responds": (r) => [200, 401, 409, 422].includes(r.status),
    });
  });
  think(1);

  group("Write — Cart Operations", () => {
    const { raw } = apiGet("/cart", { headers }, { name: "bench_cart_check" });
    recordResponse(raw, "/cart");
    check(raw, { "cart check 2xx": (r) => r.status >= 200 && r.status < 300 });
  });
  think(0.3);

  group("Write — Cleanup", () => {
    const { raw } = apiDelete("/cart", { headers }, { name: "bench_cart_cleanup" });
    recordResponse(raw, "/cart");
  });
  think(0.5);
}

export function teardown() {}
