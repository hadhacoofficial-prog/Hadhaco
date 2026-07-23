/**
 * Singleton typed HTTP client for the FastAPI backend.
 *
 * Responsibilities (single place for all of them):
 *   â€¢ Base URL join + query serialization
 *   â€¢ Authorization: Bearer <Supabase JWT> injection (read fresh per request)
 *   â€¢ Response-envelope unwrapping â†’ callers get `T`, never `{ data }`
 *   â€¢ Error normalization â†’ always throws `ApiError`
 *   â€¢ Multipart (FormData) support
 *   â€¢ Timeout (AbortController) + retry with backoff
 *   â€¢ Dev request/response logging
 *
 * Usage:
 *   const products = await api.get<ProductListResponse>("/products", { params });
 *   const order = await api.post<OrderResponse>("/orders", { body });
 */
import { ApiError } from "./errors";
import { authHeader, buildUrl, logRequest, logResponse } from "./interceptors";
import type { ApiEnvelope, QueryParams } from "@hadha/shared-types";
import { supabase } from "../supabase/client";

export interface RequestOptions {
  params?: QueryParams;
  /** JSON-serializable body, or a `FormData` for multipart uploads. */
  body?: unknown;
  headers?: Record<string, string>;
  /** Abort signal to cancel from the caller (merged with the timeout signal). */
  signal?: AbortSignal;
  /** Per-request timeout in ms. Default 20s; 0 disables. */
  timeoutMs?: number;
  /** Max retry attempts for transient failures. Default 2 (GET only). */
  retries?: number;
  /** Skip the Authorization header (for strictly public endpoints). */
  skipAuth?: boolean;
  /**
   * HTTP cache mode for the underlying `fetch`. Defaults to the browser's
   * standard behaviour (honours `Cache-Control`). Use `"no-cache"` for live
   * polls that must always revalidate against the origin (cheap 304 when
   * unchanged) instead of being served a stale `max-age` response.
   */
  cache?: RequestCache;
}

type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

const DEFAULT_TIMEOUT_MS = 20_000;
const RETRY_BASE_DELAY_MS = 300;

function isFormData(body: unknown): body is FormData {
  return typeof FormData !== "undefined" && body instanceof FormData;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Merge caller's signal with a fresh timeout signal. */
function withTimeout(
  signal: AbortSignal | undefined,
  timeoutMs: number,
): {
  signal: AbortSignal;
  cancel: () => void;
} {
  const controller = new AbortController();
  const onAbort = () =>
    controller.abort((signal as AbortSignal & { reason?: unknown })?.reason);
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  const timer =
    timeoutMs > 0
      ? setTimeout(
          () => controller.abort(new DOMException("Timeout", "TimeoutError")),
          timeoutMs,
        )
      : undefined;
  return {
    signal: controller.signal,
    cancel: () => {
      if (timer) clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", onAbort);
    },
  };
}

async function parseEnvelope<T>(
  res: Response,
  method: string,
  url: string,
): Promise<T> {
  const text = await res.text();
  let payload: ApiEnvelope<T> | undefined;

  if (text) {
    try {
      payload = JSON.parse(text) as ApiEnvelope<T>;
    } catch {
      // Non-JSON body. If the status is OK, surface a parse error; otherwise
      // fall through to the HTTP error path with the raw text as the message.
      if (res.ok) {
        throw new ApiError("Received an invalid response from the server.", {
          kind: "parse",
          status: res.status,
          request: { method, url },
        });
      }
    }
  }

  if (!res.ok) {
    // FastAPI may return { detail: { message, errors, warnings } } instead of our envelope.
    const fastapiDetail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as Record<string, unknown>).detail
        : undefined;
    const fastapiMsg =
      fastapiDetail && typeof fastapiDetail === "object"
        ? (fastapiDetail as Record<string, unknown>).message
        : undefined;

    throw new ApiError(
      (fastapiMsg as string) ||
        payload?.message ||
        res.statusText ||
        `Request failed (${res.status})`,
      {
        kind: "http",
        status: res.status,
        code: payload?.code,
        details: payload?.data ?? fastapiDetail ?? undefined,
        request: { method, url },
      },
    );
  }

  // 204 No Content / empty body on success.
  if (!payload) return undefined as T;

  if (payload.success === false) {
    throw new ApiError(payload.message || "Request was not successful.", {
      kind: "business",
      status: res.status,
      code: payload.code,
      details: payload.data,
      request: { method, url },
    });
  }

  // Unwrap: callers receive `data`, never the envelope.
  return payload.data as T;
}

