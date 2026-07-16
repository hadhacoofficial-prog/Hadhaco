// k6 comprehensive scenario runner
// Orchestrates all test suites with configurable scenarios
//
// Usage:
//   k6 run scenarios/full-storefront.js
//   k6 run --env SCENARIO=smoke scenarios/full-storefront.js
//   k6 run --env SCENARIO=load scenarios/full-storefront.js
//   k6 run --env SCENARIO=stress scenarios/full-storefront.js
//   k6 run --env SCENARIO=spike scenarios/full-storefront.js
//   k6 run --env SCENARIO=soak scenarios/full-storefront.js
//   k6 run --env SCENARIO=concurrency scenarios/full-storefront.js

import { check, group } from "k6";
import http from "k6/http";
import { apiGet, apiPost, apiDelete, apiUrl, think } from "../helpers/http.js";
import { devLogin, generateSessionId } from "../helpers/auth.js";

const SCENARIO = __ENV.SCENARIO || "smoke";

// ── Scenario configurations ──────────────────────────────────────────────────

const scenarios = {
  smoke: {
    health: { vus: 1, duration: "30s", exec: "healthCheck" },
    products: { vus: 2, duration: "1m", exec: "browseProducts" },
    search: { vus: 2, duration: "1m", exec: "searchProducts" },
  },

  load: {
    mixed: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 10 },
        { duration: "3m", target: 30 },
        { duration: "3m", target: 50 },
        { duration: "2m", target: 20 },
        { duration: "1m", target: 0 },
      ],
      exec: "fullJourney",
    },
  },

  stress: {
    reads: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 50 },
        { duration: "3m", target: 100 },
        { duration: "3m", target: 150 },
        { duration: "2m", target: 0 },
      ],
      exec: "stressReads",
    },
    writes: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 20 },
        { duration: "3m", target: 50 },
        { duration: "3m", target: 80 },
        { duration: "2m", target: 0 },
      ],
      exec: "stressWrites",
    },
  },

  spike: {
    surge: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 5 },
        { duration: "5s", target: 200 },
        { duration: "2m", target: 200 },
        { duration: "5s", target: 5 },
        { duration: "2m", target: 5 },
        { duration: "30s", target: 0 },
      ],
      exec: "spikeUser",
    },
  },

  soak: {
    endurance: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "5m", target: 30 },
        { duration: "30m", target: 30 },
        { duration: "5m", target: 0 },
      ],
      exec: "soakUser",
    },
  },

  concurrency: {
    inventory: {
      executor: "per-vu-iterations",
      vus: 100,
      iterations: 1,
      maxDuration: "5m",
      exec: "inventoryRace",
    },
  },
};

export const options = {
  scenarios: scenarios[SCENARIO] || scenarios.smoke,
  thresholds: {
    http_req_duration: ["p(95)<1000", "p(99)<3000", "max<10000"],
    http_req_failed: ["rate<0.05"],
    http_reqs: ["rate>5"],
  },
};

// ── Shared state ─────────────────────────────────────────────────────────────

let products = [];
let slugs = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "runner_setup" });
  if (body && body.data && body.data.items) {
    products = body.data.items.filter((p) => p.stock_quantity > 0);
    slugs = products.map((p) => p.slug);
  }
  return { products, slugs };
}

// ── Health Check ─────────────────────────────────────────────────────────────

export function healthCheck() {
  const baseUrl = __ENV.BASE_URL || "http://localhost:8000";
  const res = http.get(`${baseUrl}/health`, { timeout: "5s" });
  check(res, { "health — 200": (r) => r.status === 200 });
}

// ── Browse Products ──────────────────────────────────────────────────────────

export function browseProducts() {
  apiGet("/products", { query: { page: 1, page_size: 20 } }, { name: "runner_products" });
  think(0.5);
  if (slugs.length > 0) {
    apiGet(`/products/${slugs[Math.floor(Math.random() * slugs.length)]}`, {}, {
      name: "runner_product_detail",
    });
  }
  think(0.5);
}

// ── Search ───────────────────────────────────────────────────────────────────

export function searchProducts() {
  const terms = ["ring", "necklace", "bracelet", "earring", "silver"];
  const term = terms[Math.floor(Math.random() * terms.length)];
  apiGet("/search", { query: { q: term, page: 1 } }, { name: "runner_search" });
  think(0.5);
  apiGet("/search/autocomplete", { query: { q: term.substring(0, 3), limit: 8 } }, {
    name: "runner_autocomplete",
  });
  think(0.5);
}

// ── Full Journey ─────────────────────────────────────────────────────────────

