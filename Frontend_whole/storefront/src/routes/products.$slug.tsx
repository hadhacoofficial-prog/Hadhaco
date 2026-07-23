import { useState, useEffect, useRef, useCallback } from "react";
import { createFileRoute, Link, notFound, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Heart,
  Truck,
  ShieldCheck,
  RotateCcw,
  BadgeCheck,
  Star,
  Bell,
  RefreshCw,
  AlertTriangle,
  Pencil,
} from "lucide-react";
import { afterReviewSubmit, afterWishlistChange } from "@hadha/shared-api";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { QuantityStepper } from "@/components/site/QuantityStepper";
import { ProductGrid } from "@/components/site/ProductGrid";
import { InventoryBadge } from "@/components/site/InventoryBadge";
import { StarRating, WriteReviewModal } from "@/components/site/WriteReviewModal";
import { useAuthContext } from "@/providers/auth-context";
import { useCart, cartLineKey } from "@/stores/cart";
import { useBuyNowStore } from "@/stores/buyNow";
import { useInventoryStore, inventoryKey } from "@/stores/inventory";
import { computeQuantityBounds } from "@/lib/cartQuantity";
import { useWishlist } from "@/stores/wishlist";
import { useRecentlyViewed } from "@/stores/recentlyViewed";
import { useInventorySync } from "@/hooks/useInventorySync";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProductDetail, toProduct, toReview } from "@/lib/api/mappers";
import { supabase } from "@/lib/supabase/client";
import type { ProductListResponse } from "@/types/admin";
import type {
  MyProductReviewStatus,
  ProductDetail,
  ProductVariant,
  PublicReview,
  ReviewSummary,
} from "@/types/public";
import type { Product, ProductSpec, Review } from "@/types/shop";

export const Route = createFileRoute("/products/$slug")({
  // ?review=1 deep-links (from emails / order reminders) open the Reviews tab.
  validateSearch: (search: Record<string, unknown>): { review?: string } => ({
    review: search.review ? String(search.review) : undefined,
  }),
  loader: async ({ params }) => {
    const productDetail = await api
      // `no-cache`: revalidate against origin so a client-side navigation
      // never renders the stale `max-age` copy from the browser cache (the
      // live poll below also uses no-cache). On SSR this is a harmless no-op.
      .get<ProductDetail>(`/products/${params.slug}`, { cache: "no-cache" })
      .catch((e: unknown) => {
        if ((e as { status?: number }).status === 404) throw notFound();
        throw e;
      });
    const relatedRes = await api
      .get<ProductListResponse>("/products", {
        params: { page_size: 5, is_featured: true },
      })
      .catch(() => ({ items: [] }) as Pick<ProductListResponse, "items">);
    return {
      product: toProductDetail(productDetail),
      related: relatedRes.items
        .filter((p) => p.id !== productDetail.id)
        .slice(0, 4)
        .map(toProduct),
      slug: params.slug,
    };
  },
  head: ({ loaderData }) => ({
    meta: [
      { title: `${loaderData?.product.name ?? "Product"} · Hadha` },
      { name: "description", content: loaderData?.product.shortDescription ?? "" },
      { property: "og:title", content: loaderData?.product.name ?? "" },
      { property: "og:image", content: loaderData?.product.image ?? "" },
    ],
  }),
  notFoundComponent: () => (
    <SiteLayout>
      <div className="px-8 py-20 text-center">
        <h1 className="font-display text-3xl mb-3">Product not found</h1>
        <Link to="/collections" className="underline">
          Shop all collections
        </Link>
      </div>
    </SiteLayout>
  ),
  errorComponent: ({ reset }) => (
    <SiteLayout>
      <div className="px-8 py-20 text-center">
        <h1 className="font-display text-2xl mb-3">Something went wrong</h1>
        <button onClick={() => reset()} className="underline">
          Retry
        </button>
      </div>
    </SiteLayout>
  ),
  component: ProductPage,
});

