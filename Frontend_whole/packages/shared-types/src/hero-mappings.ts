/**
 * Hero Carousel – Semantic-to-Style Mapping Utilities
 *
 * All semantic tokens stored in the database are resolved to CSS values
 * through this single file. Changing design decisions requires updates
 * here only — components consume these mappings blindly.
 */
import type {
  HeroButtonStyle,
  HeroDescriptionSize,
  HeroFontFamily,
  HeroFontSize,
  HeroFontWeight,
  HeroHeightPreset,
  HeroLayoutPreset,
  HeroPaletteName,
  HeroSlideButtons,
  HeroSlideColors,
  HeroSlideConfig,
  HeroSlideLayout,
  HeroSlideMedia,
  HeroSlideTypography,
  HeroTransition,
  HeroTransitionSpeed,
  HeroCarouselConfig,
} from "./cms";
import type { ImageBundle } from "./media";

// ─────────────────────────────────────────────────────────────────────────────
// Color Palette – derives from project design tokens via CSS variables
// ─────────────────────────────────────────────────────────────────────────────

export interface PaletteEntry {
  label: string;
  value: string;
  swatch: string;
}

export const HERO_PALETTE: Record<HeroPaletteName, PaletteEntry> = {
  navy: { label: "Navy", value: "var(--primary)", swatch: "#1B2F4A" },
  gold: { label: "Gold", value: "var(--accent)", swatch: "#C89B3C" },
  white: { label: "White", value: "#FFFFFF", swatch: "#FFFFFF" },
  dark: { label: "Dark", value: "var(--foreground)", swatch: "#0F2340" },
  silver: { label: "Silver", value: "var(--secondary)", swatch: "#D4D7DC" },
  custom: { label: "Custom", value: "", swatch: "" },
};

export function resolvePaletteColor(
  name?: HeroPaletteName,
  custom?: string,
): string {
  if (!name) return HERO_PALETTE.navy.value;
  if (name === "custom" && custom) return custom;
  return HERO_PALETTE[name]?.value ?? HERO_PALETTE.navy.value;
}

// ─────────────────────────────────────────────────────────────────────────────
// Typography Mappings
// ─────────────────────────────────────────────────────────────────────────────

const FONT_FAMILY_MAP: Record<HeroFontFamily, string> = {
  display: 'var(--font-serif-display, "Cinzel", "Cormorant Garamond", serif)',
  serif: 'var(--font-serif-body, "Cormorant Garamond", serif)',
  sans: 'var(--font-sans, "Inter", system-ui, sans-serif)',
};

const HEADLINE_SIZE_MAP: Record<HeroFontSize, string> = {
  small: "clamp(1.25rem, 2vw, 1.5rem)",
  medium: "clamp(1.5rem, 3vw, 2rem)",
  large: "clamp(1.75rem, 4vw, 2.5rem)",
  xl: "clamp(2rem, 5vw, 3.5rem)",
  hero: "clamp(2.5rem, 6vw, 5rem)",
};

const HEADLINE_WEIGHT_MAP: Record<HeroFontWeight, number> = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
};

const DESCRIPTION_SIZE_MAP: Record<HeroDescriptionSize, string> = {
  small: "0.875rem",
  medium: "1rem",
  large: "1.125rem",
};

export interface ResolvedTypography {
  headlineFont: string;
  headlineSize: string;
  headlineWeight: number;
  descriptionSize: string;
  textShadow: string;
}