async function request<T>(
  method: HttpMethod,
  path: string,
  options: RequestOptions = {},
  _retried = false, // internal: prevents infinite 401-refresh loops
): Promise<T> {
  const url = buildUrl(path, options.params);
  const maxRetries = options.retries ?? (method === "GET" ? 2 : 0);
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  const baseHeaders: Record<string, string> = {
    Accept: "application/json",
    ...options.headers,
  };
  const auth = options.skipAuth ? {} : await authHeader();

  let body: BodyInit | undefined;
  if (options.body !== undefined && options.body !== null) {
    if (isFormData(options.body)) {
      body = options.body; // browser sets multipart boundary; do NOT set Content-Type
    } else {
      baseHeaders["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }
  }

  let attempt = 0;
  // Retry loop for transient (network/5xx/429) failures only.

  while (true) {
    const tag = {};
    const { signal, cancel } = withTimeout(options.signal, timeoutMs);
    logRequest(method, url, tag);
    try {
      const res = await fetch(url, {
        method,
        headers: { ...baseHeaders, ...auth },
        body,
        signal,
        cache: options.cache,
      });
      logResponse(method, url, res.status, tag);

      // 401 silent-refresh: if the access token just expired, ask Supabase to
      // refresh it and retry the request once with the new token.  _retried
      // prevents infinite loops if the backend keeps returning 401 even after
      // a successful token refresh (e.g. the account was revoked server-side).
      if (res.status === 401 && !options.skipAuth && !_retried) {
        const { data } = await supabase.auth.refreshSession();
        if (data.session) {
          // Fresh session obtained â€” retry once with the new token.
          return request<T>(method, path, options, true);
        }
        // Refresh failed (refresh token expired / session revoked).
        // Supabase has signed out the user; AuthProvider's onAuthStateChange
        // will set status="unauthenticated" and protected routes will redirect.
      }

      return await parseEnvelope<T>(res, method, url);
    } catch (err) {
      // Normalize anything thrown by fetch (network/abort) into ApiError.
      const apiErr = normalizeThrown(err, method, url, options.signal);
      if (apiErr.isRetryable && attempt < maxRetries) {
        attempt += 1;
        await delay(RETRY_BASE_DELAY_MS * 2 ** (attempt - 1));
        continue;
      }
      throw apiErr;
    } finally {
      cancel();
    }
  }
}

function normalizeThrown(
  err: unknown,
  method: string,
  url: string,
  callerSignal?: AbortSignal,
): ApiError {
  if (err instanceof ApiError) return err;
  // Abort: distinguish caller-cancel from our timeout.
  if (
    err instanceof DOMException &&
    (err.name === "AbortError" || err.name === "TimeoutError")
  ) {
    if (callerSignal?.aborted && err.name === "AbortError") {
      return new ApiError("Request was cancelled.", {
        kind: "timeout",
        request: { method, url },
        cause: err,
      });
    }
    return new ApiError("The request timed out.", {
      kind: "timeout",
      request: { method, url },
      cause: err,
    });
  }
  return new ApiError("Network request failed.", {
    kind: "network",
    request: { method, url },
    cause: err,
  });
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>("GET", path, options),
  post: <T>(path: string, options?: RequestOptions) =>
    request<T>("POST", path, options),
  patch: <T>(path: string, options?: RequestOptions) =>
    request<T>("PATCH", path, options),
  put: <T>(path: string, options?: RequestOptions) =>
    request<T>("PUT", path, options),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>("DELETE", path, options),
  /** Multipart helper â€” pass a FormData body; Content-Type is set by the browser. */
  upload: <T>(
    path: string,
    form: FormData,
    options?: Omit<RequestOptions, "body">,
  ) => request<T>("POST", path, { ...options, body: form }),
} as const;

export type ApiClient = typeof api;
