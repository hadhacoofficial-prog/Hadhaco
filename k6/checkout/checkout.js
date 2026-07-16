// k6 test — Checkout flow (product selection → cart → create payment intent)
// Tests the full pre-payment checkout journey
// NOTE: Does NOT complete payment (requires Razorpay test keys)

import { check, group, fail } from "k6";
import { apiGet, apiPost, apiPatch, apiDelete, apiAuthGet, apiAuthPost, think } from "../helpers/http.js";
import { devLogin, generateSessionId } from "../helpers/auth.js";
import { loadThresholds, checkoutThresholds } from "../thresholds/default.js";

export const options = {
  scenarios: {
    checkout_flow: {
      executor: "constant-vus",
      vus: 5,
      duration: "3m",
    },
  },
  thresholds: {
    ...checkoutThresholds,
  },
};

let products = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 20, include_collections: false },
  }, { name: "setup_products" });

  if (body && body.data && body.data.items) {
    products = body.data.items
      .filter((p) => p.stock_quantity > 0)
      .map((p) => ({
        id: p.id,
        slug: p.slug,
        name: p.name,
        base_price: p.base_price,
        variant_id: p.variants && p.variants.length > 0 ? p.variants[0].id : null,
      }));
  }

  // Authenticate as customer
  const customerEmail = __ENV.CUSTOMER_EMAIL;
  const customerPassword = __ENV.CUSTOMER_PASSWORD;
  let auth = null;
  if (customerEmail && customerPassword) {
    auth = devLogin(customerEmail, customerPassword, "customer");
  }

  return { products, auth };
}

export default function (data) {
  const prods = data.products || products;
  if (prods.length === 0) return;

  const product = prods[Math.floor(Math.random() * prods.length)];

  // If no auth, test the pre-checkout flow only (cart operations)
  const token = data.auth ? data.auth.access_token : null;

  group("Checkout Pre-Flow", () => {
    // 1. View product detail
    const { body: productDetail } = apiGet(`/products/${product.slug}`, {}, {
      name: "checkout_view_product",
    });
    check(productDetail, {
      "checkout — product loaded": (b) => b && b.success === true,
    });
    think(0.5);

    // 2. Add to cart (guest or auth)
    const headers = token
      ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
      : { "X-Session-ID": generateSessionId(), "Content-Type": "application/json" };

    const { body: cartResult } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id,
      quantity: 1,
    }, { headers }, { name: "checkout_add_to_cart" });

    check(cartResult, {
      "checkout — item added to cart": (b) => b && b.success === true,
    });
    think(0.3);

    // 3. Verify cart
    const { body: cart } = apiGet("/cart", { headers }, { name: "checkout_verify_cart" });
    check(cart, {
      "checkout — cart has items": (b) => b && b.data && b.data.item_count >= 1,
      "checkout — cart has total": (b) => b && b.data && b.data.subtotal > 0,
    });
    think(0.3);

    // 4. Validate coupon (only when authenticated — endpoint requires auth)
    if (token) {
      const { raw: couponRaw } = apiPost("/coupons/validate", {
        code: "TESTCODE",
        order_subtotal: cart ? cart.data.subtotal : 1000,
        cart_product_ids: [product.id],
        cart_category_slugs: [],
      }, { headers }, { name: "checkout_validate_coupon" });
      check(couponRaw, {
        "checkout — coupon endpoint reachable": (r) =>
          r.status === 200 || r.status === 400 || r.status === 404 || r.status === 422,
      });
    }
    think(0.3);

    // 5. Try create payment intent (requires auth + valid addresses)
    if (token) {
      // Get addresses first
      const { body: addrResult } = apiAuthGet("/me/addresses", token, {}, {
        name: "checkout_get_addresses",
      });

      if (addrResult && addrResult.data && addrResult.data.length > 0) {
        const addr = addrResult.data[0];
        const { body: paymentResult } = apiAuthPost("/orders/create-payment", {
          shipping_address_id: addr.id,
          billing_address_id: addr.id,
          notes: "k6 performance test order",
        }, token, {}, { name: "checkout_create_payment" });

        if (paymentResult && paymentResult.data) {
          check(paymentResult, {
            "checkout — payment intent created": (b) => b && b.success === true,
            "checkout — has razorpay_order_id": (b) => b && b.data && b.data.razorpay_order_id,
          });
          think(0.3);

          // NOTE: We do NOT verify payment — that requires a real Razorpay callback
          // In development, we can test the order creation path only
        } else {
          // Payment intent creation may fail for various reasons in test
          // (insufficient stock, missing addresses, etc.) — that's ok for perf testing
        }
      }
    }

    // 6. Clean up: clear cart
    apiDelete("/cart", { headers }, { name: "checkout_cleanup_cart" });
  });

  think(1);
}
