import { describe, expect, it } from "vitest";
import { buildProductHead, productDescription, productUrl } from "../productSeo";
import type { ProductDetail } from "@/types/public";

const image = (over: Record<string, unknown> = {}) => ({
  id: "i1",
  url: "https://cdn.hadha.co/a.jpg",
  original_url: "https://cdn.hadha.co/a-orig.jpg",
  thumbnail_url: null,
  medium_url: null,
  large_url: "https://cdn.hadha.co/a-large.webp",
  alt_text: "Silver anklet",
  is_primary: true,
  sort_order: 0,
  ...over,
});

const base = (over: Record<string, unknown> = {}) =>
  ({
    id: "p1",
    sku: "HDH-SH-000001",
    name: "Silver Anklet",
    slug: "silver-anklet",
    description: "Long description",
    short_description: "Short description",
    base_price: 1500,
    metal_type: "Silver",
    weight_grams: 12.5,
    meta_title: null,
    meta_description: null,
    meta_keywords: null,
    average_rating: null,
    review_count: 0,
    inventory_status: "IN_STOCK",
    can_purchase: true,
    images: [image()],
    variants: [],
    ...over,
  }) as unknown as ProductDetail;

const ld = (head: ReturnType<typeof buildProductHead>, i: number) =>
  JSON.parse(head.scripts[i].children) as Record<string, unknown>;
const metaOf = (head: ReturnType<typeof buildProductHead>, key: string) =>
  head.meta.find((m) => m.name === key || m.property === key)?.content;

describe("buildProductHead", () => {
  it("emits canonical, OG and Twitter tags from the product", () => {
    const head = buildProductHead(base());
    expect(head.links).toEqual([
      { rel: "canonical", href: "https://hadha.co/products/silver-anklet" },
    ]);
    expect(metaOf(head, "og:type")).toBe("product");
    expect(metaOf(head, "og:url")).toBe("https://hadha.co/products/silver-anklet");
    expect(metaOf(head, "og:image")).toBe("https://cdn.hadha.co/a-large.webp");
    expect(metaOf(head, "twitter:card")).toBe("summary_large_image");
    expect(metaOf(head, "product:price:amount")).toBe("1500.00");
    expect(metaOf(head, "product:availability")).toBe("in stock");
  });

  it("prefers admin meta_title / meta_description over derived values", () => {
    const head = buildProductHead(
      base({ meta_title: "Custom title", meta_description: "Custom description" }),
    );
    expect(head.meta[0]).toEqual({ title: "Custom title" });
    expect(metaOf(head, "description")).toBe("Custom description");
  });

  it("builds Product JSON-LD with a single Offer and omits an empty rating", () => {
    const product = ld(buildProductHead(base()), 0);
    expect(product["@type"]).toBe("Product");
    expect(product.sku).toBe("HDH-SH-000001");
    expect(product.aggregateRating).toBeUndefined();
    expect(product.offers).toMatchObject({
      "@type": "Offer",
      price: "1500.00",
      priceCurrency: "INR",
      availability: "https://schema.org/InStock",
    });
  });

  it("uses AggregateOffer across differently priced variants", () => {
    const head = buildProductHead(
      base({
        variants: [
          { id: "v1", price_adjustment: 0, is_active: true },
          { id: "v2", price_adjustment: 200, is_active: true },
          { id: "v3", price_adjustment: 900, is_active: false },
        ],
      }),
    );
    expect(ld(head, 0).offers).toMatchObject({
      "@type": "AggregateOffer",
      lowPrice: "1500.00",
      highPrice: "1700.00",
      offerCount: 2,
    });
  });

  it("marks sold-out products OutOfStock and includes real ratings", () => {
    const head = buildProductHead(
      base({ inventory_status: "OUT_OF_STOCK", average_rating: 4.5, review_count: 8 }),
    );
    const product = ld(head, 0);
    expect(product.offers).toMatchObject({ availability: "https://schema.org/OutOfStock" });
    expect(product.aggregateRating).toMatchObject({ ratingValue: 4.5, reviewCount: 8 });
    expect(metaOf(head, "product:availability")).toBe("out of stock");
  });

  it("emits a BreadcrumbList ending at the product", () => {
    const crumbs = ld(buildProductHead(base()), 1) as {
      itemListElement: { position: number; item: string }[];
    };
    expect(crumbs.itemListElement.map((c) => c.position)).toEqual([1, 2, 3]);
    expect(crumbs.itemListElement[2].item).toBe("https://hadha.co/products/silver-anklet");
  });

  it("escapes < in JSON-LD so product text cannot close the script tag", () => {
    const head = buildProductHead(base({ name: "</script><b>x" }));
    expect(head.scripts[0].children).not.toContain("</script>");
    expect(ld(head, 0).name).toBe("</script><b>x");
  });

  it("omits image tags when the product has no images", () => {
    const head = buildProductHead(base({ images: [] }));
    expect(metaOf(head, "og:image")).toBeUndefined();
    expect(ld(head, 0).image).toBeUndefined();
  });
});

describe("productDescription / productUrl", () => {
  it("truncates to 160 chars on a word boundary", () => {
    const long = Array.from({ length: 60 }, () => "silver").join(" ");
    const out = productDescription(base({ meta_description: long }));
    expect(out.length).toBeLessThanOrEqual(160);
    expect(out.endsWith("…")).toBe(true);
  });

  it("builds an absolute product URL", () => {
    expect(productUrl("a b")).toBe("https://hadha.co/products/a%20b");
  });
});
