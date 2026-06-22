import { useRecentSearches } from "./search";

beforeEach(() => {
  localStorage.clear();
  useRecentSearches.setState({ recent: [] });
});

describe("useRecentSearches.push", () => {
  it("adds a query to the front of the list", () => {
    useRecentSearches.getState().push("silver rings");
    expect(useRecentSearches.getState().recent[0]).toBe("silver rings");
  });

  it("trims whitespace from queries", () => {
    useRecentSearches.getState().push("  anklets  ");
    expect(useRecentSearches.getState().recent[0]).toBe("anklets");
  });

  it("ignores empty or whitespace-only strings", () => {
    useRecentSearches.getState().push("");
    useRecentSearches.getState().push("   ");
    expect(useRecentSearches.getState().recent).toHaveLength(0);
  });

  it("moves a duplicate query to the front instead of adding it again", () => {
    useRecentSearches.getState().push("earrings");
    useRecentSearches.getState().push("rings");
    useRecentSearches.getState().push("earrings"); // duplicate
    const recent = useRecentSearches.getState().recent;
    expect(recent[0]).toBe("earrings");
    expect(recent.filter((q) => q === "earrings")).toHaveLength(1);
  });

  it("keeps the most recent query at index 0", () => {
    useRecentSearches.getState().push("a");
    useRecentSearches.getState().push("b");
    useRecentSearches.getState().push("c");
    expect(useRecentSearches.getState().recent[0]).toBe("c");
  });

  it("caps the list at 6 entries", () => {
    ["a", "b", "c", "d", "e", "f", "g"].forEach((q) => useRecentSearches.getState().push(q));
    expect(useRecentSearches.getState().recent).toHaveLength(6);
  });

  it("drops the oldest entry when the cap is exceeded", () => {
    ["a", "b", "c", "d", "e", "f", "g"].forEach((q) => useRecentSearches.getState().push(q));
    // "a" was pushed first and should have been dropped
    expect(useRecentSearches.getState().recent).not.toContain("a");
  });
});

describe("useRecentSearches.clear", () => {
  it("removes all recent searches", () => {
    useRecentSearches.getState().push("rings");
    useRecentSearches.getState().push("bangles");
    useRecentSearches.getState().clear();
    expect(useRecentSearches.getState().recent).toHaveLength(0);
  });
});
