/**
 * Normalized API error model.
 *
 * Every failure that leaves the HTTP client — network failure, timeout,
 * non-2xx response, or a `{ success: false }` envelope — is converted into
 * an `ApiError`. Components/hooks never see raw `Response`/`fetch` errors.
 */

export type ApiErrorKind =
  | "network" // request never completed (offline, DNS, CORS, connection refused)
  | "timeout" // aborted by our timeout
  | "http" // server replied with a non-2xx status
  | "business" // 2xx/JSON but `success: false` in the envelope
  | "parse" // response body could not be parsed
  | "unknown";

export interface ApiErrorOptions {
  kind: ApiErrorKind;
  /** HTTP status code, when a response was received. */
  status?: number;
  /** Machine-readable code from the backend envelope (e.g. `NOT_FOUND`). */
  code?: string;
  /** Raw `data` payload from the error envelope, if any (e.g. field errors). */
  details?: unknown;
  /** The request that failed, for logging/debugging. */
  request?: { method: string; url: string };
  cause?: unknown;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly code?: string;
  readonly details?: unknown;
  readonly request?: { method: string; url: string };

  constructor(message: string, opts: ApiErrorOptions) {
    super(message);
    this.name = "ApiError";
    this.kind = opts.kind;
    this.status = opts.status;
    this.code = opts.code;
    this.details = opts.details;
    this.request = opts.request;
    if (opts.cause !== undefined) {
      // Preserve the original error for stack traces / debugging.
      (this as { cause?: unknown }).cause = opts.cause;
    }
  }

  /** True for 401 — caller should re-authenticate. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** True for 403 — authenticated but lacks the required role/permission. */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** True for 422 / validation failures — `details` usually holds field errors. */
  get isValidation(): boolean {
    return this.status === 422 || this.code === "VALIDATION_ERROR";
  }

  /** True when the failure is transient and retrying may help. */
  get isRetryable(): boolean {
    if (this.kind === "network" || this.kind === "timeout") return true;
    if (this.kind === "http" && this.status) {
      return this.status >= 500 || this.status === 408 || this.status === 429;
    }
    return false;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

/**
 * Best-effort, human-readable message for toasts. Falls back through the
 * backend message → code → a generic string so the UI always has something.
 */
export function toUserMessage(
  e: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  if (isApiError(e)) {
    if (e.kind === "network") return "Can't reach the server. Check your connection and try again.";
    if (e.kind === "timeout") return "The request took too long. Please try again.";
    if (e.message) return e.message;
    if (e.code) return e.code.replace(/_/g, " ").toLowerCase();
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}
