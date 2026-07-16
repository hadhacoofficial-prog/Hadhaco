// k6 scenario — Load test: Complete user journey simulation
// Simulates realistic mixed traffic patterns
// Duration: 10 minutes, ramping from 10 to 50 VUs

import { check, group } from "k6";
import { apiGet, apiPost, apiPatch, apiDelete, think } from "../helpers/http.js";
import { devLogin, generateSessionId } from "../helpers/auth.js";

export const options = {
  scenarios: {
    // Mixed traffic — simulates real user distribution
    mixed_traffic: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 10 },   // Warm up
        { duration: "2m", target: 30 },   // Ramp to normal
        { duration: "3m", target: 50 },   // Peak load
        { duration: "2m", target: 30 },   // Scale down
        { duration: "1m", target: 10 },   // Cool down
        { duration: "1m", target: 0 },
      ],
      exec: "userJourney",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<500", "p(99)<1000", "max<3000"],
    http_req_failed: ["rate<0.01"],
    http_reqs: ["rate>10"],
  },
};

let allProducts = [];
let allSlugs = [];
let allCategories = [];
let allCollections = [];

export function setup() {
  // Load product data
  const { body: pBody } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "load_setup_products" });
  if (pBody && pBody.data && pBody.data.items) {
    allProducts = pBody.data.items.filter((p) => p.stock_quantity > 0);
    allSlugs = allProducts.map((p) => p.slug);
  }

  // Load categories
  const { body: cBody } = apiGet("/categories/navbar", {}, { name: "load_setup_categories" });
  if (cBody && cBody.data) {
    allCategories = cBody.data;
  }

  // Load collections
  const { body: colBody } = apiGet("/collections", {}, { name: "load_setup_collections" });
  if (colBody && colBody.data) {
    allCollections = colBody.data;
  }

  return { products: allProducts, slugs: allSlugs, categories: allCategories, collections: allCollections };
}

export function userJourney(data) {
  const products = data.products || allProducts;
  const slugs = data.slugs || allSlugs;
  const collections = data.collections || allCollections;

  if (products.length === 0) return;

  // Simulate different user types
  const userType = Math.random();
  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };

  if (userType < 0.4) {
    // 40% — Browser: Homepage → Categories → Product → Leave
    browserJourney(data, headers);
  } else if (userType < 0.7) {
    // 30% — Shopper: Browse → Search → Product → Cart
    shopperJourney(data, headers);
  } else if (userType < 0.9) {
    // 20% — Buyer: Browse → Cart → Checkout attempt
    buyerJourney(data, headers);
  } else {
    // 10% — Searcher: Heavy search user
    searcherJourney(data, headers);
  }
}

function browserJourney(data, headers) {
  // Homepage
  const { body: homeBody } = apiGet("/cms/homepage", {}, { name: "journey_homepage" });
  check(homeBody, {
    "homepage — success": (b) => b && b.success === true,
  });
  think(2);

  // Browse products
  const { body: listBody } = apiGet("/products", {
    query: { page: 1, page_size: 20 },
  }, { name: "journey_browse_products" });
  check(listBody, {
    "browse — has items": (b) => b && b.data && b.data.items && b.data.items.length > 0,
  });
  think(3);

  // View a product
  if (data.slugs && data.slugs.length > 0) {
    const slug = data.slugs[Math.floor(Math.random() * data.slugs.length)];
    const { body: prodBody } = apiGet(`/products/${slug}`, {}, { name: "journey_view_product" });
    check(prodBody, {
      "view product — success": (b) => b && b.success === true,
      "view product — has name": (b) => b && b.data && b.data.name,
    });
    think(5);

    // View reviews
    if (data.products && data.products.length > 0) {
      const { body: revBody } = apiGet(`/reviews/products/${data.products[0].id}/summary`, {}, {
        name: "journey_view_reviews",
      });
      check(revBody, {
        "reviews — success": (b) => b && b.success === true,
      });
    }
  }
  think(2);
}

