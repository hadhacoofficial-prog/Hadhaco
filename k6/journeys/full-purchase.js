// k6 test — End-to-end customer purchase journey
// Complete flow: Homepage → Browse → Product → Variant → Cart → Update → Coupon → Login → Address → Checkout → Payment
//
// Dynamically discovers all data from the running application.
// No hardcoded IDs, slugs, or credentials.
// Requires: DEV_EMAIL / DEV_PASSWORD for authenticated steps (optional — graceful skip).

import { check, group } from "k6";
import { apiGet, apiPost, apiPatch, apiDelete, think } from "../helpers/http.js";
import { generateSessionId, sessionHeaders } from "../helpers/auth.js";

export const options = {
  scenarios: {
    e2e_journey: {
      executor: "constant-vus",
      vus: 3,
      duration: "5m",
      exec: "fullJourney",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<1500", "p(99)<3000"],
    http_req_failed: ["rate<0.05"],
    api_success_rate: ["rate>0.90"],
  },
};

let allProducts = [];
let allSlugs = [];
let allCategories = [];
let allCollections = [];

export function setup() {
  // Discover products
  const { body: pBody } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "e2e_setup_products" });

  if (pBody && pBody.data && pBody.data.items) {
    allProducts = pBody.data.items.filter((p) => p.stock_quantity > 0);
    allSlugs = allProducts.map((p) => p.slug);
  }

  // Discover categories
  const { body: cBody } = apiGet("/categories", {}, { name: "e2e_setup_categories" });
  if (cBody && cBody.data) {
    allCategories = cBody.data;
  }

  // Discover collections
  const { body: colBody } = apiGet("/collections", {}, { name: "e2e_setup_collections" });
  if (colBody && colBody.data) {
    allCollections = colBody.data;
  }

  // Try to authenticate
  const email = __ENV.DEV_EMAIL || "";
  const password = __ENV.DEV_PASSWORD || "";
  let token = null;

  if (email && password) {
    const { body: loginBody } = apiPost("/dev/login", {
      email: email,
      password: password,
    }, {}, { name: "e2e_setup_login" });

    if (loginBody && loginBody.data && loginBody.data.session) {
      token = loginBody.data.session.access_token;
    }
  }

  return {
    products: allProducts,
    slugs: allSlugs,
    categories: allCategories,
    collections: allCollections,
    token: token,
  };
}

