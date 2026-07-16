// k6 scenario — Spike test: Sudden traffic surge
// Simulates flash sale / social media viral moment
// Duration: 6 minutes

import { check, group } from "k6";
import { apiGet, apiPost, apiDelete, think } from "../helpers/http.js";
import { generateSessionId } from "../helpers/auth.js";

export const options = {
  scenarios: {
    spike_traffic: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 10 },    // Normal baseline
        { duration: "10s", target: 200 },  // SPIKE! (simulates viral moment)
        { duration: "2m", target: 200 },   // Sustained spike
        { duration: "10s", target: 10 },   // Drop back to normal
        { duration: "2m", target: 10 },    // Recovery period
        { duration: "30s", target: 0 },
      ],
      exec: "spikeUser",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<5000", "p(99)<15000", "max<30000"],
    http_req_failed: ["rate<0.15"],
  },
};

let products = [];
let slugs = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 30, include_collections: false },
  }, { name: "spike_setup" });
  if (body && body.data && body.data.items) {
    products = body.data.items.filter((p) => p.stock_quantity > 0);
    slugs = products.map((p) => p.slug);
  }
  return { products, slugs };
}

export function spikeUser(data) {
  const prods = data.products || products;
  const sl = data.slugs || slugs;
  if (prods.length === 0) return;

  const product = prods[Math.floor(Math.random() * prods.length)];
  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  group("Spike — Homepage + Products", () => {
    // Homepage (first thing users hit during viral traffic)
    const { body: homeBody } = apiGet("/cms/homepage", {}, { name: "spike_homepage" });
    check(homeBody, {
      "spike homepage — success": (b) => b && b.success === true,
    });
    think(0.5);

    // Featured products (homepage rails)
    const { body: featBody } = apiGet("/products", {
      query: { page: 1, page_size: 8, is_featured: true, include_collections: false },
    }, { name: "spike_featured" });
    check(featBody, {
      "spike featured — success": (b) => b && b.success === true,
    });
    think(0.5);

    // Product detail
    if (sl.length > 0) {
      const { body: detailBody } = apiGet(`/products/${sl[Math.floor(Math.random() * sl.length)]}`, {}, {
        name: "spike_product_detail",
      });
      check(detailBody, {
        "spike product detail — success": (b) => b && b.success === true,
      });
    }
    think(1);

    // Add to cart (high contention during spike)
    const { raw: addRaw } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id || null,
      quantity: 1,
    }, { headers }, { name: "spike_add_to_cart" });
    check(addRaw, {
      "spike cart add — 200 or 409": (r) => r.status === 200 || r.status === 409,
    });
    think(0.5);

    // Attempt checkout
    const { raw: payRaw } = apiPost("/orders/create-payment", {
      shipping_address_id: null,
      billing_address_id: null,
      notes: "spike test",
    }, { headers }, { name: "spike_checkout" });
    check(payRaw, {
      "spike checkout — responds": (r) => [200, 401, 409, 422].includes(r.status),
    });
    think(1);

    // Cleanup
    apiDelete("/cart", { headers }, { name: "spike_cleanup" });
  });
}
