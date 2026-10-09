import { describe, expect, it } from "vitest";

import {
  activeFilterCount,
  availableSorts,
  discoverySearchSchema,
  resolveDiscovery,
  toListApiParams,
  toUrlSearch,
  type ProductFacets,
} from "@/lib/discovery";
import { resolveDateRange } from "@hadha/shared-ui/data/DateRangeFilter";

const facets = (over: Partial<ProductFacets> = {}): ProductFacets => ({
  total: 10,
  categories: [],
  genders: [],
  metal_types: [],
  purities: [],
  price_min: 100,
  price_max: 900,
  ratings: [],
  in_stock: 10,
  on_sale: 0,
  new_arrival: 0,
  best_seller: 0,
  has_sales: false,
  ...over,
});

describe("discoverySearchSchema", () => {
  it("drops invalid values instead of throwing", () => {
    const parsed = discoverySearchSchema.parse({
      minPrice: "abc",
      rating: 9,
      sort: "bogus",
      page: 0,
      inStock: "yes",
    });
    expect(parsed).toEqual({});
  });

  it("accepts boolean flags in both JSON and string form", () => {
    expect(discoverySearchSchema.parse({ inStock: true, onSale: "true" })).toMatchObject({
      inStock: true,
      onSale: true,
    });
  });
});

describe("resolveDiscovery", () => {
  it("folds legacy params into the canonical state", () => {
    expect(resolveDiscovery({ deals: "true" }).featured).toBe(true);
    expect(resolveDiscovery({ filter: "new" }).new).toBe(true);
    expect(resolveDiscovery({ filter: "deals" }).onSale).toBe(true);
    expect(resolveDiscovery({ sort: "popular" }).sort).toBe("bestselling");
    expect(resolveDiscovery({ gender: "all" }).gender).toBeUndefined();
  });

  it("defaults to relevance only when there is a query", () => {
    expect(resolveDiscovery({ q: "chain" }).sort).toBe("relevance");
    expect(resolveDiscovery({}).sort).toBe("newest");
    expect(resolveDiscovery({ sort: "relevance" }).sort).toBe("newest");
  });

  it("normalises swapped price bounds", () => {
    const s = resolveDiscovery({ minPrice: 900, maxPrice: 100 });
    expect([s.minPrice, s.maxPrice]).toEqual([100, 900]);
  });
});

describe("toUrlSearch", () => {
  it("omits defaults and legacy keys so URLs stay canonical", () => {
    const state = resolveDiscovery({ deals: "true", sort: "newest", page: 1 });
    const url = toUrlSearch(state, "newest");
    expect(url.sort).toBeUndefined();
    expect(url.page).toBeUndefined();
    expect(url.deals).toBeUndefined();
    expect(url.featured).toBe(true);
  });

  it("round-trips through the schema", () => {
    const state = resolveDiscovery({
      category: "women-rings,women-chains",
      maxPrice: 2000,
      sort: "price_asc",
      page: 3,
    });
    const again = resolveDiscovery(discoverySearchSchema.parse(toUrlSearch(state, "newest")));
    expect(again).toEqual(state);
  });
});

describe("toListApiParams", () => {
  it("maps sort keys onto the backend allowlist", () => {
    const p = toListApiParams(resolveDiscovery({ sort: "price_desc", gender: "women,men" }));
    expect(p).toMatchObject({
      sort_by: "base_price",
      sort_dir: "desc",
      gender: "women,men",
      page: 1,
      page_size: 24,
    });
  });
});

describe("availableSorts", () => {
  it("only offers sorts the data can support", () => {
    const keys = availableSorts(resolveDiscovery({}), facets());
    expect(keys).not.toContain("bestselling");
    expect(keys).not.toContain("rating");
    expect(keys).not.toContain("discount");
    expect(keys).not.toContain("relevance");
  });

  it("adds data-backed sorts and keeps the applied one", () => {
    const keys = availableSorts(
      resolveDiscovery({ q: "ring", sort: "rating" }),
      facets({ has_sales: true, on_sale: 3 }),
    );
    expect(keys).toEqual(
      expect.arrayContaining(["relevance", "bestselling", "discount", "rating"]),
    );
  });
});

describe("activeFilterCount", () => {
  it("counts each multi-select value and ignores q/sort", () => {
    const s = resolveDiscovery({
      q: "x",
      sort: "price_asc",
      category: "a,b",
      inStock: true,
      minPrice: 10,
    });
    expect(activeFilterCount(s)).toBe(4);
  });
});

describe("resolveDateRange", () => {
  const now = new Date(2026, 9, 9, 15, 30); // 9 Oct 2026, local time

  it("uses an exclusive end at the start of the next day", () => {
    const r = resolveDateRange({ preset: "today" }, now);
    expect(new Date(r.date_from!).getTime()).toBe(new Date(2026, 9, 9).getTime());
    expect(new Date(r.date_to!).getTime()).toBe(new Date(2026, 9, 10).getTime());
  });

  it("covers the whole previous month", () => {
    const r = resolveDateRange({ preset: "lastMonth" }, now);
    expect(new Date(r.date_from!).getTime()).toBe(new Date(2026, 8, 1).getTime());
    expect(new Date(r.date_to!).getTime()).toBe(new Date(2026, 9, 1).getTime());
  });

  it("includes both ends of a custom range and fixes reversed input", () => {
    const r = resolveDateRange({ preset: "custom", from: "2026-10-05", to: "2026-10-01" }, now);
    expect(new Date(r.date_from!).getTime()).toBe(new Date(2026, 9, 1).getTime());
    expect(new Date(r.date_to!).getTime()).toBe(new Date(2026, 9, 6).getTime());
  });

  it("returns no bounds for 'any'", () => {
    expect(resolveDateRange({ preset: "any" }, now)).toEqual({
      date_from: undefined,
      date_to: undefined,
    });
  });
});
