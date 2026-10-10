// Read-only production ramp: anonymous GETs of storefront pages only.
// No auth, cart, checkout, or write endpoints. Storefront SSR calls the backend
// over the internal network, so this exercises Cloudflare -> nginx -> storefront
// -> backend -> Redis/Supabase without hitting the api.hadha.co per-IP limiter.
// Aborts automatically on sustained errors or latency.
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const BASE = __ENV.BASE || "https://hadha.co";
const API = __ENV.API || "https://api.hadha.co/api/v1";
const STEP = __ENV.STEP || "2m";
const UA = "HadhaLoadTest/1.0 (owner-initiated)";

const cfHit = new Counter("cf_cache_hit");
const cfMiss = new Counter("cf_cache_miss_or_dynamic");
const blocked = new Counter("blocked_403_429");

export const options = {
  userAgent: UA,
  stages: [
    { duration: "30s", target: 5 },
    { duration: STEP, target: 5 },
    { duration: "30s", target: 20 },
    { duration: STEP, target: 20 },
    { duration: "30s", target: 50 },
    { duration: STEP, target: 50 },
    { duration: "30s", target: 100 },
    { duration: STEP, target: 100 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_failed: [{ threshold: "rate<0.02", abortOnFail: true, delayAbortEval: "30s" }],
    http_req_duration: [{ threshold: "p(95)<5000", abortOnFail: true, delayAbortEval: "60s" }],
    "http_req_duration{page:home}": ["p(95)<999999"],
    "http_req_duration{page:products}": ["p(95)<999999"],
    "http_req_duration{page:collections}": ["p(95)<999999"],
    blocked_403_429: [{ threshold: "count<20", abortOnFail: true }],
  },
};

export function setup() {
  const r = http.get(`${API}/products?page=1&page_size=40`);
  const slugs = r.status === 200 ? r.json("data.items").map((i) => i.slug) : [];
  const c = http.get(`${API}/categories`);
  const cats = c.status === 200 ? c.json("data").map((x) => x.slug) : [];
  return { slugs, cats };
}

export default function (data) {
  const pick = (a) => a[Math.floor(Math.random() * a.length)];
  const roll = Math.random();
  let url;
  if (roll < 0.25) url = `${BASE}/`;
  else if (roll < 0.5) url = `${BASE}/products`;
  else if (roll < 0.85 && data.slugs.length) url = `${BASE}/products/${pick(data.slugs)}`;
  else if (data.cats.length) url = `${BASE}/collections`;
  else url = `${BASE}/about`;

  const res = http.get(url, { tags: { page: url.replace(BASE, "").split("/")[1] || "home" } });
  check(res, { "status 200": (r) => r.status === 200 });
  if (res.status === 403 || res.status === 429) blocked.add(1);
  (res.headers["Cf-Cache-Status"] === "HIT" ? cfHit : cfMiss).add(1);
  sleep(1 + Math.random() * 2);
}
