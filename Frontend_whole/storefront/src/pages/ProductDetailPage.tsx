import { useState, useEffect, useRef, useCallback } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  X,
  Upload,
  Clock,
} from "lucide-react";
import { toast } from "sonner";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { QuantityStepper } from "@/components/site/QuantityStepper";
import { ProductGrid } from "@/components/site/ProductGrid";
import { InventoryBadge } from "@/components/site/InventoryBadge";
import { useCart, cartLineKey } from "@/stores/cart";
import { computeQuantityBounds } from "@/lib/cartQuantity";
import { useWishlist } from "@/stores/wishlist";
import { useActiveReservations } from "@/hooks/useActiveReservations";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProductDetail, toProduct, toReview } from "@/lib/api/mappers";
import type { ProductListResponse } from "@/types/admin";
import type { ProductDetail, ProductVariant, PublicReview, ReviewSummary } from "@/types/public";
import type { ProductSpec, Review } from "@/types/shop";
import { Route } from "@/routes/products.$slug";

export default function ProductPage() {
  const { product, related, slug } = Route.useLoaderData();
  const navigate = useNavigate();
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

  // Poll live stock every 60 s so the page stays accurate without a reload
  const { data: liveDetail, dataUpdatedAt } = useQuery({
    queryKey: queryKeys.products.stock(slug),
    queryFn: () => api.get<ProductDetail>(`/products/${slug}`),
    refetchInterval: 60_000,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  const liveProduct = liveDetail ? toProductDetail(liveDetail) : product;
  const hasVariants = (liveProduct.variants?.length ?? 0) > 0;
  const currentVariant = selectedVariant
    ? (liveProduct.variants?.find((v) => v.id === selectedVariant.id) ?? selectedVariant)
    : null;

  const wished = wishlistItems.some(
    (i) => i.id === product.id && i.variantId === (currentVariant?.id ?? undefined),
  );

  const liveAvailableStock = liveProduct.availableStock;

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
  };

  useEffect(() => {
    setActive(0);
    setSelectedVariant(null);
    setVariantError(false);
  }, [product.id]);

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

  const [showReviewModal, setShowReviewModal] = useState(false);

  const gallery = product.gallery ?? [product.image];
  const galleryLarge = product.galleryLarge ?? gallery;

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
  };

  const handleBuyNow = () => {
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

  // Reservation state — check if current user has an active reservation
  const { isReserved: checkReserved, getReservation } = useActiveReservations();

  // Show Notify Me / sold-out state when product has no variants and is out of stock
  const globalSoldOut =
    !hasVariants && liveAvailableStock === 0 && !checkReserved(product.id, null);

  const currentReservation = hasVariants
    ? currentVariant
      ? getReservation(product.id, currentVariant.id)
      : undefined
    : getReservation(product.id, null);
  const isCurrentSelectionReserved = !!currentReservation;

  // When reserved, treat as "in stock" for checkout purposes (reservation holds the qty)
  const effectiveInStock = isCurrentSelectionReserved ? true : displayInStock;
  const effectiveAvailableStock = isCurrentSelectionReserved
    ? (currentReservation?.quantity ?? 1)
    : effectiveStock;

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
            {isCurrentSelectionReserved ? (
              <InventoryBadge availableStock={0} isReserved />
            ) : displayInStock !== null ? (
              <InventoryBadge
                availableStock={hasVariants && currentVariant ? variantStock : liveAvailableStock}
              />
            ) : null}
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
                  const variantReserved = outOfStock && checkReserved(product.id, v.id);
                  const isSelected = currentVariant?.id === v.id;
                  return (
                    <button
                      key={v.id}
                      type="button"
                      onClick={() =>
                        outOfStock && !variantReserved ? undefined : selectVariant(v)
                      }
                      disabled={outOfStock && !variantReserved}
                      aria-pressed={isSelected}
                      aria-label={`${v.name}${variantReserved ? " — reserved for you" : outOfStock ? " — sold out" : vStock <= 5 ? ` — only ${vStock} left` : ""}`}
                      className={`relative px-3.5 py-2 text-xs border transition-all ${
                        isSelected
                          ? "bg-foreground text-background border-foreground"
                          : variantReserved
                            ? "border-blue-400 text-blue-600"
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
                      {variantReserved && (
                        <span className="absolute -top-2 left-1/2 -translate-x-1/2 text-[9px] uppercase tracking-wide text-blue-600">
                          reserved
                        </span>
                      )}
                      {outOfStock && !variantReserved && (
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

          {/* ── Reservation banner ── */}
          {isCurrentSelectionReserved && currentReservation && (
            <div className="mt-8 flex items-center gap-3 p-4 bg-blue-50 border border-blue-200">
              <Clock className="size-5 shrink-0 text-blue-600" aria-hidden />
              <div>
                <p className="text-sm font-medium text-blue-900">This item is reserved for you</p>
                <p className="text-xs text-blue-700 mt-0.5">
                  {currentReservation.quantity}× {currentReservation.product_name}
                  {currentReservation.variant_name ? ` — ${currentReservation.variant_name}` : ""} ·
                  Expires{" "}
                  {new Date(currentReservation.expires_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
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
                  max={
                    isCurrentSelectionReserved
                      ? (currentReservation?.quantity ?? 1)
                      : bounds.remainingAllowed > 0
                        ? bounds.remainingAllowed
                        : 1
                  }
                  disabled={
                    !isCurrentSelectionReserved && effectiveInStock !== null && !bounds.canAdd
                  }
                />
                {effectiveAvailableStock > 0 &&
                  effectiveAvailableStock <= 10 &&
                  bounds.canAdd &&
                  !isCurrentSelectionReserved && (
                    <span className="text-xs text-amber-600">
                      Only {effectiveAvailableStock} left
                    </span>
                  )}
                <button
                  onClick={handleAddToCart}
                  disabled={
                    effectiveInStock === false || (!isCurrentSelectionReserved && !bounds.canAdd)
                  }
                  className="flex-1 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {effectiveInStock === false
                    ? "Out of Stock"
                    : !bounds.canAdd && !isCurrentSelectionReserved
                      ? "Max Qty in Cart"
                      : isCurrentSelectionReserved
                        ? "Add Reserved to Cart"
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
              {bounds.limitMessage && !isCurrentSelectionReserved && (
                <p className="mt-2 text-xs text-amber-700 flex items-center gap-1" role="status">
                  <AlertTriangle className="size-3 shrink-0" aria-hidden />
                  {bounds.limitMessage}
                </p>
              )}
              <button
                onClick={handleBuyNow}
                disabled={
                  effectiveInStock === false || (!isCurrentSelectionReserved && !bounds.canAdd)
                }
                className="mt-3 w-full border border-foreground text-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-foreground hover:text-background transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isCurrentSelectionReserved ? "Buy Reserved Now" : "Buy It Now"}
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

      {/* Tabs */}
      <div
        id="product-reviews"
        ref={reviewsRef}
        className="px-4 md:px-8 py-10 border-t border-border"
        style={{ scrollMarginTop: "140px" }}
      >
        <div
          role="tablist"
          className="flex gap-8 text-xs uppercase tracking-[0.22em] border-b border-border"
        >
          {(["details", "specs", "reviews"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              id={`tab-${t}`}
              aria-selected={tab === t}
              aria-controls={`panel-${t}`}
              onClick={() => setTab(t)}
              className={`pb-3 -mb-px border-b-2 transition ${tab === t ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              {t === "details" ? "Details" : t === "specs" ? "Specifications" : "Reviews"}
            </button>
          ))}
        </div>
        <div
          role="tabpanel"
          id={`panel-${tab}`}
          aria-labelledby={`tab-${tab}`}
          className="py-8 max-w-3xl"
        >
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
                queryClient.invalidateQueries({
                  queryKey: queryKeys.reviews.forProduct(product.id),
                });
                queryClient.invalidateQueries({ queryKey: queryKeys.reviews.summary(product.id) });
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

      {showReviewModal && (
        <WriteReviewModal
          productId={product.id}
          onClose={() => setShowReviewModal(false)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: queryKeys.reviews.forProduct(product.id) });
            queryClient.invalidateQueries({ queryKey: queryKeys.reviews.summary(product.id) });
          }}
        />
      )}
    </SiteLayout>
  );
}

