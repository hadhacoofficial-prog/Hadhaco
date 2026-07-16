// k6 test — Coupon validation performance
// Tests: POST /coupons/validate

import { check, group } from "k6";
import { apiPost, think } from "../helpers/http.js";
import { loadThresholds } from "../thresholds/default.js";

export const options = {
  scenarios: {
    coupon_validation: {
      executor: "constant-vus",
      vus: 10,
      duration: "2m",
    },
  },
  thresholds: {
    ...loadThresholds,
    "http_req_duration{endpoint:/coupons/validate}": ["p(95)<300"],
  },
};

const COUPON_CODES = ["TESTCODE", "SAVE10", "WELCOME", "FLAT50", "HADHA20"];

export default function () {
  const code = COUPON_CODES[Math.floor(Math.random() * COUPON_CODES.length)];

  group("Coupon Validation", () => {
    // Valid coupon attempt
    const { body } = apiPost("/coupons/validate", {
      code: code,
      order_subtotal: 2000 + Math.floor(Math.random() * 5000),
      cart_product_ids: [],
      cart_category_slugs: [],
    }, {}, { name: "coupon_validate" });

    check(body, {
      "coupon validate — response received": (b) => b && typeof b.success === "boolean",
    });

    if (body && body.data) {
      check(body, {
        "coupon validate — has valid field": (b) => typeof b.data.valid === "boolean",
      });
    }
    think(0.3);

    // Invalid coupon
    const { body: invalidBody } = apiPost("/coupons/validate", {
      code: "NONEXISTENTCODE123",
      order_subtotal: 1000,
      cart_product_ids: [],
      cart_category_slugs: [],
    }, {}, { name: "coupon_validate_invalid" });

    check(invalidBody, {
      "invalid coupon — handled gracefully": (b) => b && typeof b.success === "boolean",
    });
  });

  think(0.5);
}
