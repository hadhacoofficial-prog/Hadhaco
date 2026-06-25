import { useQuery } from "@tanstack/react-query";
import { ProductCard } from "./ProductCard";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProduct } from "@/lib/api/mappers";
import type { ProductListResponse } from "@/types/admin";

export function Trending() {
  const { data } = useQuery({
    queryKey: queryKeys.products.list({ is_best_seller: true, page_size: 4 }),
    queryFn: () =>
      api.get<ProductListResponse>("/products", {
        params: { is_best_seller: true, page_size: 4 },
      }),
    staleTime: 5 * 60_000,
  });

  const items = (data?.items ?? []).map(toProduct);

  if (items.length === 0) return null;

  return (
    <section className="px-4 md:px-12 py-20 md:py-28 border-t border-border">
      <div className="mb-10 text-center">
        <p className="text-[11px] tracking-[0.3em] uppercase text-accent mb-3">Trending now</p>
        <h2 className="font-display text-4xl md:text-5xl">What everyone's wearing</h2>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-5 md:gap-7">
        {items.map((p) => (
          <ProductCard key={p.id} p={p} />
        ))}
      </div>
    </section>
  );
}
