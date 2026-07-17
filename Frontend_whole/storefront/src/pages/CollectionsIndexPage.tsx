import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toCollection } from "@/lib/api/mappers";
import type { CollectionDto } from "@/types/public";

export default function CollectionsIndex() {
  const { data: raw, isLoading } = useQuery({
    queryKey: queryKeys.collections.list,
    queryFn: () => api.get<CollectionDto[]>("/collections"),
    staleTime: 10 * 60_000,
  });

  const collections = (Array.isArray(raw) ? raw : []).map(toCollection);

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Collections" }]} />
        <header className="text-center my-12 md:my-16">
          <p className="text-[11px] tracking-[0.3em] uppercase text-muted-foreground mb-3">
            Explore
          </p>
          <h1 className="font-display text-4xl md:text-5xl">All Collections</h1>
          <p className="text-sm text-muted-foreground mt-3 max-w-xl mx-auto">
            Crafted in 92.5 sterling silver — designed for every chapter of you.
          </p>
        </header>

        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-5 gap-y-10">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="animate-pulse">
                <div className="aspect-square bg-secondary" />
                <div className="h-5 bg-secondary mt-4 mx-auto w-24" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-5 gap-y-10">
            {collections.map((c) => (
              <Link
                key={c.id}
                to="/collections/$slug"
                params={{ slug: c.slug }}
                className="group block"
              >
                <div className="aspect-square bg-secondary overflow-hidden">
                  <img
                    src={c.image}
                    alt={c.name}
                    className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                  />
                </div>
                <div className="text-center mt-4">
                  <h2 className="font-display text-lg group-hover:text-accent transition">
                    {c.name}
                  </h2>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </SiteLayout>
  );
}
