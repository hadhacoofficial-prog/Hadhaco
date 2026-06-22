import { formatINR } from "./format";

describe("formatINR", () => {
  it("formats zero", () => {
    expect(formatINR(0)).toBe("Rs. 0.00");
  });

  it("formats a sub-thousand value without comma", () => {
    expect(formatINR(999)).toBe("Rs. 999.00");
  });

  it("formats a four-digit value with comma", () => {
    expect(formatINR(1499)).toBe("Rs. 1,499.00");
  });

  it("formats a round thousand", () => {
    expect(formatINR(1000)).toBe("Rs. 1,000.00");
  });

  it("always prefixes with 'Rs. '", () => {
    expect(formatINR(50)).toMatch(/^Rs\. /);
  });

  it("always suffixes with '.00'", () => {
    expect(formatINR(50)).toMatch(/\.00$/);
  });
});