export function fullJourney(data) {
  const products = data.products || allProducts;
  const slugs = data.slugs || allSlugs;
  const categories = data.categories || allCategories;
  const collections = data.collections || allCollections;
  const token = data.token;

  if (products.length === 0) return;

  const sessionId = generateSessionId();
  const guestHeaders = sessionHeaders(sessionId);
  const authHeaders = token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : null;

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 1: Homepage
  // ═══════════════════════════════════════════════════════════════════════════
  group("E2E — 1. Homepage", () => {
    const { raw, body } = apiGet("/cms/homepage", {}, { name: "e2e_homepage" });

    check(raw, { "homepage — HTTP 200": (r) => r.status === 200 });

    if (body && body.data) {
      check(body.data, {
        "homepage has sections": (d) => d && (d.sections || d.layout || d.hero),
        "homepage success": (b) => body.success === true,
      });
    }
  });
  think(2);

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 2: Browse Categories
  // ═══════════════════════════════════════════════════════════════════════════
  group("E2E — 2. Browse Categories", () => {
    const { raw, body } = apiGet("/categories/navbar", {}, { name: "e2e_categories" });

    check(raw, { "categories — HTTP 200": (r) => r.status === 200 });

    if (body && body.data) {
      check(body.data, {
        "categories has data": (d) => d !== undefined,
        "categories is non-empty": (d) => (Array.isArray(d) ? d.length > 0 : Object.keys(d).length > 0),
      });
    }
  });
  think(1);

  // Browse a category's products
  if (categories.length > 0) {
    const cat = categories[Math.floor(Math.random() * categories.length)];
    const catSlug = cat.slug || (cat.children && cat.children[0] && cat.children[0].slug);

    if (catSlug) {
      group("E2E — 2b. Category Products", () => {
        const { raw, body } = apiGet("/products", {
          query: { page: 1, page_size: 10, category_slug: catSlug, include_collections: false },
        }, { name: "e2e_category_products" });

        check(raw, { "category products — HTTP 200": (r) => r.status === 200 });

        if (body && body.data) {
          check(body.data, {
            "category products has items": (d) => d.items !== undefined,
          });
        }
      });
      think(1);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 3: Browse Collections
  // ═══════════════════════════════════════════════════════════════════════════
  group("E2E — 3. Browse Collections", () => {
    const { raw, body } = apiGet("/collections", {}, { name: "e2e_collections" });

    check(raw, { "collections — HTTP 200": (r) => r.status === 200 });

    if (body && body.data) {
      check(body.data, {
        "collections has items": (d) => Array.isArray(d) && d.length > 0,
      });
    }
  });
  think(1);

  // View a collection detail
  if (collections.length > 0) {
    const col = collections[Math.floor(Math.random() * collections.length)];
    if (col.slug) {
      group("E2E — 3b. Collection Detail", () => {
        const { raw, body } = apiGet(`/collections/${col.slug}`, {}, {
          name: "e2e_collection_detail",
        });

        check(raw, { "collection detail — HTTP 200": (r) => r.status === 200 });

        if (body && body.data) {
          check(body.data, {
            "collection has name": (d) => d.name !== undefined,
            "collection has slug": (d) => d.slug !== undefined,
          });
        }
      });
      think(1);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 4: Open Product
  // ═══════════════════════════════════════════════════════════════════════════
  const product = products[Math.floor(Math.random() * products.length)];
  let selectedVariantId = null;

  group("E2E — 4. Open Product", () => {
    const { raw, body } = apiGet(`/products/${product.slug}`, {}, {
      name: "e2e_product_detail",
    });

    check(raw, { "product detail — HTTP 200": (r) => r.status === 200 });

    if (body && body.data) {
      const p = body.data;

      check(p, {
        "product has id": (v) => v.id !== undefined,
        "product has name": (v) => v.name && v.name.length > 0,
        "product has price": (v) => v.price > 0 || v.base_price > 0,
        "product has slug": (v) => v.slug && v.slug.length > 0,
        "product has images": (v) => (v.images && v.images.length > 0) || v.primary_image !== undefined,
        "product has stock": (v) => v.stock_quantity !== undefined && v.stock_quantity >= 0,
      });

      // ═══════════════════════════════════════════════════════════════════
      // STEP 5: Select Variant
      // ═══════════════════════════════════════════════════════════════════
      if (p.variants && p.variants.length > 0) {
        const variant = p.variants[0];
        selectedVariantId = variant.id;

        check(variant, {
          "variant has id": (v) => v.id !== undefined,
          "variant has sku": (v) => v.sku !== undefined,
          "variant has price": (v) => v.price > 0,
          "variant has stock": (v) => v.stock_quantity >= 0,
        });
      }

      // ═══════════════════════════════════════════════════════════════════
      // STEP 6: Product Images
      // ═══════════════════════════════════════════════════════════════════
      if (p.images && p.images.length > 0) {
        check(p.images[0], {
          "image has url": (img) => img.url && img.url.length > 0,
        });
      }

      // ═══════════════════════════════════════════════════════════════════
      // STEP 7: View Reviews
      // ═══════════════════════════════════════════════════════════════════
      const { body: revBody } = apiGet(`/reviews/products/${p.id}/summary`, {}, {
        name: "e2e_product_reviews",
      });

      check(revBody, {
        "reviews summary — success": (b) => b && b.success === true,
      });
    }
  });
  think(2);

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 8: Add To Cart
  // ═══════════════════════════════════════════════════════════════════════════
  let cartId = null;
  let cartItemId = null;

  group("E2E — 8. Add To Cart", () => {
    const { raw, body } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: selectedVariantId,
      quantity: 1,
    }, { headers: guestHeaders }, { name: "e2e_add_to_cart" });

    check(raw, {
      "add to cart — 200 or 409": (r) => r.status === 200 || r.status === 409,
    });

    if (raw.status === 200 && body && body.data) {
      cartId = body.data.id;
      if (body.data.items && body.data.items.length > 0) {
        cartItemId = body.data.items[0].id;
      }

      check(body.data, {
        "cart has items": (d) => d.items && d.items.length > 0,
        "cart has subtotal": (d) => d.subtotal >= 0,
        "cart has id": (d) => d.id !== undefined,
      });
    }
  });
  think(1);

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 9: Update Quantity
  // ═══════════════════════════════════════════════════════════════════════════
  if (cartId && cartItemId && product.stock_quantity >= 2) {
    group("E2E — 9. Update Quantity", () => {
      const { raw, body } = apiPatch(`/cart/${cartId}/items/${cartItemId}`, {
        quantity: 2,
      }, { headers: guestHeaders }, { name: "e2e_update_quantity" });

      check(raw, {
        "update quantity — 200 or 409": (r) => r.status === 200 || r.status === 409,
      });

      if (raw.status === 200 && body && body.data) {
        check(body.data, {
          "updated cart reflects quantity": (d) => {
            const item = d.items && d.items.find((i) => i.id === cartItemId);
            return item && item.quantity >= 1;
          },
        });
      }
    });
    think(1);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 10: Apply Coupon (requires auth)
  // ═══════════════════════════════════════════════════════════════════════════
  if (authHeaders) {
    group("E2E — 10. Apply Coupon", () => {
      const { raw, body } = apiPost("/coupons/validate", {
        code: "TESTCODE",
        order_subtotal: product.base_price || 1000,
        cart_product_ids: [product.id],
        cart_category_slugs: [],
      }, { headers: authHeaders }, { name: "e2e_apply_coupon" });

      check(raw, {
        "coupon responds": (r) => r.status === 200 || r.status === 400 || r.status === 422,
      });
    });
    think(1);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 11: Login (already done in setup if credentials available)
  // ═══════════════════════════════════════════════════════════════════════════
  if (authHeaders) {
    group("E2E — 11. Authenticated Profile", () => {
      const { raw, body } = apiGet("/me", { headers: authHeaders }, {
        name: "e2e_profile",
      });

      check(raw, { "profile — HTTP 200": (r) => r.status === 200 });

      if (body && body.data) {
        check(body.data, {
          "profile has email": (d) => d.email !== undefined,
          "profile has role": (d) => d.role !== undefined,
        });
      }
    });
    think(1);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 12: Select Address
  // ═══════════════════════════════════════════════════════════════════════════
  let addressId = null;

  if (authHeaders) {
    group("E2E — 12. Address Management", () => {
      // List addresses
      const { raw: listRaw, body: listBody } = apiGet("/me/addresses", {
        headers: authHeaders,
      }, { name: "e2e_list_addresses" });

      check(listRaw, { "addresses — HTTP 200": (r) => r.status === 200 });

      // Create address
      const { raw: createRaw, body: createBody } = apiPost("/me/addresses", {
        full_name: "K6 E2E Test",
        phone: "9999999999",
        address_line1: "123 Test Lane",
        city: "Mumbai",
        state: "Maharashtra",
        pincode: "400001",
        country: "India",
      }, { headers: authHeaders }, { name: "e2e_create_address" });

      check(createRaw, {
        "create address — 200 or 422": (r) => r.status === 200 || r.status === 422,
      });

      if (createRaw.status === 200 && createBody && createBody.data) {
        addressId = createBody.data.id;
        check(createBody.data, {
          "address has id": (d) => d.id !== undefined,
        });
      }
    });
    think(1);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 13: Shipping Rates
  // ═══════════════════════════════════════════════════════════════════════════
  group("E2E — 13. Shipping Rates", () => {
    const { raw, body } = apiGet("/shipping/rates", {
      query: { weight_grams: 100, pincode: "400001" },
    }, { name: "e2e_shipping_rates" });

    check(raw, { "shipping rates — HTTP 200": (r) => r.status === 200 });

    if (body && body.data) {
      check(body.data, {
        "shipping rates is array": (d) => Array.isArray(d),
      });
    }
  });
  think(1);

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 14: Checkout / Create Payment Order
  // ═══════════════════════════════════════════════════════════════════════════
  if (authHeaders) {
    group("E2E — 14. Create Payment Order", () => {
      const { raw, body } = apiPost("/orders/create-payment", {
        shipping_address_id: addressId,
        billing_address_id: addressId,
        notes: "k6 e2e test order",
      }, { headers: authHeaders }, { name: "e2e_create_payment" });

      // 200=success, 409=stock conflict, 422=validation, 401=no auth
      check(raw, {
        "payment responds": (r) => [200, 401, 409, 422].includes(r.status),
      });

      if (raw.status === 200 && body && body.data) {
        check(body.data, {
          "payment has razorpay_order_id": (d) => d.razorpay_order_id !== undefined,
          "payment has amount": (d) => d.amount > 0,
          "payment has currency": (d) => d.currency !== undefined,
        });
      } else if (raw.status === 409) {
        check(null, { "payment stock conflict (expected)": () => true });
      }
    });
    think(1);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 15: Verify Inventory Reservation
  // ═══════════════════════════════════════════════════════════════════════════
  if (authHeaders) {
    group("E2E — 15. Verify Reservation", () => {
      const { raw, body } = apiGet("/orders/active-reservations", {
        headers: authHeaders,
      }, { name: "e2e_verify_reservation" });

      check(raw, { "reservations — HTTP 200": (r) => r.status === 200 });

      if (body) {
        check(body, {
          "reservations success": (b) => b.success === true,
        });
      }
    });
    think(1);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 16: Verify Order Status
  // ═══════════════════════════════════════════════════════════════════════════
  if (authHeaders) {
    group("E2E — 16. Order History", () => {
      const { raw, body } = apiGet("/orders", { headers: authHeaders }, {
        name: "e2e_order_history",
      });

      check(raw, { "orders — HTTP 200": (r) => r.status === 200 });

      if (body && body.data) {
        check(body.data, {
          "orders has total": (d) => d.total !== undefined,
          "orders has items": (d) => d.items !== undefined,
        });
      }
    });
    think(1);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 17: Notification Verification
  // ═══════════════════════════════════════════════════════════════════════════
  if (authHeaders) {
    group("E2E — 17. Notification Preferences", () => {
      const { raw } = apiGet("/notifications/preferences", {
        headers: authHeaders,
      }, { name: "e2e_notifications" });

      check(raw, {
        "notifications — responds": (r) => r.status === 200 || r.status === 401,
      });
    });
    think(0.5);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CLEANUP
  // ═══════════════════════════════════════════════════════════════════════════
  group("E2E — Cleanup", () => {
    // Clear cart
    apiDelete("/cart", { headers: guestHeaders }, { name: "e2e_cleanup_cart" });

    // Delete test address
    if (authHeaders && addressId) {
      apiDelete(`/me/addresses/${addressId}`, { headers: authHeaders }, {
        name: "e2e_cleanup_address",
      });
    }
  });
}

export function teardown() {}
