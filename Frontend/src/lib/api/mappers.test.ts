import type { ProductListItem } from "@/types/admin";
import type { CollectionDto, ProductDetail, PublicReview } from "@/types/public";
import { toCollection, toProduct, toProductDetail, toReview } from "./mappers";

// ── Factories ─────────────────────────────────────────────────────────────────

const makeListItem = (overrides: Partial<ProductListItem> = {}): ProductListItem => ({
  id: "p-1",
  sku: "SR-001",
  name: "Silver Ring",
  slug: "silver-ring",
  short_description: "A beautiful ring",
  category_id: "cat-1",
  metal_type: "silver",
  base_price: 999,
  compare_at_price: 1299,
  stock_quantity: 10,
  status: "active",
  is_featured: false,
  is_new_arrival: false,
  is_best_seller: false,
  created_at: "2024-01-01T00:00:00Z",
  primary_image: "https://cdn.example.com/ring.jpg",
  ...overrides,
});

const makeDetail = (overrides: Partial<ProductDetail> = {}): ProductDetail => ({
  id: "p-1",
  sku: "SR-001",
  name: "Silver Ring",
  slug: "silver-ring",
  description: "Beautiful 92.5 silver ring",
  short_description: "A silver ring",
  category_id: "cat-1",
  metal_type: "silver",
  purity: "92.5",
  hallmark_number: null,
  weight_grams: 5.2,
  gender: "women",
  base_price: 999,
  compare_at_price: 1299,
  tax_rate: 3,
  stock_quantity: 10,
  status: "active",
  is_featured: false,
  is_new_arrival: false,
  is_best_seller: false,
  is_customizable: false,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  images: [
    {
      id: "img-1",
      url: "https://cdn/1.jpg",
      thumbnail_url: null,
      medium_url: null,
      alt_text: null,
      is_primary: true,
      sort_order: 0,
    },
    {
      id: "img-2",
      url: "https://cdn/2.jpg",
      thumbnail_url: null,
      medium_url: null,
      alt_text: null,
      is_primary: false,
      sort_order: 1,
    },
  ],
  variants: [
    {
      id: "v-1",
      sku: "SR-S",
      name: "Small",
      price_adjustment: 0,
      stock_quantity: 5,
      weight_grams: null,
      is_active: true,
      sort_order: 1,
    },
    {
      id: "v-2",
      sku: "SR-L",
      name: "Large",
      price_adjustment: 100,
      stock_quantity: 3,
      weight_grams: null,
      is_active: false,
      sort_order: 0,
    },
    {
      id: "v-3",
      sku: "SR-M",
      name: "Medium",
      price_adjustment: 50,
      stock_quantity: 2,
      weight_grams: null,
      is_active: true,
      sort_order: 0,
    },
  ],
  attributes: [{ id: "a-1", name: "Metal", value: "Sterling Silver", sort_order: 0 }],
  ...overrides,
});

const makeCollection = (overrides: Partial<CollectionDto> = {}): CollectionDto => ({
  id: "c-1",
  name: "Rings",
  slug: "rings",
  description: "Beautiful rings collection",
  image_url: "https://cdn/rings.jpg",
  is_active: true,
  is_featured: false,
  sort_order: 0,
  seo_title: null,
  seo_description: null,
  starts_at: null,
  ends_at: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  ...overrides,
});

const makeReview = (overrides: Partial<PublicReview> = {}): PublicReview => ({
  id: "r-1",
  product_id: "p-1",
  user_id: "u-1",
  order_id: "o-1",
  rating: 5,
  title: "Absolutely love it",
  body: "Wore it to a wedding — got so many compliments.",
  is_verified_purchase: true,
  is_approved: true,
  helpful_count: 3,
  created_at: "2024-01-15T10:00:00Z",
  images: [],
  ...overrides,
});

// ── toProduct ─────────────────────────────────────────────────────────────────

