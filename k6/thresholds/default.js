// k6 shared — Threshold definitions for different test profiles

/**
 * Default thresholds applied to all tests.
 */
export const defaultThresholds = {
  http_req_duration: ["p(95)<500", "p(99)<1500", "max<5000"],
  http_req_failed: ["rate<0.01"],
  http_reqs: ["rate>5"],
  api_latency: ["p(95)<400", "p(99)<1000"],
  api_success_rate: ["rate>0.99"],
};

/**
 * Smoke test thresholds — relaxed, just checking functionality.
 */
export const smokeThresholds = {
  http_req_duration: ["p(95)<2000", "max<10000"],
  http_req_failed: ["rate<0.05"],
};

/**
 * Load test thresholds — normal production targets.
 */
export const loadThresholds = {
  http_req_duration: ["p(95)<500", "p(99)<1000", "max<3000"],
  http_req_failed: ["rate<0.01"],
  http_reqs: ["rate>10"],
  api_latency: ["p(95)<400", "p(99)<800"],
  api_success_rate: ["rate>0.99"],
};

/**
 * Stress test thresholds — degraded performance acceptable.
 */
export const stressThresholds = {
  http_req_duration: ["p(95)<2000", "p(99)<5000", "max<15000"],
  http_req_failed: ["rate<0.05"],
  http_reqs: ["rate>5"],
};

/**
 * Spike test thresholds — recovery is key.
 */
export const spikeThresholds = {
  http_req_duration: ["p(95)<3000", "p(99)<8000", "max<20000"],
  http_req_failed: ["rate<0.10"],
};

/**
 * Checkout-specific thresholds — critical path.
 */
export const checkoutThresholds = {
  http_req_duration: ["p(95)<1000", "p(99)<2000", "max<5000"],
  http_req_failed: ["rate<0.005"],
  api_success_rate: ["rate>0.995"],
};

/**
 * Inventory concurrency thresholds — race condition detection.
 */
export const inventoryThresholds = {
  http_req_duration: ["p(95)<2000", "p(99)<5000"],
  http_req_failed: ["rate<0.10"],
  api_success_rate: ["rate>0.85"],
};
