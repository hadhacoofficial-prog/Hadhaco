import { Instagram } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toCollection } from "@/lib/api/mappers";
import type { CollectionDto } from "@/types/public";
import type { InstagramGalleryConfig, InstagramItemConfig, SectionItem } from "@/types/cms";

const DEFAULTS: InstagramGalleryConfig = {
  title: "Worn by our community.",
  handle: "hadha.silver",
  max_items: 6,
  source: "collections",
};

interface InstagramSectionProps {
  config?: Partial<InstagramGalleryConfig>;
  items?: SectionItem[];
}

export function InstagramSection({ config, items = [] }: InstagramSectionProps) {
  const c = { ...DEFAULTS, ...config };
  const handle = c.handle.replace(/^@/, "");
  const url = `https://instagram.com/${handle}`;

  const { data: collections = [] } = useQuery({
    queryKey: queryKeys.collections.list,
    queryFn: () => api.get<CollectionDto[]>("/collections").then((list) => list.map(toCollection)),
    staleTime: 10 * 60_000,
    enabled: c.source !== "manual",
  });

  // Manual items mode — use CMS section items
  const manualTiles = items
    .filter((i) => i.is_enabled)
    .sort((a, b) => a.sort_order - b.sort_order)
    .slice(0, c.max_items)
    .map((i) => i.config as unknown as InstagramItemConfig);

  // Collections mode — use collection images
  const collectionTiles = collections.slice(0, c.max_items).map((t) => ({
    image_url: t.image ?? "",
    link_url: url,
    alt_text: t.name ?? "",
  }));

  const tiles = c.source === "manual" ? manualTiles : collectionTiles;
  if (tiles.length === 0) return null;

  return (
    <section className="py-20 md:py-24 border-t border-border">
      <div className="text-center mb-10 px-4">
        <p className="text-[11px] tracking-[0.3em] uppercase text-accent mb-3">@{handle}</p>
        <h2 className="font-display text-4xl md:text-5xl">{c.title}</h2>
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="mt-5 inline-flex items-center gap-2 text-xs tracking-[0.22em] uppercase border-b border-foreground pb-1 hover:text-accent hover:border-accent transition"
        >
          <Instagram className="size-4" /> Follow on Instagram
        </a>
      </div>
      <div className="grid grid-cols-3 md:grid-cols-6 gap-1 md:gap-1.5 px-1 md:px-1.5">
        {tiles.map((t, i) => (
          <a
            key={i}
            href={t.link_url || url}
            target="_blank"
            rel="noreferrer"
            className="relative aspect-square overflow-hidden group"
          >
            <img
              src={t.image_url}
              alt={t.alt_text || ""}
              loading="lazy"
              width={500}
              height={500}
              className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
            />
            <div className="absolute inset-0 bg-primary/0 group-hover:bg-primary/40 transition-colors flex items-center justify-center">
              <Instagram className="size-6 text-primary-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}
