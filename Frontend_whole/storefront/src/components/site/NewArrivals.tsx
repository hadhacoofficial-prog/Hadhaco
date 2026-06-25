import { useRef } from "react";
import { Link } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, ArrowUpRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { ProductCard } from "@/components/site/ProductCard";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProduct } from "@/lib/api/mappers";
import type { ProductListResponse } from "@/types/admin";

export function NewArrivals() {
  const { data } = useQuery({
    queryKey: queryKeys.products.list({ is_new_arrival: true, page_size: 8 }),
    queryFn: () =>
      api.get<ProductListResponse>("/products", {
        params: { is_new_arrival: true, page_size: 8 },
      }),
    staleTime: 5 * 60_000,
  });

  const list = (data?.items ?? []).map(toProduct);
  const scroller = useRef<HTMLDivElement>(null);

  const scroll = (dir: 1 | -1) => {
    const el = scroller.current;
    if (!el) return;
    el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: "smooth" });
  };

  if (list.length === 0) return null;

  return (
    <section className="px-4 md:px-12 py-20 md:py-24">
      <div className="flex items-end justify-between mb-8 md:mb-12 gap-4">
        <div>
          <p className="text-[11px] tracking-[0.32em] uppercase text-primary mb-3 font-cinzel">
            Just landed
          </p>
          <h2 className="font-cinzel text-3xl md:text-5xl">New Arrivals</h2>
          <p className="mt-3 text-foreground/70 max-w-md">
            Freshly cast and quality-checked — first dibs on this week's drop.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/search"
            search={{ filter: "new" }}
            className="hidden md:inline-flex items-center gap-2 text-xs tracking-[0.24em] uppercase border-b border-foreground pb-1 hover:text-primary hover:border-primary transition"
          >
            View all <ArrowUpRight className="size-4" />
          </Link>
          <div className="hidden md:flex items-center gap-2">
            <button
              onClick={() => scroll(-1)}
              aria-label="Previous"
              className="size-10 border border-border hover:border-primary hover:text-primary transition flex items-center justify-center"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              onClick={() => scroll(1)}
              aria-label="Next"
              className="size-10 border border-border hover:border-primary hover:text-primary transition flex items-center justify-center"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
      </div>

      <div
        ref={scroller}
        className="flex gap-4 md:gap-6 overflow-x-auto snap-x snap-mandatory scroll-smooth pb-4 -mx-4 px-4 md:mx-0 md:px-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {list.map((p) => (
          <div key={p.id} className="snap-start shrink-0 w-[70%] sm:w-[40%] md:w-[28%] lg:w-[22%]">
            <ProductCard p={p} />
          </div>
        ))}
      </div>

      <div className="md:hidden mt-6 text-center">
        <Link
          to="/search"
          search={{ filter: "new" }}
          className="inline-flex items-center gap-2 text-xs tracking-[0.24em] uppercase border-b border-primary text-primary pb-1"
        >
          View all new arrivals <ArrowUpRight className="size-4" />
        </Link>
      </div>
    </section>
  );
}
