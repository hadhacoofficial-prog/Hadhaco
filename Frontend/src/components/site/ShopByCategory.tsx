import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toCollection } from "@/lib/api/mappers";
import type { CollectionDto } from "@/types/public";

export function ShopByCategory() {
  const { data: raw } = useQuery({
    queryKey: queryKeys.collections.list,
    queryFn: () => api.get<CollectionDto[]>("/collections"),
    staleTime: 10 * 60_000,
  });

  const collections = (raw ?? []).map(toCollection);

  if (collections.length === 0) return null;

  return (
    <section className="px-4 md:px-12 py-20 md:py-28">
      <div className="flex items-end justify-between mb-10 md:mb-14">
        <div>
          <p className="text-[11px] tracking-[0.3em] uppercase text-accent mb-3">
            Shop by category
          </p>
          <h2 className="font-display text-4xl md:text-5xl">Collections</h2>
          <p className="mt-3 text-foreground/70 max-w-md">
            Timeless designs that add grace and sparkle to every look.
          </p>
        </div>
        <Link
          to="/collections"
          className="hidden md:inline-flex items-center gap-2 text-xs tracking-[0.22em] uppercase border-b border-foreground pb-1 hover:text-primary hover:border-primary transition"
        >
          Check all collections <ArrowUpRight className="size-4" />
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-5">
        {collections.map((c) => (
          <Link key={c.id} to="/search" search={{ cat: c.slug }} className="group block">
            <div className="relative aspect-square overflow-hidden bg-secondary">
              <img
                src={c.image}
                alt={c.name}
                loading="lazy"
                width={800}
                height={800}
                className="w-full h-full object-cover transition-transform duration-[1200ms] group-hover:scale-105"
              />
              <div className="absolute inset-0 bg-foreground/0 group-hover:bg-foreground/10 transition-colors" />
            </div>
            <div className="mt-3 flex items-center justify-between">
              <span className="font-display text-base md:text-lg">{c.name}</span>
              <ArrowUpRight className="size-4 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
