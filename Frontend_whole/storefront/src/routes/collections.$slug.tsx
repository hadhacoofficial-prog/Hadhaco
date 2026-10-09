import { useCallback, useMemo } from "react";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { ProductDiscovery } from "@/components/discovery/ProductDiscovery";
import { api } from "@/lib/api/client";
import { toCollection } from "@/lib/api/mappers";
import {
  discoverySearchSchema,
  resolveDiscovery,
  toUrlSearch,
  type DiscoverySearch,
  type DiscoveryState,
} from "@/lib/discovery";
import type { CollectionDto } from "@/types/public";

export const Route = createFileRoute("/collections/$slug")({
  validateSearch: discoverySearchSchema,
  loader: async ({ params }) => {
    const dto = await api.get<CollectionDto>(`/collections/${params.slug}`).catch((e: unknown) => {
      if ((e as { status?: number }).status === 404) throw notFound();
      throw e;
    });
    return { collection: toCollection(dto) };
  },
  head: ({ loaderData }) => ({
    meta: [
      { title: `${loaderData?.collection.name ?? "Collection"} · Hadha` },
      { name: "description", content: loaderData?.collection.description ?? "" },
    ],
  }),
  notFoundComponent: () => (
    <SiteLayout>
      <div className="px-8 py-20 text-center">
        <h1 className="font-display text-3xl mb-3">Collection not found</h1>
        <Link to="/collections" className="underline">
          Back to all collections
        </Link>
      </div>
    </SiteLayout>
  ),
  errorComponent: ({ reset }) => (
    <SiteLayout>
      <div className="px-8 py-20 text-center">
        <h1 className="font-display text-2xl mb-3">Something went wrong</h1>
        <button className="underline" onClick={() => reset()}>
          Try again
        </button>
      </div>
    </SiteLayout>
  ),
  component: CollectionPage,
});

const DEFAULT_SORT = "newest" as const;

function CollectionPage() {
  const { collection } = Route.useLoaderData();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const state = useMemo(() => resolveDiscovery(search, DEFAULT_SORT), [search]);
  const scope = useMemo(() => ({ collectionSlug: collection.slug }), [collection.slug]);

  const onChange = useCallback(
    (next: DiscoveryState, opts?: { replace?: boolean }) => {
      navigate({
        search: toUrlSearch(next, DEFAULT_SORT) as DiscoverySearch,
        replace: opts?.replace,
      });
    },
    [navigate],
  );

  return (
    <SiteLayout>
      {/* Banner */}
      <div className="relative h-[260px] md:h-[340px] bg-secondary overflow-hidden">
        <img
          src={collection.image}
          alt={collection.name}
          fetchPriority="high"
          decoding="async"
          className="absolute inset-0 w-full h-full object-cover opacity-60"
        />
        <div className="absolute inset-0 bg-foreground/30" />
        <div className="relative h-full flex flex-col items-center justify-center text-center px-6 text-background">
          <p className="text-[11px] tracking-[0.3em] uppercase mb-2">Collection</p>
          <h1 className="font-display text-4xl md:text-6xl">{collection.name}</h1>
          {collection.description && (
            <p className="text-sm mt-3 max-w-xl opacity-90">{collection.description}</p>
          )}
        </div>
      </div>

      <div className="px-4 md:px-8 py-6">
        <Breadcrumbs
          items={[
            { label: "Home", to: "/" },
            { label: "Collections", to: "/collections" },
            { label: collection.name },
          ]}
        />
      </div>

      <div className="px-4 md:px-8 pb-16">
        <ProductDiscovery
          state={state}
          scope={scope}
          onChange={onChange}
          emptyAction={
            <Link
              to="/collections"
              className="text-xs uppercase tracking-[0.18em] underline underline-offset-4"
            >
              Explore other collections
            </Link>
          }
        />
      </div>
    </SiteLayout>
  );
}