function shopperJourney(data, headers) {
  // Search
  const terms = ["ring", "necklace", "bracelet", "earring", "silver"];
  const term = terms[Math.floor(Math.random() * terms.length)];
  const { body: searchBody } = apiGet("/search", { query: { q: term, page: 1 } }, { name: "journey_search" });
  check(searchBody, {
    "search — success": (b) => b && b.success === true,
  });
  think(2);

  // Search autocomplete
  const { body: acBody } = apiGet("/search/autocomplete", { query: { q: term.substring(0, 3), limit: 8 } }, {
    name: "journey_autocomplete",
  });
  check(acBody, {
    "autocomplete — success": (b) => b && b.success === true,
  });
  think(1);

  // View product from search
  if (data.slugs && data.slugs.length > 0) {
    const slug = data.slugs[Math.floor(Math.random() * data.slugs.length)];
    const { body: prodBody } = apiGet(`/products/${slug}`, {}, { name: "journey_product_detail" });
    check(prodBody, {
      "product detail — success": (b) => b && b.success === true,
    });
    think(3);

    // Add to cart
    const product = data.products[Math.floor(Math.random() * data.products.length)];
    const { raw: addRaw, body: addBody } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id || null,
      quantity: 1,
    }, { headers }, { name: "journey_add_to_cart" });
    check(addRaw, {
      "add to cart — 200 or 409": (r) => r.status === 200 || r.status === 409,
    });
    think(1);

    // View cart
    const { body: cartBody } = apiGet("/cart", { headers }, { name: "journey_view_cart" });
    check(cartBody, {
      "view cart — success": (b) => b && b.success === true,
    });
    think(2);

    // Try coupon (requires auth — graceful handling)
    apiPost("/coupons/validate", {
      code: "SAVE10",
      order_subtotal: 2000,
      cart_product_ids: [product.id],
      cart_category_slugs: [],
    }, { headers }, { name: "journey_apply_coupon" });
    think(1);
  }
}

function buyerJourney(data, headers) {
  // Quick browse
  const { body: browseBody } = apiGet("/products", {
    query: { page: 1, page_size: 10, is_featured: true, include_collections: false },
  }, { name: "journey_buyer_browse" });
  check(browseBody, {
    "buyer browse — success": (b) => b && b.success === true,
  });
  think(1);

  // Add to cart
  if (data.products.length > 0) {
    const product = data.products[Math.floor(Math.random() * data.products.length)];
    const { raw: addRaw } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id || null,
      quantity: 1,
    }, { headers }, { name: "journey_buyer_cart_add" });
    check(addRaw, {
      "buyer cart add — 200 or 409": (r) => r.status === 200 || r.status === 409,
    });
    think(0.5);

    // View cart
    const { body: cartBody } = apiGet("/cart", { headers }, { name: "journey_buyer_cart_view" });
    check(cartBody, {
      "buyer view cart — success": (b) => b && b.success === true,
    });
    think(1);

    // Attempt checkout (no auth — will get 401)
    const { raw: payRaw } = apiPost("/orders/create-payment", {
      shipping_address_id: null,
      billing_address_id: null,
    }, { headers }, { name: "journey_buyer_checkout_attempt" });
    check(payRaw, {
      "checkout attempt — responds": (r) => r.status === 200 || r.status === 401 || r.status === 409 || r.status === 422,
    });
    think(1);
  }

  // Cleanup
  apiDelete("/cart", { headers }, { name: "journey_buyer_cleanup" });
}

function searcherJourney(data, headers) {
  const terms = [
    "silver ring", "gold necklace", "oxidized earrings",
    "jhumka", "pendant set", "anklet", "bangle",
    "bracelet men", "kids jewelry", "wedding",
  ];

  for (let i = 0; i < 5; i++) {
    const term = terms[Math.floor(Math.random() * terms.length)];

    const { body: searchBody } = apiGet("/search", {
      query: { q: term, page: 1, page_size: 20 },
    }, { name: `journey_search_${i}` });
    check(searchBody, {
      [`search ${i} — success`]: (b) => b && b.success === true,
    });
    think(1);

    if (Math.random() > 0.5) {
      const { body: acBody } = apiGet("/search/autocomplete", {
        query: { q: term.substring(0, Math.min(4, term.length)), limit: 10 },
      }, { name: `journey_autocomplete_${i}` });
      check(acBody, {
        [`autocomplete ${i} — success`]: (b) => b && b.success === true,
      });
    }
    think(0.5);
  }
}