// ── Reviews section ────────────────────────────────────────────────────────────

function StarRating({
  value,
  onChange,
  size = "md",
}: {
  value: number;
  onChange?: (v: number) => void;
  size?: "sm" | "md" | "lg";
}) {
  const [hovered, setHovered] = useState(0);
  const sz = size === "lg" ? "size-7" : size === "md" ? "size-5" : "size-3.5";
  return (
    <div className="flex gap-1">
      {Array.from({ length: 5 }).map((_, i) => {
        const filled = i < (hovered || value);
        return (
          <button
            key={i}
            type="button"
            onClick={() => onChange?.(i + 1)}
            onMouseEnter={() => onChange && setHovered(i + 1)}
            onMouseLeave={() => onChange && setHovered(0)}
            className={`${onChange ? "cursor-pointer" : "cursor-default pointer-events-none"}`}
            aria-label={`Rate ${i + 1} star${i > 0 ? "s" : ""}`}
          >
            <Star
              className={`${sz} ${filled ? "fill-accent text-accent" : "text-border"} transition-colors`}
            />
          </button>
        );
      })}
    </div>
  );
}

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

function WriteReviewModal({
  productId,
  onClose,
  onSuccess,
}: {
  productId: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  // Focus trap: save previous focus, move focus into modal, restore on close
  useEffect(() => {
    previousFocusRef.current = document.activeElement as HTMLElement;
    // Focus the close button as the first interactive element
    const closeBtn = modalRef.current?.querySelector<HTMLElement>("[aria-label='Close']");
    closeBtn?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = modalRef.current?.querySelectorAll<HTMLElement>(
        "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
      );
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [onClose]);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImage(file);
    setImagePreview(URL.createObjectURL(file));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (rating === 0) {
      toast.error("Please select a rating.");
      return;
    }
    if (!body.trim()) {
      toast.error("Please write a review description.");
      return;
    }
    setSubmitting(true);
    try {
      const form = new FormData();
      form.append("product_id", productId);
      form.append("rating", String(rating));
      form.append("body", body.trim());
      if (image) form.append("images", image);

      await api.upload("/reviews", form);
      toast.success("Review submitted! It will appear after approval.");
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message ?? "Failed to submit review.";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 backdrop-blur-sm p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label="Write a review"
    >
      <div
        ref={modalRef}
        className="bg-background border border-border w-full max-w-md p-6 relative"
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
          aria-label="Close"
        >
          <X className="size-5" />
        </button>
        <h2 className="font-display text-2xl mb-1">Write a Review</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Your review will be visible after admin approval.
        </p>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground block mb-2">
              Rating <span className="text-destructive">*</span>
            </label>
            <StarRating value={rating} onChange={setRating} size="lg" />
          </div>
          <div>
            <label
              htmlFor="review-body"
              className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground block mb-2"
            >
              Review <span className="text-destructive">*</span>
            </label>
            <textarea
              id="review-body"
              rows={4}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Share your experience with this product…"
              className="w-full border border-border bg-background px-3 py-2.5 text-sm resize-none focus:outline-none focus:border-foreground transition"
              maxLength={2000}
            />
            <p className="text-[11px] text-muted-foreground mt-1 text-right">{body.length}/2000</p>
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground block mb-2">
              Photo (optional)
            </label>
            {imagePreview ? (
              <div className="relative inline-block">
                <img
                  src={imagePreview}
                  alt="Preview"
                  className="size-20 object-cover border border-border"
                />
                <button
                  type="button"
                  onClick={() => {
                    setImage(null);
                    setImagePreview(null);
                  }}
                  className="absolute -top-2 -right-2 bg-destructive text-destructive-foreground rounded-full size-5 flex items-center justify-center"
                  aria-label="Remove image"
                >
                  <X className="size-3" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2 border border-dashed border-border px-4 py-3 text-sm text-muted-foreground hover:border-foreground hover:text-foreground transition"
              >
                <Upload className="size-4" />
                Upload photo
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleImageChange}
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Submitting…" : "Submit Review"}
          </button>
        </form>
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
