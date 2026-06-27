import type { ProductImage, ProductVariant, ProductAttribute } from "./public";

// ── Company config ───────────────────────────────────────────────────────────
export interface CompanyConfig {
  name: string;
  tagline: string | null;
  gstin: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string;
  phone: string | null;
  support_email: string | null;
  website: string | null;
  logo_url: string | null;
  instagram_url: string | null;
  facebook_url: string | null;
}

export type CompanyConfigUpdate = Partial<CompanyConfig>;

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
  secondary_image: string | null;
  average_rating: number | null;
  review_count: number;
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
  available_stock?: number;
  reserved_quantity?: number;
  sold_quantity?: number;
  max_order_quantity?: number;
  average_rating?: number | null;
  review_count?: number;
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
  fulfillment_status: string;
  total: number;
  item_count: number;
  complimentary_gift: string | null;
  created_at: string;
}

export interface OrderListResponse {
  items: OrderListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OrderItem {
  id: string;
  product_id: string | null;
  product_name: string;
  product_sku: string;
  variant_id: string | null;
  variant_name: string | null;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  tax_amount: number;
  line_total: number;
}

export interface OrderResponse {
  id: string;
  order_number: string;
  user_id: string;
  status: string;
  payment_status: string;
  fulfillment_status: string;
  shipping_full_name: string;
  shipping_phone: string | null;
  shipping_alternate_phone: string | null;
  shipping_line1: string;
  shipping_line2: string | null;
  shipping_landmark: string | null;
  shipping_city: string;
  shipping_state: string;
  shipping_postal: string;
  shipping_country: string;
  billing_full_name: string | null;
  billing_phone: string | null;
  billing_alternate_phone: string | null;
  billing_line1: string | null;
  billing_line2: string | null;
  billing_landmark: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_postal: string | null;
  billing_country: string | null;
  subtotal: number;
  tax_amount: number;
  shipping_charge: number;
  discount: number;
  total: number;
  coupon_code: string | null;
  payment_method: string | null;
  razorpay_order_id: string | null;
  razorpay_payment_id: string | null;
  shipping_provider: string | null;
  tracking_number: string | null;
  estimated_delivery: string | null;
  dispatched_at: string | null;
  packed_at: string | null;
  shipping_label_generated_at: string | null;
  shipment_notes: string | null;
  fulfilled_by: string | null;
  last_fulfillment_action: string | null;
  complimentary_gift: string | null;
  notes: string | null;
  cancellation_reason: string | null;
  cancelled_at: string | null;
  delivered_at: string | null;
  items: OrderItem[];
  created_at: string;
  updated_at: string;
}

// ── Coupons (admin) ──────────────────────────────────────────────────────────
export type CouponType = "percentage" | "fixed_amount" | "free_shipping";
export type CouponStatus = "active" | "inactive" | "draft";

export interface CouponDto {
  id: string;
  code: string;
  description: string | null;
  coupon_type: CouponType;
  value: number;
  status: CouponStatus;
  is_active: boolean;
  valid_from: string | null;
  valid_until: string | null;
  // Order value
  min_order_amount: number;
  max_order_amount: number | null;
  max_discount: number | null;
  // Usage limits
  usage_limit: number | null;
  usage_count: number;
  per_user_limit: number;
  one_time_per_customer: boolean;
  // Customer eligibility
  first_order_only: boolean;
  new_customer_only: boolean;
  returning_customer_only: boolean;
  // Product / category restrictions
  eligible_product_ids: string[] | null;
  eligible_collection_ids: string[] | null;
  eligible_category_slugs: string[] | null;
  excluded_product_ids: string[] | null;
  excluded_category_slugs: string[] | null;
  // Audience
  allowed_emails: string[] | null;
  allowed_phone_numbers: string[] | null;
  customer_groups: string[] | null;
  // Region
  allowed_states: string[] | null;
  allowed_cities: string[] | null;
  allowed_pincodes: string[] | null;
  // Methods
  allowed_payment_methods: string[] | null;
  allowed_shipping_methods: string[] | null;
  // Campaign & stacking
  stackable: boolean;
  campaign_name: string | null;
  created_at: string;
}

export interface CreateCouponDto {
  code: string;
  coupon_type: CouponType;
  value: number;
  description?: string | null;
  status?: CouponStatus;
  valid_from?: string | null;
  valid_until?: string | null;
  min_order_amount?: number | null;
  max_order_amount?: number | null;
  max_discount?: number | null;
  usage_limit?: number | null;
  per_user_limit?: number | null;
  one_time_per_customer?: boolean;
  first_order_only?: boolean;
  new_customer_only?: boolean;
  returning_customer_only?: boolean;
  eligible_product_ids?: string[] | null;
  eligible_collection_ids?: string[] | null;
  eligible_category_slugs?: string[] | null;
  excluded_product_ids?: string[] | null;
  excluded_category_slugs?: string[] | null;
  allowed_emails?: string[] | null;
  allowed_phone_numbers?: string[] | null;
  customer_groups?: string[] | null;
  allowed_states?: string[] | null;
  allowed_cities?: string[] | null;
  allowed_pincodes?: string[] | null;
  allowed_payment_methods?: string[] | null;
  allowed_shipping_methods?: string[] | null;
  stackable?: boolean;
  campaign_name?: string | null;
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
  product_name?: string | null;
  user_id: string;
  order_id: string | null;
  customer_name: string | null;
  rating: number;
  title: string | null;
  body: string | null;
  is_verified_purchase: boolean;
  is_approved: boolean;
  is_rejected: boolean;
  is_flagged: boolean;
  helpful_count: number;
  approved_at: string | null;
  approved_by: string | null;
  created_at: string;
  images: ReviewImageDto[];
}

export type ReviewAction = "approve" | "reject" | "flag" | "delete";

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
