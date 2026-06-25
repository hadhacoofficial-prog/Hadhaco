import type { ProductVariant } from "./public";
export type { ProductVariant };

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
  gallery?: string[];
  price: Money;
  compareAt?: Money;
  badge?: string;
  rating?: number;
  reviewCount?: number;
  collectionIds: string[];
  gender: Gender;
  inStock: boolean;
  availableStock: number;
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

export interface Review {
  id: string;
  productId?: string;
  name: string;
  text: string;
  rating: number;
  createdAt?: string;
}

export type CouponType = "percent" | "flat";

export interface Coupon {
  code: string;
  type: CouponType;
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
