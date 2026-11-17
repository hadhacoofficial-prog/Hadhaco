import { ApiError, isApiError, toUserMessage } from "./errors";

// â”€â”€ Constructor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe("ApiError â€” constructor", () => {
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

// â”€â”€ isUnauthorized â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€ isForbidden â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe("ApiError.isForbidden", () => {
  it("returns true for status 403", () => {
    expect(new ApiError("", { kind: "http", status: 403 }).isForbidden).toBe(true);
  });

  it("returns false for status 401", () => {
    expect(new ApiError("", { kind: "http", status: 401 }).isForbidden).toBe(false);
  });
});

// â”€â”€ isValidation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€ isRetryable â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€ isApiError â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€ toUserMessage â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    expect(toUserMessage(e)).toBe("Insufficient stock");
  });

  it.each([
    ["Not authenticated", 401, "Please sign in to continue."],
    ["Session expired", 401, "Your session has expired. Please sign in again."],
    ["Insufficient permissions", 403, "You don't have permission to do that."],
    ["The requested resource was not found", 404, /couldn't find/],
    ["Validation failed", 422, /missing or invalid/],
    ["Too Many Requests", 429, /Too many attempts/],
    ["Payload Too Large", 413, /file is too large/],
  ])("replaces technical wording %j (%i)", (message, status, expected) => {
    const e = new ApiError(message, { kind: "http", status });
    expect(toUserMessage(e)).toMatch(expected);
  });

  it("never shows server-error bodies", () => {
    const e = new ApiError("An internal error occurred", {
      kind: "http",
      status: 500,
      code: "INTERNAL_ERROR",
    });
    expect(toUserMessage(e)).toBe("Something went wrong on our side. Please try again in a moment.");
    expect(toUserMessage(new ApiError("Bad Gateway", { kind: "http", status: 502 }))).toMatch(
      /on our side/,
    );
  });

  it("maps session codes whatever the message says", () => {
    const e = new ApiError("Not authenticated", {
      kind: "http",
      status: 401,
      code: "SESSION_INVALID",
    });
    expect(toUserMessage(e)).toBe("Your session has expired. Please sign in again.");
  });

  it("falls back to the status when only the client's status wording is left", () => {
    const e = new ApiError("Request failed (413)", { kind: "http", status: 413 });
    expect(toUserMessage(e)).toMatch(/file is too large/);
  });

  it("keeps customer-facing backend messages", () => {
    const blocked = new ApiError("You can post up to 5 reviews per hour.", {
      kind: "http",
      status: 429,
    });
    expect(toUserMessage(blocked)).toBe("You can post up to 5 reviews per hour.");
    const notYours = new ApiError("Review not found", { kind: "http", status: 404 });
    expect(toUserMessage(notYours)).toBe("Review not found");
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
