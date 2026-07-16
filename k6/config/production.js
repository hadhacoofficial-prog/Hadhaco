// k6 configuration — Production environment
// api.hadha.co behind Nginx reverse proxy

export const env = {
  BASE_URL: __ENV.BASE_URL || "https://api.hadha.co",
  API_PREFIX: "/api/v1",
  STOREFRONT_URL: __ENV.STOREFRONT_URL || "https://hadha.co",

  // Production: NO dev auth. Read-only tests only.
  DEV_EMAIL: "",
  DEV_PASSWORD: "",
  CUSTOMER_EMAIL: __ENV.CUSTOMER_EMAIL || "",
  CUSTOMER_PASSWORD: __ENV.CUSTOMER_PASSWORD || "",

  REDIS_URL: "",
};

// Stricter thresholds for production
export const thresholds = {
  http_req_duration: ["p(95)<300", "p(99)<600"],
  http_req_failed: ["rate<0.005"],
  http_reqs: ["rate>25"],
};
