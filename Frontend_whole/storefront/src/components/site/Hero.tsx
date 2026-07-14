import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import type { HeroCarouselConfig, HeroSlideConfig, SectionItem } from "@/types/cms";
import {
  resolveSlide,
  migrateSlideConfig,
  migrateSectionConfig,
  resolveHeight,
  resolveTransition,
} from "@/types/cms";
import type { ResolvedSlide } from "@/types/cms";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { useBreakpoint } from "@/hooks/useBreakpoint";

// ── Fallback slides ───────────────────────────────────────────────────────────

const FALLBACK_SLIDES: HeroSlideConfig[] = [
  {
    media: { desktop_image_url: "" },
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
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseSlideItems(items: SectionItem[]): HeroSlideConfig[] {
  const enabled = items.filter((i) => i.is_enabled).sort((a, b) => a.sort_order - b.sort_order);
  if (enabled.length === 0) return [];
  return enabled.map((item) => migrateSlideConfig(item.config as Record<string, unknown>));
}

// ── Component ─────────────────────────────────────────────────────────────────

interface HeroProps {
  config?: Partial<HeroCarouselConfig>;
  items?: SectionItem[];
  /** When set, locks to this slide index and pauses autoplay (admin preview). */
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

  const prefersReduced = useReducedMotion();
  const breakpoint = useBreakpoint();
  const heightPreset = sectionConfig.height ?? "large";

  const autoRotate = sectionConfig.auto_rotate ?? true;
  const rotationSpeed = sectionConfig.rotation_speed ?? 6;
  const transitionStyle = sectionConfig.transition ?? "fade";
  const transitionSpeed = sectionConfig.transition_duration ?? "normal";
  const pauseOnHover = sectionConfig.pause_on_hover ?? false;

  const [activeIdx, setActiveIdx] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // When activeSlideIndex is provided (admin preview), lock to that slide and pause autoplay
  const isEditing = activeSlideIndex != null;
  useEffect(() => {
    if (isEditing && activeSlideIndex != null && activeSlideIndex !== activeIdx) {
      setIsTransitioning(true);
      setActiveIdx(activeSlideIndex);
      setTimeout(() => setIsTransitioning(false), transition.durationMs);
    }
  }, [isEditing, activeSlideIndex]);

  const { height, minHeightClass } = useMemo(
    () => resolveHeight(heightPreset, breakpoint),
    [heightPreset, breakpoint],
  );

  const transition = useMemo(
    () => resolveTransition(transitionStyle, transitionSpeed),
    [transitionStyle, transitionSpeed],
  );

  const shouldAnimate =
    autoRotate && !isPaused && !prefersReduced && slideConfigs.length > 1 && !isEditing;

  // ── Navigation ────────────────────────────────────────────────────────────

  const goTo = useCallback(
    (idx: number) => {
      if (isTransitioning) return;
      setIsTransitioning(true);
      setActiveIdx(idx);
      setTimeout(() => setIsTransitioning(false), transition.durationMs);
    },
    [isTransitioning, transition.durationMs],
  );

  const goNext = useCallback(() => {
    goTo((activeIdx + 1) % slideConfigs.length);
  }, [activeIdx, slideConfigs.length, goTo]);

  const goPrev = useCallback(() => {
    goTo((activeIdx - 1 + slideConfigs.length) % slideConfigs.length);
  }, [activeIdx, slideConfigs.length, goTo]);

  // ── Auto-rotate ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (!shouldAnimate) return;
    const id = setInterval(goNext, rotationSpeed * 1000);
    return () => clearInterval(id);
  }, [shouldAnimate, rotationSpeed, goNext]);

  // ── Keyboard navigation ───────────────────────────────────────────────────

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        goPrev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        goNext();
      } else if (e.key === " ") {
        e.preventDefault();
        setIsPaused((p) => !p);
      }
    },
    [goNext, goPrev],
  );

  // ── Render ────────────────────────────────────────────────────────────────

  const slide = resolved[activeIdx];

  return (
    <section
      ref={containerRef}
      className={`relative w-full overflow-hidden ${minHeightClass}`}
      style={{ height }}
      role="region"
      aria-roledescription="carousel"
      aria-label="Hero banner"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onMouseEnter={() => pauseOnHover && setIsPaused(true)}
      onMouseLeave={() => pauseOnHover && setIsPaused(false)}
    >
      {/* ── Slide backgrounds ── */}
      {resolved.map((s, i) => {
        const isActive = i === activeIdx;
        const isVisible = transitionStyle === "slide" ? Math.abs(i - activeIdx) <= 1 : isActive;

        return (
          <SlideBackground
            key={i}
            slide={s}
            isActive={isActive}
            isVisible={isVisible}
            transition={transition}
            isPreload={i === 0}
          />
        );
      })}

      {/* ── Overlay ── */}
      <div
        className="absolute inset-0 z-[1] pointer-events-none"
        style={{
          background: slide.colors.gradient
            ? `linear-gradient(to ${slide.colors.gradientDirection}, ${slide.colors.overlayColor}, transparent)`
            : slide.colors.overlayColor,
          opacity: slide.colors.overlayOpacity,
        }}
      />

      {/* ── Content ── */}
      <div
        className={`relative z-10 h-full ${slide.layout.containerClass} ${slide.layout.padding}`}
        style={{ textShadow: slide.typography.textShadow }}
      >
        <div
          className={`${slide.layout.maxWidth} flex flex-col ${slide.layout.contentClass} gap-4 py-12`}
        >
          {/* Eyebrow */}
          {slide.content.eyebrow && (
            <p
              className="text-[11px] tracking-[0.3em] uppercase mb-1"
              style={{ color: slide.colors.eyebrow }}
            >
              {slide.content.eyebrow}
            </p>
          )}

          {/* Headline */}
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

          {/* Subheading */}
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

          {/* Buttons */}
          <div className="mt-4 flex items-center gap-4 flex-wrap">
            {slide.content.primaryBtnText && (
              <a
                href={slide.content.primaryBtnUrl}
                className={slide.buttons.primary.className}
                style={slide.buttons.primary.style}
              >
                {slide.content.primaryBtnText}
                <ArrowRight className="size-4 group-hover:translate-x-1 transition-transform" />
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

      {/* ── Navigation arrows ── */}
      {slideConfigs.length > 1 && (
        <div className="absolute bottom-8 right-6 md:right-12 z-20 flex items-center gap-2">
          <button
            onClick={goPrev}
            className="size-10 border border-white/40 hover:bg-white/20 text-white transition flex items-center justify-center backdrop-blur-sm"
            aria-label="Previous slide"
          >
            <ChevronLeft className="size-4" />
          </button>
          <button
            onClick={goNext}
            className="size-10 border border-white/40 hover:bg-white/20 text-white transition flex items-center justify-center backdrop-blur-sm"
            aria-label="Next slide"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
      )}

      {/* ── Slide counter & progress ── */}
      {slideConfigs.length > 1 && (
        <div className="absolute bottom-12 left-6 md:left-16 z-20 flex items-center gap-3 text-xs tracking-[0.2em] text-white/70">
          <span>{String(activeIdx + 1).padStart(2, "0")}</span>
          <span className="w-16 h-px bg-white/30 relative overflow-hidden">
            <span
              className="absolute inset-y-0 left-0 bg-white transition-all duration-500"
              style={{ width: `${((activeIdx + 1) / slideConfigs.length) * 100}%` }}
            />
          </span>
          <span>{String(slideConfigs.length).padStart(2, "0")}</span>
        </div>
      )}

      {/* ── Pause/Play toggle ── */}
      {shouldAnimate && (
        <button
          onClick={() => setIsPaused((p) => !p)}
          className="absolute bottom-8 left-6 md:left-12 z-20 size-8 border border-white/30 hover:bg-white/20 text-white/70 hover:text-white transition flex items-center justify-center backdrop-blur-sm rounded-full"
          aria-label={isPaused ? "Resume autoplay" : "Pause autoplay"}
        >
          {isPaused ? <Play className="size-3 ml-0.5" /> : <Pause className="size-3" />}
        </button>
      )}
    </section>
  );
}

// ── Slide Background (memoized) ───────────────────────────────────────────────

interface SlideBackgroundProps {
  slide: ResolvedSlide;
  isActive: boolean;
  isVisible: boolean;
  transition: { durationMs: number; property: string; easing: string };
  isPreload: boolean;
}

const SlideBackground = memo(function SlideBackground({
  slide,
  isActive,
  isVisible,
  transition,
  isPreload,
}: SlideBackgroundProps) {
  if (!isVisible) return null;

  const durationMs = transition.durationMs;
  const easing = transition.easing;

  if (slide.media.hasVideo) {
    return (
      <video
        className="absolute inset-0 w-full h-full object-cover"
        src={slide.media.videoUrl}
        poster={slide.media.videoPosterUrl || undefined}
        autoPlay
        muted
        loop
        playsInline
        style={{
          opacity: isActive ? 1 : 0,
          transition: `opacity ${durationMs}ms ${easing}`,
        }}
      />
    );
  }

  return (
    <picture>
      {slide.media.mobileUrl && (
        <source media="(max-width: 639px)" srcSet={slide.media.mobileUrl} />
      )}
      {slide.media.tabletUrl && (
        <source media="(max-width: 1023px)" srcSet={slide.media.tabletUrl} />
      )}
      <img
        src={slide.media.desktopUrl}
        alt={slide.content.seoAlt}
        className="absolute inset-0 w-full h-full object-cover"
        style={{
          opacity: isActive ? 1 : 0,
          transition: `opacity ${durationMs}ms ${easing}`,
        }}
        fetchPriority={isPreload ? "high" : "low"}
        loading={isPreload ? "eager" : "lazy"}
        width={1920}
        height={1080}
      />
    </picture>
  );
});
