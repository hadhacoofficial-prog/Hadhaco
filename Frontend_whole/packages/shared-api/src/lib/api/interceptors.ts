/**
 * Request/response interceptors used by the HTTP client.
 *
 * Kept separate from `client.ts` so the cross-cutting concerns â€”
 * auth-header injection, query serialization, dev logging â€” are composable
 * and individually testable.
 */
import { ENV } from "../../config/env";
import { getCsrfToken } from "../auth/store";
import type { QueryParams } from "@hadha/shared-types";

/**
 * Serialize a params object into a query string. Arrays repeat the key
 * (`tags=a&tags=b`); null/undefined are skipped. Returns "" or "?...".
 */
export function serializeParams(params?: QueryParams): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue;
    if (Array.isArray(value)) {
      for (const v of value) {
        if (v === null || v === undefined) continue;
        sp.append(key, String(v));
      }
    } else {
      sp.append(key, String(value));
    }
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

/** Join the configured base URL with a request path, avoiding double slashes. */
export function buildUrl(path: string, params?: QueryParams): string {
  const base = ENV.apiBaseUrl.replace(/\/+$/, "");
  const rel = path.startsWith("/") ? path : `/${path}`;
  return `${base}${rel}${serializeParams(params)}`;
}

/**
 * CSRF header for cookie-authenticated writes. Safe methods need none, and a
 * signed-out browser has no token (public endpoints still work).
 */
export function csrfHeader(method: string): Record<string, string> {
  if (method === "GET" || method === "HEAD" || method === "OPTIONS") return {};
  const token = getCsrfToken();
  return token ? { "X-CSRF-Token": token } : {};
}

const reqStart = new WeakMap<object, number>();

export function logRequest(method: string, url: string, tag: object): void {
  if (!ENV.isDev) return;
  reqStart.set(tag, performance.now());

  console.debug(`%câ†’ ${method} ${url}`, "color:#888");
}

export function logResponse(method: string, url: string, status: number, tag: object): void {
  if (!ENV.isDev) return;
  const started = reqStart.get(tag);
  const ms = started ? Math.round(performance.now() - started) : undefined;
  const color = status >= 500 ? "#e74c3c" : status >= 400 ? "#e67e22" : "#2ecc71";

  console.debug(
    `%câ† ${status} ${method} ${url}${ms != null ? ` (${ms}ms)` : ""}`,
    `color:${color}`,
  );
}
