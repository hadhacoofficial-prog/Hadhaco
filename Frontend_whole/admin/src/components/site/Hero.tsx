import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import heroBg from "@/assets/hero.jpg";
import bannerBg from "@/assets/banner.jpg";
import nakshiBg from "@/assets/cat-nakshi.jpg";
import type { HeroCarouselConfig, HeroSlideConfig, SectionItem } from "@/types/cms";
import { migrateSlideConfig, migrateSectionConfig, resolveSlide } from "@/types/cms";

const FALLBACK_SLIDES: HeroSlideConfig[] = [
  {
    media: { desktop_image_url: heroBg },
    content: {
      eyebrow: "New Season · 92.5 Silver",
      headline: "Quiet luxury,\nhandcrafted for you.",
      subheading: "Sterling silver pieces shaped by artisans in Visakhapatnam.",
      primary_btn_text: "Shop collection",
      primary_btn_url: "/collections",
      secondary_btn_text: "Our story",
      secondary_btn_url: "/about",
    },
    typography: {},
    colors: {},
    layout: { preset: "classic-left" },
    buttons: {},
  },
  {
    media: { desktop_image_url: bannerBg },
    content: {
      eyebrow: "Featured · Minimal Gifting",
      headline: "Little gestures,\nlasting memories.",
      subheading: "Gift-ready pieces, hand-finished and packaged with care.",
      primary_btn_text: "Explore gifting",
      primary_btn_url: "/collections",
    },
    typography: {},
    colors: {},
    layout: { preset: "classic-left" },
    buttons: {},
  },
  {
    media: { desktop_image_url: nakshiBg },
    content: {
      eyebrow: "Heritage · Temple Series",
      headline: "Stories cast\nin sterling silver.",
      subheading: "Temple-inspired motifs reimagined for the modern wardrobe.",
      primary_btn_text: "Discover temple",
      primary_btn_url: "/collections/nakshi-mala",
    },
    typography: {},
    colors: {},
    layout: { preset: "classic-left" },
    buttons: {},
  },
];

function parseSlideItems(items: SectionItem[]): HeroSlideConfig[] {
  const enabled = items.filter((i) => i.is_enabled).sort((a, b) => a.sort_order - b.sort_order);
  if (enabled.length === 0) return [];
  return enabled.map((item) => migrateSlideConfig(item.config as Record<string, unknown>));
}

interface HeroProps {
  config?: Partial<HeroCarouselConfig>;
  items?: SectionItem[];
  activeSlideIndex?: number | null;
}

