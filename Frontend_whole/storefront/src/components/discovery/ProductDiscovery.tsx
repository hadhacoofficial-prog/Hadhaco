import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Loader2, PackageSearch, SlidersHorizontal } from "lucide-react";

import { ProductGrid } from "@/components/site/ProductGrid";
import { PaginationBar } from "@/components/site/PaginationBar";
import { EmptyState } from "@/components/site/EmptyState";
import { ProductGridSkeleton } from "@/components/loading/ProductGridSkeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ActiveFilterChips, type FilterChip } from "@hadha/shared-ui/data/ActiveFilterChips";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProduct } from "@/lib/api/mappers";
import { productListQuery } from "@/lib/discoveryQueries";
import { cn } from "@/lib/utils";
import { hydrateInventoryFromListItems } from "@/hooks/inventory/hydrateInventory";
import {
  GENDER_LABELS,
  SORT_LABELS,
  activeFilterCount,
  availableSorts,
  clearedFilters,
  formatRupees,
  joinCsv,
  splitCsv,
  titleCase,
  toFilterApiParams,
  toListApiParams,
  type DiscoveryScope,
  type DiscoveryState,
  type ProductFacets,
  type SortKey,
} from "@/lib/discovery";
import type { ProductListResponse } from "@/types/admin";
import { ProductFilterPanel } from "./ProductFilterPanel";

const FACETS_STALE = 60_000;

interface ProductDiscoveryProps {
  state: DiscoveryState;
  scope?: DiscoveryScope;
  /**
   * Called with the full next state; the page writes it to the URL.
   * `replace` is set for corrections (not user actions) so they don't add
   * a history entry.
   */
  onChange: (next: DiscoveryState, opts?: { replace?: boolean }) => void;
  /** Rendered above the toolbar on every breakpoint. */
  header?: ReactNode;
  /** Extra actions offered when no results match (e.g. "Browse all"). */
  emptyAction?: ReactNode;
  noun?: { one: string; many: string };
}

/**
 * The shared storefront discovery experience: result count, sort, filter
 * sidebar (desktop) / drawer (mobile), active-filter chips, grid, pagination,
 * loading and empty states. Pages own the URL; this component owns nothing
 * but transient UI state (drawer open), so back/forward/refresh always
 * reproduce the exact same view.
 */
