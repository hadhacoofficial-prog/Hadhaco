import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toCollection } from "@/lib/api/mappers";
import type { CollectionDto } from "@/types/public";

export interface FilterValues {
  collectionSlug?: string;
  gender?: "all" | "women" | "men" | "unisex";
  inStock?: boolean;
  isNew?: boolean;
  isBestseller?: boolean;
  maxPrice?: number;
}

export function FilterPanel({
  value,
  onChange,
  hideCollection,
}: {
  value: FilterValues;
  onChange: (v: FilterValues) => void;
  hideCollection?: boolean;
}) {
  const set = (patch: Partial<FilterValues>) => onChange({ ...value, ...patch });
  const priceMax = useMemo(() => 10000, []);

  const { data: raw } = useQuery({
    queryKey: queryKeys.collections.list,
    queryFn: () => api.get<CollectionDto[]>("/collections"),
    staleTime: 10 * 60_000,
    enabled: !hideCollection,
  });
  const collections = (raw ?? []).map(toCollection);

  return (
    <div className="space-y-8 text-sm">
      {!hideCollection && (
        <Section title="Collection">
          <div className="space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="col"
                checked={!value.collectionSlug}
                onChange={() => set({ collectionSlug: undefined })}
              />
              <span>All</span>
            </label>
            {collections.map((c) => (
              <label key={c.id} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="col"
                  checked={value.collectionSlug === c.slug}
                  onChange={() => set({ collectionSlug: c.slug })}
                />
                <span>{c.name}</span>
              </label>
            ))}
          </div>
        </Section>
      )}

      <Section title="Gender">
        <div className="space-y-2">
          {(["all", "women", "men", "unisex"] as const).map((g) => (
            <label key={g} className="flex items-center gap-2 cursor-pointer capitalize">
              <input
                type="radio"
                name="g"
                checked={(value.gender ?? "all") === g}
                onChange={() => set({ gender: g })}
              />
              <span>{g}</span>
            </label>
          ))}
        </div>
      </Section>

      <Section title="Price">
        <input
          type="range"
          min={500}
          max={priceMax}
          step={100}
          value={value.maxPrice ?? priceMax}
          onChange={(e) => set({ maxPrice: Number(e.target.value) })}
          className="w-full accent-[color:var(--primary)]"
        />
        <div className="flex justify-between text-xs text-muted-foreground mt-1">
          <span>Rs. 500</span>
          <span>Up to Rs. {(value.maxPrice ?? priceMax).toLocaleString("en-IN")}</span>
        </div>
      </Section>

      <Section title="Availability">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={!!value.inStock}
            onChange={(e) => set({ inStock: e.target.checked })}
          />
          <span>In stock only</span>
        </label>
      </Section>

      <Section title="Highlights">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={!!value.isNew}
            onChange={(e) => set({ isNew: e.target.checked })}
          />
          <span>New arrivals</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer mt-2">
          <input
            type="checkbox"
            checked={!!value.isBestseller}
            onChange={(e) => set({ isBestseller: e.target.checked })}
          />
          <span>Best sellers</span>
        </label>
      </Section>

      <button
        onClick={() => onChange({})}
        className="text-xs uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground underline underline-offset-4"
      >
        Clear all filters
      </button>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="font-display text-base mb-3 pb-2 border-b border-border">{title}</h3>
      {children}
    </div>
  );
}
