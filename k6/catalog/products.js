// k6 test — Catalog: Product listing and product detail
// Tests: GET /products, GET /products/{slug}

import { check, group } from "k6";
import { apiGet, think } from "../helpers/http.js";
import { loadThresholds } from "../thresholds/default.js";

export const options = {
  scenarios: {
    product_list: {
      executor: "constant-vus",
      vus: 10,
      duration: "2m",
    },
  },
  thresholds: {
    ...loadThresholds,
    "http_req_duration{endpoint:/products}": ["p(95)<400", "p(99)<800"],
    "http_req_duration{endpoint:/products/:slug}": ["p(95)<300", "p(99)<600"],
  },
};

// Shared product slugs — populated during setup
let productSlugs = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 30, include_collections: false },
  }, { name: "setup_products" });

  if (body && body.data && body.data.items) {
    productSlugs = body.data.items.map((p) => p.slug).filter(Boolean);
  }
  return { slugs: productSlugs };
}

export default function (data) {
  const slugs = data.slugs || productSlugs;
  if (slugs.length === 0) return;

  group("Product Listing", () => {
    // Default listing (page 1, 20 per page)
    const { body: listBody } = apiGet("/products", {
      query: { page: 1, page_size: 20 },
    }, { name: "product_list_default" });

    check(listBody, {
      "product list — success": (b) => b && b.success === true,
      "product list — has items": (b) => b && b.data && b.data.items && b.data.items.length > 0,
      "product list — has total": (b) => b && b.data && b.data.total > 0,
    });

    think(0.5);

    // Filtered listing — by metal type
    const { body: metalBody } = apiGet("/products", {
      query: { page: 1, page_size: 20, metal_type: "silver", include_collections: false },
    }, { name: "product_list_metal_filter" });

    check(metalBody, {
      "metal filter — success": (b) => b && b.success === true,
      "metal filter — has items": (b) => b && b.data && b.data.items !== undefined,
    });

    think(0.3);

    // Filtered listing — by gender
    const { body: genderBody } = apiGet("/products", {
      query: { page: 1, page_size: 20, gender: "women", include_collections: false },
    }, { name: "product_list_gender_filter" });

    check(genderBody, {
      "gender filter — success": (b) => b && b.success === true,
      "gender filter — has items": (b) => b && b.data && b.data.items !== undefined,
    });

    think(0.3);

    // Featured products
    const { body: featBody } = apiGet("/products", {
      query: { page: 1, page_size: 12, is_featured: true, include_collections: false },
    }, { name: "product_list_featured" });

    check(featBody, {
      "featured filter — success": (b) => b && b.success === true,
    });

    think(0.3);

    // New arrivals
    const { body: newArrBody } = apiGet("/products", {
      query: { page: 1, page_size: 12, is_new_arrival: true, include_collections: false },
    }, { name: "product_list_new_arrivals" });

    check(newArrBody, {
      "new arrivals filter — success": (b) => b && b.success === true,
    });

    think(0.3);

    // Best sellers
    const { body: bestBody } = apiGet("/products", {
      query: { page: 1, page_size: 12, is_best_seller: true, include_collections: false },
    }, { name: "product_list_bestsellers" });

    check(bestBody, {
      "bestsellers filter — success": (b) => b && b.success === true,
    });

    think(0.3);

    // Price range filter
    const { body: priceBody } = apiGet("/products", {
      query: { page: 1, page_size: 20, min_price: 500, max_price: 5000, include_collections: false },
    }, { name: "product_list_price_range" });

    check(priceBody, {
      "price range filter — success": (b) => b && b.success === true,
      "price range filter — items in range": (b) => {
        if (!b || !b.data || !b.data.items) return true;
        return b.data.items.every((p) => {
          const price = p.base_price || p.price || 0;
          return price >= 500 && price <= 5000;
        });
      },
    });

    think(0.3);

    // Sorted by price
    const { body: sortBody } = apiGet("/products", {
      query: { page: 1, page_size: 20, sort_by: "base_price", sort_dir: "asc", include_collections: false },
    }, { name: "product_list_sort_price_asc" });

    check(sortBody, {
      "sort filter — success": (b) => b && b.success === true,
      "sort filter — items are sorted": (b) => {
        if (!b || !b.data || !b.data.items || b.data.items.length < 2) return true;
        for (let i = 1; i < b.data.items.length; i++) {
          const prev = b.data.items[i - 1].base_price || b.data.items[i - 1].price || 0;
          const curr = b.data.items[i].base_price || b.data.items[i].price || 0;
          if (prev > curr) return false;
        }
        return true;
      },
    });

    think(0.3);

    // Page 2
    const { body: page2Body } = apiGet("/products", {
      query: { page: 2, page_size: 20 },
    }, { name: "product_list_page2" });

    check(page2Body, {
      "page 2 — success": (b) => b && b.success === true,
      "page 2 — has items": (b) => b && b.data && b.data.items && b.data.items.length > 0,
    });
  });

  think(1);

  group("Product Detail", () => {
    // Pick a random product slug
    const slug = slugs[Math.floor(Math.random() * slugs.length)];

    const { body: detailBody } = apiGet(`/products/${slug}`, {}, {
      name: "product_detail",
    });

    check(detailBody, {
      "product detail — success": (b) => b && b.success === true,
      "product detail — has name": (b) => b && b.data && b.data.name,
      "product detail — has price": (b) => b && b.data && b.data.base_price > 0,
    });
  });

  think(1);
}
