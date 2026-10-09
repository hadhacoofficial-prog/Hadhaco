import { useCallback, useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { z } from "zod";

import { SiteLayout } from "@/components/site/SiteLayout";
import { ProductDiscovery } from "@/components/discovery/ProductDiscovery";
import { productListQuery } from "@/lib/discoveryQueries";
import {
  GENDER_LABELS,
  discoverySearchSchema,
  resolveDiscovery,
  splitCsv,
  titleCase,
  toUrlSearch,
  type DiscoveryState,
} from "@/lib/discovery";

// ─── Route ───────────────────────────────────────────────────────────────────

const productsSearchSchema = discoverySearchSchema.extend({
  // Legacy: header "Deals" link (/products?deals="true") → featured pieces.
  deals: z
    .union([z.literal("true"), z.literal(true)])
    .optional()
    .catch(undefined),
});

type ProductsSearch = z.infer<typeof productsSearchSchema>;

const DEFAULT_SORT = "newest" as const;

/**
 * Canonical URLs never contain `sort=newest` without a query (it's the
 * default and gets dropped), so one arriving here is an old "New Arrivals"
 * link — keep its original meaning (new-arrival pieces, newest first).
 */
function resolveProducts(search: ProductsSearch): DiscoveryState {
  const state = resolveDiscovery(search, DEFAULT_SORT);
  if (search.sort === "newest" && !search.q) state.new = true;
  return state;
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
    await queryClient.ensureQueryData(productListQuery(resolveProducts(deps)));
  },
  head: () => ({ meta: [{ title: "Shop · Hadha" }] }),
  component: ProductsPage,
});

// ─── Page ────────────────────────────────────────────────────────────────────

function ProductsPage() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const state = useMemo(() => resolveProducts(search), [search]);

  const onChange = useCallback(
    (next: DiscoveryState, opts?: { replace?: boolean }) => {
      navigate({
        search: toUrlSearch(next, DEFAULT_SORT) as ProductsSearch,
        replace: opts?.replace,
      });
    },
    [navigate],
  );

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-screen-2xl mx-auto">
        <ProductDiscovery
          state={state}
          onChange={onChange}
          header={
            <header className="mb-6">
              <h1 className="font-display text-3xl md:text-4xl tracking-wide">
                {buildTitle(state)}
              </h1>
            </header>
          }
          emptyAction={
            state.q ? (
              <Link
                to="/products"
                className="text-xs uppercase tracking-[0.18em] underline underline-offset-4"
              >
                Browse all pieces
              </Link>
            ) : undefined
          }
          noun={{ one: "product", many: "products" }}
        />
      </div>
    </SiteLayout>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function buildTitle(state: DiscoveryState): string {
  if (state.q) return `Results for "${state.q}"`;
  if (state.featured) return "Deals";
  if (state.new) return "New Arrivals";
  if (state.bestseller) return "Bestsellers";
  if (state.onSale) return "On Sale";

  const genders = splitCsv(state.gender);
  const categories = splitCsv(state.category);
  const genderLabel = genders.length === 1 ? (GENDER_LABELS[genders[0]] ?? genders[0]) : "";
  // Category slugs are gender-prefixed ("women-rings"); drop the prefix when
  // the gender is already in the title so it doesn't read "Women — Women Rings".
  const categorySlug =
    categories.length === 1 && genders.length === 1
      ? categories[0].replace(new RegExp(`^${genders[0]}-`), "")
      : categories[0];
  const categoryLabel = categories.length === 1 ? titleCase(categorySlug) : "";

  if (genderLabel && categoryLabel) return `${genderLabel} — ${categoryLabel}`;
  if (categoryLabel) return categoryLabel;
  if (genderLabel) return `Shop ${genderLabel}`;
  return "Shop";
}
