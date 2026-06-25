import { useEffect, useState } from "react";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import heroBg from "@/assets/hero.jpg";
import bannerBg from "@/assets/banner.jpg";
import nakshiBg from "@/assets/cat-nakshi.jpg";
import type { HeroCarouselConfig, HeroSlideConfig, SectionItem } from "@/types/cms";

interface Slide {
  image: string;
  eyebrow?: string;
  title: string;
  sub?: string;
  cta?: string;
  href: string;
}

const FALLBACK_SLIDES: Slide[] = [
  {
    image: heroBg,
    eyebrow: "New Season · 92.5 Silver",
    title: "Quiet luxury,\nhandcrafted for you.",
    sub: "Sterling silver pieces shaped by artisans in Visakhapatnam.",
    cta: "Shop collection",
    href: "/collections",
  },
  {
    image: bannerBg,
    eyebrow: "Featured · Minimal Gifting",
    title: "Little gestures,\nlasting memories.",
    sub: "Gift-ready pieces, hand-finished and packaged with care.",
    cta: "Explore gifting",
    href: "/collections",
  },
  {
    image: nakshiBg,
    eyebrow: "Heritage · Temple Series",
    title: "Stories cast\nin sterling silver.",
    sub: "Temple-inspired motifs reimagined for the modern wardrobe.",
    cta: "Discover temple",
    href: "/collections/nakshi-mala",
  },
];

function cmsItemToSlide(item: SectionItem): Slide {
  const c = item.config as unknown as HeroSlideConfig;
  return {
    image: c.desktop_image_url || heroBg,
    eyebrow: c.eyebrow,
    title: c.headline || "Hadha Silver",
    sub: c.subheading,
    cta: c.primary_btn_text,
    href: c.primary_btn_url || "/collections",
  };
}

interface HeroProps {
  config?: Partial<HeroCarouselConfig>;
  items?: SectionItem[];
}

export function Hero({ config, items = [] }: HeroProps) {
  const rotationSpeed = config?.rotation_speed ?? 6;
  const autoRotate = config?.auto_rotate ?? true;

  const cmsSlides = items
    .filter((i) => i.is_enabled)
    .sort((a, b) => a.sort_order - b.sort_order)
    .map(cmsItemToSlide);

  const slides = cmsSlides.length > 0 ? cmsSlides : FALLBACK_SLIDES;
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (!autoRotate) return;
    const id = setInterval(() => setIdx((v) => (v + 1) % slides.length), rotationSpeed * 1000);
    return () => clearInterval(id);
  }, [slides.length, rotationSpeed, autoRotate]);

  const s = slides[idx];

  return (
    <section className="relative h-[78vh] min-h-[560px] w-full overflow-hidden">
      {slides.map((sl, i) => (
        <img
          key={i}
          src={sl.image}
          alt={sl.title ?? ""}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-[1200ms] ${i === idx ? "opacity-100" : "opacity-0"}`}
          width={1920}
          height={1080}
          fetchPriority={i === 0 ? "high" : "low"}
        />
      ))}
      <div className="absolute inset-0 bg-gradient-to-r from-background/85 via-background/30 to-transparent" />
      <div className="relative z-10 h-full flex items-center px-6 md:px-16">
        <div className="max-w-xl">
          {s.eyebrow && (
            <p className="text-[11px] tracking-[0.3em] uppercase text-accent mb-5">{s.eyebrow}</p>
          )}
          <h1 className="font-display text-[clamp(2.5rem,6vw,5rem)] leading-[1.05] text-foreground whitespace-pre-line">
            {s.title}
          </h1>
          {s.sub && (
            <p className="mt-5 text-base md:text-lg text-foreground/80 max-w-md">{s.sub}</p>
          )}
          <div className="mt-8 flex items-center gap-4">
            <a
              href={s.href}
              className="group inline-flex items-center gap-3 bg-primary text-primary-foreground px-7 py-3.5 text-xs tracking-[0.22em] uppercase hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              {s.cta || "Shop now"}
              <ArrowRight className="size-4 group-hover:translate-x-1 transition-transform" />
            </a>
            <a
              href="/about"
              className="text-xs tracking-[0.22em] uppercase border-b border-foreground/60 pb-0.5 hover:border-accent hover:text-accent transition"
            >
              Our story
            </a>
          </div>
        </div>
      </div>

      <div className="absolute bottom-8 right-6 md:right-12 z-10 flex items-center gap-2">
        <button
          onClick={() => setIdx((v) => (v - 1 + slides.length) % slides.length)}
          className="size-10 border border-foreground/40 hover:bg-primary hover:text-primary-foreground transition flex items-center justify-center"
          aria-label="Previous"
        >
          <ChevronLeft className="size-4" />
        </button>
        <button
          onClick={() => setIdx((v) => (v + 1) % slides.length)}
          className="size-10 border border-foreground/40 hover:bg-primary hover:text-primary-foreground transition flex items-center justify-center"
          aria-label="Next"
        >
          <ChevronRight className="size-4" />
        </button>
      </div>

      <div className="absolute bottom-12 left-6 md:left-16 z-10 flex items-center gap-3 text-xs tracking-[0.2em] text-foreground/70">
        <span>{String(idx + 1).padStart(2, "0")}</span>
        <span className="w-16 h-px bg-foreground/30 relative overflow-hidden">
          <span
            className="absolute inset-y-0 left-0 bg-accent transition-all duration-500"
            style={{ width: `${((idx + 1) / slides.length) * 100}%` }}
          />
        </span>
        <span>{String(slides.length).padStart(2, "0")}</span>
      </div>
    </section>
  );
}
