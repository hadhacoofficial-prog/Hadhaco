import { useEffect, useRef } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import {
  CheckCircle2,
  Package,
  Truck,
  Star,
  ShoppingBag,
  CreditCard,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { afterOrderCreated } from "@hadha/shared-api";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { formatINR } from "@/lib/format";
import type { CustomerOrderResponse, OrderListResponse } from "@/types/customer";

export const Route = createFileRoute("/checkout_/success")({
  validateSearch: z.object({
    order: z.string().optional(), // human-readable order number
    orderId: z.string().optional(), // UUID — enables direct fetch without list scan
  }),
  head: () => ({ meta: [{ title: "Order Confirmed · Hadha" }] }),
  component: SuccessPage,
});

// ── Status helpers ─────────────────────────────────────────────────────────────

const ORDER_STATUS_STEPS = [
  { key: "placed", label: "Order placed", icon: CheckCircle2 },
  { key: "processing", label: "Processing", icon: Package },
  { key: "shipped", label: "Shipped", icon: Truck },
  { key: "delivered", label: "Delivered", icon: Star },
] as const;

const STATUS_ORDER = ["pending", "processing", "confirmed", "shipped", "delivered"];

function statusIndex(status: string) {
  const idx = STATUS_ORDER.indexOf(status.toLowerCase());
  return idx === -1 ? 0 : idx;
}

function StatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const cls =
    s === "delivered"
      ? "bg-emerald-100 text-emerald-800"
      : s === "shipped"
        ? "bg-blue-100 text-blue-800"
        : s === "cancelled"
          ? "bg-red-100 text-red-800"
          : "bg-secondary text-foreground";
  return (
    <span className={`inline-block text-[10px] uppercase tracking-[0.22em] px-3 py-1 ${cls}`}>
      {status}
    </span>
  );
}

function PaymentBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const cls =
    s === "paid"
      ? "bg-emerald-100 text-emerald-800"
      : s === "failed"
        ? "bg-red-100 text-red-800"
        : "bg-secondary text-foreground";
  return (
    <span className={`inline-block text-[10px] uppercase tracking-[0.22em] px-3 py-1 ${cls}`}>
      {status}
    </span>
  );
}

// ── Timeline ───────────────────────────────────────────────────────────────────

