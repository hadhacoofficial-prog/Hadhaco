/**
 * Product discovery — one URL contract for every storefront product listing
 * (/products, /search, /collections/$slug).
 *
 *   ?q=chain&category=women-rings,women-chains&gender=women&minPrice=500
 *    &maxPrice=2000&rating=4&inStock=true&onSale=true&new=true&sort=price_asc&page=2
 *
 * Every field is validated with `.catch(undefined)`, so a malformed or stale
 * bookmark degrades to "filter ignored" instead of an error page. Legacy
 * params from older links (`deals`, `filter`, `sort=popular`) are still
 * accepted and folded in by `resolveDiscovery`.
 */
import { z } from "zod";

// ─── Sorting ────────────────────────────────────────────────────────────────

export const SORT_KEYS = [
  "relevance",
  "featured",
  "newest",
  "bestselling",
  "rating",
  "price_asc",
  "price_desc",
  "discount",
  "name_asc",
  "name_desc",
  // Legacy alias of "bestselling" (old /products?sort=popular links).
  "popular",
] as const;
export type SortKey = (typeof SORT_KEYS)[number];

const SORT_API: Record<SortKey, { sort_by: string; sort_dir: "asc" | "desc" }> = {
  relevance: { sort_by: "relevance", sort_dir: "desc" },
  featured: { sort_by: "featured", sort_dir: "desc" },
  newest: { sort_by: "created_at", sort_dir: "desc" },
  bestselling: { sort_by: "sold_quantity", sort_dir: "desc" },
  popular: { sort_by: "sold_quantity", sort_dir: "desc" },
  rating: { sort_by: "average_rating", sort_dir: "desc" },
  price_asc: { sort_by: "base_price", sort_dir: "asc" },
  price_desc: { sort_by: "base_price", sort_dir: "desc" },
  discount: { sort_by: "discount", sort_dir: "desc" },
  name_asc: { sort_by: "name", sort_dir: "asc" },
  name_desc: { sort_by: "name", sort_dir: "desc" },
};

export const SORT_LABELS: Record<Exclude<SortKey, "popular">, string> = {
  relevance: "Relevance",
  featured: "Featured",
  newest: "Newest",
  bestselling: "Best selling",
  rating: "Top rated",
  price_asc: "Price: Low to High",
  price_desc: "Price: High to Low",
  discount: "Biggest discount",
  name_asc: "Name: A to Z",
  name_desc: "Name: Z to A",
};

// ─── URL schema ─────────────────────────────────────────────────────────────

const flag = z
  .preprocess((v) => (v === true || v === "true" ? true : undefined), z.literal(true).optional())
  .catch(undefined);
const csv = z.string().max(1000).optional().catch(undefined);
const money = z.coerce.number().min(0).max(10_000_000).optional().catch(undefined);

export const discoverySearchSchema = z.object({
  q: z.string().max(200).optional().catch(undefined),
  category: csv,
  gender: csv,
  metal: csv,
  purity: csv,
  minPrice: money,
  maxPrice: money,
  rating: z.coerce.number().int().min(1).max(4).optional().catch(undefined),
  inStock: flag,
  onSale: flag,
  new: flag,
  bestseller: flag,
  featured: flag,
  sort: z.enum(SORT_KEYS).optional().catch(undefined),
  page: z.coerce.number().int().min(1).optional().catch(undefined),
});
export type DiscoverySearch = z.infer<typeof discoverySearchSchema>;

/** Legacy params some existing links still emit. */
export interface LegacyDiscoveryParams {
  /** /products?deals="true" → featured products (header "Deals" link). */
  deals?: "true" | true;
  /** /search?filter=new|bestseller|deals (homepage rails). */
  filter?: "new" | "bestseller" | "deals";
  /** /search?cat=<collection-slug> (search overlay collection chips). */
  cat?: string;
}

/** Fixed context a page imposes (not user-removable filters). */
export interface DiscoveryScope {
  collectionSlug?: string;
}

/** Effective, normalised filter state after folding in legacy params. */
export type DiscoveryState = Omit<DiscoverySearch, "sort" | "page"> & {
  sort: Exclude<SortKey, "popular">;
  page: number;
};

export const splitCsv = (v?: string): string[] =>
  v
    ? Array.from(
        new Set(
          v
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        ),
      )
    : [];

export const joinCsv = (values: string[]): string | undefined =>
  values.length ? Array.from(new Set(values)).join(",") : undefined;

