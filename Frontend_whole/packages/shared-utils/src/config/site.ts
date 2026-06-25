/** Commerce-wide site configuration. Tweak here, propagated everywhere. */
export const SITE = {
  currency: "INR",
  currencySymbol: "₹",
  freeShippingThreshold: 1499,
  defaultShippingFee: 99,
  taxRate: 0, // GST handled at invoice level
  defaultPageSize: 12,
  coupons: {
    HADHA10: { type: "percent", value: 10, description: "Flat 10% off" },
  },
  features: {
    razorpay: false,
    googleLogin: false,
    courierTracking: false,
    instagramFeed: false,
    cmsHomepage: false,
  },
} as const;

export type Site = typeof SITE;
