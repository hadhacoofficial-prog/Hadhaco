import { describe, expect, it } from "vitest";

import { formatReturnPolicy } from "./format";

describe("formatReturnPolicy", () => {
  it("says no return, no refund for non-returnable products", () => {
    expect(formatReturnPolicy(false, undefined)).toBe("No return, no refund");
    expect(formatReturnPolicy(false, 7)).toBe("No return, no refund");
  });

  it("shows the window for returnable products", () => {
    expect(formatReturnPolicy(true, 10)).toBe("10-day returns");
  });

  it("does not invent a window when none is set", () => {
    expect(formatReturnPolicy(true, undefined)).toBe("Returns accepted");
  });

  it("falls back when the policy is unknown", () => {
    expect(formatReturnPolicy(undefined, undefined)).toBe("Returns vary by product");
  });

  it("uses custom wording and fills in the window", () => {
    expect(formatReturnPolicy(true, 10, "Easy {days}-day returns")).toBe("Easy 10-day returns");
    expect(formatReturnPolicy(false, undefined, "Final sale")).toBe("Final sale");
  });

  it("ignores blank custom wording and tidies a missing window", () => {
    expect(formatReturnPolicy(true, 10, "   ")).toBe("10-day returns");
    expect(formatReturnPolicy(true, undefined, "Returns within {days} days")).toBe(
      "Returns within days",
    );
  });
});
