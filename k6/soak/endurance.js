// k6 scenario — Soak test: Endurance under sustained load
// 30 minutes at moderate load to detect memory leaks, connection pool exhaustion
// Duration: 35 minutes (5 min ramp + 30 min soak)

import { check, group } from "k6";
import { apiGet, apiPost, apiDelete, think } from "../helpers/http.js";
import { generateSessionId } from "../helpers/auth.js";

export const options = {
  scenarios: {
    soak_traffic: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "5m", target: 30 },    // Ramp up
        { duration: "30m", target: 30 },   // Sustained load
        { duration: "5m", target: 0 },     // Ramp down
      ],
      exec: "soakUser",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<600", "p(99)<1200", "max<5000"],
    http_req_failed: ["rate<0.01"],
    http_reqs: ["rate>15"],
  },
};

let products = [];
let slugs = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "soak_setup" });
  if (body && body.data && body.data.items) {
    products = body.data.items.filter((p) => p.stock_quantity > 0);
    slugs = products.map((p) => p.slug);
  }
  return { products, slugs };
}

export function soakUser(data) {
  const prods = data.products || products;
  const sl = data.slugs || slugs;
  if (prods.length === 0) return;

  const product = prods[Math.floor(Math.random() * prods.length)];
  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  // Full realistic user journey — moderate pace
  group("Soak — Browse", () => {
    const { body: homeBody } = apiGet("/cms/homepage", {}, { name: "soak_homepage" });
    check(homeBody, {
      "soak homepage — success": (b) => b && b.success === true,
    });
    think(2);

    const { body: listBody } = apiGet("/products", {
      query: { page: 1, page_size: 20, include_collections: false },
    }, { name: "soak_products" });
    check(listBody, {
      "soak products — success": (b) => b && b.success === true,
    });
    think(3);

    if (sl.length > 0) {
      const { body: detailBody } = apiGet(`/products/${sl[Math.floor(Math.random() * sl.length)]}`, {}, {
        name: "soak_product_detail",
      });
      check(detailBody, {
        "soak product detail — success": (b) => b && b.success === true,
      });
    }
    think(2);

    const { body: searchBody } = apiGet("/search", {
      query: { q: "silver", page: 1 },
    }, { name: "soak_search" });
    check(searchBody, {
      "soak search — success": (b) => b && b.success === true,
    });
    think(2);

    const { body: catBody } = apiGet("/categories/navbar", {}, { name: "soak_categories" });
    check(catBody, {
      "soak categories — success": (b) => b && b.success === true,
    });
    think(1);

    const { body: colBody } = apiGet("/collections", {}, { name: "soak_collections" });
    check(colBody, {
      "soak collections — success": (b) => b && b.success === true,
    });
    think(2);
  });

  group("Soak — Cart", () => {
    const { raw: addRaw } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id || null,
      quantity: 1,
    }, { headers }, { name: "soak_cart_add" });
    check(addRaw, {
      "soak cart add — 200 or 409": (r) => r.status === 200 || r.status === 409,
    });
    think(1);

    const { body: cartBody } = apiGet("/cart", { headers }, { name: "soak_cart_view" });
    check(cartBody, {
      "soak cart view — success": (b) => b && b.success === true,
    });
    think(1);

    apiDelete("/cart", { headers }, { name: "soak_cart_clear" });
    think(1);
  });

  // Longer think time for soak — simulates real browsing
  think(3);
}
