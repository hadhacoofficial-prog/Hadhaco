// k6 scenario — Stress test: Push beyond normal capacity
// Ramps to 100-200 VUs to find breaking points
// Duration: 15 minutes

import { check, group } from "k6";
import { apiGet, apiPost, apiDelete, think } from "../helpers/http.js";
import { generateSessionId } from "../helpers/auth.js";

export const options = {
  scenarios: {
    stress_read: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 50 },
        { duration: "3m", target: 100 },
        { duration: "3m", target: 150 },
        { duration: "2m", target: 200 },
        { duration: "3m", target: 200 },
        { duration: "2m", target: 0 },
      ],
      exec: "stressRead",
      tags: { scenario: "stress_read" },
    },
    stress_write: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 20 },
        { duration: "3m", target: 50 },
        { duration: "3m", target: 75 },
        { duration: "2m", target: 100 },
        { duration: "3m", target: 100 },
        { duration: "2m", target: 0 },
      ],
      exec: "stressWrite",
      tags: { scenario: "stress_write" },
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<3000", "p(99)<8000", "max<20000"],
    http_req_failed: ["rate<0.10"],
  },
};

let products = [];
let slugs = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "stress_setup" });
  if (body && body.data && body.data.items) {
    products = body.data.items.filter((p) => p.stock_quantity > 0);
    slugs = products.map((p) => p.slug);
  }
  return { products, slugs };
}

export function stressRead(data) {
  const prods = data.products || products;
  const sl = data.slugs || slugs;
  if (prods.length === 0) return;

  group("Stress — Read Operations", () => {
    // Product listing (heaviest read query)
    const { body: listBody } = apiGet("/products", {
      query: { page: 1, page_size: 20 },
    }, { name: "stress_product_list" });
    check(listBody, {
      "stress product list — success": (b) => b && b.success === true,
    });
    think(0.2);

    // Product detail
    if (sl.length > 0) {
      const { body: detailBody } = apiGet(`/products/${sl[Math.floor(Math.random() * sl.length)]}`, {}, {
        name: "stress_product_detail",
      });
      check(detailBody, {
        "stress product detail — success": (b) => b && b.success === true,
      });
    }
    think(0.2);

    // Search
    const { body: searchBody } = apiGet("/search", {
      query: { q: "ring", page: 1 },
    }, { name: "stress_search" });
    check(searchBody, {
      "stress search — success": (b) => b && b.success === true,
    });
    think(0.2);

    // Homepage
    const { body: homeBody } = apiGet("/cms/homepage", {}, { name: "stress_homepage" });
    check(homeBody, {
      "stress homepage — success": (b) => b && b.success === true,
    });
    think(0.3);

    // Categories
    const { body: catBody } = apiGet("/categories/navbar", {}, { name: "stress_categories" });
    check(catBody, {
      "stress categories — success": (b) => b && b.success === true,
    });
    think(0.2);

    // Collections
    const { body: colBody } = apiGet("/collections", {}, { name: "stress_collections" });
    check(colBody, {
      "stress collections — success": (b) => b && b.success === true,
    });
    think(0.3);
  });
}

export function stressWrite(data) {
  const prods = data.products || products;
  if (prods.length === 0) return;

  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  group("Stress — Write Operations", () => {
    const product = prods[Math.floor(Math.random() * prods.length)];

    // Add to cart
    const { raw: addRaw, body: addBody } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id || null,
      quantity: 1,
    }, { headers }, { name: "stress_cart_add" });
    check(addRaw, {
      "stress cart add — 200 or 409": (r) => r.status === 200 || r.status === 409,
    });
    think(0.3);

    // View cart
    const { body: cartBody } = apiGet("/cart", { headers }, { name: "stress_cart_view" });
    check(cartBody, {
      "stress cart view — success": (b) => b && b.success === true,
    });
    think(0.3);

    // Attempt checkout
    const { raw: payRaw } = apiPost("/orders/create-payment", {
      shipping_address_id: null,
      billing_address_id: null,
      notes: "stress test",
    }, { headers }, { name: "stress_checkout" });
    check(payRaw, {
      "stress checkout — responds": (r) => [200, 401, 409, 422].includes(r.status),
    });
    think(0.5);

    // Cleanup
    apiDelete("/cart", { headers }, { name: "stress_cleanup" });
  });
}
