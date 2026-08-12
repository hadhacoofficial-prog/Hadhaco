// k6 — Bounded production readiness validation (READ-ONLY)
// ----------------------------------------------------------
// Targets the live production API (default https://api.hadha.co) using only
// public GET endpoints — no auth, no writes, no admin routes.
//
// Profile is deliberately bounded: 2 VUs, at most 12 shared iterations
// (~60 requests max), hard wall-time cap. This is a probe, not a load test,
// and stays far below the production smoke profile (k6/config/production.js
// documents production as read-only only).
//
// Usage:
//   k6 run smoke/prod-readiness.js                       # production
//   k6 run smoke/prod-readiness.js --env BASE_URL=http://localhost:8000
//
// Output:
//   --summary-export results/prod-readiness-live.json

import { check, group } from "k6";
import { apiGet, think } from "../helpers/http.js";

export const options = {
  // shared-iterations executor: total 12 iterations across 2 VUs, ended
  // early if the 60s wall clock is hit first.
  vus: 2,
  iterations: 12,
  duration: "60s",
  thresholds: {
    http_req_failed: ["rate<0.02"],
    "http_req_duration{name:list}": ["p(95)<1000"],
    "http_req_duration{name:detail}": ["p(95)<800"],
    "http_req_duration{name:collections}": ["p(95)<1000"],
    "http_req_duration{name:homepage}": ["p(95)<1000"],
  },
};

let slugs = [];

export function setup() {
  const { body } = apiGet(
    "/products",
    { query: { page: 1, page_size: 10 } },
    { name: "setup_products" },
  );
  if (body && body.data && body.data.items) {
    slugs = body.data.items.map((p) => p.slug).filter(Boolean);
  }
  return { slugs };
}

export default function (data) {
  const s = (data && data.slugs) || slugs;

  group("Product List", () => {
    const { body } = apiGet(
      "/products",
      { query: { page: 1, page_size: 20 } },
      { name: "list" },
    );
    check(body, {
      "list — success": (b) => b && b.success === true,
      "list — has items": (b) => b && b.data && b.data.items && b.data.items.length > 0,
    });
    think(0.5);
  });

  if (s.length > 0) {
    const slug = s[Math.floor(Math.random() * s.length)];
    group("Product Detail (PDP)", () => {
      const { raw, body } = apiGet(`/products/${slug}`, {}, { name: "detail" });
      check(raw, { "detail — HTTP 200": (r) => r.status === 200 });
      check(body, {
        "detail — success": (b) => b && b.success === true,
        "detail — has product": (b) => b && b.data && b.data.slug === slug,
      });
      think(0.5);
    });
  }

  group("Collections", () => {
    const { body } = apiGet("/collections", {}, { name: "collections" });
    check(body, {
      "collections — success": (b) => b && b.success === true,
    });
    think(0.2);
  });

  group("Categories", () => {
    const { body } = apiGet("/categories", {}, { name: "categories" });
    check(body, {
      "categories — success": (b) => b && b.success === true,
    });
    think(0.2);
  });

  group("Homepage", () => {
    const { body } = apiGet("/cms/homepage", {}, { name: "homepage" });
    check(body, {
      "homepage — success": (b) => b && b.success === true,
    });
  });
}
