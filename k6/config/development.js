// k6 configuration — Development environment
// Matches docker-compose.yml: backend on :8000, storefront on :8080

export const env = {
  // Backend API
  BASE_URL: __ENV.BASE_URL || "http://localhost:8000",
  API_PREFIX: "/api/v1",

  // Frontend (for browser-level smoke tests)
  STOREFRONT_URL: __ENV.STOREFRONT_URL || "http://localhost:8080",

  // Dev auth (development only — POST /dev/login)
  DEV_EMAIL: __ENV.DEV_EMAIL || "admin@hadha.co",
  DEV_PASSWORD: __ENV.DEV_PASSWORD || "",

  // Test customer credentials (Supabase auth)
  CUSTOMER_EMAIL: __ENV.CUSTOMER_EMAIL || "customer@hadha.co",
  CUSTOMER_PASSWORD: __ENV.CUSTOMER_PASSWORD || "",

  // Redis (informational — k6 doesn't connect directly)
  REDIS_URL: __ENV.REDIS_URL || "redis://localhost:6379",
};

// Performance targets for development
export const thresholds = {
  http_req_duration: ["p(95)<500", "p(99)<1000"],
  http_req_failed: ["rate<0.01"],
  http_reqs: ["rate>10"],
};
