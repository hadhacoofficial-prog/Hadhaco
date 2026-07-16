// k6 test — Health checks and readiness probes
// Tests: /health, /health/ready, /health/live

import { check } from "k6";
import http from "k6/http";
import { apiUrl } from "../helpers/http.js";

export const options = {
  vus: 1,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(95)<200"],
    http_req_failed: ["rate<0.001"],
  },
};

export default function () {
  // Health check (no auth, no DB)
  const healthRes = http.get(apiUrl("/health").replace("/api/v1", ""), {
    tags: { name: "health" },
    timeout: "5s",
  });
  check(healthRes, {
    "health — HTTP 200": (r) => r.status === 200,
  });

  // Readiness check (checks DB + Redis)
  const readyRes = http.get(apiUrl("/health/ready").replace("/api/v1", ""), {
    tags: { name: "health_ready" },
    timeout: "10s",
  });
  check(readyRes, {
    "health/ready — HTTP 200": (r) => r.status === 200,
  });

  // Liveness check
  const liveRes = http.get(apiUrl("/health/live").replace("/api/v1", ""), {
    tags: { name: "health_live" },
    timeout: "5s",
  });
  check(liveRes, {
    "health/live — HTTP 200": (r) => r.status === 200,
  });
}
