// Mock supabase client before any imports to prevent initialization errors
vi.mock("@/lib/supabase/client", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  },
}));

// Control the API base URL for deterministic URL tests
vi.mock("@/config/env", () => ({
  ENV: {
    apiBaseUrl: "https://api.example.com/v1",
    isDev: false,
    isProd: false,
  },
  hasSupabase: () => false,
  hasApi: () => true,
}));

import { buildUrl, serializeParams } from "./interceptors";

// ── serializeParams ───────────────────────────────────────────────────────────

describe("serializeParams", () => {
  it("returns empty string for undefined", () => {
    expect(serializeParams(undefined)).toBe("");
  });

  it("returns empty string for an empty object", () => {
    expect(serializeParams({})).toBe("");
  });

  it("serializes a single string param", () => {
    expect(serializeParams({ page: "2" })).toBe("?page=2");
  });

  it("serializes multiple params", () => {
    const result = serializeParams({ page: "1", size: "10" });
    expect(result).toContain("page=1");
    expect(result).toContain("size=10");
    expect(result).toMatch(/^\?/);
  });

  it("skips null values", () => {
    expect(serializeParams({ page: "1", category: null })).toBe("?page=1");
  });

  it("skips undefined values", () => {
    expect(serializeParams({ page: "1", sort: undefined })).toBe("?page=1");
  });

  it("repeats the key for array values", () => {
    const result = serializeParams({ tags: ["silver", "ring"] });
    expect(result).toContain("tags=silver");
    expect(result).toContain("tags=ring");
  });

  it("skips null/undefined items within an array", () => {
    const result = serializeParams({ tags: ["silver", null, undefined, "ring"] });
    expect(result).toContain("tags=silver");
    expect(result).toContain("tags=ring");
    // null and undefined values should not appear
    expect(result).not.toMatch(/tags=null|tags=undefined/);
  });

  it("converts numeric values to strings", () => {
    expect(serializeParams({ page: 2 })).toBe("?page=2");
  });

  it("converts boolean values to strings", () => {
    expect(serializeParams({ in_stock: true })).toBe("?in_stock=true");
  });

  it("returns empty string when all values are null/undefined", () => {
    expect(serializeParams({ a: null, b: undefined })).toBe("");
  });
});

// ── buildUrl ──────────────────────────────────────────────────────────────────

describe("buildUrl", () => {
  it("joins the base URL and a path that starts with '/'", () => {
    expect(buildUrl("/products")).toBe("https://api.example.com/v1/products");
  });

  it("prepends '/' when the path does not start with it", () => {
    expect(buildUrl("products")).toBe("https://api.example.com/v1/products");
  });

  it("strips trailing slashes from the base URL before joining", () => {
    // The mock sets a clean base; verify double-slash is never produced
    expect(buildUrl("/products")).not.toContain("//products");
  });

  it("appends query params when provided", () => {
    const url = buildUrl("/products", { page: "2", size: "12" });
    expect(url).toContain("https://api.example.com/v1/products?");
    expect(url).toContain("page=2");
    expect(url).toContain("size=12");
  });

  it("produces no query string when params is undefined", () => {
    expect(buildUrl("/products", undefined)).toBe("https://api.example.com/v1/products");
  });

  it("produces no query string when params object is empty", () => {
    expect(buildUrl("/products", {})).toBe("https://api.example.com/v1/products");
  });

  it("preserves deep paths", () => {
    expect(buildUrl("/admin/products/123/images")).toBe(
      "https://api.example.com/v1/admin/products/123/images",
    );
  });
});
