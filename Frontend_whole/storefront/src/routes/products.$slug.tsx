import { useState, useEffect, useRef, useCallback } from "react";
import { createFileRoute, Link, notFound, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
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
} from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { QuantityStepper } from "@/components/site/QuantityStepper";
import { ProductGrid } from "@/components/site/ProductGrid";
import { InventoryBadge } from "@/components/site/InventoryBadge";
import { useCart, cartLineKey } from "@/stores/cart";
import { computeQuantityBounds } from "@/lib/cartQuantity";
import { useWishlist } from "@/stores/wishlist";
import { useRecentlyViewed } from "@/stores/recentlyViewed";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toProductDetail, toProduct, toReview } from "@/lib/api/mappers";
import type { ProductListResponse } from "@/types/admin";
import type { ProductDetail, ProductVariant, PublicReview, ReviewSummary } from "@/types/public";
import type { Product, ProductSpec } from "@/types/shop";

export const Route = createFileRoute("/products/$slug")({
  loader: async ({ params }) => {
    const productDetail = await api
      .get<ProductDetail>(`/products/${params.slug}`)
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
  const pushRV = useRecentlyViewed((s) => s.push);

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

  useEffect(() => {
    pushRV(product.id);
    setActive(0);
    setSelectedVariant(null);
    setVariantError(false);
  }, [product.id, pushRV]);

  const { data: rawReviews } = useQuery({
    queryKey: queryKeys.reviews.forProduct(product.id),
    queryFn: () =>
      api.get<PublicReview[]>(`/reviews/products/${product.id}`, { params: { limit: 20 } }),
    staleTime: 5 * 60_000,
  });
  const reviews = (rawReviews ?? []).map(toReview);

  const { data: reviewSummary } = useQuery({
    queryKey: queryKeys.reviews.summary(product.id),
    queryFn: () => api.get<ReviewSummary>(`/reviews/products/${product.id}/summary`),
    staleTime: 5 * 60_000,
  });

  const avgRating = reviewSummary?.average_rating ?? 5;
  const reviewCount = reviewSummary?.review_count ?? 0;

  const gallery = product.gallery ?? [product.image];
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
                className={`shrink-0 w-20 h-20 bg-secondary overflow-hidden border ${active === i ? "border-foreground" : "border-transparent"}`}
              >
                <img src={img} alt="" className="w-full h-full object-cover" />
              </button>
            ))}
          </div>
          <div className="relative aspect-square bg-secondary overflow-hidden group max-lg:order-1">
            <img
              src={gallery[active]}
              alt={product.name}
              className={`absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-110 ${globalSoldOut ? "opacity-60" : ""}`}
            />
            {globalSoldOut && (
              <div className="absolute inset-0 flex items-center justify-center" aria-hidden>
                <span className="bg-foreground/80 text-background text-sm tracking-[0.24em] uppercase px-6 py-2">
                  Sold Out
                </span>
              </div>
            )}
            {product.badge && !globalSoldOut && (
              <span className="absolute top-4 left-4 bg-primary text-primary-foreground text-[11px] tracking-[0.2em] uppercase px-3 py-1.5">
                {product.badge}
              </span>
            )}
          </div>
        </div>

        {/* Info */}
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
            SKU · {displaySku}
          </p>
          <h1 className="font-display text-3xl md:text-4xl mt-2 leading-tight">{product.name}</h1>

          <button
            type="button"
            onClick={scrollToReviews}
            aria-label="Jump to customer reviews"
            className="flex items-center gap-3 mt-3 cursor-pointer group focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground rounded-sm"
          >
            <div className="flex">
              {Array.from({ length: 5 }).map((_, i) => (
                <Star
                  key={i}
                  className={`size-4 ${i < Math.round(avgRating) ? "fill-accent text-accent" : "text-border"}`}
                />
              ))}
            </div>
            <span className="text-xs text-muted-foreground group-hover:text-foreground group-hover:underline transition-colors">
              {reviewCount} reviews
            </span>
          </button>

          <div className="flex items-baseline gap-3 mt-5">
            <span className="font-display text-3xl">{formatINR(displayPrice)}</span>
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
            <p className="text-sm leading-relaxed text-foreground/80">{product.description}</p>
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
            <div className="space-y-6">
              {reviews.map((r) => (
                <div key={r.id} className="border-b border-border pb-5">
                  <div className="flex gap-1 mb-1.5">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Star
                        key={i}
                        className={`size-3.5 ${i < r.rating ? "fill-accent text-accent" : "text-border"}`}
                      />
                    ))}
                  </div>
                  <p className="font-display">{r.name}</p>
                  <p className="text-sm text-foreground/80 mt-1">{r.text}</p>
                </div>
              ))}
              {reviews.length === 0 && (
                <p className="text-sm text-muted-foreground">No reviews yet.</p>
              )}
            </div>
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
    </SiteLayout>
  );
}
