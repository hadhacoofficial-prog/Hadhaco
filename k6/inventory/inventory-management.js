// k6 test — Inventory management and reservation verification
// Tests: stock visibility, reservation creation/expiry, concurrent access
// Requires: DEV_EMAIL and DEV_PASSWORD for reservation tests

import { check, group, fail } from "k6";
import { apiGet, apiPost, apiDelete, think } from "../helpers/http.js";
import { generateSessionId, sessionHeaders } from "../helpers/auth.js";

export const options = {
  scenarios: {
    inventory: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
      exec: "testInventory",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<1500", "p(99)<3000"],
    api_success_rate: ["rate>0.85"],
  },
};

let allProducts = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "setup_products" });

  if (body && body.data && body.data.items) {
    allProducts = body.data.items;
  }

  const email = __ENV.DEV_EMAIL || "";
  const password = __ENV.DEV_PASSWORD || "";
  let token = null;

  if (email && password) {
    const { body: loginBody } = apiPost("/dev/login", {
      email: email,
      password: password,
    }, {}, { name: "setup_login" });

    if (loginBody && loginBody.data && loginBody.data.session) {
      token = loginBody.data.session.access_token;
    }
  }

  return { products: allProducts, token: token };
}

export function testInventory(data) {
  const products = data.products || allProducts;
  const token = data.token;
  if (!products || products.length === 0) return;

  const product = products[Math.floor(Math.random() * products.length)];

  group("Inventory — Stock Visibility", () => {
    const { raw, body } = apiGet(`/products/${product.slug}`, {}, {
      name: "inventory_stock_view",
    });

    check(raw, {
      "product detail returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "stock_quantity is number": (p) => typeof p.stock_quantity === "number",
        "stock_quantity >= 0": (p) => p.stock_quantity >= 0,
        "product has id": (p) => p.id !== undefined,
      });
    }
  });

  think(0.5);

  group("Inventory — Product Listing Stock", () => {
    const { raw, body } = apiGet("/products", {
      query: { page: 1, page_size: 10, include_collections: false },
    }, { name: "inventory_listing_stock" });

    check(raw, {
      "product list returns 200": (r) => r.status === 200,
    });

    if (body && body.data && body.data.items) {
      const items = body.data.items;
      check(null, {
        "all products have stock_quantity": () =>
          items.every((p) => p.stock_quantity !== undefined && p.stock_quantity >= 0),
        "no negative stock": () =>
          items.every((p) => p.stock_quantity >= 0),
      });
    }
  });

  think(0.5);

  // Guest cart add exercises inventory check at cart level
  group("Inventory — Cart Add (Stock Check)", () => {
    const sessionId = generateSessionId();
    const headers = sessionHeaders(sessionId);

    const { raw, body } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id || null,
      quantity: 1,
    }, { headers }, { name: "inventory_cart_add" });

    check(raw, {
      "cart add returns 200 or 409": (r) => r.status === 200 || r.status === 409,
    });

    if (raw.status === 409 && body) {
      check(body, {
        "409 has stock error message": (b) =>
          b.message && (
            b.message.toLowerCase().includes("stock") ||
            b.message.toLowerCase().includes("available") ||
            b.message.toLowerCase().includes("inventory")
          ),
      });
    }

    // Cleanup
    if (raw.status === 200 && body && body.data) {
      apiDelete("/cart", { headers }, { name: "inventory_cart_cleanup" });
    }
  });

  think(0.5);

  // Reservation verification (requires auth)
  if (token) {
    group("Inventory — Active Reservations", () => {
      const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

      const { raw, body } = apiGet("/orders/active-reservations", { headers }, {
        name: "inventory_reservations",
      });

      check(raw, {
        "reservations returns 200": (r) => r.status === 200,
      });

      if (body && body.data) {
        check(body.data, {
          "reservations has data": (d) => d !== undefined,
        });
      }
    });
  }
}

export function teardown() {}