export function ProductDiscovery({
  state,
  scope = {},
  onChange,
  header,
  emptyAction,
  noun = { one: "piece", many: "pieces" },
}: ProductDiscoveryProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);
  const filterButtonRef = useRef<HTMLButtonElement>(null);
  const sortId = useId();

  const listQuery = productListQuery(state, scope);
  const { data, isLoading, isFetching, isPlaceholderData, isError, refetch } = useQuery({
    ...listQuery,
    placeholderData: keepPreviousData,
  });

  // Facets don't depend on page or sort — paging / re-sorting never refetches them.
  const facetParams = useMemo(() => toFilterApiParams(state, scope), [state, scope]);
  const { data: facets } = useQuery({
    queryKey: queryKeys.products.facets(facetParams),
    queryFn: () => api.get<ProductFacets>("/products/facets", { params: facetParams }),
    staleTime: FACETS_STALE,
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    if (data?.items?.length) hydrateInventoryFromListItems(data.items);
  }, [data]);

  // A page past the end (stale bookmark, catalogue shrank) would otherwise
  // render the "no products match" empty state; snap to the last real page.
  useEffect(() => {
    if (isPlaceholderData || !data) return;
    const last = Math.max(1, data.total_pages);
    if (data.items.length === 0 && state.page > 1 && state.page !== last) {
      onChange({ ...state, page: last }, { replace: true });
    }
  }, [data, isPlaceholderData, state, onChange]);

  // The drawer is mobile/tablet only; if the viewport grows to the desktop
  // layout while it's open, close it so its overlay can't linger.
  useEffect(() => {
    if (!drawerOpen || typeof window === "undefined") return;
    const mq = window.matchMedia("(min-width: 1024px)");
    const close = () => mq.matches && setDrawerOpen(false);
    close();
    mq.addEventListener("change", close);
    return () => mq.removeEventListener("change", close);
  }, [drawerOpen]);

  const products = useMemo(() => (data?.items ?? []).map(toProduct), [data]);
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 0;
  const filterCount = activeFilterCount(state);

  /** Any filter / sort change resets to page 1 (pagination is per result set). */
  const patch = (p: Partial<DiscoveryState>) => onChange({ ...state, ...p, page: 1 });

  const onPageChange = (page: number) => {
    onChange({ ...state, page });
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const chips = useMemo(
    () => buildChips(state, facets, (p) => onChange({ ...state, ...p, page: 1 })),
    [state, facets, onChange],
  );
  const clearAll = () => onChange(clearedFilters(state));

  const sortOptions = availableSorts(state, facets);

  const panel = <ProductFilterPanel state={state} facets={facets} onChange={patch} />;

  return (
    <div ref={resultsRef} className="scroll-mt-28">
      {header}

      <div className="grid lg:grid-cols-[260px_1fr] gap-10">
        <aside className="hidden lg:block" aria-label="Product filters">
          <div className="sticky top-28 max-h-[calc(100vh-8rem)] overflow-y-auto pr-2">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xs uppercase tracking-[0.22em]">Filters</h2>
              {filterCount > 0 && (
                <button
                  type="button"
                  onClick={clearAll}
                  className="text-xs underline underline-offset-4 text-muted-foreground hover:text-foreground"
                >
                  Clear all
                </button>
              )}
            </div>
            {panel}
          </div>
        </aside>

        <div className="min-w-0">
          {/* Toolbar */}
          {/* On phones the count drops to its own line so Filter + Sort keep
              full-size touch targets and nothing truncates. */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-y border-border py-3 mb-4">
            <button
              ref={filterButtonRef}
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="lg:hidden inline-flex items-center gap-2 min-h-10 px-3 border border-border text-xs uppercase tracking-[0.18em]"
              aria-haspopup="dialog"
            >
              <SlidersHorizontal className="size-4" aria-hidden />
              Filter
              {filterCount > 0 && (
                <span className="ml-0.5 inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-foreground text-background text-[10px] tracking-normal">
                  {filterCount}
                  <span className="sr-only"> active</span>
                </span>
              )}
            </button>
            <div className="order-last basis-full sm:order-none sm:basis-auto flex items-center gap-2 min-w-0">
              <p
                className="text-xs uppercase tracking-[0.18em] text-muted-foreground"
                aria-live="polite"
              >
                {data ? `${total} ${total === 1 ? noun.one : noun.many}` : " "}
              </p>
              {isFetching && !isLoading && (
                <Loader2
                  className="size-3.5 animate-spin text-muted-foreground"
                  aria-label="Updating results"
                />
              )}
            </div>

            <div className="ml-auto flex items-center gap-2">
              <label
                htmlFor={sortId}
                className="text-xs uppercase tracking-[0.18em] hidden sm:inline"
              >
                Sort
              </label>
              <select
                id={sortId}
                value={state.sort}
                onChange={(e) => patch({ sort: e.target.value as Exclude<SortKey, "popular"> })}
                aria-label="Sort products"
                className="bg-background border border-border min-h-10 px-2 text-xs max-w-[11rem] sm:max-w-none"
              >
                {sortOptions.map((k) => (
                  <option key={k} value={k}>
                    {SORT_LABELS[k]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <ActiveFilterChips
            chips={chips}
            onClearAll={chips.length > 1 ? clearAll : undefined}
            variant="storefront"
            className="mb-6"
          />

          <div aria-busy={isFetching} className="min-h-[40vh]">
            {isLoading ? (
              <ProductGridSkeleton count={12} />
            ) : isError && !data ? (
              <EmptyState
                title="We couldn't load these pieces"
                description="Please check your connection and try again."
                action={
                  <button
                    type="button"
                    onClick={() => refetch()}
                    className="text-xs uppercase tracking-[0.18em] underline underline-offset-4"
                  >
                    Try again
                  </button>
                }
              />
            ) : products.length === 0 ? (
              <EmptyState
                icon={<PackageSearch className="size-6" />}
                title="No products found matching your filters"
                description={
                  filterCount > 0
                    ? "Try removing a filter or widening your price range."
                    : state.q
                      ? `Nothing matched "${state.q}". Try a different word or browse all pieces.`
                      : "Check back soon — new pieces arrive regularly."
                }
                action={
                  <div className="flex flex-wrap items-center justify-center gap-4">
                    {filterCount > 0 && (
                      <button
                        type="button"
                        onClick={clearAll}
                        className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
                      >
                        Clear filters
                      </button>
                    )}
                    {emptyAction}
                  </div>
                }
              />
            ) : (
              <div
                className={cn(
                  "transition-opacity duration-200",
                  isPlaceholderData && "opacity-50 pointer-events-none",
                )}
              >
                <ProductGrid products={products} />
                <PaginationBar
                  page={data?.page ?? state.page}
                  totalPages={totalPages}
                  onPageChange={onPageChange}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile / tablet filter drawer — Radix Dialog handles focus trap,
          Escape and returning focus to the Filter button. Results update live
          behind it; the footer shows the live count. */}
      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent
          side="right"
          className="w-[90%] max-w-sm p-0 flex flex-col gap-0 lg:hidden"
          // Opened from state (no SheetTrigger), so hand focus back explicitly.
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            filterButtonRef.current?.focus();
          }}
        >
          <SheetHeader className="px-6 pt-6 pb-3 border-b border-border text-left">
            <SheetTitle className="font-display text-xl font-normal">Filters</SheetTitle>
            <SheetDescription className="sr-only">
              Narrow the product list. Results update as you choose.
            </SheetDescription>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto px-6">{panel}</div>
          <div className="border-t border-border p-4 flex items-center gap-3">
            <button
              type="button"
              onClick={clearAll}
              disabled={filterCount === 0}
              className="min-h-11 px-4 text-xs uppercase tracking-[0.18em] underline underline-offset-4 disabled:opacity-40 disabled:no-underline"
            >
              Clear all
            </button>
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              className="flex-1 min-h-11 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em]"
            >
              {data ? `Show ${total} ${total === 1 ? "result" : "results"}` : "Show results"}
            </button>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function buildChips(
  state: DiscoveryState,
  facets: ProductFacets | undefined,
  apply: (p: Partial<DiscoveryState>) => void,
): FilterChip[] {
  const chips: FilterChip[] = [];
  const catName = (slug: string) =>
    facets?.categories.find((c) => c.slug === slug)?.name ?? titleCase(slug);

  const csvChips = (
    key: "category" | "gender" | "metal" | "purity",
    group: string,
    label: (v: string) => string,
  ) => {
    const values = splitCsv(state[key]);
    for (const v of values) {
      chips.push({
        key: `${key}:${v}`,
        label: `${group}: ${label(v)}`,
        onRemove: () => apply({ [key]: joinCsv(values.filter((x) => x !== v)) }),
      });
    }
  };
  csvChips("category", "Category", catName);
  csvChips("gender", "Gender", (v) => GENDER_LABELS[v] ?? titleCase(v));
  csvChips("metal", "Metal", (v) => v);
  csvChips("purity", "Purity", (v) => v);

  if (state.minPrice !== undefined || state.maxPrice !== undefined) {
    const label =
      state.minPrice !== undefined && state.maxPrice !== undefined
        ? `${formatRupees(state.minPrice)}–${formatRupees(state.maxPrice)}`
        : state.minPrice !== undefined
          ? `From ${formatRupees(state.minPrice)}`
          : `Up to ${formatRupees(state.maxPrice!)}`;
    chips.push({
      key: "price",
      label: `Price: ${label}`,
      onRemove: () => apply({ minPrice: undefined, maxPrice: undefined }),
    });
  }
  if (state.rating) {
    chips.push({
      key: "rating",
      label: `Rating: ${state.rating}★ & up`,
      onRemove: () => apply({ rating: undefined }),
    });
  }
  const flags: [keyof DiscoveryState, string][] = [
    ["inStock", "In stock"],
    ["onSale", "On sale"],
    ["new", "New arrivals"],
    ["bestseller", "Best sellers"],
    ["featured", "Featured"],
  ];
  for (const [key, label] of flags) {
    if (state[key]) {
      chips.push({ key, label, onRemove: () => apply({ [key]: undefined }) });
    }
  }
  return chips;
}