export function resolveTypography(
  typography?: HeroSlideTypography,
): ResolvedTypography {
  return {
    headlineFont: FONT_FAMILY_MAP[typography?.headline_font ?? "display"],
    headlineSize: HEADLINE_SIZE_MAP[typography?.headline_size ?? "hero"],
    headlineWeight:
      HEADLINE_WEIGHT_MAP[typography?.headline_weight ?? "semibold"],
    descriptionSize:
      DESCRIPTION_SIZE_MAP[typography?.description_size ?? "medium"],
    textShadow:
      typography?.text_shadow === false
        ? "none"
        : "0 2px 16px rgba(0,0,0,0.35)",
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Layout Presets
// ─────────────────────────────────────────────────────────────────────────────

export interface ResolvedLayout {
  containerClass: string;
  contentClass: string;
  alignText: string;
  alignItems: string;
  justifyContent: string;
  maxWidth: string;
  padding: string;
}

const LAYOUT_PRESET_MAP: Record<
  HeroLayoutPreset,
  Omit<ResolvedLayout, "padding">
> = {
  "classic-left": {
    containerClass: "flex items-center",
    contentClass: "flex flex-col items-start text-left",
    alignText: "text-left",
    alignItems: "items-start",
    justifyContent: "justify-start",
    maxWidth: "max-w-xl",
  },
  "centered-luxury": {
    containerClass: "flex items-center",
    contentClass: "flex flex-col items-center text-center mx-auto",
    alignText: "text-center",
    alignItems: "items-center",
    justifyContent: "justify-center",
    maxWidth: "max-w-lg",
  },
  editorial: {
    containerClass: "flex items-end",
    contentClass: "flex flex-col items-start text-left",
    alignText: "text-left",
    alignItems: "items-start",
    justifyContent: "justify-start",
    maxWidth: "max-w-2xl",
  },
  minimal: {
    containerClass: "flex items-start",
    contentClass: "flex flex-col items-center text-center mx-auto",
    alignText: "text-center",
    alignItems: "items-center",
    justifyContent: "justify-center",
    maxWidth: "max-w-lg",
  },
  "image-focused": {
    containerClass: "flex items-end",
    contentClass: "flex flex-col items-center text-center mx-auto",
    alignText: "text-center",
    alignItems: "items-center",
    justifyContent: "justify-center",
    maxWidth: "max-w-2xl",
  },
  split: {
    containerClass: "flex items-center",
    contentClass: "flex flex-col items-end text-right",
    alignText: "text-right",
    alignItems: "items-end",
    justifyContent: "justify-end",
    maxWidth: "max-w-xl",
  },
};

const PADDING_MAP: Record<string, string> = {
  compact: "px-4 md:px-8",
  standard: "px-6 md:px-16",
  generous: "px-8 md:px-20 lg:px-24",
};

export function resolveLayout(layout?: HeroSlideLayout): ResolvedLayout {
  const preset = layout?.preset ?? "classic-left";
  const base = LAYOUT_PRESET_MAP[preset];

  const advanced = layout?.advanced;
  if (advanced) {
    let justifyContent = base.justifyContent;
    if (advanced.alignment === "center") justifyContent = "justify-center";
    else if (advanced.alignment === "right") justifyContent = "justify-end";
    else justifyContent = "justify-start";

    let alignItems = base.alignItems;
    if (advanced.alignment === "center") alignItems = "items-center";
    else if (advanced.alignment === "right") alignItems = "items-end";
    else alignItems = "items-start";

    const containerClass =
      advanced.vertical === "top"
        ? "flex items-start"
        : advanced.vertical === "bottom"
          ? "flex items-end"
          : "flex items-center";

    const maxWidth =
      advanced.content_width === "wide" ? "max-w-2xl" : "max-w-xl";

    return {
      ...base,
      containerClass,
      alignItems,
      justifyContent,
      maxWidth,
      padding:
        PADDING_MAP[advanced.padding ?? "standard"] ?? PADDING_MAP.standard,
    };
  }

  return {
    ...base,
    padding: PADDING_MAP.standard,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Height Mappings
// ─────────────────────────────────────────────────────────────────────────────

interface HeightValues {
  desktop: string;
  tablet: string;
  mobile: string;
  minHeight: string;
}

const HEIGHT_MAP: Record<HeroHeightPreset, HeightValues> = {
  compact: {
    desktop: "50vh",
    tablet: "45vh",
    mobile: "50vh",
    minHeight: "min-h-[400px]",
  },
  medium: {
    desktop: "70vh",
    tablet: "60vh",
    mobile: "65vh",
    minHeight: "min-h-[350px]",
  },
  large: {
    desktop: "78vh",
    tablet: "70vh",
    mobile: "75vh",
    minHeight: "min-h-[560px]",
  },
  fullscreen: {
    desktop: "100vh",
    tablet: "100vh",
    mobile: "100vh",
    minHeight: "min-h-[600px]",
  },
};

export function resolveHeight(
  preset?: HeroHeightPreset,
  breakpoint: "desktop" | "tablet" | "mobile" = "desktop",
): { height: string; minHeightClass: string } {
  const h = HEIGHT_MAP[preset ?? "large"];
  return {
    height: h[breakpoint] ?? h.desktop,
    minHeightClass: h.minHeight,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Transition Mappings
// ─────────────────────────────────────────────────────────────────────────────

interface TransitionValues {
  durationMs: number;
  property: string;
  easing: string;
}

const TRANSITION_SPEED_MAP: Record<HeroTransitionSpeed, number> = {
  fast: 600,
  normal: 1200,
  slow: 2000,
};

export function resolveTransition(
  style?: HeroTransition,
  speed?: HeroTransitionSpeed,
): TransitionValues {
  const durationMs = TRANSITION_SPEED_MAP[speed ?? "normal"];
  if (style === "slide") {
    return {
      durationMs: Math.round(durationMs * 0.5),
      property: "transform",
      easing: "cubic-bezier(0.25, 0.1, 0.25, 1)",
    };
  }
  return {
    durationMs,
    property: "opacity",
    easing: "ease-in-out",
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Button Style Mappings
// ─────────────────────────────────────────────────────────────────────────────

interface ResolvedButton {
  className: string;
  style: React.CSSProperties;
}

const BUTTON_BASE =
  "inline-flex items-center gap-3 px-7 py-3.5 text-xs tracking-[0.22em] uppercase transition-colors";

const BUTTON_STYLE_MAP: Record<HeroButtonStyle, string> = {
  filled: `${BUTTON_BASE} text-primary-foreground`,
  outline: `${BUTTON_BASE} border border-current bg-transparent`,
  ghost: `${BUTTON_BASE} bg-transparent hover:underline`,
  text: `${BUTTON_BASE} bg-transparent border-b border-current rounded-none px-0 pb-0.5`,
};

export function resolveButton(
  style?: HeroButtonStyle,
  color?: HeroPaletteName,
  colorCustom?: string,
): ResolvedButton {
  const btnStyle = style ?? "filled";
  const resolved = BUTTON_STYLE_MAP[btnStyle];
  const cssColor = resolvePaletteColor(color, colorCustom);

  if (btnStyle === "filled") {
    return {
      className: resolved,
      style: {
        backgroundColor: cssColor,
        color:
          cssColor === "#FFFFFF" || cssColor === "var(--secondary)"
            ? "var(--foreground)"
            : "var(--primary-foreground)",
      },
    };
  }

  return {
    className: resolved,
    style: { color: cssColor },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Media Helpers
// ─────────────────────────────────────────────────────────────────────────────

export function resolveImageUrl(
  media?: HeroSlideMedia,
  breakpoint: "desktop" | "tablet" | "mobile" = "desktop",
): string {
  if (!media) return "";
  if (breakpoint === "tablet" && media.tablet_image_url)
    return media.tablet_image_url;
  if (breakpoint === "mobile" && media.mobile_image_url)
    return media.mobile_image_url;
  return media.desktop_image_url;
}

export function hasVideoBackground(media?: HeroSlideMedia): boolean {
  return Boolean(media?.video_url);
}

// ─────────────────────────────────────────────────────────────────────────────
// Full Slide Resolution
// ─────────────────────────────────────────────────────────────────────────────

export interface ResolvedSlide {
  media: {
    desktopUrl: string;
    tabletUrl: string;
    mobileUrl: string;
    videoUrl: string;
    videoPosterUrl: string;
    hasVideo: boolean;
    /** Present once this slide has been through the Universal Responsive
     * Image System — takes priority over desktopUrl/tabletUrl/mobileUrl,
     * since those legacy fields may still carry stale values that were
     * simply hidden (not cleared) by the old "auto-adjust" UI. */
    imageBundle?: ImageBundle;
  };
  content: {
    eyebrow: string;
    headline: string;
    subheading: string;
    primaryBtnText: string;
    primaryBtnUrl: string;
    secondaryBtnText: string;
    secondaryBtnUrl: string;
    seoAlt: string;
  };
  typography: ResolvedTypography;
  colors: {
    text: string;
    eyebrow: string;
    background: string;
    overlayColor: string;
    overlayOpacity: number;
    gradient: boolean;
    gradientDirection: string;
  };
  layout: ResolvedLayout;
  buttons: {
    primary: ResolvedButton;
    secondary: ResolvedButton;
    hasSecondary: boolean;
  };
}

export function resolveSlide(slide: HeroSlideConfig): ResolvedSlide {
  const media = slide.media ?? {};
  const content = slide.content ?? {};
  const colors = slide.colors ?? {};
  const layout = slide.layout ?? {};
  const buttons = slide.buttons ?? {};

  return {
    media: {
      desktopUrl: media.desktop_image_url ?? "",
      tabletUrl: media.tablet_image_url ?? "",
      mobileUrl: media.mobile_image_url ?? "",
      videoUrl: media.video_url ?? "",
      videoPosterUrl: media.video_poster_url ?? "",
      hasVideo: hasVideoBackground(media),
      imageBundle: media.image_bundle,
    },
    content: {
      eyebrow: content.eyebrow ?? "",
      headline: content.headline ?? "",
      subheading: content.subheading ?? "",
      primaryBtnText: content.primary_btn_text ?? "",
      primaryBtnUrl: content.primary_btn_url ?? "/collections",
      secondaryBtnText: content.secondary_btn_text ?? "",
      secondaryBtnUrl: content.secondary_btn_url ?? "",
      seoAlt: content.seo_alt ?? "",
    },
    typography: resolveTypography(slide.typography),
    colors: {
      text: resolvePaletteColor(colors.text, colors.text_custom),
      eyebrow: resolvePaletteColor(colors.eyebrow, colors.eyebrow_custom),
      background: resolvePaletteColor(
        colors.background,
        colors.background_custom,
      ),
      overlayColor: resolvePaletteColor(
        colors.overlay_color,
        colors.overlay_color_custom,
      ),
      overlayOpacity: colors.overlay_opacity ?? 0.5,
      gradient: colors.gradient ?? false,
      gradientDirection: colors.gradient_direction ?? "right",
    },
    layout: resolveLayout(layout),
    buttons: {
      primary: resolveButton(
        buttons.primary_style,
        buttons.primary_color,
        buttons.primary_color_custom,
      ),
      secondary: resolveButton(
        buttons.secondary_style ?? "outline",
        buttons.secondary_color,
        buttons.secondary_color_custom,
      ),
      hasSecondary: Boolean(content.secondary_btn_text),
    },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Backward Compatibility – Legacy Config Migration
// ─────────────────────────────────────────────────────────────────────────────

/** Detects if a slide config is in the old flat format */
function isLegacySlideConfig(config: Record<string, unknown>): boolean {
  return "headline" in config || "desktop_image_url" in config;
}

/** Detects if a section-level config is in the old format */
function isLegacySectionConfig(config: Record<string, unknown>): boolean {
  return !("transition" in config) && !("height" in config);
}

function legacyAlignmentToPreset(alignment?: string): HeroLayoutPreset {
  if (alignment === "center") return "centered-luxury";
  if (alignment === "right") return "split";
  return "classic-left";
}

/**
 * Migrate a legacy flat HeroSlideConfig to the new grouped format.
 * Returns the new config if legacy, or the original if already new format.
 */
export function migrateSlideConfig(
  config: Record<string, unknown>,
): HeroSlideConfig {
  if (!isLegacySlideConfig(config)) {
    return config as unknown as HeroSlideConfig;
  }
  const c = config;
  return {
    media: {
      desktop_image_url: (c.desktop_image_url as string) ?? "",
      tablet_image_url: (c.tablet_image_url as string) || undefined,
      mobile_image_url: (c.mobile_image_url as string) || undefined,
      video_url: (c.video_url as string) || undefined,
      video_poster_url: (c.video_poster_url as string) || undefined,
    },
    content: {
      eyebrow: (c.eyebrow as string) || undefined,
      headline: (c.headline as string) ?? "",
      subheading: (c.subheading as string) || undefined,
      primary_btn_text: (c.primary_btn_text as string) || undefined,
      primary_btn_url: (c.primary_btn_url as string) || undefined,
      secondary_btn_text: (c.secondary_btn_text as string) || undefined,
      secondary_btn_url: (c.secondary_btn_url as string) || undefined,
      seo_alt: (c.seo_alt as string) || undefined,
    },
    typography: {},
    colors: {
      overlay_opacity:
        typeof c.overlay_opacity === "number" ? c.overlay_opacity : undefined,
    },
    layout: {
      preset: legacyAlignmentToPreset(c.alignment as string),
    },
    buttons: {},
  };
}

/**
 * Migrate a legacy section-level HeroCarouselConfig to the new format.
 */
export function migrateSectionConfig(
  config: Record<string, unknown>,
): HeroCarouselConfig {
  if (!isLegacySectionConfig(config)) {
    return config as unknown as HeroCarouselConfig;
  }
  return {
    auto_rotate: (config.auto_rotate as boolean) ?? true,
    rotation_speed: (config.rotation_speed as number) ?? 6,
    auto_adjust: true,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Validation
// ─────────────────────────────────────────────────────────────────────────────

import type {
  HeroValidationResult,
  HeroValidationError,
  HeroValidationWarning,
} from "./cms";

export function validateHeroConfig(
  items: HeroSlideConfig[],
  sectionConfig: HeroCarouselConfig,
): HeroValidationResult {
  const errors: HeroValidationError[] = [];
  const warnings: HeroValidationWarning[] = [];

  if (items.length === 0) {
    errors.push({
      type: "error",
      field: "slides",
      message: "At least one slide is required.",
    });
    return { errors, warnings };
  }

  const primaryUrls: string[] = [];

  items.forEach((slide, i) => {
    const hasImage = Boolean(
      slide.media?.desktop_image_url || slide.media?.image_bundle,
    );
    const hasVideo = Boolean(slide.media?.video_url);

    if (!slide.content?.headline) {
      errors.push({
        type: "error",
        field: "content.headline",
        message: `Slide ${i + 1}: Headline is required.`,
        slideIndex: i,
      });
    }

    if (!hasImage && !hasVideo) {
      errors.push({
        type: "error",
        field: "media",
        message: `Slide ${i + 1}: An image or video is required.`,
        slideIndex: i,
      });
    }

    if (slide.content?.primary_btn_text && !slide.content?.primary_btn_url) {
      errors.push({
        type: "error",
        field: "content.primary_btn_url",
        message: `Slide ${i + 1}: Primary button URL is required when button text is provided.`,
        slideIndex: i,
      });
    }

    if (slide.content?.primary_btn_url && !slide.content?.primary_btn_text) {
      errors.push({
        type: "error",
        field: "content.primary_btn_text",
        message: `Slide ${i + 1}: Primary button text is required when URL is provided.`,
        slideIndex: i,
      });
    }

    if (
      slide.content?.secondary_btn_text &&
      !slide.content?.secondary_btn_url
    ) {
      errors.push({
        type: "error",
        field: "content.secondary_btn_url",
        message: `Slide ${i + 1}: Secondary button URL is required when button text is provided.`,
        slideIndex: i,
      });
    }

    if (slide.content?.primary_btn_url) {
      primaryUrls.push(slide.content.primary_btn_url);
    }

    if (!slide.content?.seo_alt) {
      warnings.push({
        type: "warning",
        field: "content.seo_alt",
        message: `Slide ${i + 1}: Missing SEO alt text.`,
        slideIndex: i,
      });
    }

    if (
      slide.media?.desktop_image_url &&
      !slide.media?.mobile_image_url &&
      !slide.media?.image_bundle
    ) {
      warnings.push({
        type: "warning",
        field: "media.mobile_image_url",
        message: `Slide ${i + 1}: No mobile image set. Desktop image will be used.`,
        slideIndex: i,
      });
    }

    if (slide.media?.video_url && !slide.media?.video_poster_url) {
      warnings.push({
        type: "warning",
        field: "media.video_poster_url",
        message: `Slide ${i + 1}: Video has no poster image.`,
        slideIndex: i,
      });
    }
  });

  // Check for duplicate CTA URLs across slides
  if (primaryUrls.length > 1) {
    const seen = new Set<string>();
    primaryUrls.forEach((url) => {
      if (seen.has(url)) {
        warnings.push({
          type: "warning",
          field: "content.primary_btn_url",
          message: `Duplicate CTA URL detected: "${url}"`,
        });
      }
      seen.add(url);
    });
  }

  return { errors, warnings };
}
