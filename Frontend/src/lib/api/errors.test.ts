import { ApiError, isApiError, toUserMessage } from "./errors";

// ── Constructor ───────────────────────────────────────────────────────────────

describe("ApiError — constructor", () => {
  it("sets name to 'ApiError'", () => {
    const e = new ApiError("oops", { kind: "http", status: 404 });
    expect(e.name).toBe("ApiError");
  });

  it("stores the message", () => {
    const e = new ApiError("not found", { kind: "http", status: 404 });
    expect(e.message).toBe("not found");
  });

  it("is an instance of Error", () => {
    const e = new ApiError("err", { kind: "unknown" });
    expect(e).toBeInstanceOf(Error);
  });

  it("stores kind, status, code, details, and request", () => {
    const e = new ApiError("err", {
      kind: "business",
      status: 200,
      code: "INSUFFICIENT_STOCK",
      details: { sku: "SR-001" },
      request: { method: "POST", url: "/orders" },
    });
    expect(e.kind).toBe("business");
    expect(e.status).toBe(200);
    expect(e.code).toBe("INSUFFICIENT_STOCK");
    expect(e.details).toEqual({ sku: "SR-001" });
    expect(e.request).toEqual({ method: "POST", url: "/orders" });
  });

  it("attaches cause when provided", () => {
    const cause = new Error("root");
    const e = new ApiError("wrapped", { kind: "unknown", cause });
    expect(e.cause).toBe(cause);
  });

  it("does not set cause property when cause is not provided", () => {
    const e = new ApiError("no cause", { kind: "http", status: 500 });
    expect(e.cause).toBeUndefined();
  });
});

// ── isUnauthorized ────────────────────────────────────────────────────────────

describe("ApiError.isUnauthorized", () => {
  it("returns true for status 401", () => {
    expect(new ApiError("", { kind: "http", status: 401 }).isUnauthorized).toBe(true);
  });

  it("returns false for status 403", () => {
    expect(new ApiError("", { kind: "http", status: 403 }).isUnauthorized).toBe(false);
  });

  it("returns false when status is absent", () => {
    expect(new ApiError("", { kind: "network" }).isUnauthorized).toBe(false);
  });
});

// ── isForbidden ───────────────────────────────────────────────────────────────

describe("ApiError.isForbidden", () => {
  it("returns true for status 403", () => {
    expect(new ApiError("", { kind: "http", status: 403 }).isForbidden).toBe(true);
  });

  it("returns false for status 401", () => {
    expect(new ApiError("", { kind: "http", status: 401 }).isForbidden).toBe(false);
  });
});

// ── isValidation ──────────────────────────────────────────────────────────────

describe("ApiError.isValidation", () => {
  it("returns true for status 422", () => {
    expect(new ApiError("", { kind: "http", status: 422 }).isValidation).toBe(true);
  });

  it("returns true for VALIDATION_ERROR code regardless of status", () => {
    expect(new ApiError("", { kind: "business", code: "VALIDATION_ERROR" }).isValidation).toBe(
      true,
    );
  });

  it("returns false for status 400", () => {
    expect(new ApiError("", { kind: "http", status: 400 }).isValidation).toBe(false);
  });
});

// ── isRetryable ───────────────────────────────────────────────────────────────

describe("ApiError.isRetryable", () => {
  it("returns true for network kind", () => {
    expect(new ApiError("", { kind: "network" }).isRetryable).toBe(true);
  });

  it("returns true for timeout kind", () => {
    expect(new ApiError("", { kind: "timeout" }).isRetryable).toBe(true);
  });

  it("returns true for 500 (internal server error)", () => {
    expect(new ApiError("", { kind: "http", status: 500 }).isRetryable).toBe(true);
  });

  it("returns true for 503 (service unavailable)", () => {
    expect(new ApiError("", { kind: "http", status: 503 }).isRetryable).toBe(true);
  });

  it("returns true for 429 (rate limited)", () => {
    expect(new ApiError("", { kind: "http", status: 429 }).isRetryable).toBe(true);
  });

  it("returns true for 408 (request timeout)", () => {
    expect(new ApiError("", { kind: "http", status: 408 }).isRetryable).toBe(true);
  });

  it("returns false for 404 (not found)", () => {
    expect(new ApiError("", { kind: "http", status: 404 }).isRetryable).toBe(false);
  });

  it("returns false for 400 (bad request)", () => {
    expect(new ApiError("", { kind: "http", status: 400 }).isRetryable).toBe(false);
  });

  it("returns false for business kind", () => {
    expect(new ApiError("", { kind: "business" }).isRetryable).toBe(false);
  });

  it("returns false for parse kind", () => {
    expect(new ApiError("", { kind: "parse" }).isRetryable).toBe(false);
  });
});

// ── isApiError ────────────────────────────────────────────────────────────────

describe("isApiError", () => {
  it("returns true for an ApiError instance", () => {
    expect(isApiError(new ApiError("err", { kind: "unknown" }))).toBe(true);
  });

  it("returns false for a plain Error", () => {
    expect(isApiError(new Error("plain"))).toBe(false);
  });

  it("returns false for an object with an error-like shape", () => {
    expect(isApiError({ message: "fake", kind: "http" })).toBe(false);
  });

  it("returns false for null", () => {
    expect(isApiError(null)).toBe(false);
  });

  it("returns false for undefined", () => {
    expect(isApiError(undefined)).toBe(false);
  });

  it("returns false for a string", () => {
    expect(isApiError("error string")).toBe(false);
  });
});

// ── toUserMessage ─────────────────────────────────────────────────────────────

describe("toUserMessage", () => {
  it("returns a connection message for network errors", () => {
    const e = new ApiError("connect failed", { kind: "network" });
    expect(toUserMessage(e)).toMatch(/connection/i);
  });

  it("returns a timeout message for timeout errors", () => {
    const e = new ApiError("took too long", { kind: "timeout" });
    expect(toUserMessage(e)).toMatch(/long/i);
  });

  it("returns the ApiError message for http/business errors with a message", () => {
    const e = new ApiError("Product not found", { kind: "http", status: 404 });
    expect(toUserMessage(e)).toBe("Product not found");
  });

  it("humanizes the code when the message is empty", () => {
    const e = new ApiError("", { kind: "business", code: "INSUFFICIENT_STOCK" });
    expect(toUserMessage(e)).toBe("insufficient stock");
  });

  it("uses the message of a plain Error", () => {
    expect(toUserMessage(new Error("something bad"))).toBe("something bad");
  });

  it("uses the default fallback for non-Error values", () => {
    expect(toUserMessage(null)).toBe("Something went wrong. Please try again.");
    expect(toUserMessage(42)).toBe("Something went wrong. Please try again.");
  });

  it("uses a custom fallback string", () => {
    expect(toUserMessage(undefined, "Custom error")).toBe("Custom error");
  });
});
