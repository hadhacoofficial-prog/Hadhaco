import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

// Count API calls made by the real route loader / live poll.
vi.mock("@/lib/api/client", () => {
  const get = vi.fn();
  return { api: { get } };
});

import { api } from "@/lib/api/client";
import { Route } from "@/routes/products.$slug";
import { queryKeys } from "@/lib/api/queryKeys";
import type { ProductDetail } from "@/types/public";

const mockedGet = api.get as unknown as ReturnType<typeof vi.fn>;

// TanStack Router types the route loader as a union of loader functions and
// loader objects (RouteLoaderFn | RouteLoaderObject), which is not directly
// callable. Cast to the concrete signature this test exercises.
type LoaderCtx = {
  context: { queryClient: QueryClient };
  params: { slug: string };
};
type LoaderResult = { product: ProductDetail };
const loadRoute = Route.options.loader as unknown as (
  ctx: LoaderCtx,
) => Promise<LoaderResult>;

function makeDetail(slug: string): ProductDetail {
  return {
    id: "p1",
    sku: "SKU-E2E-1",
    name: "Silver Ring",
    slug,
    description: "A test product",
    short_description: null,
    category_id: null,
    metal_type: "silver",
    purity: "925",
    hallmark_number: null,
    weight_grams: 5,
    making_charges: null,
    wastage_percent: null,
    gender: "unisex",
    base_price: 4999,
    compare_at_price: 5999,
    cost_price: null,
    tax_rate: 3,
    hsn_code: null,
    track_inventory: true,
    allow_backorder: false,
    low_stock_threshold: 5,
    stock_quantity: 10,
    available_stock: 10,
    inventory_status: "IN_STOCK",
    can_purchase: true,
    reserved_quantity: 0,
    sold_quantity: 0,
    max_order_quantity: 5,
    average_rating: 4.5,
    review_count: 3,
    status: "active",
    is_featured: true,
    is_new_arrival: false,
    is_best_seller: false,
    is_customizable: false,
    requires_shipping: true,
    length_cm: null,
    width_cm: null,
    height_cm: null,
    meta_title: null,
    meta_description: null,
    meta_keywords: null,
    images: [
      {
        id: "img1",
        url: "https://cdn.example.test/p1.jpg",
        original_url: "https://cdn.example.test/p1-original.jpg",
        medium_url: "https://cdn.example.test/p1-medium.jpg",
        large_url: "https://cdn.example.test/p1-large.jpg",
        thumbnail_url: "https://cdn.example.test/p1-thumb.jpg",
        is_primary: true,
        sort_order: 0,
        alt_text: null,
        crop_x: null,
        crop_y: null,
        crop_width: null,
        crop_height: null,
        crop_zoom: null,
        crop_rotation: null,
        updated_at: "2026-01-01T12:00:00Z",
      },
    ],
    variants: [
      {
        id: "v1",
        sku: "SKU-E2E-1-S",
        name: "Size 12",
        price_adjustment: 0,
        stock_quantity: 5,
        weight_grams: null,
        is_active: true,
        sort_order: 0,
        inventory_status: "IN_STOCK",
      },
    ],
    attributes: [],
    collections: [],
    created_at: "2026-01-01T12:00:00Z",
    updated_at: "2026-01-01T12:00:00Z",
    published_at: "2026-01-01T12:00:00Z",
  };
}

const SLUG = "silver-ring-e2e";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
}

function productDetailGets(): number {
  return mockedGet.mock.calls.filter(([url]) => url === `/products/${SLUG}`).length;
}

function wrapper(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("PDP single-request behavior (P1-3 / P3-2)", () => {
  beforeEach(() => {
    mockedGet.mockReset();
    mockedGet.mockImplementation((url: string) => {
      if (url === `/products/${SLUG}`) return Promise.resolve(makeDetail(SLUG));
      // Related products (loader only) — empty list is enough.
      return Promise.resolve({ items: [] });
    });
  });

  it("cold load: route loader issues exactly ONE product-detail GET and seeds the poll query key", async () => {
    const qc = makeQueryClient();
    const loaderData = await loadRoute({
      context: { queryClient: qc },
      params: { slug: SLUG },
    });

    // The loader fetched the product detail exactly once…
    expect(productDetailGets()).toBe(1);
    // …and seeded the exact key the live poll below uses.
    expect(qc.getQueryData(queryKeys.products.stock(SLUG))).toBeDefined();
    // Loader return value is the mapped product.
    expect(loaderData.product.slug).toBe(SLUG);
    expect(loaderData.product.name).toBe("Silver Ring");
  });

  it("live poll reuses the loader-seeded cache — mounting the poll query issues NO extra GET", async () => {
    const qc = makeQueryClient();
    // Simulate the route loader running first (as TanStack Router does).
    await loadRoute({
      context: { queryClient: qc },
      params: { slug: SLUG },
    });
    const getsAfterLoader = productDetailGets();
    expect(getsAfterLoader).toBe(1);

    // Mount the exact query config the ProductPage live poll uses
    // (same key, same staleTime — see products.$slug.tsx).
    const { result } = renderHook(
      () =>
        useQuery({
          queryKey: queryKeys.products.stock(SLUG),
          queryFn: () => api.get<ProductDetail>(`/products/${SLUG}`, { cache: "no-cache" }),
          staleTime: 30_000,
          refetchInterval: 60_000,
          refetchOnWindowFocus: true,
        }),
      { wrapper: wrapper(qc) },
    );

    await waitFor(() => expect(result.current.data).toBeDefined());
    // Data came from the cache seeded by the loader — no additional GET.
    expect(productDetailGets()).toBe(1);
  });

  it("subsequent navigation back within staleTime serves from cache — no extra GET", async () => {
    const qc = makeQueryClient();
    // First visit.
    await loadRoute({
      context: { queryClient: qc },
      params: { slug: SLUG },
    });
    expect(productDetailGets()).toBe(1);

    // Navigate away and back immediately (data still fresh: staleTime=30s).
    await loadRoute({
      context: { queryClient: qc },
      params: { slug: SLUG },
    });
    expect(productDetailGets()).toBe(1);
  });

  it("navigating back AFTER staleTime serves cached data — loader adds NO GET (poll owns refresh)", async () => {
    const qc = makeQueryClient();
    await loadRoute({
      context: { queryClient: qc },
      params: { slug: SLUG },
    });
    expect(productDetailGets()).toBe(1);

    // Age the cached entry well past staleTime=30s (as a real later
    // navigation would encounter it). ensureQueryData (React Query v5) only
    // refetches on a hard miss (data undefined) or with revalidateIfStale:
    // true — the PDP loader uses neither. So the loader returns the cached
    // value WITHOUT a GET; freshness is maintained by the live poll's
    // refetchInterval (60s) / refetchOnWindowFocus, not by the loader.
    qc.setQueryData(queryKeys.products.stock(SLUG), makeDetail(SLUG), {
      updatedAt: Date.now() - 120_000,
    });

    const loaderData = await loadRoute({
      context: { queryClient: qc },
      params: { slug: SLUG },
    });
    expect(loaderData.product.slug).toBe(SLUG);
    // Still exactly one product-detail GET — the loader never duplicates.
    expect(productDetailGets()).toBe(1);
  });
});
