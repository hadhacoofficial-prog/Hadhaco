// Backend DTO types for PUBLIC (non-admin) API endpoints.
// Mappers in src/lib/api/mappers.ts convert these to the frontend shop types.

// ── Products ─────────────────────────────────────────────────────────────────
export interface ProductImage {
  id: string;
  url: string;
  thumbnail_url: string | null;
  medium_url: string | null;
  large_url: string | null;
  alt_text: string | null;
  is_primary: boolean;
  sort_order: number;
  crop_x: number | null;
  crop_y: number | null;
  crop_width: number | null;
  crop_height: number | null;
  crop_zoom: number | null;
  crop_rotation: number | null;
  updated_at: string;
}

export interface ProductVariant {
  id: string;
  sku: string;
  name: string;
  price_adjustment: number;
  stock_quantity: number;
  available_stock?: number;
  weight_grams: number | null;
  is_active: boolean;
  sort_order: number;
}

export interface ProductAttribute {
  id: string;
  name: string;
  value: string;
  sort_order: number;
}

// ── Collections ───────────────────────────────────────────────────────────────
export interface CollectionDto {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  image_url: string | null;
  is_active: boolean;
  is_featured: boolean;
  sort_order: number;
  seo_title: string | null;
  seo_description: string | null;
  starts_at: string | null;
  ends_at: string | null;
  created_at: string;
  updated_at: string;
}

// ── Categories ────────────────────────────────────────────────────────────────
export interface CategoryTreeNode {
  id: string;
  parent_id: string | null;
  name: string;
  slug: string;
  image_url: string | null;
  sort_order: number;
  product_count: number;
  children: CategoryTreeNode[];
}

/** Response shape from GET /categories/navbar */
export interface NavbarCategoriesResponse {
  women: CategoryTreeNode[];
  men: CategoryTreeNode[];
  unisex: CategoryTreeNode[];
  kids: CategoryTreeNode[];
}

/** Lean category item from GET /categories/navigation */
export interface NavCategoryItem {
  id: string;
  name: string;
  slug: string;
  image_url: string | null;
}

/** Top-level gender category metadata (Women / Men / Unisex / Kids) */
export interface GenderMeta {
  id: string;
  name: string;
  slug: string;
  image_url: string | null;
  sort_order: number;
}

/** Response shape from GET /categories/navigation */
export interface NavigationCategoriesResponse {
  women: NavCategoryItem[];
  men: NavCategoryItem[];
  unisex: NavCategoryItem[];
  kids: NavCategoryItem[];
  /** Top-level gender category metadata keyed by gender key */
  gender_meta: Record<string, GenderMeta>;
}

// ── Reviews ───────────────────────────────────────────────────────────────────
export interface PublicReview {
  id: string;
  product_id: string;
  user_id: string;
  order_id: string | null;
  customer_name: string | null;
  rating: number;
  title: string | null;
  body: string | null;
  is_verified_purchase: boolean;
  is_approved: boolean;
  is_rejected: boolean;
  helpful_count: number;
  approved_at: string | null;
  created_at: string;
  images: { id: string; url: string; sort_order: number }[];
}

export interface ReviewSummary {
  product_id: string;
  review_count: number;
  average_rating: number;
  five_star: number;
  four_star: number;
  three_star: number;
  two_star: number;
  one_star: number;
}

// ── Search ────────────────────────────────────────────────────────────────────
export interface SearchProduct {
  id: string;
  name: string;
  slug: string;
  base_price: number;
  compare_at_price: number | null;
  stock_quantity: number;
  available_stock?: number;
  metal_type: string | null;
  is_featured: boolean;
  rank?: number;
}

export interface SearchResponse {
  items: SearchProduct[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AutocompleteResponse {
  suggestions: string[];
}

export interface TrendingSearchItem {
  query: string;
  count: number;
}

export interface TrendingResponse {
  result: TrendingSearchItem[];
}

// ── CMS (public) ──────────────────────────────────────────────────────────────
export interface BannerDto {
  id: string;
  name: string;
  banner_type: string;
  title: string | null;
  subtitle: string | null;
  cta_text: string | null;
  cta_url: string | null;
  desktop_image_url: string | null;
  mobile_image_url: string | null;
  sort_order: number;
}

export interface HomePageData {
  hero_banners: BannerDto[];
  promo_strip: BannerDto | null;
  sections: {
    id: string;
    section_key: string;
    title: string | null;
    subtitle: string | null;
    config: Record<string, unknown>;
    is_active: boolean;
    sort_order: number;
  }[];
}
