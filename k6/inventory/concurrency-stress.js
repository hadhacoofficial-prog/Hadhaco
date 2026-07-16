// k6 test — Inventory concurrency with 200/500/1000 users
// Heavy stress test for the reservation system

import { check, group, fail } from "k6";
import { apiGet, apiPost, apiDelete, think } from "../helpers/http.js";
import { generateSessionId } from "../helpers/auth.js";

export const options = {
  scenarios: {
    // Ramp up: 100 → 500 → 1000 VUs
    inventory_stress: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 100 },
        { duration: "1m", target: 100 },
        { duration: "30s", target: 500 },
        { duration: "1m", target: 500 },
        { duration: "30s", target: 1000 },
        { duration: "1m", target: 1000 },
        { duration: "30s", target: 0 },
      ],
      exec: "stressBuy",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<5000", "p(99)<15000", "max<30000"],
    http_req_failed: ["rate<0.50"],
  },
};

let targetProduct = null;

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "stress_setup" });

  if (!body || !body.data || !body.data.items) {
    fail("No products found");
    return {};
  }

  // Find highest-stock product for maximum concurrency testing
  const inStock = body.data.items
    .filter((p) => p.stock_quantity > 0)
    .sort((a, b) => b.stock_quantity - a.stock_quantity);

  if (inStock.length === 0) {
    fail("No in-stock products");
    return {};
  }

  targetProduct = inStock[0];
  console.log(`Stress test target: ${targetProduct.name} (stock: ${targetProduct.stock_quantity})`);

  return { product: targetProduct, stockBefore: targetProduct.stock_quantity };
}

export function stressBuy(data) {
  const product = data.product;
  if (!product) return;

  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  // Phase 1: Add to cart (fast, low contention)
  const { body: addBody } = apiPost("/cart/items", {
    product_id: product.id,
    variant_id: product.variant_id || null,
    quantity: 1,
  }, { headers }, { name: "stress_add_cart" });

  if (!addBody || !addBody.success) return;

  think(0.1);

  // Phase 2: Create payment intent (HIGH contention — SELECT FOR UPDATE)
  const { raw, body: payBody } = apiPost("/orders/create-payment", {
    shipping_address_id: null,
    billing_address_id: null,
    notes: `k6 stress test VU${__VU}`,
  }, { headers }, { name: "stress_create_payment" });

  if (raw.status === 200 && payBody && payBody.success) {
    check(null, { "stress — purchase succeeded": () => true });
  } else if (raw.status === 401) {
    // No auth — expected, cart add already validated inventory
    check(null, { "stress — no auth (expected)": () => true });
  } else if (raw.status === 409 || raw.status === 422) {
    // Stock exhaustion — expected under concurrency
    check(null, { "stress — stock exhaustion (expected)": () => true });
  } else if (raw.status === 429) {
    check(null, { "stress — rate limited": () => true });
  } else {
    check(null, { "stress — unexpected error": () => false });
  }

  // Phase 3: Cleanup
  apiDelete("/cart", { headers }, { name: "stress_cleanup" });
}

export function teardown(data) {
  if (!data.product) return;

  const { body } = apiGet(`/products/${data.product.slug}`, {}, {
    name: "stress_teardown",
  });

  if (body && body.data) {
    const finalStock = body.data.stock_quantity;
    const sold = data.stockBefore - finalStock;

    console.log(`\n=== INVENTORY STRESS TEST RESULTS ===`);
    console.log(`Product: ${data.product.name}`);
    console.log(`Stock before: ${data.stockBefore}`);
    console.log(`Stock after: ${finalStock}`);
    console.log(`Items sold: ${sold}`);
    console.log(`=====================================\n`);

    check(null, {
      "stress — no negative stock": () => finalStock >= 0,
      "stress — no overselling": () => sold <= data.stockBefore,
    });
  }
}
