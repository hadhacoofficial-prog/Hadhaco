/**
 * localStorage key registry. Keep existing keys to avoid wiping
 * users' persisted carts/wishlists; add new ones here.
 */
export const STORAGE_KEYS = {
  cart: "hadha-cart",
  wishlist: "hadha-wishlist",
  recentlyViewed: "hadha-recent",
  recentSearch: "hadha-recent-search",
  auth: "hadha-auth",
  addresses: "hadha-addresses",
  orders: "hadha-orders",
  theme: "hadha-theme",
} as const;

export type StorageKey = (typeof STORAGE_KEYS)[keyof typeof STORAGE_KEYS];
