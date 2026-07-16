// k6 test — Product reviews
// Tests: GET /reviews/products/{id}, GET /reviews/products/{id}/summary

import { check, group } from "k6";
import { apiGet, think } from "../helpers/http.js";
import { loadThresholds } from "../thresholds/default.js";

export const options = {
  scenarios: {
    review_browsing: {
      executor: "constant-vus",
      vus: 10,
      duration: "2m",
    },
  },
  thresholds: loadThresholds,
};

let productIds = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 30, include_collections: false },
  }, { name: "setup_products" });

  if (body && body.data && body.data.items) {
    productIds = body.data.items.map((p) => p.id);
  }
  return { ids: productIds };
}

export default function (data) {
  const ids = data.ids || productIds;
  if (ids.length === 0) return;

  const productId = ids[Math.floor(Math.random() * ids.length)];

  group("Product Reviews", () => {
    // List reviews for a product
    const { body: reviewsBody } = apiGet(`/reviews/products/${productId}`, {
      query: { page: 1, page_size: 10 },
    }, { name: "reviews_list" });

    check(reviewsBody, {
      "reviews list — success": (b) => b && b.success === true,
    });
    think(0.3);

    // Rating summary
    const { body: summaryBody } = apiGet(`/reviews/products/${productId}/summary`, {}, {
      name: "reviews_summary",
    });

    check(summaryBody, {
      "reviews summary — success": (b) => b && b.success === true,
      "reviews summary — has counts": (b) => b && b.data && typeof b.data.review_count === "number",
    });
    think(0.3);

    // Review status (requires auth, gracefully handles 401)
    apiGet(`/reviews/products/${productId}/my-status`, {}, {
      name: "reviews_my_status",
    });
  });

  think(0.5);
}
