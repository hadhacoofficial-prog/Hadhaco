import type { ProductListItem } from "@/types/admin";
import type { ProductDetail, CollectionDto, PublicReview } from "@/types/public";
import type { Product, Collection, Review, Gender } from "@/types/shop";

export function toProduct(p: ProductListItem): Product {
  const availableStock = p.available_stock ?? p.stock_quantity;
  return {
    id: p.id,
    slug: p.slug,
    sku: p.sku,
    name: p.name,
    image: p.primary_image ?? "",
    altImage: p.secondary_image ?? undefined,
    price: p.base_price,
    compareAt: p.compare_at_price ?? undefined,
    inStock: availableStock > 0,
    availableStock,
    isNew: p.is_new_arrival,
    isBestseller: p.is_best_seller,
    collectionIds: [],
    gender: "unisex",
    shortDescription: p.short_description ?? undefined,
    rating: p.average_rating ?? undefined,
    reviewCount: p.review_count ?? 0,
    badge: p.is_new_arrival ? "New" : p.is_best_seller ? "Bestseller" : undefined,
  };
}

const VALID_GENDERS = new Set<string>(["women", "men", "kids", "unisex"]);
function parseGender(raw: string | null): Gender {
  return raw && VALID_GENDERS.has(raw) ? (raw as Gender) : "unisex";
}

export function toProductDetail(p: ProductDetail): Product {
  const primary = p.images.find((i) => i.is_primary) ?? p.images[0];
  const availableStock = p.available_stock ?? p.stock_quantity;
  // Gallery/main image use the cropped medium size; zoom uses the cropped
  // large size. original.jpg is never exposed to the storefront.
  const mediumOf = (i: (typeof p.images)[number]) => i.medium_url ?? i.url;
  const largeOf = (i: (typeof p.images)[number]) => i.large_url ?? i.medium_url ?? i.url;
  return {
    id: p.id,
    slug: p.slug,
    sku: p.sku,
    name: p.name,
    image: primary ? mediumOf(primary) : "",
    altImage: p.images[1] ? mediumOf(p.images[1]) : undefined,
    gallery: p.images.length > 0 ? p.images.map(mediumOf) : undefined,
    galleryLarge: p.images.length > 0 ? p.images.map(largeOf) : undefined,
    price: p.base_price,
    compareAt: p.compare_at_price ?? undefined,
    inStock: availableStock > 0,
    availableStock,
    maxOrderQty: p.max_order_quantity ?? 0,
    isNew: p.is_new_arrival,
    isBestseller: p.is_best_seller,
    collectionIds: [],
    gender: parseGender(p.gender),
    shortDescription: p.short_description ?? undefined,
    description: p.description ?? undefined,
    rating: p.average_rating ?? undefined,
    reviewCount: p.review_count ?? 0,
    badge: p.is_new_arrival ? "New" : p.is_best_seller ? "Bestseller" : undefined,
    specifications: (() => {
      const specs: { label: string; value: string }[] = [];
      if (p.metal_type) specs.push({ label: "Metal", value: p.metal_type });
      if (p.purity) specs.push({ label: "Purity", value: p.purity });
      if (p.weight_grams != null) specs.push({ label: "Weight", value: `${p.weight_grams}g` });
      for (const a of p.attributes) specs.push({ label: a.name, value: a.value });
      return specs.length > 0 ? specs : undefined;
    })(),
    attributes: {
      metal: p.metal_type ?? undefined,
      purity: p.purity ?? undefined,
      weight: p.weight_grams != null ? `${p.weight_grams}g` : undefined,
    },
    variants: p.variants.filter((v) => v.is_active).sort((a, b) => a.sort_order - b.sort_order),
  };
}

export function toCollection(c: CollectionDto): Collection {
  return {
    id: c.id,
    slug: c.slug,
    name: c.name,
    image: c.image_url ?? "",
    description: c.description ?? undefined,
  };
}

export function toReview(r: PublicReview): Review {
  return {
    id: r.id,
    productId: r.product_id,
    userId: r.user_id,
    name: r.customer_name ?? (r.is_verified_purchase ? "Verified Buyer" : "Customer"),
    text: r.body ?? "",
    rating: r.rating,
    createdAt: r.created_at,
    isVerifiedPurchase: r.is_verified_purchase,
    isApproved: r.is_approved,
    isRejected: r.is_rejected,
    images: r.images,
  };
}
