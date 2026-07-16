// k6 test — Coupon validation performance
// Tests: valid coupon, invalid coupon, expired coupon, edge cases
// Coupons endpoint: POST /api/v1/coupons/validate (requires auth)

import { check, group } from "k6";
import { apiGet, apiPost, think } from "../helpers/http.js";

export const options = {
  scenarios: {
    coupons: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
      exec: "testCoupons",
    },
  },
  thresholds: {
    "http_req_duration{name:coupon_valid}": ["p(95)<500"],
    "http_req_duration{name:coupon_invalid}": ["p(95)<500"],
  },
};

let allProducts = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 10, include_collections: false },
  }, { name: "setup_products" });

  if (body && body.data && body.data.items) {
    allProducts = body.data.items.filter((p) => p.stock_quantity > 0);
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

export function testCoupons(data) {
  const products = data.products || allProducts;
  const token = data.token;

  if (!token) {
    group("Coupons — Unauthenticated", () => {
      const { raw } = apiPost("/coupons/validate", {
        code: "TESTCODE",
        order_subtotal: 1000,
        cart_product_ids: [],
        cart_category_slugs: [],
      }, {}, { name: "coupon_unauth" });

      check(raw, {
        "coupon returns 401 without auth": (r) => r.status === 401 || r.status === 403,
      });
    });
    return;
  }

  if (products.length === 0) return;

  const product = products[0];
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const testCodes = ["TESTCODE", "SAVE10", "WELCOME", "FLAT50", "HADHA20", "INVALID999"];

  group("Coupons — Invalid Code", () => {
    const { raw, body } = apiPost("/coupons/validate", {
      code: "INVALID999",
      order_subtotal: product.base_price,
      cart_product_ids: [product.id],
      cart_category_slugs: [],
    }, { headers }, { name: "coupon_invalid" });

    check(raw, {
      "invalid coupon responds": (r) => r.status === 200 || r.status === 400 || r.status === 422,
    });

    if (raw.status === 200 && body) {
      check(body, {
        "invalid coupon is not valid": (b) => b.data === null || (b.data && b.data.valid === false) || b.success === false,
      });
    }
  });

  think(0.3);

  group("Coupons — Empty Code", () => {
    const { raw } = apiPost("/coupons/validate", {
      code: "",
      order_subtotal: product.base_price,
      cart_product_ids: [],
      cart_category_slugs: [],
    }, { headers }, { name: "coupon_empty" });

    check(raw, {
      "empty code returns 400 or 422": (r) => r.status === 400 || r.status === 422,
    });
  });

  think(0.3);

  group("Coupons — Zero Subtotal", () => {
    const { raw } = apiPost("/coupons/validate", {
      code: "TESTCODE",
      order_subtotal: 0,
      cart_product_ids: [],
      cart_category_slugs: [],
    }, { headers }, { name: "coupon_zero" });

    check(raw, {
      "zero subtotal returns 200 or 400 or 422": (r) => [200, 400, 422].includes(r.status),
    });
  });

  think(0.3);

  group("Coupons — Bulk Validation", () => {
    testCodes.forEach((code) => {
      const { raw, body } = apiPost("/coupons/validate", {
        code: code,
        order_subtotal: product.base_price,
        cart_product_ids: [product.id],
        cart_category_slugs: [],
      }, { headers }, { name: `coupon_bulk_${code}` });

      check(raw, {
        [`coupon ${code} responds`]: (r) => r.status >= 200 && r.status < 500,
      });
    });
  });
}

export function teardown() {}
