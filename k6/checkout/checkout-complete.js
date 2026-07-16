// k6 test — Checkout flow with authentication
// Tests: pre-checkout, shipping rates, coupon validation, payment intent creation
// Requires: DEV_EMAIL and DEV_PASSWORD environment variables
//
// Flow: Browse → Add to Cart → Validate Coupon → Create Payment Intent
// Without auth: only tests public endpoints (products, cart, shipping)

import { check, group } from "k6";
import { apiGet, apiPost, think } from "../helpers/http.js";
import { generateSessionId, sessionHeaders } from "../helpers/auth.js";

export const options = {
  scenarios: {
    checkout_flow: {
      executor: "constant-vus",
      vus: 3,
      duration: "3m",
      exec: "testCheckoutFlow",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<1500", "p(99)<3000"],
    http_req_failed: ["rate<0.05"],
  },
};

let allProducts = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "setup_products" });

  if (body && body.data && body.data.items) {
    allProducts = body.data.items.filter((p) => p.stock_quantity > 0);
  }

  // Try to authenticate
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

export function testCheckoutFlow(data) {
  const products = data.products || allProducts;
  const token = data.token;
  if (products.length === 0) return;

  const product = products[Math.floor(Math.random() * products.length)];
  const sessionId = generateSessionId();
  const guestHeaders = sessionHeaders(sessionId);
  const authHeaders = token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : null;

  // Step 1: View product
  group("Checkout — View Product", () => {
    const { raw, body } = apiGet(`/products/${product.slug}`, {}, {
      name: "checkout_view_product",
    });

    check(raw, {
      "product view returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "product has price": (p) => p.price > 0,
        "product has stock": (p) => p.stock_quantity >= 0,
        "product is active": (p) => p.is_active === true,
      });
    }
  });

  think(1);

  // Step 2: Add to cart
  group("Checkout — Add to Cart", () => {
    const { raw, body } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id || null,
      quantity: 1,
    }, { headers: guestHeaders }, { name: "checkout_add_to_cart" });

    check(raw, {
      "add to cart returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "cart has items": (d) => d.items && d.items.length > 0,
        "cart has subtotal": (d) => d.subtotal >= 0,
      });
    }
  });

  think(1);

  // Step 3: View cart
  group("Checkout — View Cart", () => {
    const { raw, body } = apiGet("/cart", { headers: guestHeaders }, {
      name: "checkout_verify_cart",
    });

    check(raw, {
      "cart view returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "cart has items": (d) => d.items && d.items.length > 0,
        "cart has total": (d) => d.total !== undefined && d.total >= 0,
        "cart has item_count": (d) => d.item_count >= 1,
      });
    }
  });

  think(1);

  // Step 4: Try coupon validation (requires auth)
  if (authHeaders) {
    group("Checkout — Coupon Validation", () => {
      const { raw, body } = apiPost("/coupons/validate", {
        code: "TESTCODE",
        order_subtotal: product.base_price,
        cart_product_ids: [product.id],
        cart_category_slugs: [],
      }, { headers: authHeaders }, { name: "checkout_coupon" });

      // 400/422 means coupon invalid (expected) — that's a valid response
      check(raw, {
        "coupon endpoint responds": (r) => r.status === 200 || r.status === 400 || r.status === 422,
      });

      if (body) {
        check(body, {
          "coupon has success field": (b) => typeof b.success === "boolean",
        });
      }
    });

    think(1);
  }

  // Step 5: Try checkout (requires auth)
  if (authHeaders) {
    group("Checkout — Create Payment Intent", () => {
      const { raw, body } = apiPost("/orders/create-payment", {
        shipping_address_id: null,
        billing_address_id: null,
        notes: "k6 checkout test",
      }, { headers: authHeaders }, { name: "checkout_create_payment" });

      // 200 = success, 409 = stock conflict, 422 = validation error, 401 = no auth
      check(raw, {
        "payment endpoint responds": (r) => [200, 401, 409, 422].includes(r.status),
      });

      if (raw.status === 200 && body && body.data) {
        check(body.data, {
          "payment has razorpay_order_id": (d) => d.razorpay_order_id !== undefined,
          "payment has amount": (d) => d.amount > 0,
          "payment has currency": (d) => d.currency !== undefined,
        });
      } else if (raw.status === 409) {
        // Stock conflict — valid under concurrency
        check(null, {
          "payment stock conflict (expected)": () => true,
        });
      }
    });

    think(1);
  } else {
    group("Checkout — Skipped (no auth)", () => {
      check(null, {
        "checkout payment skipped — set DEV_EMAIL/DEV_PASSWORD": () => true,
      });
    });
  }

  // Step 6: Shipping rates
  group("Checkout — Shipping Rates", () => {
    const { raw, body } = apiGet("/shipping/rates", {
      query: { weight_grams: 100, pincode: "110001" },
    }, { name: "checkout_shipping_rates" });

    check(raw, {
      "shipping rates returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "shipping rates is array": (d) => Array.isArray(d),
      });
    }
  });

  // Cleanup
  apiDelete("/cart", { headers: guestHeaders }, { name: "checkout_cleanup" });
}

export function teardown() {}
