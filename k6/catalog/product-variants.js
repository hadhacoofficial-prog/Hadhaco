// k6 test — Product variants and product images
// Verifies: Product detail with variants, variant selection, image URLs

import { check, group } from "k6";
import { apiGet, think } from "../helpers/http.js";

export const options = {
  scenarios: {
    variants: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
      exec: "testProductVariants",
    },
  },
  thresholds: {
    "http_req_duration{endpoint:/products}": ["p(95)<500", "p(99)<1500"],
    "http_req_duration{endpoint:/products/:slug}": ["p(95)<500", "p(99)<1500"],
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
  return { products: allProducts };
}

export function testProductVariants(data) {
  const products = data.products || allProducts;
  if (products.length === 0) return;

  const product = products[Math.floor(Math.random() * products.length)];

  group("Product Variants — Detail View", () => {
    const { body } = apiGet(`/products/${product.slug}`, {}, {
      name: "variant_product_detail",
    });

    if (body && body.data) {
      const p = body.data;

      check(p, {
        "product has id": (v) => v && v.id !== undefined,
        "product has name": (v) => v && v.name && v.name.length > 0,
        "product has slug": (v) => v && v.slug && v.slug.length > 0,
        "product has base_price": (v) => v && v.base_price !== undefined && v.base_price > 0,
        "product has stock_quantity": (v) => v && v.stock_quantity !== undefined,
        "product has status": (v) => v && v.status !== undefined,
        "product has created_at": (v) => v && v.created_at !== undefined,
      });

      // Check variants if present
      if (p.variants && p.variants.length > 0) {
        const variant = p.variants[0];

        check(variant, {
          "variant has id": (v) => v && v.id !== undefined,
          "variant has sku": (v) => v && v.sku !== undefined,
          "variant has base_price": (v) => v && v.base_price !== undefined && v.base_price > 0,
          "variant has stock_quantity": (v) => v && v.stock_quantity !== undefined,
        });

        // Store first variant ID for later
        product.variant_id = variant.id;
      }

      // Check images if present
      if (p.images && p.images.length > 0) {
        const image = p.images[0];

        check(image, {
          "image has url": (v) => v && v.url && v.url.length > 0,
          "image url is valid": (v) => v && v.url && (v.url.startsWith("http") || v.url.startsWith("/")),
        });
      } else if (p.primary_image) {
        check(p, {
          "primary_image is valid url": (v) => v && v.primary_image && typeof v.primary_image === "string" && v.primary_image.startsWith("http"),
        });
      }

      // Check attributes if present
      if (p.attributes && p.attributes.length > 0) {
        check(null, {
          "product has attributes": () => true,
        });
      }

      // Check category/collection associations
      if (p.category) {
        check(p.category, {
          "category has id": (v) => v && v.id !== undefined,
          "category has name": (v) => v && v.name !== undefined,
        });
      }

      if (p.collections && p.collections.length > 0) {
        check(null, {
          "product has collections": () => true,
        });
      }
    }
  });

  think(1);
}

export function teardown() {}