describe("toProduct", () => {
  it("maps scalar fields directly", () => {
    const result = toProduct(makeListItem());
    expect(result.id).toBe("p-1");
    expect(result.slug).toBe("silver-ring");
    expect(result.sku).toBe("SR-001");
    expect(result.name).toBe("Silver Ring");
    expect(result.price).toBe(999);
  });

  it("maps primary_image to image", () => {
    const result = toProduct(makeListItem({ primary_image: "https://cdn/img.jpg" }));
    expect(result.image).toBe("https://cdn/img.jpg");
  });

  it("falls back to empty string when primary_image is null", () => {
    const result = toProduct(makeListItem({ primary_image: null }));
    expect(result.image).toBe("");
  });

  it("maps compare_at_price to compareAt", () => {
    const result = toProduct(makeListItem({ compare_at_price: 1299 }));
    expect(result.compareAt).toBe(1299);
  });

  it("omits compareAt when compare_at_price is null", () => {
    const result = toProduct(makeListItem({ compare_at_price: null }));
    expect(result.compareAt).toBeUndefined();
  });

  it("inStock is true when stock_quantity > 0", () => {
    expect(toProduct(makeListItem({ stock_quantity: 1 })).inStock).toBe(true);
  });

  it("inStock is false when stock_quantity is 0", () => {
    expect(toProduct(makeListItem({ stock_quantity: 0 })).inStock).toBe(false);
  });

  it("badge is 'New' when is_new_arrival is true", () => {
    expect(toProduct(makeListItem({ is_new_arrival: true })).badge).toBe("New");
  });

  it("badge is 'Bestseller' when is_best_seller is true (and not new)", () => {
    expect(toProduct(makeListItem({ is_best_seller: true })).badge).toBe("Bestseller");
  });

  it("badge is undefined when neither new nor bestseller", () => {
    expect(toProduct(makeListItem()).badge).toBeUndefined();
  });

  it("'New' badge takes precedence over 'Bestseller'", () => {
    const result = toProduct(makeListItem({ is_new_arrival: true, is_best_seller: true }));
    expect(result.badge).toBe("New");
  });

  it("gender is always 'unisex' (list items carry no gender)", () => {
    expect(toProduct(makeListItem()).gender).toBe("unisex");
  });

  it("collectionIds is always an empty array", () => {
    expect(toProduct(makeListItem()).collectionIds).toEqual([]);
  });
});

// ── toProductDetail ───────────────────────────────────────────────────────────

