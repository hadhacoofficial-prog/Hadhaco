import type { ImageBundle } from "./media";

// ── Section types ──────────────────────────────────────────────────────────────

export type SectionType =
  | "announcement_bar"
  | "hero_carousel"
  | "navbar"
  | "category_grid"
  | "collection_showcase"
  | "product_grid"
  | "video_section"
  | "image_banner"
  | "content_block"
  | "testimonials"
  | "instagram_gallery"
  | "newsletter"
  | "footer"
  | "custom";

// ── Public homepage API ────────────────────────────────────────────────────────

export interface LayoutSection {
  section_key: string;
  section_type: SectionType;
  sort_order: number;
  is_active: boolean;
  title: string | null;
}

export interface SectionItem {
  id: string;
  section_id: string;
  sort_order: number;
  is_enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SectionData {
  config: Record<string, unknown>;
  items: SectionItem[];
}

export interface HomepageData {
  cache_version: number;
  layout: LayoutSection[];
  sections: Record<string, SectionData>;
}

// ── Admin section data ─────────────────────────────────────────────────────────

export type SectionStatus = "published" | "draft" | "scheduled";

export interface AdminSection {
  id: string;
  section_key: string;
  section_type: SectionType;
  title: string | null;
  subtitle: string | null;
  config: Record<string, unknown>;
  draft_config: Record<string, unknown>;
  is_active: boolean;
  sort_order: number;
  status: SectionStatus;
  published_at: string | null;
  scheduled_at: string | null;
  version_number: number;
  items: SectionItem[];
  created_at: string;
  updated_at: string;
}

export interface ReorderEntry {
  id: string;
  sort_order: number;
}

export interface VersionHistoryEntry {
  id: string;
  section_id: string;
  version_number: number;
  config_snapshot: Record<string, unknown>;
  items_snapshot: SectionItem[];
  change_summary: string | null;
  created_at: string;
}

// ── Hero Carousel – Semantic Types ─────────────────────────────────────────────

export type HeroPaletteName =
  | "navy"
  | "gold"
  | "white"
  | "dark"
  | "silver"
  | "custom";

export type HeroFontFamily = "display" | "serif" | "sans";

export type HeroFontSize = "small" | "medium" | "large" | "xl" | "hero";

export type HeroFontWeight = "regular" | "medium" | "semibold" | "bold";

export type HeroDescriptionSize = "small" | "medium" | "large";

export type HeroLayoutPreset =
  | "classic-left"
  | "centered-luxury"
  | "editorial"
  | "minimal"
  | "image-focused"
  | "split";

export type HeroHeightPreset = "compact" | "medium" | "large" | "fullscreen";

export type HeroButtonStyle = "filled" | "outline" | "ghost" | "text";

export type HeroTransition = "fade" | "slide";

export type HeroTransitionSpeed = "fast" | "normal" | "slow";

export interface HeroSlideMedia {
  desktop_image_url: string;
  tablet_image_url?: string;
  mobile_image_url?: string;
  /** Set once the desktop image goes through the Universal Responsive Image
   * System instead of the legacy plain-upload `desktop_image_url` above.
   * Desktop and mobile are independent uploads/crops — see
   * resolveSlide()/hero-mappings.ts. */
  desktop_image_bundle?: ImageBundle;
  /** Same as `desktop_image_bundle`, for the mobile frame — independent
   * upload/crop, not derived from the desktop image. */
  mobile_image_bundle?: ImageBundle;
  video_url?: string;
  video_poster_url?: string;
}

export interface HeroSlideContent {
  eyebrow?: string;
  headline: string;
  subheading?: string;
  primary_btn_text?: string;
  primary_btn_url?: string;
  secondary_btn_text?: string;
  secondary_btn_url?: string;
  seo_alt?: string;
}

export interface HeroSlideTypography {
  headline_font?: HeroFontFamily;
  headline_size?: HeroFontSize;
  headline_weight?: HeroFontWeight;
  description_size?: HeroDescriptionSize;
  text_shadow?: boolean;
}

export interface HeroSlideColors {
  text?: HeroPaletteName;
  text_custom?: string;
  eyebrow?: HeroPaletteName;
  eyebrow_custom?: string;
  background?: HeroPaletteName;
  background_custom?: string;
  overlay_color?: HeroPaletteName;
  overlay_color_custom?: string;
  overlay_opacity?: number;
  gradient?: boolean;
  gradient_direction?: "left" | "right";
}

export interface HeroSlideButtons {
  primary_style?: HeroButtonStyle;
  primary_color?: HeroPaletteName;
  primary_color_custom?: string;
  secondary_style?: HeroButtonStyle;
  secondary_color?: HeroPaletteName;
  secondary_color_custom?: string;
}

export interface HeroSlideLayout {
  preset?: HeroLayoutPreset;
  advanced?: {
    alignment?: "left" | "center" | "right";
    vertical?: "top" | "center" | "bottom";
    content_width?: "narrow" | "wide";
    padding?: "compact" | "standard" | "generous";
  };
}

export interface HeroSlideConfig {
  media: HeroSlideMedia;
  content: HeroSlideContent;
  typography: HeroSlideTypography;
  colors: HeroSlideColors;
  layout: HeroSlideLayout;
  buttons: HeroSlideButtons;
}

export interface HeroCarouselConfig {
  auto_rotate: boolean;
  rotation_speed: number;
  transition?: HeroTransition;
  transition_duration?: HeroTransitionSpeed;
  height?: HeroHeightPreset;
  pause_on_hover?: boolean;
  auto_adjust?: boolean;
}

// ── Config shapes per section type ────────────────────────────────────────────

export interface AnnouncementConfig {
  rotation_speed: number;
  show_close: boolean;
}

export interface AnnouncementItemConfig {
  text: string;
  bg_color?: string;
  text_color?: string;
  link?: string;
  link_text?: string;
}

export interface ProductGridConfig {
  title: string;
  eyebrow?: string;
  source: "featured" | "newest" | "best_seller" | "trending" | "manual";
  max_products: number;
  view_all_url?: string;
  manual_product_ids?: string[];
  filters?: { gender?: string; category_id?: string };
}

export interface VideoSectionConfig {
  eyebrow?: string;
  title?: string;
  subtitle?: string;
  mp4_url?: string;
  webm_url?: string;
  poster_url?: string;
  autoplay: boolean;
  loop: boolean;
  muted: boolean;
  controls: boolean;
  cta_text?: string;
  cta_url?: string;
}

export interface ImageBannerConfig {
  title?: string;
  subtitle?: string;
  desktop_image_url?: string;
  mobile_image_url?: string;
  overlay?: boolean;
  overlay_opacity?: number;
  cta_text?: string;
  cta_url?: string;
}

export interface NewsletterConfig {
  heading: string;
  description: string;
  placeholder: string;
  btn_text: string;
  success_message: string;
  bg_color?: string;
}

export interface InstagramGalleryConfig {
  title: string;
  handle: string;
  max_items: number;
  source?: "api" | "manual" | "collections";
}

export interface FooterConfig {
  copyright_name: string;
  company_address: string;
  phone: string;
  email: string;
  whatsapp?: string;
  instagram?: string;
  youtube?: string;
  facebook?: string;
  description?: string;
  logo_url?: string;
  columns?: Array<{
    title: string;
    links: Array<{ label: string; url: string }>;
  }>;
}

// ── Per-item config shapes ─────────────────────────────────────────────────────

export interface InstagramItemConfig {
  image_url: string;
  link_url?: string;
  alt_text?: string;
}

export interface CollectionCardConfig {
  image_url: string;
  hover_image_url?: string;
  eyebrow?: string;
  title: string;
  subtitle?: string;
  button_text?: string;
  button_url?: string;
}

export interface ReviewItemConfig {
  customer_name: string;
  rating: number;
  text: string;
  photo_url?: string;
  verified?: boolean;
  location?: string;
}

export interface WhyChooseCardConfig {
  icon?: "shield" | "gem" | "sparkles" | "heart";
  title: string;
  text: string;
}

// ── Media library ──────────────────────────────────────────────────────────────

export interface CmsMedia {
  id: string;
  filename: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  width: number | null;
  height: number | null;
  duration: number | null;
  cdn_url: string;
  thumbnail_url: string | null;
  folder: string;
  alt_text: string | null;
  tags: string[];
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface MediaListResponse {
  items: CmsMedia[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface PublishLogEntry {
  id: string;
  action: string;
  section_key: string | null;
  admin_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

// ── Hero validation ────────────────────────────────────────────────────────────

export type HeroValidationError = {
  type: "error";
  field: string;
  message: string;
  slideIndex?: number;
};

export type HeroValidationWarning = {
  type: "warning";
  field: string;
  message: string;
  slideIndex?: number;
};

export type HeroValidationResult = {
  errors: HeroValidationError[];
  warnings: HeroValidationWarning[];
};
