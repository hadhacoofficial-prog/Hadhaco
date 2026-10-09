import { useCallback, useEffect, useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { z } from "zod";
import { Search as SearchIcon, X } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { ProductDiscovery } from "@/components/discovery/ProductDiscovery";
import { productListQuery } from "@/lib/discoveryQueries";
import { useRecentSearches } from "@/stores/search";
import {
  activeFilterCount,
  discoverySearchSchema,
  resolveDiscovery,
  toUrlSearch,
  type DiscoveryState,
} from "@/lib/discovery";

const searchSchema = discoverySearchSchema.extend({
  // Legacy / scope params still emitted by existing links.
  cat: z.string().max(200).optional().catch(undefined), // collection slug (search overlay)
  filter: z.enum(["new", "bestseller", "deals"]).optional().catch(undefined), // homepage rails
});

type SearchSearch = z.infer<typeof searchSchema>;

const DEFAULT_SORT = "newest" as const;

const isActive = (s: SearchSearch, state: DiscoveryState) =>
  !!(s.q || s.cat || activeFilterCount(state) > 0);

export const Route = createFileRoute("/search")({
  validateSearch: searchSchema,
  loaderDeps: ({ search }) => search,
  // See products.index.tsx for why this is pre-populated in the loader: it
  // keeps the router's "pending" state in sync with real data-readiness so
  // the previous search/filter results never flash back in after the
  // loading indicator disappears.
  loader: async ({ context: { queryClient }, deps }) => {
    const state = resolveDiscovery(deps, DEFAULT_SORT);
    if (!isActive(deps, state)) return;
    await queryClient.ensureQueryData(productListQuery(state, { collectionSlug: deps.cat }));
  },
  head: () => ({ meta: [{ title: "Search · Hadha" }] }),
  component: SearchPage,
});

const TRENDING = ["Bugadi", "Chains", "Anklets", "Nakshi Mala", "Bangles", "Black Bead"];

function SearchPage() {
  const search = Route.useSearch();
  const { q, cat } = search;
  const [input, setInput] = useState(q ?? "");
  const navigate = Route.useNavigate();
  const { recent, push, clear } = useRecentSearches();

  const state = useMemo(() => resolveDiscovery(search, DEFAULT_SORT), [search]);
  const scope = useMemo(() => ({ collectionSlug: cat }), [cat]);

  useEffect(() => {
    if (q) push(q);
  }, [q, push]);

  // Keep the box in sync with back/forward navigation.
  useEffect(() => {
    setInput(q ?? "");
  }, [q]);

  const active = isActive(search, state);

  const headline = state.new
    ? "New Arrivals"
    : state.onSale
      ? "Deals of the Day"
      : state.bestseller
        ? "Bestsellers"
        : cat
          ? `Shop ${cat.replace(/-/g, " ")}`
          : q
            ? `Results for "${q}"`
            : "Search";

  const onChange = useCallback(
    (next: DiscoveryState, opts?: { replace?: boolean }) => {
      navigate({
        search: { ...toUrlSearch(next, DEFAULT_SORT), cat } as SearchSearch,
        replace: opts?.replace,
      });
    },
    [navigate, cat],
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // A new query keeps the active filters but starts back at page 1 and
    // lets the sort fall back to Relevance.
    const nextQ = input.trim() || undefined;
    onChange({ ...state, q: nextQ, sort: nextQ ? "relevance" : DEFAULT_SORT, page: 1 });
  };

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-12 max-w-screen-2xl mx-auto">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-display text-4xl md:text-5xl text-center mb-8 capitalize">
            {headline}
          </h1>
          <form
            role="search"
            onSubmit={onSubmit}
            className="flex items-center gap-3 border-b border-foreground pb-3"
          >
            <SearchIcon className="size-5" aria-hidden />
            <label htmlFor="site-search" className="sr-only">
              Search products
            </label>
            <input
              id="site-search"
              type="search"
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="What are you looking for?"
              className="flex-1 bg-transparent outline-none text-lg tracking-wide placeholder:text-muted-foreground [&::-webkit-search-cancel-button]:hidden"
            />
            {input && (
              <button type="button" onClick={() => setInput("")} aria-label="Clear search text">
                <X className="size-4" />
              </button>
            )}
          </form>
        </div>

        {!active && (
          <div className="mt-10 space-y-8 max-w-3xl mx-auto">
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

        {active && (
          <div className="mt-10">
            <ProductDiscovery
              state={state}
              scope={scope}
              onChange={onChange}
              noun={{ one: "result", many: "results" }}
              emptyAction={
                <Link
                  to="/products"
                  className="text-xs uppercase tracking-[0.18em] underline underline-offset-4"
                >
                  Browse all pieces
                </Link>
              }
            />
          </div>
        )}
      </div>
    </SiteLayout>
  );
}
