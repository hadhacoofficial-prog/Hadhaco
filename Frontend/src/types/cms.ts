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

export interface HeroCarouselConfig {
  auto_rotate: boolean;
  rotation_speed: number;
}

export interface HeroSlideConfig {
  desktop_image_url: string;
  tablet_image_url?: string;
  mobile_image_url?: string;
  video_url?: string;
  video_poster_url?: string;
  eyebrow?: string;
  headline: string;
  subheading?: string;
  primary_btn_text?: string;
  primary_btn_url?: string;
  secondary_btn_text?: string;
  secondary_btn_url?: string;
  alignment?: "left" | "center" | "right";
  overlay?: boolean;
  overlay_opacity?: number;
  seo_alt?: string;
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
  columns?: Array<{ title: string; links: Array<{ label: string; url: string }> }>;
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
