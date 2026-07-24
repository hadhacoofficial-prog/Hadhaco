import { useMemo, useEffect } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { z } from "zod";
import { Package } from "lucide-react";

import { SiteLayout } from "@/components/site/SiteLayout";
import { ProductGrid } from "@/components/site/ProductGrid";
import { EmptyState } from "@/components/site/EmptyState";
import { ProductGridSkeleton } from "@/components/loading/ProductGridSkeleton";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProduct } from "@/lib/api/mappers";
import { hydrateInventoryFromListItems } from "@/hooks/inventory/hydrateInventory";
import type { ProductListResponse } from "@/types/admin";

// ─── Route ───────────────────────────────────────────────────────────────────

const productsSearchSchema = z.object({
  gender: z.enum(["women", "men", "unisex", "kids"]).optional(),
  category: z.string().optional(), // category slug → category_slug on API
  deals: z.enum(["true"]).optional(), // /products?deals=true
  sort: z.enum(["newest", "popular", "price_asc", "price_desc"]).optional(),
  q: z.string().optional(),
  page: z.coerce.number().min(1).optional(),
});

type ProductsSearch = z.infer<typeof productsSearchSchema>;

/** Shared between the loader and the component so both hit the identical query key. */
function buildProductsApiParams({ gender, category, deals, sort, q, page = 1 }: ProductsSearch) {
  return {
    gender,
    category_slug: category,
    is_featured: deals === "true" ? true : undefined,
    is_new_arrival: sort === "newest" ? true : undefined,
    sort_by: sort === "price_asc" || sort === "price_desc" ? "base_price" : "created_at",
    sort_dir: sort === "price_asc" ? "asc" : "desc",
    search: q,
    page,
    page_size: 24,
  };
}

export const Route = createFileRoute("/products/")({
  validateSearch: productsSearchSchema,
  // Reload only when a search param that actually affects the results changes.
  loaderDeps: ({ search }) => search,
  // Pre-populates the query cache before the router commits the new location,
  // so the router's own "pending" state reflects real data-readiness instead
  // of flipping back to "idle" (and revealing the previous category's
  // keepPreviousData) before the new products have actually arrived.
  loader: async ({ context: { queryClient }, deps }) => {
    const apiParams = buildProductsApiParams(deps);
    await queryClient.ensureQueryData({
      queryKey: queryKeys.products.list(apiParams),
      queryFn: () => api.get<ProductListResponse>("/products", { params: apiParams }),
      staleTime: 30_000,
    });
  },
  head: () => ({ meta: [{ title: "Shop · Hadha" }] }),
  component: ProductsPage,
});

// ─── Page ────────────────────────────────────────────────────────────────────

function ProductsPage() {
  const search = Route.useSearch();
  const { gender, category, deals, sort, q } = search;

  const apiParams = useMemo(() => buildProductsApiParams(search), [search]);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.products.list(apiParams),
    queryFn: () => api.get<ProductListResponse>("/products", { params: apiParams }),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    if (data?.items?.length) hydrateInventoryFromListItems(data.items);
  }, [data]);

  const products = useMemo(() => (data?.items ?? []).map(toProduct), [data]);

  const title = buildTitle({ gender, category, deals, sort, q });

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-screen-xl mx-auto">
        <header className="mb-8">
          <h1 className="font-display text-3xl md:text-4xl tracking-wide capitalize">{title}</h1>
          {data?.total != null && (
            <p className="mt-1 text-sm text-muted-foreground">
              {data.total} {data.total === 1 ? "product" : "products"}
            </p>
          )}
        </header>

        {isLoading ? (
          <ProductGridSkeleton count={24} />
        ) : products.length === 0 ? (
          <EmptyState
            icon={<Package className="size-6" />}
            title="No products found"
            description="Try a different category or check back soon."
          />
        ) : (
          <ProductGrid products={products} />
        )}
      </div>
    </SiteLayout>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function buildTitle({
  gender,
  category,
  deals,
  sort,
  q,
}: {
  gender?: string;
  category?: string;
  deals?: string;
  sort?: string;
  q?: string;
}): string {
  if (deals === "true") return "Deals";
  if (sort === "newest") return "New Arrivals";
  if (sort === "popular") return "Bestsellers";

  const genderLabel = gender ? gender.charAt(0).toUpperCase() + gender.slice(1) : "";
  const categoryLabel = category
    ? category
        .split("-")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ")
    : "";

  if (q) return `Results for "${q}"`;
  if (genderLabel && categoryLabel) return `${genderLabel} — ${categoryLabel}`;
  if (genderLabel) return `Shop ${genderLabel}`;
  return "Shop";
}