export function fullJourney(data) {
  const prods = data.products || products;
  const sl = data.slugs || slugs;
  if (prods.length === 0) return;

  const product = prods[Math.floor(Math.random() * prods.length)];
  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  // Homepage
  apiGet("/cms/homepage", {}, { name: "runner_homepage" });
  think(1);

  // Browse
  apiGet("/products", { query: { page: 1, page_size: 20 } }, { name: "runner_browse" });
  think(2);

  // Product detail
  if (sl.length > 0) {
    apiGet(`/products/${sl[Math.floor(Math.random() * sl.length)]}`, {}, {
      name: "runner_detail",
    });
  }
  think(2);

  // Search
  apiGet("/search", { query: { q: "ring", page: 1 } }, { name: "runner_search" });
  think(1);

  // Cart
  apiPost("/cart/items", {
    product_id: product.id,
    variant_id: product.variant_id || null,
    quantity: 1,
  }, { headers }, { name: "runner_cart_add" });
  think(1);

  apiGet("/cart", { headers }, { name: "runner_cart_view" });
  think(1);

  // Cleanup
  apiDelete("/cart", { headers }, { name: "runner_cleanup" });
  think(1);
}

// ── Stress Read ──────────────────────────────────────────────────────────────

export function stressReads(data) {
  const sl = data.slugs || slugs;
  apiGet("/products", { query: { page: 1, page_size: 20 } }, { name: "runner_stress_products" });
  think(0.1);
  if (sl.length > 0) {
    apiGet(`/products/${sl[Math.floor(Math.random() * sl.length)]}`, {}, {
      name: "runner_stress_detail",
    });
  }
  think(0.1);
  apiGet("/search", { query: { q: "silver", page: 1 } }, { name: "runner_stress_search" });
  think(0.1);
  apiGet("/cms/homepage", {}, { name: "runner_stress_homepage" });
  think(0.2);
}

// ── Stress Write ─────────────────────────────────────────────────────────────

export function stressWrites(data) {
  const prods = data.products || products;
  if (prods.length === 0) return;

  const product = prods[Math.floor(Math.random() * prods.length)];
  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  apiPost("/cart/items", {
    product_id: product.id,
    variant_id: product.variant_id || null,
    quantity: 1,
  }, { headers }, { name: "runner_stress_cart_add" });
  think(0.2);
  apiGet("/cart", { headers }, { name: "runner_stress_cart" });
  think(0.2);
  apiDelete("/cart", { headers }, { name: "runner_stress_cleanup" });
  think(0.3);
}

// ── Spike ────────────────────────────────────────────────────────────────────

export function spikeUser(data) {
  const prods = data.products || products;
  const sl = data.slugs || slugs;
  if (prods.length === 0) return;

  const product = prods[Math.floor(Math.random() * prods.length)];
  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  apiGet("/cms/homepage", {}, { name: "runner_spike_homepage" });
  think(0.3);
  apiGet("/products", { query: { page: 1, page_size: 8, is_featured: true, include_collections: false } }, {
    name: "runner_spike_featured",
  });
  think(0.5);
  if (sl.length > 0) {
    apiGet(`/products/${sl[Math.floor(Math.random() * sl.length)]}`, {}, {
      name: "runner_spike_detail",
    });
  }
  think(1);
  apiPost("/cart/items", {
    product_id: product.id,
    variant_id: product.variant_id || null,
    quantity: 1,
  }, { headers }, { name: "runner_spike_cart" });
  think(0.5);
  apiDelete("/cart", { headers }, { name: "runner_spike_cleanup" });
}

// ── Soak ─────────────────────────────────────────────────────────────────────

export function soakUser(data) {
  fullJourney(data);
  think(3);
}

// ── Inventory Race ───────────────────────────────────────────────────────────

export function inventoryRace(data) {
  const prods = data.products || products;
  if (prods.length === 0) return;

  const product = prods[Math.floor(Math.random() * prods.length)];
  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  apiPost("/cart/items", {
    product_id: product.id,
    variant_id: product.variant_id || null,
    quantity: 1,
  }, { headers }, { name: "runner_inventory_cart" });
  think(0.1);

  const { body } = apiPost("/orders/create-payment", {
    shipping_address_id: null,
    billing_address_id: null,
    notes: `k6 inventory race VU${__VU}`,
  }, { headers }, { name: "runner_inventory_checkout" });

  if (body && body.success) {
    check(null, { "inventory — purchase succeeded": () => true });
  }

  apiDelete("/cart", { headers }, { name: "runner_inventory_cleanup" });
}
