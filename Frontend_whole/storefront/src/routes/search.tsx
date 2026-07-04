import { useState, useEffect, useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { z } from "zod";
import { Search as SearchIcon, X } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { ProductGrid } from "@/components/site/ProductGrid";
import { EmptyState } from "@/components/site/EmptyState";
import { ProductGridSkeleton } from "@/components/loading/ProductGridSkeleton";
import { useRecentSearches } from "@/stores/search";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProduct } from "@/lib/api/mappers";
import type { ProductListResponse } from "@/types/admin";

const searchSchema = z.object({
  q: z.string().optional(),
  cat: z.string().optional(),
  gender: z.enum(["men", "women", "kids", "unisex", "all"]).optional(),
  filter: z.enum(["new", "bestseller", "deals"]).optional(),
});

type SearchSearch = z.infer<typeof searchSchema>;

/** Shared between the loader and the component so both hit the identical query key. */
function buildSearchApiParams({ q, cat, gender, filter }: SearchSearch) {
  return {
    search: q || undefined,
    collection_slug: cat || undefined,
    gender: gender && gender !== "all" ? gender : undefined,
    is_new_arrival: filter === "new" ? true : undefined,
    is_best_seller: filter === "bestseller" ? true : undefined,
    page_size: 24,
  };
}

export const Route = createFileRoute("/search")({
  validateSearch: searchSchema,
  loaderDeps: ({ search }) => search,
  // See products.index.tsx for why this is pre-populated in the loader: it
  // keeps the router's "pending" state in sync with real data-readiness so
  // the previous search/filter results never flash back in after the
  // loading indicator disappears.
  loader: async ({ context: { queryClient }, deps }) => {
    if (!(deps.q || deps.cat || deps.gender || deps.filter)) return;
    const apiParams = buildSearchApiParams(deps);
    await queryClient.ensureQueryData({
      queryKey: queryKeys.products.list(apiParams),
      queryFn: () => api.get<ProductListResponse>("/products", { params: apiParams }),
      staleTime: 30_000,
    });
  },
  head: () => ({ meta: [{ title: "Search · Hadha" }] }),
  component: SearchPage,
});

const TRENDING = ["Bugadi", "Chains", "Anklets", "Nakshi Mala", "Bangles", "Black Bead"];

function SearchPage() {
  const search = Route.useSearch();
  const { q, cat, gender, filter } = search;
  const [input, setInput] = useState(q ?? "");
  const navigate = Route.useNavigate();
  const { recent, push, clear } = useRecentSearches();

  useEffect(() => {
    if (q) push(q);
  }, [q, push]);

  const apiParams = useMemo(() => buildSearchApiParams(search), [search]);

  const hasFilters = !!(q || cat || gender || filter);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.products.list(apiParams),
    queryFn: () => api.get<ProductListResponse>("/products", { params: apiParams }),
    enabled: hasFilters,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const results = useMemo(() => (data?.items ?? []).map(toProduct), [data]);
  const total = data?.total ?? 0;

  const headline =
    filter === "new"
      ? "New Arrivals"
      : filter === "deals"
        ? "Deals of the Day"
        : filter === "bestseller"
          ? "Bestsellers"
          : cat
            ? `Shop ${cat.replace(/-/g, " ")}`
            : gender
              ? `Shop ${gender}`
              : q
                ? `Results for "${q}"`
                : "Search";

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate({ search: { q: input.trim() || undefined } });
  };

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-12 max-w-5xl mx-auto">
        <h1 className="font-display text-4xl md:text-5xl text-center mb-8 capitalize">
          {headline}
        </h1>
        <form
          onSubmit={onSubmit}
          className="flex items-center gap-3 border-b border-foreground pb-3"
        >
          <SearchIcon className="size-5" />
          <input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="What are you looking for?"
            className="flex-1 bg-transparent outline-none text-lg tracking-wide placeholder:text-muted-foreground"
          />
          {input && (
            <button type="button" onClick={() => setInput("")}>
              <X className="size-4" />
            </button>
          )}
        </form>

        {!hasFilters && (
          <div className="mt-10 space-y-8">
            <section>
              <h2 className="text-xs uppercase tracking-[0.22em] text-muted-foreground mb-3">
                Trending
              </h2>
              <div className="flex flex-wrap gap-2">
                {TRENDING.map((t) => (
                  <Link
                    key={t}
                    to="/search"
                    search={{ q: t }}
                    className="border border-border px-4 py-2 text-sm hover:bg-secondary"
                  >
                    {t}
                  </Link>
                ))}
              </div>
            </section>
            {recent.length > 0 && (
              <section>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
                    Recent searches
                  </h2>
                  <button onClick={clear} className="text-xs underline text-muted-foreground">
                    Clear
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {recent.map((t) => (
                    <Link
                      key={t}
                      to="/search"
                      search={{ q: t }}
                      className="border border-border px-4 py-2 text-sm hover:bg-secondary"
                    >
                      {t}
                    </Link>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        {hasFilters && (
          <div className="mt-10">
            {isLoading ? (
              <ProductGridSkeleton count={12} />
            ) : (
              <>
                <p className="text-sm text-muted-foreground mb-6">
                  {total} result{total === 1 ? "" : "s"}
                </p>
                {results.length === 0 ? (
                  <EmptyState
                    icon={<SearchIcon className="size-5" />}
                    title="No matches"
                    description="We couldn't find anything matching these filters. Try something else."
                  />
                ) : (
                  <ProductGrid products={results} />
                )}
              </>
            )}
          </div>
        )}
      </div>
    </SiteLayout>
  );
}
