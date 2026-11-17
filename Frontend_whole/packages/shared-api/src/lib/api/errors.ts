/**
 * Normalized API error model.
 *
 * Every failure that leaves the HTTP client â€” network failure, timeout,
 * non-2xx response, or a `{ success: false }` envelope â€” is converted into
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

  /** True for 401 â€” caller should re-authenticate. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** True for 403 â€” authenticated but lacks the required role/permission. */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** True for 422 / validation failures â€” `details` usually holds field errors. */
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

const GENERIC_MESSAGE = "Something went wrong. Please try again.";
const SIGN_IN_MESSAGE = "Please sign in to continue.";
const SESSION_EXPIRED_MESSAGE = "Your session has expired. Please sign in again.";
const NO_PERMISSION_MESSAGE = "You don't have permission to do that.";
const NOT_FOUND_MESSAGE = "We couldn't find what you were looking for. It may have been removed.";
const INVALID_INPUT_MESSAGE = "Some details are missing or invalid. Please check and try again.";
const TOO_MANY_MESSAGE = "Too many attempts. Please wait a moment and try again.";
const FILE_TOO_LARGE_MESSAGE = "That file is too large. Please choose a smaller one.";
const SERVER_MESSAGE = "Something went wrong on our side. Please try again in a moment.";

/**
 * Framework/infrastructure wording that means nothing to a shopper. Matched
 * case-insensitively against the whole message; anything else the backend
 * sends is written for customers and shown as-is.
 */
const TECHNICAL_MESSAGES: Record<string, string> = {
  "not authenticated": SIGN_IN_MESSAGE,
  "authentication required": SIGN_IN_MESSAGE,
  unauthorized: SIGN_IN_MESSAGE,
  "invalid token": SESSION_EXPIRED_MESSAGE,
  "token expired": SESSION_EXPIRED_MESSAGE,
  "invalid session": SESSION_EXPIRED_MESSAGE,
  "session expired": SESSION_EXPIRED_MESSAGE,
  "session revoked": SESSION_EXPIRED_MESSAGE,
  "could not validate credentials": SESSION_EXPIRED_MESSAGE,
  forbidden: NO_PERMISSION_MESSAGE,
  "insufficient permissions": NO_PERMISSION_MESSAGE,
  "not enough permissions": NO_PERMISSION_MESSAGE,
  "not found": NOT_FOUND_MESSAGE,
  "the requested resource was not found": NOT_FOUND_MESSAGE,
  "method not allowed": GENERIC_MESSAGE,
  "bad request": INVALID_INPUT_MESSAGE,
  "validation failed": INVALID_INPUT_MESSAGE,
  "unprocessable entity": INVALID_INPUT_MESSAGE,
  "unprocessable content": INVALID_INPUT_MESSAGE,
  "payload too large": FILE_TOO_LARGE_MESSAGE,
  "request entity too large": FILE_TOO_LARGE_MESSAGE,
  "content too large": FILE_TOO_LARGE_MESSAGE,
  "too many requests": TOO_MANY_MESSAGE,
  "rate limit exceeded": TOO_MANY_MESSAGE,
  "an internal error occurred": SERVER_MESSAGE,
  "internal server error": SERVER_MESSAGE,
  "request was not successful.": GENERIC_MESSAGE,
  "received an invalid response from the server.": SERVER_MESSAGE,
};

/** Codes whose meaning is fixed, whatever message accompanies them. */
const CODE_MESSAGES: Record<string, string> = {
  SESSION_INVALID: SESSION_EXPIRED_MESSAGE,
  SESSION_EXPIRED: SESSION_EXPIRED_MESSAGE,
  INTERNAL_ERROR: SERVER_MESSAGE,
  METHOD_NOT_ALLOWED: GENERIC_MESSAGE,
};

/** Status-only fallbacks for bodies with no usable message (proxy HTML pages). */
function messageForStatus(status: number): string | undefined {
  if (status === 401) return SIGN_IN_MESSAGE;
  if (status === 403) return NO_PERMISSION_MESSAGE;
  if (status === 404) return NOT_FOUND_MESSAGE;
  if (status === 413) return FILE_TOO_LARGE_MESSAGE;
  if (status === 422 || status === 400) return INVALID_INPUT_MESSAGE;
  if (status === 429) return TOO_MANY_MESSAGE;
  if (status >= 500) return SERVER_MESSAGE;
  return undefined;
}

/**
 * Human-readable message for toasts and inline errors. Customer-facing
 * backend messages pass through; framework wording ("Not authenticated",
 * "Validation failed", raw status text) is replaced with plain language.
 */
export function toUserMessage(e: unknown, fallback = GENERIC_MESSAGE): string {
  if (isApiError(e)) {
    if (e.kind === "network") return "Can't reach the server. Check your connection and try again.";
    if (e.kind === "timeout") return "The request took too long. Please try again.";
    if (e.code && CODE_MESSAGES[e.code]) return CODE_MESSAGES[e.code];
    // 5xx bodies are never customer copy, and nginx serves its own pages.
    if (e.status !== undefined && e.status >= 500) return SERVER_MESSAGE;
    const message = e.message.trim();
    const technical = TECHNICAL_MESSAGES[message.toLowerCase()];
    if (technical) return technical;
    // The client's own last-resort wording when the body had no message.
    const statusOnly = /^Request failed \(\d+\)$/.test(message);
    if (message && !statusOnly) return message;
    const byStatus = e.status !== undefined ? messageForStatus(e.status) : undefined;
    if (byStatus) return byStatus;
    if (e.code) {
      const words = e.code.replace(/_/g, " ").toLowerCase();
      return words.charAt(0).toUpperCase() + words.slice(1);
    }
    return fallback;
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}
