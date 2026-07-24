import { useState, useMemo, useEffect } from "react";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { SlidersHorizontal, X } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { ProductGrid } from "@/components/site/ProductGrid";
import { FilterPanel, type FilterValues } from "@/components/site/FilterPanel";
import { EmptyState } from "@/components/site/EmptyState";
import { ProductGridSkeleton } from "@/components/loading/ProductGridSkeleton";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toCollection, toProduct } from "@/lib/api/mappers";
import { hydrateInventoryFromListItems } from "@/hooks/inventory/hydrateInventory";
import type { CollectionDto } from "@/types/public";
import type { ProductListResponse } from "@/types/admin";

export const Route = createFileRoute("/collections/$slug")({
  loader: async ({ params }) => {
    const dto = await api.get<CollectionDto>(`/collections/${params.slug}`).catch((e: unknown) => {
      if ((e as { status?: number }).status === 404) throw notFound();
      throw e;
    });
    return { collection: toCollection(dto) };
  },
  head: ({ loaderData }) => ({
    meta: [
      { title: `${loaderData?.collection.name ?? "Collection"} · Hadha` },
      { name: "description", content: loaderData?.collection.description ?? "" },
    ],
  }),
  notFoundComponent: () => (
    <SiteLayout>
      <div className="px-8 py-20 text-center">
        <h1 className="font-display text-3xl mb-3">Collection not found</h1>
        <Link to="/collections" className="underline">
          Back to all collections
        </Link>
      </div>
    </SiteLayout>
  ),
  errorComponent: ({ reset }) => (
    <SiteLayout>
      <div className="px-8 py-20 text-center">
        <h1 className="font-display text-2xl mb-3">Something went wrong</h1>
        <button className="underline" onClick={() => reset()}>
          Try again
        </button>
      </div>
    </SiteLayout>
  ),
  component: CollectionPage,
});

