import { useId, useState, type ReactNode } from "react";
import { ChevronDown, Star } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  GENDER_LABELS,
  joinCsv,
  splitCsv,
  titleCase,
  type DiscoveryState,
  type ProductFacets,
} from "@/lib/discovery";
import { PriceRangeFilter } from "./PriceRangeFilter";

interface ProductFilterPanelProps {
  state: DiscoveryState;
  facets: ProductFacets | undefined;
  onChange: (patch: Partial<DiscoveryState>) => void;
}

/**
 * Filter groups are driven entirely by the facets response: a group only
 * renders when it has at least two values to choose between (or one is
 * already selected), and every option shows how many pieces it would match
 * under the other active filters — so there are no dead-end options.
 */
export function ProductFilterPanel({ state, facets, onChange }: ProductFilterPanelProps) {
  if (!facets) return <FilterPanelSkeleton />;

  const toggleCsv = (key: "category" | "gender" | "metal" | "purity", value: string) => {
    const current = splitCsv(state[key]);
    const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
    onChange({ [key]: joinCsv(next) });
  };

  const selectedCategories = splitCsv(state.category);
  const categoryIds = new Set(facets.categories.map((c) => c.id));
  const roots = facets.categories.filter((c) => !c.parent_id || !categoryIds.has(c.parent_id));
  const childrenOf = (id: string) => facets.categories.filter((c) => c.parent_id === id);

  const showGroup = (options: number, selected: number) => options >= 2 || selected > 0;

  const highlights: {
    key: "inStock" | "onSale" | "new" | "bestseller";
    label: string;
    count: number;
  }[] = [
    { key: "inStock", label: "In stock only", count: facets.in_stock },
    { key: "onSale", label: "On sale", count: facets.on_sale },
    { key: "new", label: "New arrivals", count: facets.new_arrival },
    { key: "bestseller", label: "Best sellers", count: facets.best_seller },
  ];
  // A toggle that matches none, or every one, of the current results would
  // not change anything — only offer the ones that actually narrow.
  const visibleHighlights = highlights.filter(
    (h) => state[h.key] || (h.count > 0 && h.count < facets.total),
  );

  return (
    <div className="text-sm divide-y divide-border border-y border-border">
      {showGroup(facets.categories.length, selectedCategories.length) && (
        <FilterGroup title="Category" count={selectedCategories.length}>
          <ul className="space-y-1">
            {roots.map((root) => (
              <li key={root.id}>
                <CheckOption
                  label={root.name}
                  count={root.count}
                  checked={selectedCategories.includes(root.slug)}
                  onToggle={() => toggleCsv("category", root.slug)}
                />
                {childrenOf(root.id).length > 0 && (
                  <ul className="ml-6 mt-1 space-y-1 border-l border-border pl-3">
                    {childrenOf(root.id).map((child) => (
                      <li key={child.id}>
                        <CheckOption
                          label={child.name}
                          count={child.count}
                          checked={selectedCategories.includes(child.slug)}
                          onToggle={() => toggleCsv("category", child.slug)}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </FilterGroup>
      )}

      {showGroup(facets.genders.length, splitCsv(state.gender).length) && (
        <FilterGroup title="Gender" count={splitCsv(state.gender).length}>
          <ul className="space-y-1">
            {facets.genders.map((g) => (
              <li key={g.value}>
                <CheckOption
                  label={GENDER_LABELS[g.value] ?? titleCase(g.value)}
                  count={g.count}
                  checked={splitCsv(state.gender).includes(g.value)}
                  onToggle={() => toggleCsv("gender", g.value)}
                />
              </li>
            ))}
          </ul>
        </FilterGroup>
      )}

      {facets.price_min !== null &&
        facets.price_max !== null &&
        (facets.price_max > facets.price_min ||
          state.minPrice !== undefined ||
          state.maxPrice !== undefined) && (
          <FilterGroup
            title="Price"
            count={state.minPrice !== undefined || state.maxPrice !== undefined ? 1 : 0}
          >
            <PriceRangeFilter
              bounds={{ min: facets.price_min, max: facets.price_max }}
              value={{ min: state.minPrice, max: state.maxPrice }}
              onChange={({ min, max }) => onChange({ minPrice: min, maxPrice: max })}
            />
          </FilterGroup>
        )}

      {(facets.ratings.length > 0 || state.rating) && (
        <FilterGroup title="Rating" count={state.rating ? 1 : 0}>
          <ul className="space-y-1" role="radiogroup" aria-label="Minimum rating">
            {facets.ratings.map((r) => (
              <li key={r.min_rating}>
                <button
                  type="button"
                  role="radio"
                  aria-checked={state.rating === r.min_rating}
                  onClick={() =>
                    onChange({ rating: state.rating === r.min_rating ? undefined : r.min_rating })
                  }
                  className={cn(
                    "w-full flex items-center justify-between gap-2 min-h-10 px-2 -mx-2 hover:bg-secondary",
                    state.rating === r.min_rating && "font-medium",
                  )}
                >
                  <span className="flex items-center gap-1.5">
                    <span
                      aria-hidden
                      className={cn(
                        "size-4 rounded-full border border-foreground/60 flex items-center justify-center",
                      )}
                    >
                      {state.rating === r.min_rating && (
                        <span className="size-2 rounded-full bg-foreground" />
                      )}
                    </span>
                    <span className="inline-flex" aria-hidden>
                      {Array.from({ length: 5 }, (_, i) => (
                        <Star
                          key={i}
                          className={cn(
                            "size-3.5",
                            i < r.min_rating
                              ? "fill-foreground text-foreground"
                              : "text-muted-foreground/40",
                          )}
                        />
                      ))}
                    </span>
                    <span>{r.min_rating}★ & up</span>
                  </span>
                  <span className="text-xs text-muted-foreground tabular-nums">{r.count}</span>
                </button>
              </li>
            ))}
          </ul>
        </FilterGroup>
      )}

      {showGroup(facets.metal_types.length, splitCsv(state.metal).length) && (
        <FilterGroup title="Metal" count={splitCsv(state.metal).length}>
          <ul className="space-y-1">
            {facets.metal_types.map((m) => (
              <li key={m.value}>
                <CheckOption
                  label={m.value}
                  count={m.count}
                  checked={splitCsv(state.metal).includes(m.value)}
                  onToggle={() => toggleCsv("metal", m.value)}
                />
              </li>
            ))}
          </ul>
        </FilterGroup>
      )}

      {showGroup(facets.purities.length, splitCsv(state.purity).length) && (
        <FilterGroup title="Purity" count={splitCsv(state.purity).length}>
          <ul className="space-y-1">
            {facets.purities.map((p) => (
              <li key={p.value}>
                <CheckOption
                  label={p.value}
                  count={p.count}
                  checked={splitCsv(state.purity).includes(p.value)}
                  onToggle={() => toggleCsv("purity", p.value)}
                />
              </li>
            ))}
          </ul>
        </FilterGroup>
      )}

      {visibleHighlights.length > 0 && (
        <FilterGroup
          title="Availability & offers"
          count={visibleHighlights.filter((h) => state[h.key]).length}
        >
          <ul className="space-y-1">
            {visibleHighlights.map((h) => (
              <li key={h.key}>
                <CheckOption
                  label={h.label}
                  count={h.count}
                  checked={!!state[h.key]}
                  onToggle={() => onChange({ [h.key]: state[h.key] ? undefined : true })}
                />
              </li>
            ))}
            {state.featured && (
              <li>
                <CheckOption
                  label="Featured"
                  checked
                  onToggle={() => onChange({ featured: undefined })}
                />
              </li>
            )}
          </ul>
        </FilterGroup>
      )}
    </div>
  );
}

function FilterGroup({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const id = useId();
  return (
    <section className="py-4">
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-center justify-between min-h-10 font-display text-base text-left"
        >
          <span>
            {title}
            {count > 0 && (
              <span className="ml-2 text-xs font-sans text-muted-foreground">({count})</span>
            )}
          </span>
          <ChevronDown
            aria-hidden
            className={cn("size-4 transition-transform", open && "rotate-180")}
          />
        </button>
      </h3>
      <div id={id} hidden={!open} className="pt-2">
        {children}
      </div>
    </section>
  );
}

function CheckOption({
  label,
  count,
  checked,
  onToggle,
}: {
  label: string;
  count?: number;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex items-center justify-between gap-3 min-h-10 cursor-pointer px-2 -mx-2 hover:bg-secondary">
      <span className="flex items-center gap-2.5">
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          aria-label={count !== undefined ? `${label}, ${count} items` : label}
          className="size-4 accent-[color:var(--primary)] cursor-pointer"
        />
        <span className={cn(checked && "font-medium")}>{label}</span>
      </span>
      {count !== undefined && (
        <span className="text-xs text-muted-foreground tabular-nums">{count}</span>
      )}
    </label>
  );
}

function FilterPanelSkeleton() {
  return (
    <div className="space-y-6 py-4" aria-hidden>
      {[5, 4, 2].map((rows, i) => (
        <div key={i} className="space-y-3">
          <div className="h-4 w-24 bg-secondary animate-pulse" />
          {Array.from({ length: rows }, (_, j) => (
            <div key={j} className="h-3 w-full bg-secondary/70 animate-pulse" />
          ))}
        </div>
      ))}
    </div>
  );
}