export function resolveDiscovery(
  search: DiscoverySearch & LegacyDiscoveryParams,
  defaultSort: Exclude<SortKey, "popular"> = "newest",
): DiscoveryState {
  const { deals, filter, cat: _cat, sort, page, ...rest } = search;
  void _cat;
  const state: DiscoveryState = {
    ...rest,
    sort: sort === "popular" ? "bestselling" : (sort ?? (rest.q ? "relevance" : defaultSort)),
    page: page ?? 1,
  };
  // Older gender links used "all" to mean "no gender filter".
  if (state.gender) state.gender = joinCsv(splitCsv(state.gender).filter((g) => g !== "all"));
  if (deals === "true" || deals === true) state.featured = true;
  if (filter === "new") state.new = true;
  if (filter === "bestseller") state.bestseller = true;
  if (filter === "deals") state.onSale = true;
  if (state.sort === "relevance" && !state.q) state.sort = defaultSort;
  if (
    state.minPrice !== undefined &&
    state.maxPrice !== undefined &&
    state.minPrice > state.maxPrice
  ) {
    [state.minPrice, state.maxPrice] = [state.maxPrice, state.minPrice];
  }
  return state;
}

/**
 * Canonical URL search for a state: drops defaults, legacy keys and empty
 * values so URLs stay short, stable and shareable.
 */
export function toUrlSearch(
  state: DiscoveryState,
  defaultSort: Exclude<SortKey, "popular">,
): DiscoverySearch & LegacyDiscoveryParams {
  const implicitSort = state.q ? "relevance" : defaultSort;
  return {
    q: state.q || undefined,
    category: state.category || undefined,
    gender: state.gender || undefined,
    metal: state.metal || undefined,
    purity: state.purity || undefined,
    minPrice: state.minPrice,
    maxPrice: state.maxPrice,
    rating: state.rating,
    inStock: state.inStock,
    onSale: state.onSale,
    new: state.new,
    bestseller: state.bestseller,
    featured: state.featured,
    sort: state.sort === implicitSort ? undefined : state.sort,
    page: state.page > 1 ? state.page : undefined,
    // Explicitly clear legacy keys — they've been folded into the state.
    deals: undefined,
    filter: undefined,
  };
}

// ─── API ────────────────────────────────────────────────────────────────────

export const PAGE_SIZE = 24;

/** Filter params shared by `/products` and `/products/facets`. */
export function toFilterApiParams(state: DiscoveryState, scope: DiscoveryScope = {}) {
  return {
    search: state.q || undefined,
    category_slug: state.category || undefined,
    collection_slug: scope.collectionSlug || undefined,
    gender: state.gender || undefined,
    metal_type: state.metal || undefined,
    purity: state.purity || undefined,
    min_price: state.minPrice,
    max_price: state.maxPrice,
    min_rating: state.rating,
    in_stock: state.inStock,
    on_sale: state.onSale,
    is_new_arrival: state.new,
    is_best_seller: state.bestseller,
    is_featured: state.featured,
  };
}

export function toListApiParams(state: DiscoveryState, scope: DiscoveryScope = {}) {
  return {
    ...toFilterApiParams(state, scope),
    ...SORT_API[state.sort],
    page: state.page,
    page_size: PAGE_SIZE,
  };
}

// ─── Facets ─────────────────────────────────────────────────────────────────

export interface ProductFacets {
  total: number;
  categories: {
    id: string;
    slug: string;
    name: string;
    parent_id: string | null;
    count: number;
  }[];
  genders: { value: string; count: number }[];
  metal_types: { value: string; count: number }[];
  purities: { value: string; count: number }[];
  price_min: number | null;
  price_max: number | null;
  ratings: { min_rating: number; count: number }[];
  in_stock: number;
  on_sale: number;
  new_arrival: number;
  best_seller: number;
  has_sales: boolean;
}

/** Sort options worth offering for this result set — no dead options. */
export function availableSorts(
  state: DiscoveryState,
  facets: ProductFacets | undefined,
): Exclude<SortKey, "popular">[] {
  const keys: Exclude<SortKey, "popular">[] = [];
  if (state.q) keys.push("relevance");
  keys.push("featured", "newest");
  if (facets?.has_sales) keys.push("bestselling");
  if (facets?.ratings.length) keys.push("rating");
  keys.push("price_asc", "price_desc");
  if (facets && facets.on_sale > 0) keys.push("discount");
  keys.push("name_asc", "name_desc");
  // Never hide the option that's currently applied (e.g. from a shared URL).
  if (!keys.includes(state.sort)) keys.push(state.sort);
  return keys;
}

export const GENDER_LABELS: Record<string, string> = {
  women: "Women",
  men: "Men",
  unisex: "Unisex",
  kids: "Kids",
};

export const titleCase = (s: string) =>
  s
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

export const formatRupees = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;

/** Number of user-removable filters currently applied (excludes q / sort). */
export function activeFilterCount(state: DiscoveryState): number {
  return (
    splitCsv(state.category).length +
    splitCsv(state.gender).length +
    splitCsv(state.metal).length +
    splitCsv(state.purity).length +
    (state.minPrice !== undefined || state.maxPrice !== undefined ? 1 : 0) +
    (state.rating ? 1 : 0) +
    [state.inStock, state.onSale, state.new, state.bestseller, state.featured].filter(Boolean)
      .length
  );
}

/** State with every user-removable filter cleared (keeps q and sort). */
export function clearedFilters(state: DiscoveryState): DiscoveryState {
  return { q: state.q, sort: state.sort, page: 1 };
}
