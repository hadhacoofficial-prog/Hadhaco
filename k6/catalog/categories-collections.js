// k6 test — Catalog: Categories and Collections browsing
// Tests: GET /categories, GET /categories/navbar, GET /categories/navigation
//        GET /collections, GET /collections/{slug}

import { check, group } from "k6";
import { apiGet, think } from "../helpers/http.js";
import { loadThresholds } from "../thresholds/default.js";

export const options = {
  scenarios: {
    browse_catalog: {
      executor: "constant-vus",
      vus: 10,
      duration: "2m",
    },
  },
  thresholds: {
    ...loadThresholds,
    "http_req_duration{endpoint:/categories}": ["p(95)<300"],
    "http_req_duration{endpoint:/categories/navigation}": ["p(95)<300"],
    "http_req_duration{endpoint:/collections}": ["p(95)<300"],
  },
};

let collectionSlugs = [];

export function setup() {
  const { body } = apiGet("/collections", {}, { name: "setup_collections" });
  if (body && body.data) {
    collectionSlugs = body.data.map((c) => c.slug).filter(Boolean);
  }
  return { slugs: collectionSlugs };
}

export default function (data) {
  const slugs = data.slugs || collectionSlugs;

  group("Categories", () => {
    // Full category tree
    const { body: treeBody } = apiGet("/categories", {}, { name: "category_tree" });
    check(treeBody, {
      "category tree — success": (b) => b && b.success === true,
      "category tree — has data": (b) => b && b.data !== null,
    });
    think(0.5);

    // Navbar categories (lightweight, heavily cached)
    const { body: navBody } = apiGet("/categories/navbar", {}, { name: "category_navbar" });
    check(navBody, {
      "category navbar — success": (b) => b && b.success === true,
    });
    think(0.3);

    // Navigation categories (used by main nav)
    const { body: navigationBody } = apiGet("/categories/navigation", {}, { name: "category_navigation" });
    check(navigationBody, {
      "category navigation — success": (b) => b && b.success === true,
      "category navigation — has gender sections": (b) =>
        b && b.data && (b.data.women || b.data.men || b.data.unisex || b.data.kids),
    });
    think(0.5);

    // Products filtered by category slug
    if (treeBody && treeBody.data) {
      const firstCategory = treeBody.data.find((c) => c.slug);
      if (firstCategory) {
        apiGet("/products", {
          query: { page: 1, page_size: 20, category_slug: firstCategory.slug, include_collections: false },
        }, { name: "products_by_category_slug" });
        think(0.5);
      }
    }
  });

  group("Collections", () => {
    // List all collections
    const { body: listBody } = apiGet("/collections", {}, { name: "collection_list" });
    check(listBody, {
      "collection list — success": (b) => b && b.success === true,
      "collection list — has items": (b) => b && b.data && b.data.length > 0,
    });
    think(0.5);

    // Get collection by slug
    if (slugs.length > 0) {
      const slug = slugs[Math.floor(Math.random() * slugs.length)];
      const { body: detailBody } = apiGet(`/collections/${slug}`, {}, {
        name: "collection_detail",
      });
      check(detailBody, {
        "collection detail — success": (b) => b && b.success === true,
        "collection detail — has name": (b) => b && b.data && b.data.name,
      });
      think(0.5);

      // Products in collection
      apiGet("/products", {
        query: { page: 1, page_size: 20, collection_slug: slug, include_collections: false },
      }, { name: "products_by_collection_slug" });
    }
  });

  think(1);
}
