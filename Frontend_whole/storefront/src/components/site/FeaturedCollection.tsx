import banner from "@/assets/banner.jpg";
import hero from "@/assets/hero.jpg";
import { ArrowRight } from "lucide-react";
import type { CollectionCardConfig, SectionItem } from "@/types/cms";

const FALLBACK_CARDS: CollectionCardConfig[] = [
  {
    image_url: hero,
    eyebrow: "Featured edit",
    title: "Finger Rings, redefined.",
    subtitle:
      "Stylish rings crafted to bring subtle elegance to every look — from stackable everyday bands to statement temple stones.",
    button_text: "Shop rings",
    button_url: "#",
  },
  {
    image_url: banner,
    eyebrow: "Bestseller",
    title: "The Bugadi edit.",
    subtitle:
      "Heritage temple ear cuffs reimagined — non-piercing, press-on, and poised to become your new favourite.",
    button_text: "Discover Bugadi",
    button_url: "#",
  },
];

interface FeaturedCollectionProps {
  items?: SectionItem[];
}

export function FeaturedCollection({ items = [] }: FeaturedCollectionProps) {
  const cmsCards = items
    .filter((i) => i.is_enabled)
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((i) => i.config as unknown as CollectionCardConfig);
  const cards = cmsCards.length > 0 ? cmsCards : FALLBACK_CARDS;

  return (
    <>
      {cards.map((card, i) => {
        const imageOnLeft = i % 2 === 0;
        const dark = i % 2 === 1;
        const image = (
          <div className="relative aspect-[4/5] md:aspect-auto overflow-hidden group">
            <img
              src={card.image_url || hero}
              alt={card.title}
              loading="lazy"
              width={1200}
              height={1500}
              className="absolute inset-0 w-full h-full object-cover transition-transform duration-[1500ms] group-hover:scale-105"
            />
          </div>
        );
        const panel = (
          <div
            className={`flex items-center justify-center px-8 py-20 md:py-0 ${dark ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground"}`}
          >
            <div className="max-w-md">
              {card.eyebrow && (
                <p className="text-[11px] tracking-[0.3em] uppercase text-accent mb-4">
                  {card.eyebrow}
                </p>
              )}
              <h3 className="font-display text-4xl md:text-5xl leading-tight">{card.title}</h3>
              {card.subtitle && (
                <p className={`mt-5 ${dark ? "text-primary-foreground/80" : "text-foreground/75"}`}>
                  {card.subtitle}
                </p>
              )}
              {card.button_text && (
                <a
                  href={card.button_url || "#"}
                  className={`group mt-8 inline-flex items-center gap-3 px-7 py-3.5 text-xs tracking-[0.22em] uppercase transition-colors ${dark ? "bg-accent text-accent-foreground hover:bg-primary-foreground hover:text-primary" : "bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground"}`}
                >
                  {card.button_text}{" "}
                  <ArrowRight className="size-4 group-hover:translate-x-1 transition-transform" />
                </a>
              )}
            </div>
          </div>
        );
        return (
          <section key={card.title || i} className="grid md:grid-cols-2">
            {imageOnLeft ? (
              <>
                {image}
                {panel}
              </>
            ) : (
              <>
                {panel}
                {image}
              </>
            )}
          </section>
        );
      })}
    </>
  );
}
