// Backend DTO types for authenticated customer endpoints.

// ── Addresses ─────────────────────────────────────────────────────────────────
export interface AddressResponse {
  id: string;
  user_id: string;
  type: "shipping" | "billing";
  full_name: string;
  phone: string | null;
  line1: string;
  line2: string | null;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface AddressCreateRequest {
  type: "shipping" | "billing";
  full_name: string;
  phone?: string | null;
  line1: string;
  line2?: string | null;
  city: string;
  state: string;
  postal_code: string;
  country?: string;
  is_default?: boolean;
}

// ── Wishlist ──────────────────────────────────────────────────────────────────
export interface WishlistItemResponse {
  id: string;
  product_id: string;
  variant_id: string | null;
  added_at: string;
}

export interface WishlistResponse {
  id: string;
  items: WishlistItemResponse[];
  total: number;
}

// ── Cart ──────────────────────────────────────────────────────────────────────
export interface CartItemResponse {
  id: string;
  product_id: string;
  variant_id: string | null;
  quantity: number;
  unit_price: number;
  line_total: number;
}

export interface CartSummary {
  id: string;
  items: CartItemResponse[];
  item_count: number;
  subtotal: number;
  tax_amount: number;
  discount: number;
  total: number;
  coupon_code: string | null;
  expires_at: string;
}

// ── Orders ────────────────────────────────────────────────────────────────────
export interface OrderListItem {
  id: string;
  order_number: string;
  status: string;
  payment_status: string;
  fulfillment_status: string;
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

export interface OrderItemResponse {
  id: string;
  product_id: string;
  product_name: string;
  product_sku: string;
  variant_name: string | null;
  image_url: string | null;
  unit_price: number;
  quantity: number;
  line_total: number;
}

export interface OrderResponse {
  id: string;
  order_number: string;
  user_id: string;
  status: string;
  payment_status: string;
  fulfillment_status: string;
  subtotal: number;
  tax_amount: number;
  shipping_charge: number;
  discount: number;
  total: number;
  coupon_code: string | null;
  payment_method: string;
  razorpay_order_id: string | null;
  tracking_number: string | null;
  shipping_provider: string | null;
  dispatched_at: string | null;
  estimated_delivery: string | null;
  cancellation_reason: string | null;
  created_at: string;
  items: OrderItemResponse[];
}

export interface CreateOrderRequest {
  shipping_address_id: string;
  billing_address_id?: string;
  payment_method?: "razorpay" | "cod";
  coupon_code?: string;
  notes?: string;
}

// ── Razorpay checkout ─────────────────────────────────────────────────────────
export interface CreatePaymentIntentRequest {
  shipping_address_id: string;
  billing_address_id?: string;
  coupon_code?: string;
  notes?: string;
}

export interface CreatePaymentIntentResponse {
  order_id: string;
  razorpay_order_id: string;
  amount: number; // paise
  currency: string;
  key: string;
}

export interface VerifyPaymentRequest {
  order_id: string;
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

export interface VerifyPaymentResponse {
  success: boolean;
  order_id: string;
  order_number: string;
}

// ── Coupons ───────────────────────────────────────────────────────────────────
export interface CouponValidateResponse {
  valid: boolean;
  discount_amount: number;
  message: string;
  coupon: {
    id: string;
    code: string;
    coupon_type: string;
    value: number;
    min_order_amount: number | null;
  } | null;
}
