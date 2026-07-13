import { useEffect, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { Search as SearchIcon, X, TrendingUp, Clock } from "lucide-react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useUi } from "@/stores/ui";
import { useRecentSearches } from "@/stores/search";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProduct, toCollection } from "@/lib/api/mappers";
import { formatINR } from "@/lib/format";
import { useDebounce } from "@hadha/shared-ui/common/use-debounce";
import type { ProductListResponse } from "@/types/admin";
import type { CollectionDto } from "@/types/public";

const TRENDING = ["Bugadi", "Chains", "Anklets", "Nakshi Mala", "Bangles", "Black Bead"];

export function SearchOverlay() {
  const open = useUi((s) => s.searchOpen);
  const close = useUi((s) => s.closeSearch);
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const debouncedQ = useDebounce(q, 200);
  const { recent, push, clear } = useRecentSearches();

  // Reset when closing
  useEffect(() => {
    if (!open) {
      setQ("");
    }
  }, [open]);

  // Esc to close
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    document.documentElement.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.documentElement.style.overflow = "";
    };
  }, [open, close]);

  const searchTerm = debouncedQ.trim();

  const { data: searchData } = useQuery({
    queryKey: queryKeys.products.list({ search: searchTerm, page_size: 6 }),
    queryFn: () =>
      api.get<ProductListResponse>("/products", {
        params: { search: searchTerm, page_size: 6 },
      }),
    enabled: searchTerm.length >= 2,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const results = (searchData?.items ?? []).map(toProduct);

  const { data: collectionData } = useQuery({
    queryKey: queryKeys.collections.list,
    queryFn: () => api.get<CollectionDto[]>("/collections"),
    staleTime: 10 * 60_000,
  });
  const popular = (collectionData ?? []).slice(0, 6).map(toCollection);

  const goSearch = () => {
    const term = q.trim();
    if (!term) return;
    push(term);
    close();
    navigate({ to: "/search", search: { q: term } });
  };

  const onFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    goSearch();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] animate-fade-in" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-foreground/60 backdrop-blur-sm" onClick={close} />

      <div className="relative h-full md:h-auto md:max-h-[88vh] md:mt-16 md:max-w-5xl md:mx-auto bg-background md:shadow-[0_40px_100px_-40px_rgba(17,24,39,0.5)] overflow-y-auto animate-scale-in">
        {/* Input bar */}
        <form
          onSubmit={onFormSubmit}
          className="sticky top-0 z-10 bg-background border-b border-border px-5 md:px-8 py-5 flex items-center gap-4"
        >
          <SearchIcon className="size-5 text-muted-foreground" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search for bugadi, chains, anklets…"
            className="flex-1 bg-transparent outline-none text-base md:text-lg tracking-wide placeholder:text-muted-foreground"
          />
          {q && (
            <button
              type="button"
              onClick={() => setQ("")}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          )}
          <button
            type="button"
            onClick={close}
            aria-label="Close search"
            className="ml-2 text-[11px] tracking-[0.24em] uppercase text-muted-foreground hover:text-foreground border-l border-border pl-4"
          >
            Esc
          </button>
        </form>

        <div className="grid md:grid-cols-[1fr_1.4fr]">
          {/* Left: discovery */}
          <div className="border-b md:border-b-0 md:border-r border-border p-6 md:p-8 space-y-8">
            <section>
              <h3 className="text-[10px] tracking-[0.3em] uppercase text-muted-foreground mb-3 flex items-center gap-2">
                <TrendingUp className="size-3" />
                Trending
              </h3>
              <div className="flex flex-wrap gap-2">
                {TRENDING.map((t) => (
                  <button
                    key={t}
                    onClick={() => setQ(t)}
                    className="border border-border px-3 py-1.5 text-xs hover:bg-accent hover:border-primary hover:text-primary transition"
                  >
                    {t}
                  </button>
                ))}
              </div>
            </section>

            {recent.length > 0 && (
              <section>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-[10px] tracking-[0.3em] uppercase text-muted-foreground flex items-center gap-2">
                    <Clock className="size-3" />
                    Recent
                  </h3>
                  <button
                    onClick={clear}
                    className="text-[10px] underline text-muted-foreground hover:text-foreground"
                  >
                    Clear
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {recent.map((t) => (
                    <button
                      key={t}
                      onClick={() => setQ(t)}
                      className="border border-border px-3 py-1.5 text-xs hover:bg-accent hover:text-primary transition"
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </section>
            )}

            {popular.length > 0 && (
              <section>
                <h3 className="text-[10px] tracking-[0.3em] uppercase text-muted-foreground mb-3">
                  Popular categories
                </h3>
                <ul className="grid grid-cols-2 gap-2">
                  {popular.map((c) => (
                    <li key={c.id}>
                      <Link
                        to="/search"
                        search={{ cat: c.slug }}
                        onClick={close}
                        className="flex items-center gap-3 p-2 border border-border hover:border-primary hover:bg-accent/40 transition"
                      >
                        <img
                          src={c.image}
                          alt=""
                          loading="lazy"
                          decoding="async"
                          className="size-10 object-cover"
                        />
                        <span className="text-xs tracking-[0.16em] uppercase">{c.name}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>

          {/* Right: live results */}
          <div className="p-6 md:p-8 min-h-[50vh]">
            {!q && (
              <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground py-12">
                <SearchIcon className="size-8 mb-3 opacity-40" />
                <p className="text-sm">Start typing to see live suggestions.</p>
              </div>
            )}
            {q && results.length === 0 && (
              <div className="text-center text-muted-foreground py-12">
                <p className="text-sm">No instant matches — press enter to search.</p>
              </div>
            )}
            {q && results.length > 0 && (
              <>
                <h3 className="text-[10px] tracking-[0.3em] uppercase text-muted-foreground mb-4">
                  Products
                </h3>
                <ul className="divide-y divide-border">
                  {results.map((p) => (
                    <li key={p.id}>
                      <Link
                        to="/products/$slug"
                        params={{ slug: p.slug }}
                        onClick={close}
                        className="flex items-center gap-4 py-3 group"
                      >
                        <img
                          src={p.image}
                          alt=""
                          loading="lazy"
                          decoding="async"
                          className="size-14 object-cover bg-secondary"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm line-clamp-1 group-hover:text-primary transition">
                            {p.name}
                          </p>
                          <p className="text-xs text-muted-foreground">{p.sku}</p>
                        </div>
                        <span className="font-sans font-bold text-sm">{formatINR(p.price)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
                <div className="mt-6 pt-5 border-t border-border text-center">
                  <button
                    onClick={goSearch}
                    className="text-xs tracking-[0.24em] uppercase text-primary hover:underline"
                  >
                    See all results for "{q}" →
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