function OrderTimeline({ status }: { status: string }) {
  const current = statusIndex(status);
  const steps = [
    { label: "Order placed", sub: "Payment received", threshold: 0 },
    { label: "Processing", sub: "Handcrafted & quality-checked", threshold: 1 },
    { label: "Shipped", sub: "On the way to you", threshold: 3 },
    { label: "Delivered", sub: "Enjoy your piece", threshold: 4 },
  ];

  return (
    <div className="relative">
      {/* connector line */}
      <div className="absolute left-[13px] top-6 bottom-6 w-px bg-border" />
      <div className="space-y-5">
        {steps.map((step, i) => {
          const done = current >= step.threshold;
          const active = done && (i === steps.length - 1 || current < steps[i + 1].threshold);
          return (
            <div key={step.label} className="flex items-start gap-4 relative">
              <div
                className={`relative z-10 size-7 rounded-full flex items-center justify-center border-2 shrink-0 ${
                  done
                    ? "bg-accent border-accent text-accent-foreground"
                    : "bg-background border-border text-muted-foreground"
                } ${active ? "ring-4 ring-accent/20" : ""}`}
              >
                {done ? (
                  <CheckCircle2 className="size-3.5" />
                ) : (
                  <span className="size-2 rounded-full bg-border" />
                )}
              </div>
              <div className="pt-0.5">
                <p
                  className={`text-sm font-medium ${done ? "text-foreground" : "text-muted-foreground"}`}
                >
                  {step.label}
                </p>
                <p className="text-xs text-muted-foreground">{step.sub}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function SuccessSkeleton() {
  return (
    <div className="px-4 md:px-8 py-12 max-w-3xl mx-auto">
      <div className="text-center mb-10">
        <div className="mx-auto size-16 rounded-full bg-muted animate-pulse mb-6" />
        <Skeleton className="h-5 w-40 mx-auto mb-3" />
        <Skeleton className="h-10 w-72 mx-auto mb-2" />
        <Skeleton className="h-4 w-56 mx-auto" />
      </div>
      <div className="border border-border bg-card p-6 space-y-4">
        <div className="flex justify-between">
          <div className="space-y-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-44" />
          </div>
          <Skeleton className="h-6 w-20" />
        </div>
        <div className="grid grid-cols-2 gap-4 py-4 border-y border-border">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="space-y-1.5">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-4 w-24" />
            </div>
          ))}
        </div>
        <div className="space-y-3 py-2">
          {[1, 2].map((i) => (
            <div key={i} className="flex justify-between items-start">
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-3 w-24" />
              </div>
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
        <div className="pt-4 border-t space-y-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="flex justify-between">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-16" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Error states ───────────────────────────────────────────────────────────────

function OrderNotFoundState({
  orderNumber,
  onRetry,
}: {
  orderNumber: string;
  onRetry: () => void;
}) {
  return (
    <div className="px-4 md:px-8 py-20 max-w-xl mx-auto text-center">
      <div className="mx-auto size-16 rounded-full bg-destructive/10 flex items-center justify-center text-destructive mb-6">
        <AlertCircle className="size-8" />
      </div>
      <h1 className="font-display text-3xl">Order not found</h1>
      <p className="text-sm text-muted-foreground mt-3">
        We couldn't load details for order{" "}
        <span className="font-medium text-foreground">{orderNumber}</span>.
      </p>
      <p className="text-sm text-muted-foreground mt-1">
        Your payment may have succeeded. Check your email for a confirmation, or view your orders.
      </p>
      <div className="mt-8 flex flex-col sm:flex-row justify-center gap-3">
        <button
          onClick={onRetry}
          className="inline-flex items-center justify-center gap-2 border border-foreground text-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3 hover:bg-foreground hover:text-background transition"
        >
          <RefreshCw className="size-3.5" />
          Retry
        </button>
        <Link
          to="/account"
          search={{ tab: "orders" }}
          className="inline-flex items-center justify-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
        >
          <ShoppingBag className="size-3.5" />
          View Orders
        </Link>
        <a
          href="mailto:support@hadha.in"
          className="inline-flex items-center justify-center gap-2 border border-border text-[11px] uppercase tracking-[0.22em] px-6 py-3 hover:bg-secondary transition"
        >
          Contact Support
        </a>
      </div>
    </div>
  );
}

function NoIdentifierState() {
  return (
    <div className="px-4 md:px-8 py-20 max-w-xl mx-auto text-center">
      <div className="mx-auto size-16 rounded-full bg-secondary flex items-center justify-center mb-6">
        <Package className="size-8 text-muted-foreground" />
      </div>
      <h1 className="font-display text-3xl">No order specified</h1>
      <p className="text-sm text-muted-foreground mt-3">
        This page requires an order number. Please navigate here from the checkout flow.
      </p>
      <div className="mt-8 flex justify-center gap-3">
        <Link
          to="/account"
          search={{ tab: "orders" }}
          className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
        >
          View Orders
        </Link>
        <Link
          to="/collections"
          className="border border-foreground text-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3 hover:bg-foreground hover:text-background transition"
        >
          Shop Now
        </Link>
      </div>
    </div>
  );
}

// ── Success content ────────────────────────────────────────────────────────────

function SuccessContent({ order }: { order: CustomerOrderResponse }) {
  const date = new Date(order.created_at).toLocaleDateString("en-IN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const time = new Date(order.created_at).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
  });

  const methodLabel = order.payment_method === "razorpay" ? "Razorpay" : order.payment_method;

  return (
    <div className="px-4 md:px-8 py-12 max-w-3xl mx-auto">
      {/* ── Hero ── */}
      <div className="text-center mb-10">
        <div
          className="mx-auto size-18 w-[72px] h-[72px] rounded-full bg-accent/15 flex items-center justify-center text-accent mb-6"
          style={{ animation: "scale-in 0.4s cubic-bezier(0.34,1.56,0.64,1) both" }}
        >
          <CheckCircle2 className="size-9" />
        </div>
        <p className="text-[11px] uppercase tracking-[0.3em] text-accent">Payment Successful</p>
        <h1 className="font-display text-4xl md:text-5xl mt-2">Thank you!</h1>
        <p className="text-sm text-muted-foreground mt-3 max-w-sm mx-auto">
          Your order has been placed and is being processed. A confirmation has been sent to your
          email.
        </p>
      </div>

      {/* ── Order card ── */}
      <div className="border border-border bg-card p-6">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-4 pb-5 border-b border-border">
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Order number
            </p>
            <p className="font-display text-2xl mt-0.5">{order.order_number}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusBadge status={order.status} />
            <PaymentBadge status={order.payment_status} />
          </div>
        </div>

        {/* Meta grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 py-5 border-b border-border text-sm">
          <div>
            <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">
              Date
            </p>
            <p>
              {date}
              <br />
              <span className="text-muted-foreground">{time}</span>
            </p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">
              Payment
            </p>
            <div className="flex items-center gap-1.5">
              <CreditCard className="size-3.5 text-muted-foreground" />
              <span>{methodLabel}</span>
            </div>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">
              Items
            </p>
            <p>
              {order.items.length} {order.items.length === 1 ? "item" : "items"}
            </p>
          </div>
          {order.tracking_number && (
            <div>
              <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">
                Tracking
              </p>
              <p className="font-medium">{order.tracking_number}</p>
            </div>
          )}
        </div>

        {/* Items */}
        <div className="py-5 border-b border-border space-y-4">
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">Items</p>
          {order.items.map((item) => (
            <div key={item.id} className="flex items-start justify-between gap-4 text-sm">
              <div className="flex-1 min-w-0">
                <p className="leading-snug">{item.product_name}</p>
                {item.variant_name && (
                  <p className="text-xs text-muted-foreground mt-0.5">{item.variant_name}</p>
                )}
                <p className="text-xs text-muted-foreground mt-0.5">
                  Qty {item.quantity} · SKU {item.product_sku}
                  {item.quantity > 1 && (
                    <span className="ml-1">({formatINR(item.unit_price)} each)</span>
                  )}
                </p>
              </div>
              <p className="font-sans font-bold shrink-0">{formatINR(item.line_total)}</p>
            </div>
          ))}
        </div>

        {/* Totals */}
        <div className="pt-5 space-y-2 text-sm">
          <TotalRow label="Subtotal" value={formatINR(order.subtotal)} />
          {order.discount > 0 && (
            <TotalRow
              label={`Discount${order.coupon_code ? ` (${order.coupon_code})` : ""}`}
              value={`−${formatINR(order.discount)}`}
              accent
            />
          )}
          <TotalRow label="Tax (GST, included in price)" value={formatINR(order.tax_amount)} />
          <TotalRow
            label="Shipping"
            value={order.shipping_charge === 0 ? "Free" : formatINR(order.shipping_charge)}
          />
          <div className="pt-3 border-t border-border">
            <TotalRow label="Total" value={formatINR(order.total)} bold />
          </div>
        </div>

        {/* Complimentary Gift */}
        {order.complimentary_gift && (
          <div className="mt-4 pt-4 border-t border-border flex items-center gap-3 text-sm">
            <span className="text-lg">
              {order.complimentary_gift === "Traditional Sweet" ? "🍬" : "🌶️"}
            </span>
            <div>
              <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-0.5">
                Complimentary Gift
              </p>
              <p className="font-medium">{order.complimentary_gift}</p>
            </div>
          </div>
        )}
      </div>

      {/* ── Timeline ── */}
      <div className="mt-5 border border-border bg-card p-6">
        <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground mb-5">
          Order status
        </p>
        <OrderTimeline status={order.status} />
      </div>

      {/* ── What's next ── */}
      <div className="mt-5 border border-border bg-card p-6">
        <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground mb-4">
          What's next
        </p>
        <ul className="space-y-3 text-sm">
          <li className="flex items-start gap-3">
            <CheckCircle2 className="size-4 mt-0.5 shrink-0 text-accent" />
            <span>
              <span className="font-medium">Confirmation email sent</span> — check your inbox for
              order details and updates.
            </span>
          </li>
          <li className="flex items-start gap-3">
            <Package className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
            <span>
              <span className="font-medium">Handcrafted for you</span> — your piece is being
              quality-checked before dispatch.
            </span>
          </li>
          <li className="flex items-start gap-3">
            <Truck className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
            <span>
              <span className="font-medium">Estimated delivery in 5–7 business days</span> — you'll
              receive a tracking number once shipped.
            </span>
          </li>
        </ul>
      </div>

      {/* ── Actions ── */}
      <div className="mt-8 flex flex-col sm:flex-row justify-center gap-3">
        <Link
          to="/collections"
          className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-8 py-3.5 text-center"
        >
          Continue Shopping
        </Link>
        <Link
          to="/account"
          search={{ tab: "orders" }}
          className="border border-foreground text-foreground text-[11px] uppercase tracking-[0.22em] px-8 py-3.5 text-center inline-flex items-center justify-center gap-2 hover:bg-foreground hover:text-background transition"
        >
          <ShoppingBag className="size-3.5" />
          View All Orders
        </Link>
      </div>
    </div>
  );
}

function TotalRow({
  label,
  value,
  bold,
  accent,
}: {
  label: string;
  value: string;
  bold?: boolean;
  accent?: boolean;
}) {
  return (
    <div className={`flex justify-between ${bold ? "font-sans font-bold text-base" : ""}`}>
      <span className={accent ? "text-accent" : "text-muted-foreground"}>{label}</span>
      <span className={accent ? "text-accent" : ""}>{value}</span>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

function SuccessPage() {
  const { order: orderNumber, orderId } = Route.useSearch();
  const queryClient = useQueryClient();
  const didClean = useRef(false);

  // Single-fire on mount: bust caches so fresh order + cart data is displayed.
  // Store cleanup (cart/buyNow) is handled authoritatively by
  // verifyPaymentMutation.onSuccess in checkout.tsx before navigation.
  useEffect(() => {
    if (didClean.current) return;
    didClean.current = true;
    // Centralized sync: invalidate orders + cart + inventory for all pages
    afterOrderCreated();
  }, []);

  const fetchKey = orderId ?? orderNumber ?? "";

  const {
    data: order,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: queryKeys.orders.detail(fetchKey),
    queryFn: async (): Promise<CustomerOrderResponse> => {
      // Fast path: UUID is in the URL (set by checkout verify-payment flow)
      if (orderId) {
        return api.get<CustomerOrderResponse>(`/orders/${orderId}`);
      }
      // Fallback: scan recent orders by order_number (handles hard-refresh / deep-link)
      const list = await api.get<OrderListResponse>("/orders", {
        params: { page: 1, page_size: 10 },
      });
      const match = list.items.find((o) => o.order_number === orderNumber);
      if (!match) throw new Error("Order not found");
      return api.get<CustomerOrderResponse>(`/orders/${match.id}`);
    },
    enabled: !!(orderId || orderNumber),
    staleTime: 2 * 60_000,
    retry: 2,
  });

  if (!orderId && !orderNumber) {
    return (
      <SiteLayout>
        <NoIdentifierState />
      </SiteLayout>
    );
  }

  if (isLoading) {
    return (
      <SiteLayout>
        <SuccessSkeleton />
      </SiteLayout>
    );
  }

  if (isError || !order) {
    return (
      <SiteLayout>
        <OrderNotFoundState
          orderNumber={orderNumber ?? orderId ?? "Unknown"}
          onRetry={() => refetch()}
        />
      </SiteLayout>
    );
  }

  return (
    <SiteLayout>
      <SuccessContent order={order} />
    </SiteLayout>
  );
}
