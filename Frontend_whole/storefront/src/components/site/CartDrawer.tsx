import { Link } from "@tanstack/react-router";
import { X, ShoppingBag, Trash2, Lock } from "lucide-react";
import { useCart } from "@/stores/cart";
import { useBuyNowStore } from "@/stores/buyNow";
import { useActiveReservations } from "@/hooks/useActiveReservations";
import { useReservationCountdown } from "@/hooks/reservation/useReservationCountdown";
import { formatINR } from "@/lib/format";
import { QuantityStepper } from "@/components/site/QuantityStepper";
import { NavJewelleryBgMobile } from "@/components/site/NavJewelleryBgMobile";

export function CartDrawer() {
  const { isOpen, close, lines, setQty, remove, subtotal } = useCart();
  const clearBuyNow = useBuyNowStore((s) => s.clear);
  const { isReserved, getReservation } = useActiveReservations();
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60]">
      <div className="absolute inset-0 bg-foreground/40" onClick={close} />
      <aside className="absolute right-0 top-0 h-full w-full sm:w-[440px] bg-background flex flex-col shadow-2xl animate-slide-in-right">
        <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
          <NavJewelleryBgMobile />
        </div>

        <div className="relative z-10 flex items-center justify-between px-6 py-5 border-b border-border">
          <h2 className="font-display text-xl">Your Cart ({lines.length})</h2>
          <button onClick={close} aria-label="Close cart">
            <X className="size-5" />
          </button>
        </div>

        {lines.length === 0 ? (
          <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 text-center gap-4">
            <ShoppingBag className="size-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Your cart is empty.</p>
            <button
              onClick={close}
              className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
            >
              Continue Shopping
            </button>
          </div>
        ) : (
          <>
            <div className="relative z-10 flex-1 overflow-y-auto px-6 py-4 divide-y divide-border">
              {lines.map((line) => (
                <div key={`${line.productId}::${line.variantId ?? ""}`} className="flex gap-4 py-4">
                  {line.snapshot ? (
                    <Link
                      to="/products/$slug"
                      params={{ slug: line.snapshot.slug }}
                      onClick={close}
                      className="block w-20 h-20 bg-secondary overflow-hidden shrink-0"
                    >
                      <img
                        src={line.snapshot.image}
                        alt={line.snapshot.name}
                        className="w-full h-full object-cover"
                      />
                    </Link>
                  ) : (
                    <div className="w-20 h-20 bg-secondary shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    {line.snapshot ? (
                      <Link
                        to="/products/$slug"
                        params={{ slug: line.snapshot.slug }}
                        onClick={close}
                        className="text-sm leading-snug line-clamp-2 hover:text-accent"
                      >
                        {line.snapshot.name}
                      </Link>
                    ) : (
                      <span className="text-sm text-muted-foreground">Product</span>
                    )}
                    {line.snapshot?.variantName && (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {line.snapshot.variantName}
                      </p>
                    )}
                    {isReserved(line.productId, line.variantId) && (
                      <ReservationInlineBadge
                        productId={line.productId}
                        variantId={line.variantId}
                      />
                    )}
                    <div className="mt-1 font-sans font-bold">
                      {line.snapshot ? formatINR(line.snapshot.price) : "—"}
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      <QuantityStepper
                        value={line.qty}
                        onChange={(n) => setQty(line.productId, n, line.variantId)}
                      />
                      <button
                        onClick={() => remove(line.productId, line.variantId)}
                        aria-label="Remove"
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="relative z-10 border-t border-border px-6 py-5 space-y-4">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Subtotal</span>
                <span className="font-sans font-bold text-lg">{formatINR(subtotal())}</span>
              </div>
              <p className="text-[11px] text-muted-foreground uppercase tracking-[0.16em]">
                Shipping calculated at checkout
              </p>
              <div className="grid grid-cols-2 gap-2">
                <Link
                  to="/cart"
                  onClick={close}
                  className="border border-foreground text-foreground text-[11px] uppercase tracking-[0.22em] py-3 text-center hover:bg-foreground hover:text-background transition"
                >
                  View Cart
                </Link>
                <Link
                  to="/checkout"
                  onClick={() => {
                    clearBuyNow();
                    close();
                  }}
                  className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3 text-center hover:bg-accent hover:text-accent-foreground transition"
                >
                  Checkout
                </Link>
              </div>
            </div>
          </>
        )}
      </aside>
    </div>
  );
}

function ReservationInlineBadge({
  productId,
  variantId,
}: {
  productId: string;
  variantId?: string | null;
}) {
  const { getReservation } = useActiveReservations();
  const reservation = getReservation(productId, variantId);
  const countdown = useReservationCountdown(reservation?.expires_at ?? null);

  if (!reservation || countdown.isExpired) return null;

  return (
    <span
      role="timer"
      aria-live="polite"
      aria-atomic="true"
      aria-label={`Reserved for you — ${countdown.formatted} remaining`}
      className={`inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.14em] font-medium rounded-sm ${countdown.isUrgent ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"}`}
    >
      <Lock className="size-2.5" aria-hidden />
      Reserved · {countdown.formatted}
    </span>
  );
}
