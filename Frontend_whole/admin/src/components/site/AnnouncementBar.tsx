import type { AnnouncementConfig, AnnouncementItemConfig, SectionItem } from "@/types/cms";

const FALLBACK_MESSAGES = [
  "Certified 92.5 Sterling Silver",
  "Return eligibility depends on the individual product",
  "Handcrafted in Visakhapatnam",
];

interface AnnouncementBarProps {
  config?: Partial<AnnouncementConfig>;
  items?: SectionItem[];
}

export function AnnouncementBar({ config: _config, items = [] }: AnnouncementBarProps) {
  const cmsMessages = items
    .filter((i) => i.is_enabled)
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((i) => (i.config as unknown as AnnouncementItemConfig).text)
    .filter(Boolean);

  const messages = cmsMessages.length > 0 ? cmsMessages : FALLBACK_MESSAGES;
  const loop = [...messages, ...messages, ...messages];

  return (
    <div className="bg-primary text-primary-foreground text-xs tracking-[0.18em] uppercase overflow-hidden">
      <div className="flex whitespace-nowrap marquee-track py-2.5">
        {loop.map((m, i) => (
          <span key={i} className="px-8 flex items-center gap-3">
            <span className="inline-block size-1 rounded-full bg-accent" />
            {m}
          </span>
        ))}
      </div>
    </div>
  );
}
