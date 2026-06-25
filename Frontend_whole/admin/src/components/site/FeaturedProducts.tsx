import { ArrowUpRight } from "lucide-react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { ProductCard } from "./ProductCard";
import { staggerContainer, staggerItem } from "@/components/common/Reveal";
import { ProductCardSkeleton } from "@/components/loading/ProductCardSkeleton";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProduct } from "@/lib/api/mappers";
import type { ProductListResponse } from "@/types/admin";
import type { ProductGridConfig } from "@/types/cms";

const DEFAULTS: ProductGridConfig = {
  title: "Most-loved silver, curated.",
  eyebrow: "Featured products",
  source: "featured",
  max_products: 8,
  view_all_url: "/search",
};

function sourceToParams(source: ProductGridConfig["source"]) {
  switch (source) {
    case "featured":
      return { is_featured: true };
    case "newest":
      return { sort: "newest" };
    case "best_seller":
      return { sort: "best_seller" };
    case "trending":
      return { sort: "trending" };
    default:
      return { is_featured: true };
  }
}

interface FeaturedProductsProps {
  config?: Partial<ProductGridConfig>;
}

export function FeaturedProducts({ config }: FeaturedProductsProps) {
  const c = { ...DEFAULTS, ...config };
  const params = { ...sourceToParams(c.source), page_size: c.max_products };

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.products.list(params),
    queryFn: () => api.get<ProductListResponse>("/products", { params }),
    staleTime: 5 * 60_000,
  });

  const items = (data?.items ?? []).map(toProduct);
  if (!isLoading && items.length === 0) return null;

  return (
    <section className="relative px-4 md:px-12 py-20 md:py-28 bg-background overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_50%_40%_at_100%_0%,oklch(0.91_0.02_250/0.5)_0%,transparent_60%)]" />
      <div className="relative">
        <div className="flex items-end justify-between mb-10 md:mb-14 gap-6">
          <div className="max-w-2xl">
            {c.eyebrow && (
              <p className="text-[11px] tracking-[0.32em] uppercase text-accent mb-3 font-cinzel">
                {c.eyebrow}
              </p>
            )}
            <h2 className="font-cinzel text-3xl md:text-5xl">{c.title}</h2>
          </div>
          {c.view_all_url && (
            <a
              href={c.view_all_url}
              className="hidden md:inline-flex shrink-0 items-center gap-2 text-xs tracking-[0.24em] uppercase border-b border-primary text-primary pb-1 hover:gap-3 transition-all"
            >
              View all <ArrowUpRight className="size-4" />
            </a>
          )}
        </div>

        {isLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-7">
            {Array.from({ length: c.max_products }).map((_, i) => (
              <ProductCardSkeleton key={i} />
            ))}
          </div>
        ) : (
          <motion.div
            variants={staggerContainer}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.15 }}
            className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-7"
          >
            {items.map((p) => (
              <motion.div key={p.id} variants={staggerItem}>
                <ProductCard p={p} />
              </motion.div>
            ))}
          </motion.div>
        )}

        {c.view_all_url && (
          <div className="mt-10 md:hidden text-center">
            <a
              href={c.view_all_url}
              className="inline-flex items-center gap-2 text-xs tracking-[0.24em] uppercase border-b border-primary text-primary pb-1"
            >
              View all <ArrowUpRight className="size-4" />
            </a>
          </div>
        )}
      </div>
    </section>
  );
}
