import { describe, expect, it } from "vitest";
import { formatINR } from "@/lib/format";
import { gstBreakdown, parseTaxRate } from "@/lib/pricing";

describe("gstBreakdown", () => {
  it("extracts GST from an inclusive price instead of adding it", () => {
    expect(gstBreakdown(1520, 3)).toEqual({ gstIncluded: 44.27, priceBeforeGst: 1475.73 });
    expect(gstBreakdown(1260, 3)).toEqual({ gstIncluded: 36.7, priceBeforeGst: 1223.3 });
  });

  it("returns no GST for a 0% rate", () => {
    expect(gstBreakdown(1000, 0)).toEqual({ gstIncluded: 0, priceBeforeGst: 1000 });
  });
});

describe("parseTaxRate", () => {
  it("keeps an explicit 0 and parses numbers", () => {
    expect(parseTaxRate("0")).toBe(0);
    expect(parseTaxRate("5")).toBe(5);
  });

  it("falls back to 3 when blank or invalid", () => {
    expect(parseTaxRate("")).toBe(3);
    expect(parseTaxRate("abc")).toBe(3);
  });
});

describe("formatINR", () => {
  it("always shows exactly two decimals", () => {
    expect(formatINR(1520)).toBe("Rs. 1,520.00");
    expect(formatINR(1565.6)).toBe("Rs. 1,565.60");
    expect(formatINR(36.7)).toBe("Rs. 36.70");
    expect(formatINR(1223.3)).toBe("Rs. 1,223.30");
  });
});