function CollectionPage() {
  const { collection } = Route.useLoaderData();
  const [filters, setFilters] = useState<FilterValues>({});
  const [sort, setSort] = useState<"featured" | "price-asc" | "price-desc" | "newest">("newest");
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

  const apiParams = useMemo(
    () => ({
      collection_slug: collection.slug,
      page_size: 24,
      is_featured: sort === "featured" ? true : undefined,
      is_new_arrival: filters.isNew || undefined,
      is_best_seller: filters.isBestseller || undefined,
      max_price: filters.maxPrice || undefined,
      gender: filters.gender && filters.gender !== "all" ? filters.gender : undefined,
      sort_by:
        sort === "price-asc" || sort === "price-desc"
          ? ("base_price" as const)
          : ("created_at" as const),
      sort_dir: sort === "price-asc" ? ("asc" as const) : ("desc" as const),
    }),
    [collection.slug, filters, sort],
  );

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.products.list(apiParams),
    queryFn: () => api.get<ProductListResponse>("/products", { params: apiParams }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    if (data?.items?.length) hydrateInventoryFromListItems(data.items);
  }, [data]);

  const products = useMemo(() => (data?.items ?? []).map(toProduct), [data]);
  const total = data?.total ?? 0;

  const activeChips = useMemo(() => {
    const chips: { key: keyof FilterValues; label: string }[] = [];
    if (filters.gender && filters.gender !== "all")
      chips.push({ key: "gender", label: filters.gender });
    if (filters.inStock) chips.push({ key: "inStock", label: "In stock" });
    if (filters.isNew) chips.push({ key: "isNew", label: "New" });
    if (filters.isBestseller) chips.push({ key: "isBestseller", label: "Best seller" });
    if (filters.maxPrice)
      chips.push({ key: "maxPrice", label: `≤ Rs. ${filters.maxPrice.toLocaleString("en-IN")}` });
    return chips;
  }, [filters]);

  return (
    <SiteLayout>
      {/* Banner */}
      <div className="relative h-[260px] md:h-[340px] bg-secondary overflow-hidden">
        <img
          src={collection.image}
          alt={collection.name}
          fetchPriority="high"
          decoding="async"
          className="absolute inset-0 w-full h-full object-cover opacity-60"
        />
        <div className="absolute inset-0 bg-foreground/30" />
        <div className="relative h-full flex flex-col items-center justify-center text-center px-6 text-background">
          <p className="text-[11px] tracking-[0.3em] uppercase mb-2">Collection</p>
          <h1 className="font-display text-4xl md:text-6xl">{collection.name}</h1>
          {collection.description && (
            <p className="text-sm mt-3 max-w-xl opacity-90">{collection.description}</p>
          )}
        </div>
      </div>

      <div className="px-4 md:px-8 py-6">
        <Breadcrumbs
          items={[
            { label: "Home", to: "/" },
            { label: "Collections", to: "/collections" },
            { label: collection.name },
          ]}
        />
      </div>

      <div className="px-4 md:px-8 pb-16 grid lg:grid-cols-[240px_1fr] gap-10">
        {/* Desktop filter sidebar */}
        <aside className="hidden lg:block">
          <FilterPanel value={filters} onChange={setFilters} hideCollection />
        </aside>

        <div>
          <div className="flex items-center justify-between border-y border-border py-3 mb-6">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setMobileFilterOpen(true)}
                className="lg:hidden flex items-center gap-2 text-xs uppercase tracking-[0.18em]"
              >
                <SlidersHorizontal className="size-4" /> Filter
              </button>
              <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                {data ? `${total} ${total === 1 ? "piece" : "pieces"}` : null}
              </span>
            </div>
            <label className="flex items-center gap-2 text-xs uppercase tracking-[0.18em]">
              Sort
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as typeof sort)}
                className="bg-transparent border border-border px-2 py-1.5 text-xs"
              >
                <option value="featured">Featured</option>
                <option value="newest">Newest</option>
                <option value="price-asc">Price · Low to High</option>
                <option value="price-desc">Price · High to Low</option>
              </select>
            </label>
          </div>

          {activeChips.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-6">
              {activeChips.map((c) => (
                <button
                  key={c.key}
                  onClick={() =>
                    setFilters({ ...filters, [c.key]: c.key === "gender" ? "all" : undefined })
                  }
                  className="inline-flex items-center gap-2 border border-border bg-card px-3 py-1.5 text-xs uppercase tracking-[0.16em] hover:bg-secondary"
                >
                  {c.label} <X className="size-3" />
                </button>
              ))}
              <button
                onClick={() => setFilters({})}
                className="text-xs uppercase tracking-[0.16em] underline underline-offset-4 text-muted-foreground"
              >
                Clear
              </button>
            </div>
          )}

          {isLoading ? (
            <ProductGridSkeleton count={12} />
          ) : products.length === 0 && data ? (
            <EmptyState
              title="No pieces match these filters"
              description="Try widening your selection or clearing filters."
            />
          ) : (
            <ProductGrid products={products} />
          )}
        </div>
      </div>

      {/* Mobile filter drawer */}
      {mobileFilterOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-foreground/40"
            onClick={() => setMobileFilterOpen(false)}
          />
          <aside className="absolute left-0 top-0 h-full w-[88%] max-w-sm bg-background p-6 overflow-y-auto animate-slide-in-right">
            <div className="flex justify-between items-center mb-6">
              <h2 className="font-display text-xl">Filters</h2>
              <button onClick={() => setMobileFilterOpen(false)}>
                <X className="size-5" />
              </button>
            </div>
            <FilterPanel value={filters} onChange={setFilters} hideCollection />
            <button
              onClick={() => setMobileFilterOpen(false)}
              className="mt-8 w-full bg-primary text-primary-foreground py-3 text-xs uppercase tracking-[0.22em]"
            >
              Apply
            </button>
          </aside>
        </div>
      )}
    </SiteLayout>
  );
}
