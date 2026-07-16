// k6 test — Search functionality
// Tests: GET /search, GET /search/autocomplete, GET /search/trending

import { check, group } from "k6";
import { apiGet, think } from "../helpers/http.js";
import { loadThresholds } from "../thresholds/default.js";

const SEARCH_TERMS = [
  "silver ring",
  "necklace",
  "bracelet",
  "earring",
  "pendant",
  "anklet",
  "bangle",
  "chain",
  "gold",
  "oxidized",
  "jhumka",
  "band",
];

export const options = {
  scenarios: {
    search_users: {
      executor: "constant-vus",
      vus: 15,
      duration: "2m",
    },
  },
  thresholds: {
    ...loadThresholds,
    "http_req_duration{endpoint:/search}": ["p(95)<500", "p(99)<1000"],
    "http_req_duration{endpoint:/search/autocomplete}": ["p(95)<200"],
    "http_req_duration{endpoint:/search/trending}": ["p(95)<300"],
  },
};

export default function () {
  const term = SEARCH_TERMS[Math.floor(Math.random() * SEARCH_TERMS.length)];

  group("Full Text Search", () => {
    const { body } = apiGet("/search", {
      query: { q: term, page: 1, page_size: 20 },
    }, { name: "search_full_text" });

    check(body, {
      "search — success": (b) => b && b.success === true,
      "search — has results": (b) => b && b.data && typeof b.data.total === "number",
    });
    think(1);

    // Search with category filter
    apiGet("/search", {
      query: { q: term, page: 1, page_size: 20, min_price: 500 },
    }, { name: "search_with_filters" });
    think(0.5);
  });

  group("Autocomplete", () => {
    // Autocomplete needs min 2 chars
    const partial = term.substring(0, Math.min(3, term.length));
    const { body } = apiGet("/search/autocomplete", {
      query: { q: partial, limit: 8 },
    }, { name: "search_autocomplete" });

    check(body, {
      "autocomplete — success": (b) => b && b.success === true,
      "autocomplete — has suggestions": (b) => b && b.data && Array.isArray(b.data.suggestions),
    });
    think(0.3);
  });

  group("Trending Searches", () => {
    const { body } = apiGet("/search/trending", {
      query: { limit: 10 },
    }, { name: "search_trending" });

    check(body, {
      "trending — success": (b) => b && b.success === true,
    });
    think(0.3);
  });

  think(0.5);
}
