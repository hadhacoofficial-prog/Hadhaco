import { SITE_URL } from "@/lib/seo-routes";
import type { ProductDetail } from "@/types/public";

const BRAND = "Hadha";
const DESCRIPTION_MAX = 160;

type MetaTag = Record<string, string>;
type LinkTag = { rel: string; href: string };
type ScriptTag = { type: string; children: string };

export interface ProductHead {
  meta: MetaTag[];
  links: LinkTag[];
  scripts: ScriptTag[];
}

/** Canonical, query-free product URL — used for rel=canonical, og:url and sharing. */
export function productUrl(slug: string): string {
  return `${SITE_URL}/products/${encodeURIComponent(slug)}`;
}

function absoluteUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  return `${SITE_URL}${url.startsWith("/") ? "" : "/"}${url}`;
}

function truncate(text: string, max: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max - 1);
  const lastSpace = cut.lastIndexOf(" ");
  return `${(lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`;
}

/** JSON-LD is inlined in a <script>; escape `<` so product text can never close the tag. */
function jsonLd(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

export function productDescription(p: ProductDetail): string {
  const source =
    p.meta_description ||
    p.short_description ||
    p.description ||
    `${p.name} — handcrafted 92.5 sterling silver jewellery from ${BRAND}.`;
  return truncate(source, DESCRIPTION_MAX);
}

/**
 * Everything the <head> of a product page needs: title, description, canonical,
 * Open Graph (product), Twitter card, and Product + BreadcrumbList JSON-LD.
 * Pure — derived from the API payload only, so SSR and client agree.
 */
export function buildProductHead(p: ProductDetail): ProductHead {
  const url = productUrl(p.slug);
  const title = p.meta_title || `${p.name} · ${BRAND}`;
  const description = productDescription(p);

  const images = [...p.images]
    .sort((a, b) => Number(b.is_primary) - Number(a.is_primary) || a.sort_order - b.sort_order)
    .map((i) => absoluteUrl(i.large_url ?? i.medium_url ?? i.url));
  const primaryImage = p.images.find((i) => i.is_primary) ?? p.images[0];
  const imageAlt = primaryImage?.alt_text || p.name;

  const activeVariants = p.variants.filter((v) => v.is_active);
  const prices = (activeVariants.length > 0 ? activeVariants : [null]).map(
    (v) => p.base_price + (v?.price_adjustment ?? 0),
  );
  const lowPrice = Math.min(...prices);
  const highPrice = Math.max(...prices);

  const soldOut = p.inventory_status === "OUT_OF_STOCK" || p.can_purchase === false;
  const availability = `https://schema.org/${soldOut ? "OutOfStock" : "InStock"}`;

  const offerBase = {
    "@type": lowPrice === highPrice ? "Offer" : "AggregateOffer",
    priceCurrency: "INR",
    availability,
    itemCondition: "https://schema.org/NewCondition",
    url,
    seller: { "@type": "Organization", name: BRAND },
  };
  const offers =
    lowPrice === highPrice
      ? { ...offerBase, price: lowPrice.toFixed(2) }
      : {
          ...offerBase,
          lowPrice: lowPrice.toFixed(2),
          highPrice: highPrice.toFixed(2),
          offerCount: activeVariants.length,
        };

  const product: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Product",
    "@id": `${url}#product`,
    name: p.name,
    description,
    sku: p.sku,
    url,
    brand: { "@type": "Brand", name: BRAND },
    category: "Jewellery",
    offers,
  };
  if (images.length > 0) product.image = images;
  if (p.metal_type) product.material = p.metal_type;
  if (p.weight_grams != null) {
    product.weight = { "@type": "QuantitativeValue", value: p.weight_grams, unitCode: "GRM" };
  }
  if (p.average_rating && (p.review_count ?? 0) > 0) {
    product.aggregateRating = {
      "@type": "AggregateRating",
      ratingValue: p.average_rating,
      reviewCount: p.review_count,
      bestRating: 5,
      worstRating: 1,
    };
  }

  const breadcrumbs = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: SITE_URL },
      { "@type": "ListItem", position: 2, name: "Collections", item: `${SITE_URL}/collections` },
      { "@type": "ListItem", position: 3, name: p.name, item: url },
    ],
  };

  const meta: MetaTag[] = [
    { title },
    { name: "description", content: description },
    { name: "robots", content: "index,follow,max-image-preview:large" },
    { property: "og:type", content: "product" },
    { property: "og:site_name", content: "Hadha Silver Jewellery" },
    { property: "og:locale", content: "en_IN" },
    { property: "og:url", content: url },
    { property: "og:title", content: title },
    { property: "og:description", content: description },
    { property: "product:price:amount", content: lowPrice.toFixed(2) },
    { property: "product:price:currency", content: "INR" },
    { property: "product:availability", content: soldOut ? "out of stock" : "in stock" },
    { property: "product:brand", content: BRAND },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:title", content: title },
    { name: "twitter:description", content: description },
  ];
  if (p.meta_keywords) meta.push({ name: "keywords", content: p.meta_keywords });
  if (images[0]) {
    meta.push(
      { property: "og:image", content: images[0] },
      { property: "og:image:alt", content: imageAlt },
      { name: "twitter:image", content: images[0] },
      { name: "twitter:image:alt", content: imageAlt },
    );
  }

  return {
    meta,
    links: [{ rel: "canonical", href: url }],
    scripts: [
      { type: "application/ld+json", children: jsonLd(product) },
      { type: "application/ld+json", children: jsonLd(breadcrumbs) },
    ],
  };
}
