import type { ProductListItem } from "@/types/admin";
import type { ProductDetail, CollectionDto, PublicReview } from "@/types/public";
import type { Product, Collection, Review, Gender } from "@/types/shop";

export function toProduct(p: ProductListItem): Product {
  return {
    id: p.id,
    slug: p.slug,
    sku: p.sku,
    name: p.name,
    image: p.primary_image ?? "",
    price: p.base_price,
    compareAt: p.compare_at_price ?? undefined,
    inStock: p.stock_quantity > 0,
    isNew: p.is_new_arrival,
    isBestseller: p.is_best_seller,
    collectionIds: [],
    gender: "unisex",
    shortDescription: p.short_description ?? undefined,
    badge: p.is_new_arrival ? "New" : p.is_best_seller ? "Bestseller" : undefined,
  };
}

const VALID_GENDERS = new Set<string>(["women", "men", "kids", "unisex"]);
function parseGender(raw: string | null): Gender {
  return raw && VALID_GENDERS.has(raw) ? (raw as Gender) : "unisex";
}

export function toProductDetail(p: ProductDetail): Product {
  const primary = p.images.find((i) => i.is_primary) ?? p.images[0];
  return {
    id: p.id,
    slug: p.slug,
    sku: p.sku,
    name: p.name,
    image: primary?.url ?? "",
    altImage: p.images[1]?.url,
    gallery: p.images.length > 0 ? p.images.map((i) => i.url) : undefined,
    price: p.base_price,
    compareAt: p.compare_at_price ?? undefined,
    inStock: p.stock_quantity > 0,
    isNew: p.is_new_arrival,
    isBestseller: p.is_best_seller,
    collectionIds: [],
    gender: parseGender(p.gender),
    shortDescription: p.short_description ?? undefined,
    description: p.description ?? undefined,
    badge: p.is_new_arrival ? "New" : p.is_best_seller ? "Bestseller" : undefined,
    specifications:
      p.attributes.length > 0
        ? p.attributes.map((a) => ({ label: a.name, value: a.value }))
        : undefined,
    attributes: {
      metal: p.metal_type ?? undefined,
      purity: p.purity ?? undefined,
      weight: p.weight_grams != null ? `${p.weight_grams}g` : undefined,
    },
    variants: p.variants
      .filter((v) => v.is_active)
      .sort((a, b) => a.sort_order - b.sort_order),
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
    name: r.title ?? (r.is_verified_purchase ? "Verified Buyer" : "Customer"),
    text: r.body ?? "",
    rating: r.rating,
    createdAt: r.created_at,
  };
}