function ProductPage() {
  const { product, related, slug } = Route.useLoaderData();
  const search = Route.useSearch();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuthContext();
  const [active, setActive] = useState(0);
  const [qty, setQty] = useState(1);
  const [tab, setTab] = useState<"details" | "specs" | "reviews">("details");
  const [selectedVariant, setSelectedVariant] = useState<ProductVariant | null>(null);
  const [variantError, setVariantError] = useState(false);

  const add = useCart((s) => s.add);
  const cartQty = useCart((s) => {
    const k = cartLineKey(product.id, selectedVariant?.id);
    return s.lines.find((l) => cartLineKey(l.productId, l.variantId) === k)?.qty ?? 0;
  });
  const wishlistItems = useWishlist((s) => s.items);
  const wishToggle = useWishlist((s) => s.toggle);
  const pushRV = useRecentlyViewed((s) => s.push);

  // Poll live stock/variant data every 60 s so the page stays accurate without
  // a reload. `cache: "no-cache"` forces the fetch to revalidate against the
  // origin every time (cheap 304 when unchanged) instead of being served the
  // stale `Cache-Control: max-age` copy from the browser cache — otherwise the
  // poll silently reuses the cached response and admin edits to variant data
  // only surface once that max-age window expires.
  const { data: liveDetail, dataUpdatedAt } = useQuery({
    queryKey: queryKeys.products.stock(slug),
    queryFn: () => api.get<ProductDetail>(`/products/${slug}`, { cache: "no-cache" }),
    refetchInterval: 60_000,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  const liveProduct = liveDetail ? toProductDetail(liveDetail) : product;

  // Sync product inventory into Zustand store (source of truth for stock).
  // Must receive raw ProductDetail, not the mapped Product type.
  useInventorySync(slug, liveDetail);

  const hasVariants = (liveProduct.variants?.length ?? 0) > 0;
  const currentVariant = selectedVariant
    ? (liveProduct.variants?.find((v) => v.id === selectedVariant.id) ?? selectedVariant)
    : null;

  const wished = wishlistItems.some(
    (i) => i.id === product.id && i.variantId === (currentVariant?.id ?? undefined),
  );

  // Read stock from Zustand store (source of truth)
  const inventoryEntry = useInventoryStore((s) => s.get(product.id, currentVariant?.id ?? null));

  const liveAvailableStock = inventoryEntry?.availableStock ?? liveProduct.availableStock;

  // Resolved variant stock (use live data if we have it)
  const variantStock = currentVariant
    ? (currentVariant.available_stock ?? currentVariant.stock_quantity)
    : 0;

  // Effective stock for the current selection
  const effectiveStock = hasVariants
    ? currentVariant !== null
      ? variantStock
      : 0
    : liveAvailableStock;

  const bounds = computeQuantityBounds({
    availableStock: effectiveStock,
    maxOrderQty: liveProduct.maxOrderQty ?? 0,
    cartQty,
  });

  // Clamp stepper qty whenever the allowed-remaining changes
  useEffect(() => {
    if (bounds.remainingAllowed > 0) {
      setQty((prev) => Math.max(1, Math.min(prev, bounds.remainingAllowed)));
    }
  }, [bounds.remainingAllowed]);

  const displayPrice = product.price + (currentVariant?.price_adjustment ?? 0);
  const displayCompareAt = currentVariant
    ? product.compareAt != null
      ? product.compareAt + currentVariant.price_adjustment
      : undefined
    : product.compareAt;
  const displaySku = currentVariant?.sku ?? product.sku;

  const displayInStock: boolean | null = hasVariants
    ? currentVariant !== null
      ? variantStock > 0
      : null
    : liveAvailableStock > 0;

  useEffect(() => {
    pushRV(product.id);
    setActive(0);
    setSelectedVariant(null);
    setVariantError(false);
  }, [product.id, pushRV]);

  const queryClient = useQueryClient();

  const { data: rawReviews, refetch: refetchReviews } = useQuery({
    queryKey: queryKeys.reviews.forProduct(product.id),
    queryFn: () =>
      api.get<PublicReview[]>(`/reviews/products/${product.id}`, { params: { limit: 50 } }),
    staleTime: 2 * 60_000,
  });
  const reviews = (rawReviews ?? []).map(toReview);

  const { data: reviewSummary, refetch: refetchSummary } = useQuery({
    queryKey: queryKeys.reviews.summary(product.id),
    queryFn: () => api.get<ReviewSummary>(`/reviews/products/${product.id}/summary`),
    staleTime: 2 * 60_000,
  });

  const avgRating = reviewSummary?.average_rating ?? product.rating ?? 0;
  const reviewCount = reviewSummary?.review_count ?? product.reviewCount ?? 0;

  // Purchased-and-delivered review reminder banner (read-only state — never
  // gates who may submit a review, see Backend/app/modules/reviews/service.py).
  const { data: myReviewStatus, refetch: refetchMyReviewStatus } = useQuery({
    queryKey: queryKeys.reviews.myStatus(product.id),
    queryFn: () => api.get<MyProductReviewStatus>(`/reviews/products/${product.id}/my-status`),
    enabled: isAuthenticated,
    staleTime: 60_000,
  });
  const showPurchasedBanner = Boolean(
    myReviewStatus?.has_purchased_delivered && !myReviewStatus.has_reviewed,
  );

  const [showReviewModal, setShowReviewModal] = useState(false);

  const gallery = product.gallery ?? [product.image];
  const galleryLarge = product.galleryLarge ?? gallery;
  const recentlyViewed: Product[] = [];

  const handleAddToCart = () => {
    if (hasVariants && !currentVariant) {
      setVariantError(true);
      return;
    }
    if (!bounds.canAdd) return;
    add(
      product.id,
      qty,
      {
        name: product.name,
        image: product.image,
        slug: product.slug,
        sku: displaySku,
        price: displayPrice,
        variantName: currentVariant?.name,
      },
      currentVariant?.id,
    );
    // Optimistic: decrement stock in Zustand store (source of truth)
    // so badges and quantity steppers update immediately across all pages.
    useInventoryStore.getState().optimisticDecrement(product.id, currentVariant?.id ?? null, qty);
  };

  const handleWishlistToggle = () => {
    if (hasVariants && !currentVariant) {
      setVariantError(true);
      return;
    }
    wishToggle({
      id: product.id,
      slug: product.slug,
      name: product.name,
      image: product.image,
      price: displayPrice,
      sku: displaySku,
      variantId: currentVariant?.id,
      variantName: currentVariant?.name,
    });
    afterWishlistChange();
  };

  const handleBuyNow = () => {
    if (hasVariants && !currentVariant) {
      setVariantError(true);
      return;
    }
    if (!bounds.canAdd) return;
    useBuyNowStore.getState().setItems([
      {
        productId: product.id,
        qty,
        snapshot: {
          name: product.name,
          image: product.image,
          slug: product.slug,
          sku: displaySku,
          price: displayPrice,
          variantName: currentVariant?.name,
        },
        variantId: currentVariant?.id,
      },
    ]);
    navigate({ to: "/checkout" });
  };

  const selectVariant = (v: ProductVariant) => {
    setSelectedVariant(v);
    setVariantError(false);
    setQty(1);
  };

  const reviewsRef = useRef<HTMLDivElement>(null);

  const scrollToReviews = useCallback(() => {
    setTab("reviews");
    setTimeout(() => {
      reviewsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  }, []);

  // Deep link from emails/order reminders: /products/slug?review=1 opens the
  // Reviews tab and scrolls straight to it.
  useEffect(() => {
    if (search.review) scrollToReviews();
  }, [search.review, scrollToReviews]);

  // Show Notify Me / sold-out state when product has no variants and is out of stock
  const globalSoldOut = !hasVariants && liveAvailableStock === 0;

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 pt-6">
        <Breadcrumbs
          items={[
            { label: "Home", to: "/" },
            { label: "Collections", to: "/collections" },
            { label: product.name },
          ]}
        />
      </div>

      <div className="px-4 md:px-8 py-8 grid lg:grid-cols-2 gap-10">
        {/* Gallery */}
        <div className="grid grid-cols-[80px_1fr] gap-4 max-lg:grid-cols-1">
          <div className="flex lg:flex-col gap-3 max-lg:order-2 max-lg:overflow-x-auto">
            {gallery.map((img: string, i: number) => (
              <button
                key={i}
                onClick={() => setActive(i)}
                className={`shrink-0 w-20 h-20 bg-white overflow-hidden border ${active === i ? "border-foreground" : "border-transparent"}`}
              >
                <img
                  src={img}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  width={80}
                  height={80}
                  className="w-full h-full object-contain"
                />
              </button>
            ))}
          </div>
          <ProductImageViewer
            src={gallery[active]}
            zoomSrc={galleryLarge[active] ?? gallery[active]}
            alt={product.name}
            globalSoldOut={globalSoldOut}
            badge={product.badge}
          />
        </div>

        {/* Info */}
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-amber-600">Hadha Jewellery</p>
          <h1 className="font-display text-3xl md:text-4xl mt-2 leading-tight">{product.name}</h1>

          <button
            type="button"
            onClick={scrollToReviews}
            aria-label="Jump to customer reviews"
            className="flex items-center gap-3 mt-3 cursor-pointer group focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground rounded-sm"
          >
            {reviewCount > 0 ? (
              <>
                <div className="flex">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Star
                      key={i}
                      className={`size-4 ${i < Math.round(avgRating) ? "fill-accent text-accent" : "text-border"}`}
                    />
                  ))}
                </div>
                <span className="text-xs text-muted-foreground group-hover:text-foreground group-hover:underline transition-colors">
                  {avgRating.toFixed(1)} · {reviewCount} review{reviewCount !== 1 ? "s" : ""}
                </span>
              </>
            ) : (
              <span className="text-xs text-muted-foreground group-hover:text-foreground group-hover:underline transition-colors">
                No reviews yet
              </span>
            )}
          </button>

          <div className="flex items-baseline gap-3 mt-5">
            <span className="font-sans font-bold text-3xl">{formatINR(displayPrice)}</span>
            {displayCompareAt && (
              <span className="text-muted-foreground line-through">
                {formatINR(displayCompareAt)}
              </span>
            )}
            {displayCompareAt && displayCompareAt > displayPrice && (
              <span className="text-xs uppercase tracking-[0.2em] text-accent">
                {Math.round((1 - displayPrice / displayCompareAt) * 100)}% off
              </span>
            )}
          </div>

          <p className="text-sm text-muted-foreground mt-3">Inclusive of all taxes</p>

          {/* Live stock badge */}
          <div className="flex items-center gap-3 mt-3">
            {displayInStock !== null && (
              <InventoryBadge
                availableStock={hasVariants && currentVariant ? variantStock : liveAvailableStock}
              />
            )}
            {hasVariants && displayInStock === null && (
              <span className="text-xs text-muted-foreground tracking-wide">
                Select a variant to check availability
              </span>
            )}
            {/* Last refreshed indicator */}
            {dataUpdatedAt > 0 && (
              <span
                className="text-[10px] text-muted-foreground/60 flex items-center gap-1"
                title={`Stock last refreshed at ${new Date(dataUpdatedAt).toLocaleTimeString()}`}
              >
                <RefreshCw className="size-3" aria-hidden />
                Live
              </span>
            )}
          </div>

          <p className="mt-6 text-sm text-foreground/80 leading-relaxed">
            {product.shortDescription}
          </p>

          {/* ── Variant selector ── */}
          {hasVariants && (
            <div className="mt-7">
              <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground mb-3">
                Select variant{" "}
                <span className="text-destructive" aria-hidden>
                  *
                </span>
                {currentVariant && (
                  <span className="ml-2 normal-case tracking-normal text-foreground font-medium">
                    — {currentVariant.name}
                  </span>
                )}
              </p>
              <div className="flex flex-wrap gap-2">
                {liveProduct.variants!.map((v) => {
                  const vStock = v.available_stock ?? v.stock_quantity;
                  const outOfStock = vStock === 0;
                  const isSelected = currentVariant?.id === v.id;
                  return (
                    <button
                      key={v.id}
                      type="button"
                      onClick={() => !outOfStock && selectVariant(v)}
                      disabled={outOfStock}
                      aria-pressed={isSelected}
                      aria-label={`${v.name}${outOfStock ? " — sold out" : vStock <= 5 ? ` — only ${vStock} left` : ""}`}
                      className={`relative px-3.5 py-2 text-xs border transition-all ${
                        isSelected
                          ? "bg-foreground text-background border-foreground"
                          : outOfStock
                            ? "border-border text-muted-foreground line-through cursor-not-allowed opacity-40"
                            : "border-border hover:border-foreground"
                      }`}
                    >
                      {v.name}
                      {v.price_adjustment !== 0 && (
                        <span
                          className={`ml-1.5 ${isSelected ? "text-background/70" : "text-muted-foreground"}`}
                        >
                          {v.price_adjustment > 0
                            ? `+${formatINR(v.price_adjustment)}`
                            : `−${formatINR(Math.abs(v.price_adjustment))}`}
                        </span>
                      )}
                      {outOfStock && (
                        <span className="absolute -top-2 left-1/2 -translate-x-1/2 text-[9px] uppercase tracking-wide text-destructive">
                          sold out
                        </span>
                      )}
                      {!outOfStock && vStock <= 5 && (
                        <span className="absolute -top-2 left-1/2 -translate-x-1/2 text-[9px] uppercase tracking-wide text-amber-600">
                          {vStock} left
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
              {variantError && (
                <p className="mt-2 text-xs text-destructive" role="alert">
                  Please select a variant to continue.
                </p>
              )}
            </div>
          )}

          {/* ── Add to cart / Sold-out actions ── */}
          {globalSoldOut ? (
            <div className="mt-8 space-y-3">
              <div className="flex items-center gap-2 p-4 bg-muted/50 border border-border">
                <InventoryBadge availableStock={0} />
                <p className="text-sm text-muted-foreground">
                  This product is currently unavailable.
                </p>
              </div>
              <button
                onClick={handleWishlistToggle}
                className="w-full flex items-center justify-center gap-2 border border-foreground text-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-foreground hover:text-background transition"
                aria-label="Add to wishlist to get notified when back in stock"
              >
                <Bell className="size-4" />
                {wished ? "Added to Wishlist" : "Notify Me When Available"}
              </button>
              <Link
                to="/collections"
                className="flex items-center justify-center gap-2 border border-border text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-secondary transition"
              >
                Browse Similar Items
              </Link>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-4 mt-8">
                <QuantityStepper
                  value={qty}
                  onChange={setQty}
                  max={bounds.remainingAllowed > 0 ? bounds.remainingAllowed : 1}
                  disabled={displayInStock !== null && !bounds.canAdd}
                />
                {effectiveStock > 0 && effectiveStock <= 10 && bounds.canAdd && (
                  <span className="text-xs text-amber-600">Only {effectiveStock} left</span>
                )}
                <button
                  onClick={handleAddToCart}
                  disabled={displayInStock === false || !bounds.canAdd}
                  className="flex-1 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {displayInStock === false
                    ? "Out of Stock"
                    : !bounds.canAdd
                      ? "Max Qty in Cart"
                      : "Add to Cart"}
                </button>
                <button
                  onClick={handleWishlistToggle}
                  aria-label={wished ? "Remove from wishlist" : "Add to wishlist"}
                  className={`size-12 border border-foreground flex items-center justify-center transition ${wished ? "bg-foreground text-background" : "hover:bg-secondary"}`}
                >
                  <Heart className={`size-4 ${wished ? "fill-current" : ""}`} />
                </button>
              </div>
              {bounds.limitMessage && (
                <p className="mt-2 text-xs text-amber-700 flex items-center gap-1" role="status">
                  <AlertTriangle className="size-3 shrink-0" aria-hidden />
                  {bounds.limitMessage}
                </p>
              )}
              <button
                onClick={handleBuyNow}
                disabled={displayInStock === false || !bounds.canAdd}
                className="mt-3 w-full border border-foreground text-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-foreground hover:text-background transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Buy It Now
              </button>
            </>
          )}

          {/* Trust */}
          <div className="mt-8 grid grid-cols-2 gap-3 border-t border-border pt-6">
            {[
              { icon: <Truck className="size-4" />, label: "Free shipping over Rs. 999" },
              { icon: <RotateCcw className="size-4" />, label: "Returns vary by product" },
              { icon: <ShieldCheck className="size-4" />, label: "Secure payments" },
              { icon: <BadgeCheck className="size-4" />, label: "BIS-hallmarked 92.5 silver" },
            ].map((t) => (
              <div key={t.label} className="flex items-center gap-2.5 text-xs">
                <span className="text-accent">{t.icon}</span>
                {t.label}
              </div>
            ))}
          </div>
        </div>
      </div>

      {showPurchasedBanner && (
        <div className="px-4 md:px-8 pt-8">
          <div className="flex flex-wrap items-center justify-between gap-4 bg-accent/10 border border-accent/30 px-6 py-5">
            <div>
              <p className="font-display text-lg">You purchased this product.</p>
              <p className="text-sm text-muted-foreground mt-0.5">
                Share your experience with other customers.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowReviewModal(true)}
              className="shrink-0 inline-flex items-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-5 py-3 hover:bg-accent hover:text-accent-foreground transition"
            >
              <Pencil className="size-3.5" />
              Write a Review
            </button>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div
        id="product-reviews"
        ref={reviewsRef}
        className="px-4 md:px-8 py-10 border-t border-border"
        style={{ scrollMarginTop: "140px" }}
      >
        <div className="flex gap-8 text-xs uppercase tracking-[0.22em] border-b border-border">
          {(["details", "specs", "reviews"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`pb-3 -mb-px border-b-2 transition ${tab === t ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              {t === "details" ? "Details" : t === "specs" ? "Specifications" : "Reviews"}
            </button>
          ))}
        </div>
        <div className="py-8 max-w-3xl">
          {tab === "details" && (
            <p className="text-sm leading-relaxed text-foreground/80 whitespace-pre-line">
              {product.description}
            </p>
          )}
          {tab === "specs" && (
            <table className="w-full text-sm">
              <tbody>
                {(product.specifications ?? []).map((s: ProductSpec) => (
                  <tr key={s.label} className="border-b border-border">
                    <td className="py-3 pr-6 text-muted-foreground uppercase tracking-[0.16em] text-xs w-44">
                      {s.label}
                    </td>
                    <td className="py-3">{s.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {tab === "reviews" && (
            <ReviewsSection
              reviews={reviews}
              productId={product.id}
              onWriteReview={() => setShowReviewModal(true)}
              onRefresh={() => {
                refetchReviews();
                refetchSummary();
                afterReviewSubmit(product.id);
              }}
            />
          )}
        </div>
      </div>

      {related.length > 0 && (
        <section className="px-4 md:px-8 py-12 border-t border-border">
          <h2 className="font-display text-2xl md:text-3xl mb-6">You may also like</h2>
          <ProductGrid products={related} />
        </section>
      )}

      {recentlyViewed.length > 0 && (
        <section className="px-4 md:px-8 py-12 border-t border-border">
          <h2 className="font-display text-2xl md:text-3xl mb-6">Recently viewed</h2>
          <ProductGrid products={recentlyViewed} />
        </section>
      )}

      {showReviewModal && (
        <WriteReviewModal
          productId={product.id}
          onClose={() => setShowReviewModal(false)}
          onSuccess={() => {
            afterReviewSubmit(product.id);
            refetchMyReviewStatus();
          }}
        />
      )}
    </SiteLayout>
  );
}

// ── Reviews section ────────────────────────────────────────────────────────────

function ReviewCard({ review }: { review: Review }) {
  const [imgIdx, setImgIdx] = useState(0);

  return (
    <div className="border-b border-border pb-6">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-medium text-sm">{review.name}</p>
            {review.isVerifiedPurchase && (
              <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-[0.16em] px-2 py-0.5 bg-accent/10 text-accent border border-accent/20">
                <BadgeCheck className="size-3" />
                Verified Purchase
              </span>
            )}
          </div>
          <StarRating value={review.rating} size="sm" />
        </div>
        {review.createdAt && (
          <p className="text-[11px] text-muted-foreground shrink-0">
            {new Date(review.createdAt).toLocaleDateString("en-IN", {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </p>
        )}
      </div>
      {review.text && <p className="text-sm text-foreground/80 leading-relaxed">{review.text}</p>}
      {(review.images?.length ?? 0) > 0 && (
        <div className="mt-3 flex gap-2 flex-wrap">
          {review.images!.map((img, i) => (
            <button
              key={img.id}
              type="button"
              onClick={() => setImgIdx(i)}
              className={`size-16 border overflow-hidden shrink-0 ${imgIdx === i ? "border-foreground" : "border-border"}`}
            >
              <img
                src={img.url}
                alt={`Review image ${i + 1}`}
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ReviewsSection({
  reviews,
  productId,
  onWriteReview,
  onRefresh,
}: {
  reviews: Review[];
  productId: string;
  onWriteReview: () => void;
  onRefresh: () => void;
}) {
  const [currentUserId, setCurrentUserId] = useState<string | undefined>(undefined);

  useEffect(() => {
    import("@/lib/supabase/session").then(({ getSession }) => {
      getSession().then((s) => setCurrentUserId(s?.user?.id));
    });
  }, []);

  const approvedReviews = reviews.filter((r) => r.isApproved);
  const ownUnapproved = reviews.filter((r) => r.userId === currentUserId && !r.isApproved);
  const displayReviews = [...ownUnapproved, ...approvedReviews];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm text-muted-foreground">
          {approvedReviews.length === 0
            ? "No reviews yet — be the first!"
            : `${approvedReviews.length} review${approvedReviews.length > 1 ? "s" : ""}`}
        </p>
        <button
          type="button"
          onClick={onWriteReview}
          className="inline-flex items-center gap-2 border border-foreground text-foreground text-[11px] uppercase tracking-[0.22em] px-4 py-2.5 hover:bg-foreground hover:text-background transition"
        >
          <Pencil className="size-3.5" />
          Write a Review
        </button>
      </div>
      <div className="space-y-6">
        {displayReviews.map((r) => (
          <ReviewCard key={r.id} review={r} />
        ))}
        {displayReviews.length === 0 && (
          <p className="text-sm text-muted-foreground">No reviews yet.</p>
        )}
      </div>
    </div>
  );
}

// ── Product image viewer: desktop cursor-zoom + mobile pinch/double-tap ────────
//
// React registers touchstart/touchmove as PASSIVE listeners, so calling
// e.preventDefault() inside a React synthetic handler is silently ignored and
// the browser still pinch-zooms the page. We fix this by attaching ALL touch
// (and wheel) listeners as non-passive native listeners via a containerRef.
// React synthetic handlers are only used for mouse events (which are fine).

function ProductImageViewer({
  src,
  zoomSrc,
  alt,
  globalSoldOut,
  badge,
}: {
  src: string;
  zoomSrc: string;
  alt: string;
  globalSoldOut: boolean;
  badge?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Desktop hover state (React state is fine — mouse events are non-passive by default)
  const [isHovering, setIsHovering] = useState(false);
  const [cursorOrigin, setCursorOrigin] = useState("50% 50%");
  const isHoveringRef = useRef(false); // mirror for use inside non-passive handlers

  // Desktop wheel-scale multiplier (1 = default, adjusted by scroll wheel)
  const [wheelScale, setWheelScale] = useState(1);
  const wheelScaleRef = useRef(1);

  // Mobile pinch/pan state (mirrors in both React state and a ref)
  const [touchScale, setTouchScale] = useState(1);
  const [touchOrigin, setTouchOrigin] = useState({ x: 50, y: 50 });

  // Single mutable ref for all touch bookkeeping — avoids stale-closure issues
  // inside the native event handlers.
  const tRef = useRef({
    scale: 1,
    origin: { x: 50, y: 50 },
    lastTap: 0,
    lastPinchDist: 0,
    drag: { active: false, startX: 0, startY: 0, ox: 50, oy: 50 },
  });

  const DESKTOP_BASE_ZOOM = 2.5;
  const WHEEL_MIN = 0.5;
  const WHEEL_MAX = 2.0;
  const MOBILE_MAX_SCALE = 5;

  // zoomSrc is the cropped large.webp variant, passed in explicitly by the
  // caller (never derived from the displayed src) — see toProductDetail.
  const effectiveZoomSrc = zoomSrc || src;

  // Preload the large image so hover/zoom switches are instant
  useEffect(() => {
    if (effectiveZoomSrc === src) return;
    const img = new Image();
    img.src = effectiveZoomSrc;
  }, [effectiveZoomSrc, src]);

  // Reset all zoom state when the displayed image changes (thumbnail click)
  useEffect(() => {
    tRef.current = {
      scale: 1,
      origin: { x: 50, y: 50 },
      lastTap: 0,
      lastPinchDist: 0,
      drag: { active: false, startX: 0, startY: 0, ox: 50, oy: 50 },
    };
    setTouchScale(1);
    setTouchOrigin({ x: 50, y: 50 });
    wheelScaleRef.current = 1;
    setWheelScale(1);
    setIsHovering(false);
    isHoveringRef.current = false;
    setCursorOrigin("50% 50%");
  }, [src]);

  // ── Non-passive native event listeners ─────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // ── Touch handlers ────────────────────────────────────────────────────────

    const onTouchStart = (e: TouchEvent) => {
      const t = tRef.current;

      if (e.touches.length === 2) {
        // Two-finger pinch start — always intercept
        e.preventDefault();
        t.drag.active = false;
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        t.lastPinchDist = Math.hypot(dx, dy);
        // Anchor the zoom origin at the midpoint between the two fingers
        const rect = el.getBoundingClientRect();
        const mx = (e.touches[0].clientX + e.touches[1].clientX) / 2;
        const my = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        const newOrigin = {
          x: ((mx - rect.left) / rect.width) * 100,
          y: ((my - rect.top) / rect.height) * 100,
        };
        t.origin = newOrigin;
        setTouchOrigin(newOrigin);
        return;
      }

      if (e.touches.length === 1) {
        const now = Date.now();
        const isDoubleTap = now - t.lastTap < 300;

        if (isDoubleTap) {
          e.preventDefault();
          t.lastTap = 0;
          if (t.scale > 1) {
            // Reset zoom
            t.scale = 1;
            t.origin = { x: 50, y: 50 };
            setTouchScale(1);
            setTouchOrigin({ x: 50, y: 50 });
          } else {
            // Zoom in to the tapped point
            const rect = el.getBoundingClientRect();
            const newOrigin = {
              x: ((e.touches[0].clientX - rect.left) / rect.width) * 100,
              y: ((e.touches[0].clientY - rect.top) / rect.height) * 100,
            };
            t.scale = 2.5;
            t.origin = newOrigin;
            setTouchScale(2.5);
            setTouchOrigin(newOrigin);
          }
          return;
        }

        t.lastTap = now;

        if (t.scale > 1) {
          // Begin panning when already zoomed
          e.preventDefault();
          t.drag = {
            active: true,
            startX: e.touches[0].clientX,
            startY: e.touches[0].clientY,
            ox: t.origin.x,
            oy: t.origin.y,
          };
        }
        // If scale === 1, let the single-finger touch fall through so the
        // page can still be scrolled by touching outside the image.
      }
    };

    const onTouchMove = (e: TouchEvent) => {
      const t = tRef.current;

      if (e.touches.length === 2) {
        e.preventDefault();
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.hypot(dx, dy);
        if (t.lastPinchDist > 0) {
          const newScale = Math.max(
            1,
            Math.min(MOBILE_MAX_SCALE, t.scale * (dist / t.lastPinchDist)),
          );
          t.scale = newScale;
          setTouchScale(newScale);
        }
        t.lastPinchDist = dist;
        return;
      }

      if (e.touches.length === 1 && t.drag.active && t.scale > 1) {
        e.preventDefault();
        const rect = el.getBoundingClientRect();
        const dxPct = ((e.touches[0].clientX - t.drag.startX) / rect.width) * 100;
        const dyPct = ((e.touches[0].clientY - t.drag.startY) / rect.height) * 100;
        // As the finger moves right the origin shifts left (more of the right side is revealed)
        const panFactor = 1 / (t.scale - 1);
        const newOrigin = {
          x: Math.max(0, Math.min(100, t.drag.ox - dxPct * panFactor)),
          y: Math.max(0, Math.min(100, t.drag.oy - dyPct * panFactor)),
        };
        t.origin = newOrigin;
        setTouchOrigin(newOrigin);
      }
    };

    const onTouchEnd = (e: TouchEvent) => {
      const t = tRef.current;
      // Multi-touch lift — reset pinch distance but keep scale/drag state
      // until all fingers are lifted.
      if (e.touches.length === 0) {
        t.drag.active = false;
        t.lastPinchDist = 0;
        if (t.scale < 1.1) {
          t.scale = 1;
          t.origin = { x: 50, y: 50 };
          setTouchScale(1);
          setTouchOrigin({ x: 50, y: 50 });
        }
      } else {
        // One finger lifted during pinch — stop pinch, start possible pan
        t.lastPinchDist = 0;
      }
    };

    // ── Wheel handler (desktop) ───────────────────────────────────────────────
    // Prevents the page from scrolling when the cursor is over the image and
    // the user spins the wheel; instead the zoom multiplier is adjusted.
    const onWheel = (e: WheelEvent) => {
      if (!isHoveringRef.current) return;
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      const next = Math.max(WHEEL_MIN, Math.min(WHEEL_MAX, wheelScaleRef.current + delta));
      wheelScaleRef.current = next;
      setWheelScale(next);
    };

    el.addEventListener("touchstart", onTouchStart, { passive: false });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd, { passive: true });
    el.addEventListener("wheel", onWheel, { passive: false });

    return () => {
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
      el.removeEventListener("wheel", onWheel);
    };
  }, []); // stable — all mutable state lives in refs

  // ── Desktop mouse handlers (React synthetic events — fine for mouse) ────────
  const handleMouseEnter = () => {
    isHoveringRef.current = true;
    setIsHovering(true);
  };

  const handleMouseLeave = () => {
    isHoveringRef.current = false;
    setIsHovering(false);
    setCursorOrigin("50% 50%");
    // Reset wheel scale so next hover starts fresh
    wheelScaleRef.current = 1;
    setWheelScale(1);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    setCursorOrigin(`${x}% ${y}%`);
  };

  const effectiveDesktopScale = isHovering ? DESKTOP_BASE_ZOOM * wheelScale : 1;
  const isZoomedTouch = touchScale > 1;
  // Use high-res source whenever any zoom is active
  const desktopSrc = isHovering ? effectiveZoomSrc : src;
  const mobileSrc = isZoomedTouch ? effectiveZoomSrc : src;

  return (
    <div
      ref={containerRef}
      className="relative aspect-square bg-white overflow-hidden max-lg:order-1 select-none"
      // touch-action is a browser-level directive evaluated before any JS runs —
      // it is NOT just a hint that our preventDefault() calls can override.
      // "none" would block native one-finger vertical scrolling outright, even
      // though the handlers below never call preventDefault for a single,
      // non-zoomed finger. So: default to "pan-y" (native vertical scroll stays
      // smooth/immediate; pinch and horizontal gestures aren't in the allowed
      // set, so the browser still hands those to our non-passive handlers).
      // Only switch to "none" while actually zoomed in, so a one-finger drag
      // pans the zoomed image instead of scrolling the page underneath it.
      style={{ touchAction: isZoomedTouch ? "none" : "pan-y" }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onMouseMove={handleMouseMove}
    >
      {/* Desktop image — cursor-follow zoom with optional wheel multiplier */}
      <img
        src={desktopSrc}
        alt={alt}
        draggable={false}
        className="absolute inset-0 w-full h-full object-contain pointer-events-none hidden md:block"
        style={{
          transformOrigin: cursorOrigin,
          transform: `scale(${effectiveDesktopScale})`,
          transition: isHovering ? "transform 0.15s ease-out" : "transform 0.3s ease-out",
          willChange: "transform",
          imageRendering: "auto",
        }}
      />

      {/* Mobile image — pinch / double-tap / pan */}
      <img
        src={mobileSrc}
        alt={alt}
        draggable={false}
        className="absolute inset-0 w-full h-full object-contain pointer-events-none md:hidden"
        style={{
          transformOrigin: `${touchOrigin.x}% ${touchOrigin.y}%`,
          transform: `scale(${touchScale})`,
          transition: touchScale === 1 ? "transform 0.3s ease-out" : "none",
          willChange: "transform",
          imageRendering: "auto",
        }}
      />

      {globalSoldOut && (
        <div className="absolute inset-0 flex items-center justify-center" aria-hidden>
          <span className="bg-foreground/80 text-background text-sm tracking-[0.24em] uppercase px-6 py-2">
            Sold Out
          </span>
        </div>
      )}

      {badge && !globalSoldOut && (
        <span className="absolute top-4 left-4 bg-primary text-primary-foreground text-[11px] tracking-[0.2em] uppercase px-3 py-1.5">
          {badge}
        </span>
      )}

      {/* Desktop zoom hint */}
      {!isHovering && !globalSoldOut && (
        <div className="absolute bottom-3 right-3 hidden md:flex items-center gap-1.5 bg-background/75 backdrop-blur-sm px-2 py-1 text-[9px] uppercase tracking-[0.18em] text-muted-foreground pointer-events-none">
          <svg
            className="size-3"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35M11 8v6M8 11h6" />
          </svg>
          Zoom
        </div>
      )}

      {/* Mobile zoom hint */}
      {!isZoomedTouch && !globalSoldOut && (
        <div className="absolute bottom-3 right-3 md:hidden flex items-center gap-1.5 bg-background/75 backdrop-blur-sm px-2 py-1 text-[9px] uppercase tracking-[0.18em] text-muted-foreground pointer-events-none">
          Pinch to zoom
        </div>
      )}
    </div>
  );
}
