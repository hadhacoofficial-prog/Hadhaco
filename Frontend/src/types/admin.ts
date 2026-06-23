// ── Admin dashboard ──────────────────────────────────────────────────────────
export interface KPIStats {
  today_orders: number;
  today_revenue: number;
  new_customers_today: number;
  pending_orders: number;
  open_support_tickets: number;
  unresolved_fraud_signals: number;
  low_stock_products: number;
}

// ── Categories ───────────────────────────────────────────────────────────────
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

export interface CategoryAdminListItem {
  id: string;
  parent_id: string | null;
  name: string;
  slug: string;
  image_url: string | null;
  sort_order: number;
  is_active: boolean;
  product_count: number;
  children_count: number;
  updated_at: string;
}

export interface CategoryAdminListResponse {
  items: CategoryAdminListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CategoryDetail {
  id: string;
  parent_id: string | null;
  name: string;
  slug: string;
  description: string | null;
  image_url: string | null;
  sort_order: number;
  is_active: boolean;
  seo_title: string | null;
  seo_description: string | null;
  product_count: number;
  children_count: number;
  created_at: string;
  updated_at: string;
}

export interface CategoryProductItem {
  id: string;
  sku: string;
  name: string;
  slug: string;
  base_price: number;
  stock_quantity: number;
  status: string;
  is_featured: boolean;
  primary_image: string | null;
}

export interface CategoryProductsResponse {
  items: CategoryProductItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
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
}

export interface CollectionListItem {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  image_url: string | null;
  is_active: boolean;
  is_featured: boolean;
  sort_order: number;
  product_count: number;
  updated_at: string;
}

export interface CollectionListResponse {
  items: CollectionListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CollectionDetail {
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
  product_count: number;
  created_at: string;
  updated_at: string;
}

export interface CollectionProductItem {
  id: string;
  sku: string;
  name: string;
  slug: string;
  category_id: string | null;
  base_price: number;
  stock_quantity: number;
  status: string;
  is_featured: boolean;
  primary_image: string | null;
  sort_order: number;
}

export interface CollectionProductsResponse {
  items: CollectionProductItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── Products (admin) ─────────────────────────────────────────────────────────
export interface ProductCollectionRef {
  id: string;
  name: string;
  slug: string;
}

export interface ProductListItem {
  id: string;
  sku: string;
  name: string;
  slug: string;
  short_description: string | null;
  category_id: string | null;
  metal_type: string | null;
  base_price: number;
  compare_at_price: number | null;
  stock_quantity: number;
  available_stock?: number;
  status: string;
  is_featured: boolean;
  is_new_arrival: boolean;
  is_best_seller: boolean;
  created_at: string;
  primary_image: string | null;
  collections: ProductCollectionRef[];
}

export interface ProductListResponse {
  items: ProductListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export type ProductStatus = "draft" | "active" | "archived";

export interface ProductImage {
  id: string;
  url: string;
  thumbnail_url: string | null;
  medium_url: string | null;
  alt_text: string | null;
  is_primary: boolean;
  sort_order: number;
}

export interface ProductVariant {
  id: string;
  sku: string;
  name: string;
  price_adjustment: number;
  stock_quantity: number;
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

export interface ProductDetail {
  id: string;
  sku: string;
  name: string;
  slug: string;
  description: string | null;
  short_description: string | null;
  category_id: string | null;
  metal_type: string | null;
  purity: string | null;
  hallmark_number: string | null;
  weight_grams: number | null;
  making_charges: number | null;
  wastage_percent: number | null;
  gender: string | null;
  base_price: number;
  compare_at_price: number | null;
  cost_price: number | null;
  tax_rate: number;
  hsn_code: string | null;
  track_inventory: boolean;
  allow_backorder: boolean;
  low_stock_threshold: number;
  stock_quantity: number;
  status: ProductStatus;
  is_featured: boolean;
  is_new_arrival: boolean;
  is_best_seller: boolean;
  is_customizable: boolean;
  requires_shipping: boolean;
  length_cm: number | null;
  width_cm: number | null;
  height_cm: number | null;
  meta_title: string | null;
  meta_description: string | null;
  meta_keywords: string | null;
  images: ProductImage[];
  variants: ProductVariant[];
  attributes: ProductAttribute[];
  collections: ProductCollectionRef[];
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

// ── Orders (admin) ───────────────────────────────────────────────────────────
export interface OrderListItem {
  id: string;
  order_number: string;
  status: string;
  payment_status: string;
  total: number;
  item_count: number;
  created_at: string;
}

export interface OrderListResponse {
  items: OrderListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── Coupons (admin) ──────────────────────────────────────────────────────────
export type CouponType = "percentage" | "fixed_amount" | "free_shipping";

export interface CouponDto {
  id: string;
  code: string;
  description: string | null;
  coupon_type: CouponType;
  value: number;
  min_order_amount: number | null;
  max_discount: number | null;
  usage_limit: number | null;
  usage_count: number;
  per_user_limit: number | null;
  is_active: boolean;
  valid_from: string | null;
  valid_until: string | null;
  created_at: string;
}

export interface CreateCouponDto {
  code: string;
  coupon_type: CouponType;
  value: number;
  description?: string | null;
  min_order_amount?: number | null;
  max_discount?: number | null;
  usage_limit?: number | null;
  per_user_limit?: number | null;
  valid_from?: string | null;
  valid_until?: string | null;
}

// ── Reviews (admin) ──────────────────────────────────────────────────────────
export interface ReviewImageDto {
  id: string;
  url: string;
  sort_order: number;
}

export interface ReviewDto {
  id: string;
  product_id: string;
  user_id: string;
  order_id: string | null;
  rating: number;
  title: string | null;
  body: string | null;
  is_verified_purchase: boolean;
  is_approved: boolean;
  helpful_count: number;
  created_at: string;
  images: ReviewImageDto[];
}

export type ReviewAction = "approve" | "reject" | "flag";

// ── CMS sections (admin) ─────────────────────────────────────────────────────
export interface LandingSectionDto {
  id: string;
  section_key: string;
  title: string | null;
  subtitle: string | null;
  config: Record<string, unknown>;
  is_active: boolean;
  sort_order: number;
}

// ── Users / customers (admin) ────────────────────────────────────────────────
export interface AdminUserDto {
  id: string;
  email: string;
  full_name: string | null;
  phone: string | null;
  avatar_url: string | null;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface AdminUserListResponse {
  items: AdminUserDto[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── Inventory (admin) ────────────────────────────────────────────────────────
export interface LowStockItem {
  id: string;
  sku: string;
  name: string;
  stock_quantity: number;
  low_stock_threshold: number;
  status: string;
  category_id: string | null;
}

// ── Analytics dashboard ──────────────────────────────────────────────────────
export interface RevenueByDay {
  date: string;
  total: number;
}

export interface TopProduct {
  product_id: string;
  product_name: string;
  total_quantity: number;
  total_revenue: number;
}

export interface AnalyticsDashboard {
  revenue: { total?: number; growth_percent?: number } & Record<string, unknown>;
  orders: { total?: number; growth_percent?: number } & Record<string, unknown>;
  aov: { value?: number; growth_percent?: number } & Record<string, unknown>;
  conversion_rate: number;
  top_products: TopProduct[];
  revenue_by_day: RevenueByDay[];
  orders_by_status: Record<string, number>;
}
