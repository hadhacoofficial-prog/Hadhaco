import type { ProductVariant, InventoryStatus } from "./public";
import type { ImageBundle } from "./media";
export type { ProductVariant, InventoryStatus };

export type Money = number; // INR rupees

export interface Collection {
  id: string;
  slug: string;
  name: string;
  image: string;
  description?: string;
  productCount?: number;
}

export type Gender = "women" | "men" | "kids" | "unisex";

export interface ProductSpec {
  label: string;
  value: string;
}

export interface Product {
  id: string;
  slug: string;
  sku: string;
  name: string;
  image: string;
  altImage?: string;
  /** Responsive variant set for `image`, when the API supplied one — lets
   * ProductCard render a real srcset instead of the flat desktop URL
   * (docs audit HP-4/MP-1). Undefined for legacy/incomplete responses. */
  imageBundle?: ImageBundle;
  gallery?: string[];
  /** Same order as `gallery`, but the large (1200x1200) crop — used only for zoom. */
  galleryLarge?: string[];
  price: Money;
  compareAt?: Money;
  badge?: string;
  rating?: number;
  reviewCount?: number;
  collectionIds: string[];
  gender: Gender;
  /** Internal only — quantity-stepper caps, SSE sync, cart validation. Never
   * render as text; use `inventoryStatus` for all customer-facing display. */
  inStock: boolean;
  availableStock: number;
  /** Customer-facing business state — the only inventory signal storefront
   * UI may render. Optional so existing mock/test data that predates this
   * field still type-checks; display components fall back to deriving it
   * from `availableStock` (never render `availableStock` itself). */
  inventoryStatus?: InventoryStatus;
  canPurchase?: boolean;
  maxOrderQty?: number;
  isNew?: boolean;
  isBestseller?: boolean;
  shortDescription?: string;
  description?: string;
  specifications?: ProductSpec[];
  attributes?: { metal?: string; purity?: string; weight?: string; finish?: string };
  variants?: ProductVariant[];
}

export interface CartLine {
  productId: string;
  qty: number;
}

export interface ProductQuery {
  collectionSlug?: string;
  q?: string;
  gender?: Gender | "all";
  inStock?: boolean;
  isNew?: boolean;
  isBestseller?: boolean;
  minPrice?: number;
  maxPrice?: number;
  sort?: "featured" | "price-asc" | "price-desc" | "newest";
  page?: number;
  pageSize?: number;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ReviewImage {
  id: string;
  url: string;
  sort_order: number;
}

export interface Review {
  id: string;
  productId?: string;
  userId?: string;
  name: string;
  text: string;
  rating: number;
  createdAt?: string;
  isVerifiedPurchase?: boolean;
  isApproved?: boolean;
  isRejected?: boolean;
  images?: ReviewImage[];
}

export type CartCouponType = "percent" | "flat";

export interface Coupon {
  code: string;
  type: CartCouponType;
  value: number;
  description?: string;
  minSubtotal?: number;
}

export interface CouponValidation {
  valid: boolean;
  coupon?: Coupon;
  discount: number;
  reason?: string;
}

export interface ActiveReservationItem {
  reservation_number: string;
  product_id: string;
  variant_id: string | null;
  product_name: string;
  variant_name: string | null;
  quantity: number;
  expires_at: string;
}

export interface ActiveReservationResponse {
  items: ActiveReservationItem[];
}
