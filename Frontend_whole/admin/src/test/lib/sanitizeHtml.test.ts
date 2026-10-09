import { describe, expect, it } from "vitest";
import { sanitizeHtml } from "@/lib/sanitizeHtml";

describe("sanitizeHtml", () => {
  it("strips script tags and event handlers", () => {
    const out = sanitizeHtml(
      '<p onclick="x()">Hi</p><img src=x onerror="alert(1)"><script>alert(1)</script>',
    );
    expect(out).not.toMatch(/script/i);
    expect(out).not.toMatch(/onerror/i);
    expect(out).not.toMatch(/onclick/i);
    expect(out).toContain("Hi");
  });

  it("removes javascript: URLs and iframes", () => {
    const out = sanitizeHtml(
      '<a href="javascript:alert(1)">x</a><iframe src="https://evil"></iframe>',
    );
    expect(out).not.toMatch(/javascript:/i);
    expect(out).not.toMatch(/iframe/i);
  });

  it("keeps ordinary email formatting", () => {
    const out = sanitizeHtml(
      '<h1>Order</h1><p><strong>#1</strong> <a href="https://hadha.co">view</a></p>',
    );
    expect(out).toContain("<h1>Order</h1>");
    expect(out).toContain('href="https://hadha.co"');
  });
});
