import { describe, expect, it } from "vitest";
import { buildCsp, cspHeader, cspMode, generateNonce } from "./csp";

describe("generateNonce", () => {
  it("returns a base64 nonce that differs per call", () => {
    const a = generateNonce();
    const b = generateNonce();
    expect(a).toMatch(/^[A-Za-z0-9+/]{22}==$/);
    expect(a).not.toBe(b);
  });
});

describe("buildCsp", () => {
  const policy = buildCsp("TESTNONCE==");
  const scriptSrc = policy.split("; ").find((d) => d.startsWith("script-src")) ?? "";

  it("puts the nonce in script-src", () => {
    expect(scriptSrc).toContain("'nonce-TESTNONCE=='");
  });

  it("does not allow inline or eval scripts", () => {
    expect(scriptSrc).not.toContain("'unsafe-inline'");
    expect(scriptSrc).not.toContain("'unsafe-eval'");
  });

  it("keeps the third-party script hosts the storefront needs", () => {
    expect(scriptSrc).toContain("https://checkout.razorpay.com");
    expect(scriptSrc).toContain("https://static.cloudflareinsights.com");
  });

  it("locks down plugins, base URI and framing", () => {
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("base-uri 'self'");
    expect(policy).toContain("frame-ancestors 'self'");
  });
});

describe("cspMode / cspHeader", () => {
  it("defaults to report-only", () => {
    expect(cspMode({})).toBe("report-only");
    expect(cspMode({ CSP_MODE: "bogus" })).toBe("report-only");
    expect(cspHeader("n", {})?.name).toBe("Content-Security-Policy-Report-Only");
  });

  it("enforces only when asked", () => {
    expect(cspMode({ CSP_MODE: " Enforce " })).toBe("enforce");
    expect(cspHeader("n", { CSP_MODE: "enforce" })?.name).toBe("Content-Security-Policy");
  });

  it("can be switched off", () => {
    expect(cspHeader("n", { CSP_MODE: "off" })).toBeNull();
  });

  it("appends report-uri when configured", () => {
    const h = cspHeader("n", { CSP_REPORT_URI: "https://errors.example/api/1/security/?k=x" });
    expect(h?.value).toMatch(/; report-uri https:\/\/errors\.example\/api\/1\/security\/\?k=x$/);
    expect(cspHeader("n", {})?.value).not.toContain("report-uri");
  });
});
