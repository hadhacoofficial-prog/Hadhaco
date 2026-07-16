// k6 scenario — Smoke test suite
// Quick validation that all critical endpoints are working
// Duration: ~2 minutes, 1-2 VUs

import { check, group } from "k6";
import http from "k6/http";
import { apiGet, apiPost, apiUrl, think } from "../helpers/http.js";
import { generateSessionId } from "../helpers/auth.js";

export const options = {
  vus: 2,
  duration: "2m",
  thresholds: {
    http_req_duration: ["p(95)<2000", "max<10000"],
    http_req_failed: ["rate<0.05"],
  },
};

export default function () {
  group("Smoke — Health", () => {
    const baseUrl = __ENV.BASE_URL || "http://localhost:8000";
    const healthRes = http.get(`${baseUrl}/health`, { timeout: "5s" });
    check(healthRes, { "health — HTTP 200": (r) => r.status === 200 });
    const readyRes = http.get(`${baseUrl}/health/ready`, { timeout: "10s" });
    check(readyRes, { "health/ready — responds": (r) => r.status === 200 || r.status === 503 });
  });

  group("Smoke — Product List", () => {
    const { body } = apiGet("/products", {
      query: { page: 1, page_size: 10 },
    }, { name: "smoke_products" });
    check(body, {
      "products — success": (b) => b && b.success === true,
      "products — has items": (b) => b && b.data && b.data.items && b.data.items.length > 0,
    });
  });

  group("Smoke — Categories", () => {
    const { body } = apiGet("/categories", {}, { name: "smoke_categories" });
    check(body, { "categories — success": (b) => b && b.success === true });
  });

  group("Smoke — Collections", () => {
    const { body } = apiGet("/collections", {}, { name: "smoke_collections" });
    check(body, { "collections — success": (b) => b && b.success === true });
  });

  group("Smoke — Search", () => {
    const { body } = apiGet("/search", {
      query: { q: "ring", page: 1, page_size: 10 },
    }, { name: "smoke_search" });
    check(body, { "search — success": (b) => b && b.success === true });
  });

  group("Smoke — Homepage", () => {
    const { body } = apiGet("/cms/homepage", {}, { name: "smoke_homepage" });
    check(body, { "homepage — success": (b) => b && b.success === true });
  });

  group("Smoke — Cart", () => {
    const sessionId = generateSessionId();
    const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };
    const { body } = apiGet("/cart", { headers }, { name: "smoke_cart" });
    check(body, { "cart — success": (b) => b && b.success === true });
  });

  group("Smoke — Trending", () => {
    const { body } = apiGet("/search/trending", {}, { name: "smoke_trending" });
    check(body, { "trending — success": (b) => b && b.success === true });
  });
}