export function Hero({ config: rawConfig, items = [], activeSlideIndex }: HeroProps) {
  const sectionConfig = useMemo(
    () => migrateSectionConfig((rawConfig ?? {}) as Record<string, unknown>),
    [rawConfig],
  );

  const rawSlides = useMemo(() => parseSlideItems(items), [items]);
  const slideConfigs = useMemo(
    () => (rawSlides.length > 0 ? rawSlides : FALLBACK_SLIDES),
    [rawSlides],
  );

  const resolved = useMemo(() => slideConfigs.map(resolveSlide), [slideConfigs]);

  const autoRotate = sectionConfig.auto_rotate ?? true;
  const rotationSpeed = sectionConfig.rotation_speed ?? 6;

  const [idx, setIdx] = useState(0);
  const [shouldAnimate, setShouldAnimate] = useState(true);

  // Lock to actively edited slide; resume autoplay when editing stops
  useEffect(() => {
    if (activeSlideIndex != null && slideConfigs.length > 0) {
      const clamped = Math.min(Math.max(activeSlideIndex, 0), slideConfigs.length - 1);
      setIdx(clamped);
      setShouldAnimate(false);
      return;
    }
    setShouldAnimate(true);
  }, [activeSlideIndex, slideConfigs.length]);

  useEffect(() => {
    if (!autoRotate || slideConfigs.length <= 1 || !shouldAnimate) return;
    const id = setInterval(
      () => setIdx((v) => (v + 1) % slideConfigs.length),
      rotationSpeed * 1000,
    );
    return () => clearInterval(id);
  }, [slideConfigs.length, rotationSpeed, autoRotate, shouldAnimate]);

  const slide = resolved[idx];
  if (!slide) return null;

  return (
    <section className="relative h-[78vh] min-h-[560px] w-full overflow-hidden">
      {/* Backgrounds */}
      {resolved.map((s, i) => (
        <img
          key={i}
          src={s.media.desktopUrl || heroBg}
          alt={s.content.seoAlt || s.content.headline}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-[1200ms] ${i === idx ? "opacity-100" : "opacity-0"}`}
          width={1920}
          height={1080}
          fetchPriority={i === 0 ? "high" : "low"}
        />
      ))}

      {/* Overlay */}
      <div
        className="absolute inset-0 z-[1] pointer-events-none"
        style={{
          background: slide.colors.gradient
            ? `linear-gradient(to ${slide.colors.gradientDirection}, ${slide.colors.overlayColor}, transparent)`
            : slide.colors.overlayColor,
          opacity: slide.colors.overlayOpacity,
        }}
      />

      {/* Content */}
      <div
        className={`relative z-10 h-full ${slide.layout.containerClass} ${slide.layout.padding}`}
        style={{ textShadow: slide.typography.textShadow }}
      >
        <div
          className={`${slide.layout.maxWidth} flex flex-col ${slide.layout.contentClass} gap-4 py-12`}
        >
          {slide.content.eyebrow && (
            <p
              className="text-[11px] tracking-[0.3em] uppercase mb-1"
              style={{ color: slide.colors.eyebrow }}
            >
              {slide.content.eyebrow}
            </p>
          )}
          <h1
            className="whitespace-pre-line leading-[1.05]"
            style={{
              fontFamily: slide.typography.headlineFont,
              fontSize: slide.typography.headlineSize,
              fontWeight: slide.typography.headlineWeight,
              color: slide.colors.text,
            }}
          >
            {slide.content.headline}
          </h1>
          {slide.content.subheading && (
            <p
              className="max-w-md"
              style={{
                fontSize: slide.typography.descriptionSize,
                color: slide.colors.text,
                opacity: 0.8,
              }}
            >
              {slide.content.subheading}
            </p>
          )}
          <div className="mt-4 flex items-center gap-4 flex-wrap">
            {slide.content.primaryBtnText && (
              <a
                href={slide.content.primaryBtnUrl}
                className={slide.buttons.primary.className}
                style={slide.buttons.primary.style}
              >
                {slide.content.primaryBtnText}
                <ArrowRight className="size-4" />
              </a>
            )}
            {slide.buttons.hasSecondary && slide.content.secondaryBtnText && (
              <a
                href={slide.content.secondaryBtnUrl}
                className={slide.buttons.secondary.className}
                style={slide.buttons.secondary.style}
              >
                {slide.content.secondaryBtnText}
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Arrows */}
      {slideConfigs.length > 1 && (
        <div className="absolute bottom-8 right-6 md:right-12 z-20 flex items-center gap-2">
          <button
            onClick={() => setIdx((v) => (v - 1 + slideConfigs.length) % slideConfigs.length)}
            className="size-10 border border-white/40 hover:bg-white/20 text-white transition flex items-center justify-center backdrop-blur-sm"
            aria-label="Previous"
          >
            <ChevronLeft className="size-4" />
          </button>
          <button
            onClick={() => setIdx((v) => (v + 1) % slideConfigs.length)}
            className="size-10 border border-white/40 hover:bg-white/20 text-white transition flex items-center justify-center backdrop-blur-sm"
            aria-label="Next"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
      )}

      {/* Counter */}
      {slideConfigs.length > 1 && (
        <div className="absolute bottom-12 left-6 md:left-16 z-20 flex items-center gap-3 text-xs tracking-[0.2em] text-white/70">
          <span>{String(idx + 1).padStart(2, "0")}</span>
          <span className="w-16 h-px bg-white/30 relative overflow-hidden">
            <span
              className="absolute inset-y-0 left-0 bg-white transition-all duration-500"
              style={{ width: `${((idx + 1) / slideConfigs.length) * 100}%` }}
            />
          </span>
          <span>{String(slideConfigs.length).padStart(2, "0")}</span>
        </div>
      )}
    </section>
  );
}