describe("toProductDetail", () => {
  it("uses the primary image as the main image", () => {
    const result = toProductDetail(makeDetail());
    expect(result.image).toBe("https://cdn/1.jpg");
  });

  it("falls back to the first image when none is marked primary", () => {
    const result = toProductDetail(
      makeDetail({
        images: [
          {
            id: "img-1",
            url: "https://cdn/first.jpg",
            thumbnail_url: null,
            medium_url: null,
            alt_text: null,
            is_primary: false,
            sort_order: 0,
          },
          {
            id: "img-2",
            url: "https://cdn/second.jpg",
            thumbnail_url: null,
            medium_url: null,
            alt_text: null,
            is_primary: false,
            sort_order: 1,
          },
        ],
      }),
    );
    expect(result.image).toBe("https://cdn/first.jpg");
  });

  it("sets altImage to the second image url", () => {
    const result = toProductDetail(makeDetail());
    expect(result.altImage).toBe("https://cdn/2.jpg");
  });

  it("builds gallery from all image urls", () => {
    const result = toProductDetail(makeDetail());
    expect(result.gallery).toEqual(["https://cdn/1.jpg", "https://cdn/2.jpg"]);
  });

  it("gallery is undefined when there are no images", () => {
    const result = toProductDetail(makeDetail({ images: [] }));
    expect(result.gallery).toBeUndefined();
  });

  it("image is empty string when images array is empty", () => {
    const result = toProductDetail(makeDetail({ images: [] }));
    expect(result.image).toBe("");
  });

  it("filters variants to only active ones", () => {
    const result = toProductDetail(makeDetail());
    // v-2 is_active: false → excluded; v-1 and v-3 are active
    expect(result.variants).toHaveLength(2);
    expect(result.variants!.every((v) => v.is_active)).toBe(true);
  });

  it("sorts active variants by sort_order ascending", () => {
    const result = toProductDetail(makeDetail());
    // v-3 sort_order:0, v-1 sort_order:1 → v-3 first
    expect(result.variants![0].id).toBe("v-3");
    expect(result.variants![1].id).toBe("v-1");
  });

  it("parses a valid gender string", () => {
    expect(toProductDetail(makeDetail({ gender: "men" })).gender).toBe("men");
    expect(toProductDetail(makeDetail({ gender: "kids" })).gender).toBe("kids");
  });

  it("falls back to 'unisex' for an invalid or null gender", () => {
    expect(toProductDetail(makeDetail({ gender: null })).gender).toBe("unisex");
    expect(toProductDetail(makeDetail({ gender: "unknown" })).gender).toBe("unisex");
  });

  it("maps attributes to specifications", () => {
    const result = toProductDetail(makeDetail());
    expect(result.specifications).toEqual([{ label: "Metal", value: "Sterling Silver" }]);
  });

  it("specifications is undefined when attributes is empty", () => {
    const result = toProductDetail(makeDetail({ attributes: [] }));
    expect(result.specifications).toBeUndefined();
  });

  it("formats weight_grams as '<n>g'", () => {
    const result = toProductDetail(makeDetail({ weight_grams: 5.2 }));
    expect(result.attributes?.weight).toBe("5.2g");
  });

  it("weight attribute is undefined when weight_grams is null", () => {
    const result = toProductDetail(makeDetail({ weight_grams: null }));
    expect(result.attributes?.weight).toBeUndefined();
  });
});

// ── toCollection ──────────────────────────────────────────────────────────────

describe("toCollection", () => {
  it("maps scalar fields", () => {
    const result = toCollection(makeCollection());
    expect(result.id).toBe("c-1");
    expect(result.slug).toBe("rings");
    expect(result.name).toBe("Rings");
  });

  it("maps image_url to image", () => {
    const result = toCollection(makeCollection({ image_url: "https://cdn/rings.jpg" }));
    expect(result.image).toBe("https://cdn/rings.jpg");
  });

  it("falls back to empty string when image_url is null", () => {
    const result = toCollection(makeCollection({ image_url: null }));
    expect(result.image).toBe("");
  });

  it("maps description to description", () => {
    const result = toCollection(makeCollection({ description: "Nice rings" }));
    expect(result.description).toBe("Nice rings");
  });

  it("description is undefined when null", () => {
    const result = toCollection(makeCollection({ description: null }));
    expect(result.description).toBeUndefined();
  });
});

// ── toReview ──────────────────────────────────────────────────────────────────

describe("toReview", () => {
  it("maps scalar fields", () => {
    const result = toReview(makeReview());
    expect(result.id).toBe("r-1");
    expect(result.productId).toBe("p-1");
    expect(result.rating).toBe(5);
    expect(result.createdAt).toBe("2024-01-15T10:00:00Z");
  });

  it("uses the title as name when title is present", () => {
    const result = toReview(makeReview({ title: "Great ring!" }));
    expect(result.name).toBe("Great ring!");
  });

  it("falls back to 'Verified Buyer' when title is null and purchase is verified", () => {
    const result = toReview(makeReview({ title: null, is_verified_purchase: true }));
    expect(result.name).toBe("Verified Buyer");
  });

  it("falls back to 'Customer' when title is null and purchase is not verified", () => {
    const result = toReview(makeReview({ title: null, is_verified_purchase: false }));
    expect(result.name).toBe("Customer");
  });

  it("maps body to text", () => {
    const result = toReview(makeReview({ body: "Excellent quality" }));
    expect(result.text).toBe("Excellent quality");
  });

  it("text is empty string when body is null", () => {
    const result = toReview(makeReview({ body: null }));
    expect(result.text).toBe("");
  });
});
