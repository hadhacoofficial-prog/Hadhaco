import http from "k6/http";
import { check } from "k6";

export default function () {
  const baseUrl = __ENV.BASE_URL || "http://localhost:8000";

  // Test search with URL params (like our helper now does)
  const r1 = http.get(`${baseUrl}/api/v1/search?q=ring&page=1&page_size=10`);
  console.log(`Search URL: status=${r1.status}`);

  // Test cart
  const r2 = http.get(`${baseUrl}/api/v1/cart`, {
    headers: { "X-Session-ID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" },
  });
  console.log(`Cart: status=${r2.status}`);

  // Test trending
  const r3 = http.get(`${baseUrl}/api/v1/search/trending?limit=10`);
  console.log(`Trending: status=${r3.status}`);

  check(r1, { "search — 200": (r) => r.status === 200 });
  check(r2, { "cart — 200": (r) => r.status === 200 });
  check(r3, { "trending — 200": (r) => r.status === 200 });
}
