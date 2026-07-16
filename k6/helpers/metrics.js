// k6 helpers — Extended performance metrics
// Tracks throughput, status codes, business metrics, and bottleneck indicators

import { Trend, Counter, Rate, Gauge } from "k6/metrics";
import { check } from "k6";

// ── Throughput metrics ────────────────────────────────────────────────────────

export const throughput = new Counter("total_requests");
export const activeVUs = new Gauge("active_vus");

// ── Status code breakdown ────────────────────────────────────────────────────

export const status2xx = new Counter("status_2xx");
export const status3xx = new Counter("status_3xx");
export const status4xx = new Counter("status_4xx");
export const status5xx = new Counter("status_5xx");

// ── Endpoint-specific latency ────────────────────────────────────────────────

export const productLatency = new Trend("endpoint_products", true);
export const productDetailLatency = new Trend("endpoint_product_detail", true);
export const searchLatency = new Trend("endpoint_search", true);
export const homepageLatency = new Trend("endpoint_homepage", true);
export const cartLatency = new Trend("endpoint_cart", true);
export const checkoutLatency = new Trend("endpoint_checkout", true);
export const categoriesLatency = new Trend("endpoint_categories", true);
export const collectionsLatency = new Trend("endpoint_collections", true);

// ── Business metrics ─────────────────────────────────────────────────────────

export const cartAddSuccessRate = new Rate("business_cart_add_success");
export const checkoutSuccessRate = new Rate("business_checkout_success");
export const searchSuccessRate = new Rate("business_search_success");
export const productViewSuccessRate = new Rate("business_product_view_success");

// ── Connection pool / bottleneck indicators ───────────────────────────────────

export const timeouts = new Counter("timeouts");
export const connectionErrors = new Counter("connection_errors");
export const slowRequests = new Trend("slow_requests", true);

// ── Recording helpers ────────────────────────────────────────────────────────

/**
 * Record a request result against status code counters.
 */
export function recordStatusCode(status) {
  throughput.add(1);
  if (status >= 200 && status < 300) status2xx.add(1);
  else if (status >= 300 && status < 400) status3xx.add(1);
  else if (status >= 400 && status < 500) status4xx.add(1);
  else if (status >= 500) status5xx.add(1);
}

/**
 * Record timeout/connection error from response timings.
 */
export function recordConnectionError(res) {
  if (res.timings.duration > 10000) {
    slowRequests.add(res.timings.duration);
  }
  if (res.error) {
    if (res.error.includes("timeout")) timeouts.add(1);
    else connectionErrors.add(1);
  }
}

/**
 * Map endpoint path to the correct Trend metric.
 */
const trendMap = {
  "/products": productLatency,
  "/categories": categoriesLatency,
  "/collections": collectionsLatency,
  "/cms/homepage": homepageLatency,
  "/search": searchLatency,
  "/cart": cartLatency,
};

/**
 * Record latency against the right endpoint-specific trend.
 */
export function recordEndpointLatency(duration, path) {
  for (const [prefix, trend] of Object.entries(trendMap)) {
    if (path.startsWith(prefix)) {
      trend.add(duration);
      return;
    }
  }
  // Fallback for checkout/payment/order endpoints
  if (path.includes("order") || path.includes("payment") || path.includes("checkout")) {
    checkoutLatency.add(duration);
  }
}

/**
 * Wrap a raw k6 response to record all metrics automatically.
 */
export function recordResponse(res, path) {
  recordStatusCode(res.status);
  recordConnectionError(res);
  recordEndpointLatency(res.timings.duration, path);
}

/**
 * Create a check that records business metric.
 */
export function businessCheck(label, successFn, metricFn) {
  const result = successFn();
  metricFn(result);
  return result;
}
