/**
 * Centralized TanStack Query key registry.
 *
 * Every query/mutation references keys from here â€” never hardcode a key array
 * at a call site. Keys are hierarchical so invalidation can be broad
 * (`queryKeys.products.all`) or precise (`queryKeys.products.detail(slug)`).
 */
import type { QueryParams } from "@hadha/shared-types";

/** Normalizes filter objects so the same filters always produce the same key. */
type Filters = Record<string, unknown> | undefined;

export const queryKeys = {
  auth: {
    session: ["auth", "session"] as const,
    user: ["auth", "user"] as const,
  },

  profile: {
    me: ["profile", "me"] as const,
  },

  products: {
    all: ["products"] as const,
    list: (filters?: Filters) => ["products", "list", filters ?? {}] as const,
    infinite: (filters?: Filters) => ["products", "infinite", filters ?? {}] as const,
    detail: (slug: string) => ["products", "detail", slug] as const,
    byId: (id: string) => ["products", "id", id] as const,
    related: (id: string) => ["products", "related", id] as const,
    stock: (slug: string) => ["products", "stock", slug] as const,
  },

  inventory: {
    cartStock: (slugs: string[]) => ["inventory", "cart-stock", ...slugs.sort()] as const,
  },

  categories: {
    all: ["categories"] as const,
    tree: ["categories", "tree"] as const,
    navbar: ["categories", "navbar"] as const,
    navigation: ["categories", "navigation"] as const,
  },

  collections: {
    all: ["collections"] as const,
    list: ["collections", "list"] as const,
    detail: (slug: string) => ["collections", "detail", slug] as const,
  },

  search: {
    all: ["search"] as const,
    query: (q: string, params?: QueryParams) => ["search", "query", q, params ?? {}] as const,
    autocomplete: (q: string) => ["search", "autocomplete", q] as const,
    trending: ["search", "trending"] as const,
  },

  cart: {
    all: ["cart"] as const,
    detail: ["cart", "detail"] as const,
    count: ["cart", "count"] as const,
  },

  wishlist: {
    all: ["wishlist"] as const,
    detail: ["wishlist", "detail"] as const,
  },

  coupons: {
    all: ["coupons"] as const,
    validate: (code: string, subtotal: number) => ["coupons", "validate", code, subtotal] as const,
  },

  addresses: {
    all: ["addresses"] as const,
  },

  orders: {
    all: ["orders"] as const,
    list: (filters?: Filters) => ["orders", "list", filters ?? {}] as const,
    detail: (id: string) => ["orders", "detail", id] as const,
    payment: (id: string) => ["orders", "payment", id] as const,
    invoice: (id: string) => ["orders", "invoice", id] as const,
    shipment: (id: string) => ["orders", "shipment", id] as const,
  },

  returns: {
    all: ["returns"] as const,
    detail: (id: string) => ["returns", "detail", id] as const,
  },

  shipping: {
    tracking: (awb: string) => ["shipping", "tracking", awb] as const,
    rates: (params?: QueryParams) => ["shipping", "rates", params ?? {}] as const,
  },

  reviews: {
    all: ["reviews"] as const,
    forProduct: (productId: string) => ["reviews", "product", productId] as const,
    summary: (productId: string) => ["reviews", "summary", productId] as const,
  },

  cms: {
    home: ["cms", "home"] as const,
    homepage: ["cms", "homepage"] as const,
    page: (slug: string) => ["cms", "page", slug] as const,
  },

  seo: {
    page: (path: string) => ["seo", "page", path] as const,
  },

  notifications: {
    all: ["notifications"] as const,
    preferences: ["notifications", "preferences"] as const,
  },

  support: {
    tickets: ["support", "tickets"] as const,
    ticket: (id: string) => ["support", "ticket", id] as const,
  },

  analytics: {
    dashboard: ["analytics", "dashboard"] as const,
  },

  // ---- Admin namespace ----
  admin: {
    dashboard: ["admin", "dashboard"] as const,
    auditLogs: (filters?: Filters) => ["admin", "audit-logs", filters ?? {}] as const,
    products: (filters?: Filters) => ["admin", "products", filters ?? {}] as const,
    product: (id: string) => ["admin", "product", id] as const,
    productCollections: (id: string) => ["admin", "product", id, "collections"] as const,
    categories: ["admin", "categories"] as const,
    categoriesList: (filters?: Filters) => ["admin", "categories", "list", filters ?? {}] as const,
    category: (id: string) => ["admin", "category", id] as const,
    categoryProducts: (id: string, filters?: Filters) =>
      ["admin", "category", id, "products", filters ?? {}] as const,
    collections: ["admin", "collections"] as const,
    collectionsList: (filters?: Filters) =>
      ["admin", "collections", "list", filters ?? {}] as const,
    collection: (id: string) => ["admin", "collection", id] as const,
    collectionProducts: (id: string, filters?: Filters) =>
      ["admin", "collection", id, "products", filters ?? {}] as const,
    orders: (filters?: Filters) => ["admin", "orders", filters ?? {}] as const,
    order: (id: string) => ["admin", "order", id] as const,
    fulfillment: {
      timeline: (orderId: string) => ["admin", "fulfillment", "timeline", orderId] as const,
      shippingLabel: (orderId: string) =>
        ["admin", "fulfillment", "shipping-label", orderId] as const,
      packingSlip: (orderId: string) =>
        ["admin", "fulfillment", "packing-slip", orderId] as const,
    },
    inventory: (filters?: Filters) => ["admin", "inventory", filters ?? {}] as const,
    lowStock: ["admin", "inventory", "low-stock"] as const,
    coupons: (filters?: Filters) => ["admin", "coupons", filters ?? {}] as const,
    reviewsPending: ["admin", "reviews", "pending"] as const,
    cms: ["admin", "cms"] as const,
    cmsSections: ["admin", "cms", "sections"] as const,
    cmsSection: (key: string) => ["admin", "cms", "section", key] as const,
    cmsSectionItems: (key: string) => ["admin", "cms", "section", key, "items"] as const,
    cmsSectionVersions: (key: string) => ["admin", "cms", "section", key, "versions"] as const,
    cmsMedia: (params?: Record<string, unknown>) =>
      ["admin", "cms", "media", params ?? {}] as const,
    cmsPublishLog: ["admin", "cms", "publish-log"] as const,
    customers: (filters?: Filters) => ["admin", "customers", filters ?? {}] as const,
    fraud: (filters?: Filters) => ["admin", "fraud", filters ?? {}] as const,
    settings: ["admin", "settings", "flags"] as const,
    notificationLogs: (filters?: Filters) =>
      ["admin", "notifications", "logs", filters ?? {}] as const,
    returns: (filters?: Filters) => ["admin", "returns", filters ?? {}] as const,
    support: (filters?: Filters) => ["admin", "support", filters ?? {}] as const,
  },
} as const;

export type QueryKeys = typeof queryKeys;
