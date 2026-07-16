// k6 helpers — HTTP client with envelope unwrapping
// Mirrors the backend's BaseSuccessResponse { success, code, message, data } format

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Counter, Rate } from "k6/metrics";

// ── Custom metrics ───────────────────────────────────────────────────────────

export const apiLatency = new Trend("api_latency", true);
export const apiErrors = new Counter("api_errors");
export const apiSuccessRate = new Rate("api_success_rate");

// ── Core HTTP helpers ────────────────────────────────────────────────────────

/**
 * Build full API URL.
 */
export function apiUrl(path, baseUrl) {
  const base = baseUrl || __ENV.BASE_URL || "http://localhost:8000";
  const prefix = __ENV.API_PREFIX || "/api/v1";
  return `${base}${prefix}${path}`;
}

/**
 * Parse the backend envelope response.
 * Returns { success, code, message, data } or null on failure.
 */
export function parseEnvelope(res, label) {
  check(res, {
    [`${label} — HTTP 2xx`]: (r) => r.status >= 200 && r.status < 300,
  });

  if (res.status < 200 || res.status >= 300) {
    apiErrors.add(1);
    apiSuccessRate.add(false);
    return null;
  }

  let body;
  try {
    body = JSON.parse(res.body);
  } catch (e) {
    apiErrors.add(1);
    apiSuccessRate.add(false);
    return null;
  }

  const ok = body.success === true;
  apiSuccessRate.add(ok);
  if (!ok) apiErrors.add(1);

  return body;
}

/**
 * Append query parameters to a URL string.
 * We embed them directly because k6's `params` object serialises values
 * differently (e.g. booleans as "true" instead of "1"), which causes
 * FastAPI/Pydantic 422 ValidationErrors on integer/boolean query params.
 */
function appendQuery(url, query) {
  if (!query) return url;
  const parts = [];
  for (const [key, val] of Object.entries(query)) {
    if (val === undefined || val === null) continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(val)}`);
  }
  return parts.length ? `${url}?${parts.join("&")}` : url;
}

/**
 * Build k6 HTTP params from our helper options.
 * Handles headers and timeout only — query params are embedded in the URL.
 */
function buildHttpParams(opts) {
  const result = {};
  if (opts.headers) result.headers = opts.headers;
  if (opts.timeout) result.timeout = opts.timeout;
  return result;
}

/**
 * GET request with query params, metrics, and envelope parsing.
 *
 * @param {string} path - API path e.g. "/products"
 * @param {object} opts - { headers, query: {q:"ring", page:1}, timeout }
 * @param {object} tags - k6 tags { name }
 */
export function apiGet(path, opts = {}, tags = {}) {
  const url = appendQuery(apiUrl(path), opts.query);
  const label = tags.name || `GET ${path}`;
  const httpOpts = buildHttpParams(opts);
  httpOpts.tags = { ...tags, method: "GET", endpoint: path };
  if (!httpOpts.timeout) httpOpts.timeout = "10s";

  const res = http.get(url, httpOpts);
  apiLatency.add(res.timings.duration, { endpoint: path, method: "GET" });
  return { raw: res, body: parseEnvelope(res, label) };
}

/**
 * POST request with JSON body.
 */
export function apiPost(path, body, opts = {}, tags = {}) {
  const url = appendQuery(apiUrl(path), opts.query);
  const label = tags.name || `POST ${path}`;
  const httpOpts = buildHttpParams(opts);
  httpOpts.headers = { "Content-Type": "application/json", ...(httpOpts.headers || {}) };
  httpOpts.tags = { ...tags, method: "POST", endpoint: path };
  if (!httpOpts.timeout) httpOpts.timeout = "15s";

  const res = http.post(url, JSON.stringify(body), httpOpts);
  apiLatency.add(res.timings.duration, { endpoint: path, method: "POST" });
  return { raw: res, body: parseEnvelope(res, label) };
}

/**
 * PATCH request with JSON body.
 */
export function apiPatch(path, body, opts = {}, tags = {}) {
  const url = appendQuery(apiUrl(path), opts.query);
  const label = tags.name || `PATCH ${path}`;
  const httpOpts = buildHttpParams(opts);
  httpOpts.headers = { "Content-Type": "application/json", ...(httpOpts.headers || {}) };
  httpOpts.tags = { ...tags, method: "PATCH", endpoint: path };
  if (!httpOpts.timeout) httpOpts.timeout = "15s";

  const res = http.patch(url, JSON.stringify(body), httpOpts);
  apiLatency.add(res.timings.duration, { endpoint: path, method: "PATCH" });
  return { raw: res, body: parseEnvelope(res, label) };
}

/**
 * PUT request with JSON body.
 */
export function apiPut(path, body, opts = {}, tags = {}) {
  const url = appendQuery(apiUrl(path), opts.query);
  const label = tags.name || `PUT ${path}`;
  const httpOpts = buildHttpParams(opts);
  httpOpts.headers = { "Content-Type": "application/json", ...(httpOpts.headers || {}) };
  httpOpts.tags = { ...tags, method: "PUT", endpoint: path };
  if (!httpOpts.timeout) httpOpts.timeout = "15s";

  const res = http.put(url, JSON.stringify(body), httpOpts);
  apiLatency.add(res.timings.duration, { endpoint: path, method: "PUT" });
  return { raw: res, body: parseEnvelope(res, label) };
}

/**
 * DELETE request.
 */
export function apiDelete(path, opts = {}, tags = {}) {
  const url = appendQuery(apiUrl(path), opts.query);
  const label = tags.name || `DELETE ${path}`;
  const httpOpts = buildHttpParams(opts);
  httpOpts.tags = { ...tags, method: "DELETE", endpoint: path };
  if (!httpOpts.timeout) httpOpts.timeout = "10s";

  const res = http.del(url, null, httpOpts);
  apiLatency.add(res.timings.duration, { endpoint: path, method: "DELETE" });
  return { raw: res, body: parseEnvelope(res, label) };
}

/**
 * Authenticated GET helper.
 */
export function apiAuthGet(path, token, extraHeaders = {}, tags = {}) {
  return apiGet(path, {
    headers: { Authorization: `Bearer ${token}`, ...extraHeaders },
  }, tags);
}

/**
 * Authenticated POST helper.
 */
export function apiAuthPost(path, body, token, extraHeaders = {}, tags = {}) {
  return apiPost(path, body, {
    headers: { Authorization: `Bearer ${token}`, ...extraHeaders },
  }, tags);
}

/**
 * Authenticated PATCH helper.
 */
export function apiAuthPatch(path, body, token, extraHeaders = {}, tags = {}) {
  return apiPatch(path, body, {
    headers: { Authorization: `Bearer ${token}`, ...extraHeaders },
  }, tags);
}

/**
 * Authenticated DELETE helper.
 */
export function apiAuthDelete(path, token, extraHeaders = {}, tags = {}) {
  return apiDelete(path, {
    headers: { Authorization: `Bearer ${token}`, ...extraHeaders },
  }, tags);
}

// ── Throttle helper ──────────────────────────────────────────────────────────

/**
 * Sleep with jitter to simulate realistic think time.
 */
export function think(baseSeconds) {
  const jitter = (Math.random() - 0.5) * baseSeconds * 0.3;
  sleep(Math.max(0.1, baseSeconds + jitter));
}
