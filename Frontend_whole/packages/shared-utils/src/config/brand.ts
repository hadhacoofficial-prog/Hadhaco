/**
 * Hadha Silver Jewellery — single source of truth for brand identity.
 * Consume this everywhere instead of hardcoding strings.
 */
export const BRAND = {
  name: "Hadha Silver Jewellery",
  shortName: "Hadha",
  legalName: "Popula Dabba's Hadha",
  tagline: "92.5 Silver Jewellery",
  description:
    "Premium 92.5 Silver Jewellery for Women, Men, Kids, Gifts and Accessories. Handcrafted with South Indian heritage.",
  domain: "hadha.co",
  url: "https://hadha.co",
  email: "hello@hadha.co",
  phone: "+91 98765 43210",
  whatsappNumber: "919876543210",
  address: {
    line1: "MVP Sector 1, MVP Colony",
    city: "Visakhapatnam",
    state: "Andhra Pradesh",
    pincode: "530017",
    country: "India",
  },
  social: {
    instagram: "https://instagram.com/hadha",
    youtube: "https://youtube.com/@hadha",
    facebook: "https://facebook.com/hadha",
  },
  themeColor: "#A8C8E8",
} as const;

export type Brand = typeof BRAND;
