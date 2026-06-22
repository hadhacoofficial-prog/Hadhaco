import { cn } from "./utils";

describe("cn", () => {
  it("returns a single class unchanged", () => {
    expect(cn("foo")).toBe("foo");
  });

  it("joins multiple classes with spaces", () => {
    expect(cn("foo", "bar", "baz")).toBe("foo bar baz");
  });

  it("deduplicates conflicting Tailwind utilities — last wins", () => {
    expect(cn("p-4", "p-8")).toBe("p-8");
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });

  it("ignores undefined and null", () => {
    expect(cn("base", undefined, null, "end")).toBe("base end");
  });

  it("ignores false conditionals", () => {
    const show = false;
    expect(cn("base", show && "hidden", "visible")).toBe("base visible");
  });

  it("supports conditional object syntax", () => {
    expect(cn("base", { active: true, hidden: false })).toBe("base active");
  });

  it("returns empty string when all inputs are falsy", () => {
    expect(cn(undefined, false, null)).toBe("");
  });
});
