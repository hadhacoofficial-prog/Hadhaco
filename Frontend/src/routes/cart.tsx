import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQueries } from "@tanstack/react-query";
import { ShoppingBag, Trash2, Tag, AlertTriangle, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { EmptyState } from "@/components/site/EmptyState";
import { QuantityStepper } from "@/components/site/QuantityStepper";
import { InventoryBadge } from "@/components/site/InventoryBadge";
import { useCart } from "@/stores/cart";
import { api } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import { queryKeys } from "@/lib/api/queryKeys";
import type { ProductDetail } from "@/types/public";
import type { CouponValidateResponse } from "@/types/customer";

export const Route = createFileRoute("/cart")({
  head: () => ({ meta: [{ title: "Cart · Hadha" }] }),
  component: CartPage,
});

function CartPage() {
  const { lines, setQty, remove, subtotal } = useCart();
  const [coupon, setCoupon] = useState("");
  const [pin, setPin] = useState("");
  const [shipping, setShipping] = useState<number | null>(null);
  const [discount, setDiscount] = useState(0);
  const [appliedCode, setAppliedCode] = useState<string | null>(null);

  // Fetch live stock for every cart line (polls every 60 s)
  const stockQueries = useQueries({
    queries: lines.map((line) => ({
      queryKey: queryKeys.products.stock(line.snapshot?.slug ?? `product-${line.productId}`),
      queryFn: () => api.get<ProductDetail>(`/products/${line.snapshot!.slug}`),
      enabled: !!line.snapshot?.slug,
      staleTime: 30_000,
      refetchInterval: 60_000,
      refetchOnWindowFocus: true,
      select: (data: ProductDetail) => ({
        productId: line.productId,
        availableStock: data.available_stock ?? data.stock_quantity,
      }),
    })),
  });

  // Build productId → availableStock map
  const stockMap: Record<string, number> = {};
  stockQueries.forEach((q) => {
    if (q.data) stockMap[q.data.productId] = q.data.availableStock;
  });

  // Detect items where cart qty exceeds available stock
  const stockIssues = lines.filter(
    (line) =>
      stockMap[line.productId] !== undefined && line.qty > (stockMap[line.productId] ?? Infinity),
  );
  const hasStockIssues = stockIssues.length > 0;

  // Any item with zero available stock
  const soldOutItems = lines.filter((line) => (stockMap[line.productId] ?? 1) === 0);

  const subtotalAmt = subtotal();
  const ship = shipping ?? (subtotalAmt > 999 ? 0 : 99);
  const total = subtotalAmt - discount + (lines.length ? ship : 0);

  const couponMutation = useMutation({
    mutationFn: (code: string) =>
      api.post<CouponValidateResponse>("/coupons/validate", {
        body: { code, order_amount: subtotalAmt },
      }),
    onSuccess: (res) => {
      if (res.valid) {
        setDiscount(res.discount_amount);
        setAppliedCode(res.coupon?.code ?? coupon.trim().toUpperCase());
        toast.success(`Coupon applied — ${formatINR(res.discount_amount)} off`);
      } else {
        setDiscount(0);
        setAppliedCode(null);
        toast.error(res.message || "Invalid coupon code");
      }
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  function applyCoupon() {
    const code = coupon.trim();
    if (!code) return;
    couponMutation.mutate(code);
  }

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-6xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Cart" }]} />
        <h1 className="font-display text-4xl md:text-5xl mt-6 mb-10">Shopping Cart</h1>

        {lines.length === 0 ? (
          <EmptyState
            icon={<ShoppingBag className="size-5" />}
            title="Your cart is empty"
            description="Discover pieces handcrafted in sterling silver."
            action={
              <Link
                to="/collections"
                className="inline-block bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
              >
                Start Shopping
              </Link>
            }
          />
        ) : (
          <div className="grid lg:grid-cols-[1fr_380px] gap-10">
            <div>
              {/* Stock issues banner */}
              {hasStockIssues && (
                <div
                  className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 mb-4"
                  role="alert"
                  aria-live="polite"
                >
                  <AlertTriangle className="size-4 shrink-0 text-amber-600 mt-0.5" aria-hidden />
                  <div className="text-sm">
                    <p className="font-medium text-amber-900">Stock has changed</p>
                    <p className="text-amber-700 mt-0.5">
                      {soldOutItems.length > 0
                        ? "Some items are now sold out. Remove them before checking out."
                        : "Quantities for some items exceed available stock. Adjust before checking out."}
                    </p>
                  </div>
                </div>
              )}

              <div className="border-y border-border divide-y divide-border">
                <div className="hidden md:grid grid-cols-[1fr_140px_140px_40px] gap-4 py-3 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                  <span>Product</span>
                  <span>Quantity</span>
                  <span className="text-right">Total</span>
                  <span />
                </div>
                {lines.map((line) => {
                  const available = stockMap[line.productId];
                  const isSoldOut = available !== undefined && available === 0;
                  const isOverQty = available !== undefined && line.qty > available;

                  return (
                    <div
                      key={`${line.productId}::${line.variantId ?? ""}`}
                      className={`grid grid-cols-[80px_1fr] md:grid-cols-[100px_1fr_140px_140px_40px] gap-4 py-5 items-start ${isSoldOut ? "opacity-60" : ""}`}
                    >
                      {line.snapshot ? (
                        <Link
                          to="/products/$slug"
                          params={{ slug: line.snapshot.slug }}
                          className="block w-20 md:w-24 aspect-square bg-secondary overflow-hidden"
                        >
                          <img
                            src={line.snapshot.image}
                            alt={line.snapshot.name}
                            className="w-full h-full object-cover"
                          />
                        </Link>
                      ) : (
                        <div className="w-20 md:w-24 aspect-square bg-secondary" />
                      )}

                      <div className="min-w-0">
                        {line.snapshot ? (
                          <Link
                            to="/products/$slug"
                            params={{ slug: line.snapshot.slug }}
                            className="font-display text-base hover:text-accent line-clamp-2"
                          >
                            {line.snapshot.name}
                          </Link>
                        ) : (
                          <span className="font-display text-base text-muted-foreground">
                            Product
                          </span>
                        )}
                        {line.snapshot?.variantName && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {line.snapshot.variantName}
                          </p>
                        )}
                        {line.snapshot && (
                          <p className="text-xs text-muted-foreground mt-1">
                            SKU · {line.snapshot.sku}
                          </p>
                        )}

                        {/* Available stock badge */}
                        {available !== undefined && (
                          <div className="mt-2">
                            <InventoryBadge availableStock={available} />
                          </div>
                        )}

                        {/* Over-qty warning */}
                        {isOverQty && !isSoldOut && (
                          <p className="mt-1.5 text-[11px] text-amber-700 flex items-center gap-1">
                            <AlertTriangle className="size-3 shrink-0" aria-hidden />
                            Only {available} available — reduce quantity
                          </p>
                        )}

                        <p className="font-display mt-1 md:hidden">
                          {line.snapshot ? formatINR(line.snapshot.price) : "—"}
                        </p>
                        <div className="mt-3 md:hidden flex items-center justify-between">
                          {isSoldOut ? (
                            <span className="text-xs text-destructive uppercase tracking-[0.18em]">
                              Sold Out
                            </span>
                          ) : (
                            <QuantityStepper
                              value={line.qty}
                              onChange={(n) => setQty(line.productId, n, line.variantId)}
                              max={available ?? 99}
                            />
                          )}
                          <button
                            onClick={() => remove(line.productId, line.variantId)}
                            aria-label={`Remove ${line.snapshot?.name ?? "item"}`}
                            className="text-muted-foreground hover:text-destructive transition"
                          >
                            <Trash2 className="size-4" />
                          </button>
                        </div>
                      </div>

                      <div className="hidden md:block">
                        {isSoldOut ? (
                          <span className="text-xs text-destructive uppercase tracking-[0.18em]">
                            Sold Out
                          </span>
                        ) : (
                          <QuantityStepper
                            value={line.qty}
                            onChange={(n) => setQty(line.productId, n, line.variantId)}
                            max={available ?? 99}
                          />
                        )}
                      </div>

                      <div className="hidden md:block text-right font-display">
                        {line.snapshot ? formatINR(line.snapshot.price * line.qty) : "—"}
                      </div>

                      <button
                        onClick={() => remove(line.productId, line.variantId)}
                        aria-label={`Remove ${line.snapshot?.name ?? "item"}`}
                        className="hidden md:flex justify-end text-muted-foreground hover:text-destructive transition"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  );
                })}
              </div>

              {/* Live stock indicator */}
              <p className="mt-3 text-[10px] text-muted-foreground/60 flex items-center gap-1">
                <RefreshCw className="size-3" aria-hidden />
                Stock availability refreshes automatically
              </p>
            </div>

            <aside className="space-y-6">
              <div className="border border-border bg-card p-6">
                <h2 className="font-display text-xl mb-4">Order Summary</h2>
                <div className="space-y-2 text-sm">
                  <Row label="Subtotal" value={formatINR(subtotalAmt)} />
                  {discount > 0 && appliedCode && (
                    <Row
                      label={`Discount (${appliedCode})`}
                      value={`- ${formatINR(discount)}`}
                      accent
                    />
                  )}
                  <Row
                    label="Shipping"
                    value={lines.length && ship === 0 ? "Free" : formatINR(ship)}
                  />
                </div>
                <div className="border-t border-border mt-4 pt-4 flex justify-between items-baseline">
                  <span className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
                    Total
                  </span>
                  <span className="font-display text-2xl">{formatINR(total)}</span>
                </div>

                {hasStockIssues ? (
                  <div className="mt-5 space-y-2">
                    <p className="text-xs text-amber-700 text-center flex items-center justify-center gap-1">
                      <AlertTriangle className="size-3.5" aria-hidden />
                      Resolve stock issues to checkout
                    </p>
                    <button
                      disabled
                      className="w-full bg-primary/40 text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 cursor-not-allowed"
                      aria-disabled="true"
                    >
                      Proceed to Checkout
                    </button>
                  </div>
                ) : (
                  <Link
                    to="/checkout"
                    className="mt-5 w-full inline-flex justify-center bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition"
                  >
                    Proceed to Checkout
                  </Link>
                )}

                <Link
                  to="/collections"
                  className="mt-3 w-full inline-flex justify-center text-xs uppercase tracking-[0.18em] underline underline-offset-4 text-muted-foreground hover:text-foreground"
                >
                  Continue Shopping
                </Link>
              </div>

              <div className="border border-border bg-card p-6">
                <label className="text-xs uppercase tracking-[0.22em] flex items-center gap-2 mb-3">
                  <Tag className="size-3.5" /> Coupon code
                </label>
                <div className="flex gap-2">
                  <input
                    value={coupon}
                    onChange={(e) => setCoupon(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && applyCoupon()}
                    placeholder="HADHA10"
                    className="flex-1 bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground"
                  />
                  <button
                    onClick={applyCoupon}
                    disabled={couponMutation.isPending || !coupon.trim()}
                    className="bg-foreground text-background px-4 text-[11px] uppercase tracking-[0.22em] disabled:opacity-50"
                  >
                    {couponMutation.isPending ? "…" : "Apply"}
                  </button>
                </div>
              </div>

              <div className="border border-border bg-card p-6">
                <label className="text-xs uppercase tracking-[0.22em] mb-3 block">
                  Estimate shipping
                </label>
                <div className="flex gap-2">
                  <input
                    value={pin}
                    onChange={(e) => setPin(e.target.value)}
                    maxLength={6}
                    placeholder="Pincode"
                    className="flex-1 bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground"
                  />
                  <button
                    onClick={() =>
                      setShipping(pin.length === 6 ? (subtotalAmt > 999 ? 0 : 99) : null)
                    }
                    className="bg-foreground text-background px-4 text-[11px] uppercase tracking-[0.22em]"
                  >
                    Check
                  </button>
                </div>
              </div>
            </aside>
          </div>
        )}
      </div>
    </SiteLayout>
  );
}

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`flex justify-between ${accent ? "text-accent" : ""}`}>
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}
