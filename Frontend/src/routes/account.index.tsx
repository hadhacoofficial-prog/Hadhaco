import { useEffect, useState } from "react";
import { createFileRoute, Link, redirect, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import {
  User, Package, MapPin, LogOut, Heart, Plus, Trash2, Star,
  CheckCircle2, Truck, CreditCard, ChevronDown, ChevronUp,
} from "lucide-react";
import { toast } from "sonner";

import { SiteLayout } from "@/components/site/SiteLayout";
import { PageLoader } from "@/components/common/PageLoader";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { api } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { queryKeys } from "@/lib/api/queryKeys";
import { getSession } from "@/lib/supabase/session";
import { useAuthContext } from "@/providers/auth-context";
import { useWishlist } from "@/stores/wishlist";
import { formatINR } from "@/lib/format";
import { useProfile } from "@/hooks/auth/useProfile";
import { Skeleton } from "@/components/ui/skeleton";
import type { ProfileDto, ProfileUpdateDto } from "@/types/profile";
import type {
  AddressResponse,
  AddressCreateRequest,
  OrderListResponse,
  OrderResponse,
} from "@/types/customer";

const TAB_VALUES = ["overview", "orders", "addresses", "wishlist", "profile"] as const;

export const Route = createFileRoute("/account/")({
  validateSearch: z.object({
    tab: z.enum(TAB_VALUES).optional(),
  }),
  beforeLoad: async () => {
    // During SSR (typeof window === "undefined"), localStorage is unavailable and
    // getSession() always returns null.  Redirecting server-side would send an HTTP 302
    // to /account/login even for authenticated users, because the session lives in the
    // browser's localStorage and cannot be read on the server.
    //
    // Skip the guard on the server.  The AppContent auth gate in __root.tsx shows a
    // loading screen until the Supabase session is restored on the client, then the
    // component-level guard below handles any truly-unauthenticated case.
    if (typeof window === "undefined") return;
    const session = await getSession();
    if (!session) throw redirect({ to: "/account/login", search: { redirect: "/account" } });
  },
  head: () => ({ meta: [{ title: "My Account · Hadha" }] }),
  component: AccountPage,
});

type Tab = (typeof TAB_VALUES)[number];

function AccountPage() {
  const navigate = useNavigate();
  const { tab: initialTab } = Route.useSearch();
  const { user, status, logout } = useAuthContext();
  const [tab, setTab] = useState<Tab>(initialTab ?? "overview");

  // status="loading" is prevented from reaching here by the global AppContent
  // auth gate in __root.tsx, but guard defensively in case of direct mount.
  if (status === "loading") return <PageLoader />;

  if (status === "unauthenticated" || !user) {
    return (
      <SiteLayout>
        <div className="px-4 md:px-8 py-20 max-w-md mx-auto text-center">
          <div className="mx-auto size-14 rounded-full bg-secondary flex items-center justify-center mb-5">
            <User className="size-6" />
          </div>
          <h1 className="font-display text-3xl mb-2">My Account</h1>
          <p className="text-sm text-muted-foreground mb-6">
            Sign in to view your orders, addresses and wishlist.
          </p>
          <div className="flex justify-center gap-3">
            <Link
              to="/account/login"
              className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
            >
              Sign In
            </Link>
            <Link
              to="/account/register"
              className="border border-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
            >
              Register
            </Link>
          </div>
        </div>
      </SiteLayout>
    );
  }

  const displayName = user.user_metadata?.full_name ?? user.email ?? "";

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "overview", label: "Overview", icon: <User className="size-4" /> },
    { id: "orders", label: "Orders", icon: <Package className="size-4" /> },
    { id: "addresses", label: "Addresses", icon: <MapPin className="size-4" /> },
    { id: "wishlist", label: "Wishlist", icon: <Heart className="size-4" /> },
    { id: "profile", label: "Profile", icon: <User className="size-4" /> },
  ];

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-6xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Account" }]} />
        <div className="mt-6 mb-10">
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
            Hello, {displayName.split(" ")[0]}
          </p>
          <h1 className="font-display text-4xl md:text-5xl mt-1">My Account</h1>
        </div>

        <div className="grid lg:grid-cols-[240px_1fr] gap-10">
          <aside className="lg:border-r lg:border-border lg:pr-6 space-y-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 text-sm tracking-wide text-left transition ${tab === t.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60"}`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
            <button
              onClick={async () => {
                await logout();
                navigate({ to: "/" });
              }}
              className="w-full flex items-center gap-3 px-4 py-3 text-sm tracking-wide text-left text-muted-foreground hover:bg-secondary/60 transition mt-6 border-t border-border pt-4"
            >
              <LogOut className="size-4" />
              Sign Out
            </button>
          </aside>

          <div>
            {tab === "overview" && <Overview onNavigate={setTab} />}
            {tab === "orders" && <OrdersTab />}
            {tab === "addresses" && <AddressesTab />}
            {tab === "wishlist" && <WishlistTab />}
            {tab === "profile" && <ProfileTab />}
          </div>
        </div>
      </div>
    </SiteLayout>
  );
}

function Overview({ onNavigate }: { onNavigate: (t: Tab) => void }) {
  const { data: ordersData } = useQuery({
    queryKey: queryKeys.orders.list({}),
    queryFn: () => api.get<OrderListResponse>("/orders", { params: { page: 1, page_size: 1 } }),
    staleTime: 60_000,
  });
  const { data: addresses = [] } = useQuery({
    queryKey: queryKeys.addresses.all,
    queryFn: () => api.get<AddressResponse[]>("/me/addresses"),
    staleTime: 60_000,
  });
  const wishlistItems = useWishlist((s) => s.items);

  const cards = [
    { label: "Orders", value: ordersData?.total ?? 0, tab: "orders" as Tab },
    { label: "Saved Addresses", value: addresses.length, tab: "addresses" as Tab },
    { label: "Wishlist Items", value: wishlistItems.length, tab: "wishlist" as Tab },
  ];

  return (
    <div className="grid sm:grid-cols-3 gap-4">
      {cards.map((c) => (
        <button
          key={c.label}
          onClick={() => onNavigate(c.tab)}
          className="border border-border bg-card p-6 text-left hover:border-foreground transition"
        >
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">{c.label}</p>
          <p className="font-display text-4xl mt-2">{c.value}</p>
        </button>
      ))}
    </div>
  );
}

function OrdersTab() {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.orders.list({}),
    queryFn: () => api.get<OrderListResponse>("/orders", { params: { page: 1, page_size: 20 } }),
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="border border-border bg-card p-5 animate-pulse h-24" />
        ))}
      </div>
    );
  }

  const orders = data?.items ?? [];

  if (orders.length === 0) {
    return (
      <div className="border border-border bg-card p-10 text-center">
        <Package className="size-10 mx-auto text-muted-foreground mb-3" />
        <p className="font-display text-xl">No orders yet</p>
        <p className="text-sm text-muted-foreground mt-1 mb-5">
          Once you place an order it will show up here.
        </p>
        <Link
          to="/collections"
          className="inline-block bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
        >
          Start Shopping
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {orders.map((o) => (
        <OrderCard
          key={o.id}
          order={o}
          expanded={expandedId === o.id}
          onToggle={() => setExpandedId(expandedId === o.id ? null : o.id)}
        />
      ))}
    </div>
  );
}

// ── Order detail helpers ──────────────────────────────────────────────────────

function OrderStatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const cls =
    s === "delivered" ? "bg-accent/15 text-accent"
    : s === "shipped" ? "bg-blue-100 text-blue-800"
    : s === "cancelled" ? "bg-destructive/15 text-destructive"
    : "bg-secondary text-foreground";
  return (
    <span className={`text-[10px] uppercase tracking-[0.22em] px-3 py-1 ${cls}`}>
      {status}
    </span>
  );
}

function PaymentBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const cls =
    s === "paid" ? "bg-emerald-100 text-emerald-800"
    : s === "failed" ? "bg-red-100 text-red-800"
    : "bg-secondary text-foreground";
  return (
    <span className={`text-[10px] uppercase tracking-[0.22em] px-3 py-1 ${cls}`}>
      {status}
    </span>
  );
}

const STATUS_ORDER = ["pending", "processing", "confirmed", "shipped", "delivered"];
function statusIndex(s: string) {
  const i = STATUS_ORDER.indexOf(s.toLowerCase());
  return i === -1 ? 0 : i;
}

function OrderTimeline({ status }: { status: string }) {
  const current = statusIndex(status);
  const steps = [
    { label: "Order placed",  sub: "Payment received",              threshold: 0 },
    { label: "Processing",    sub: "Handcrafted & quality-checked", threshold: 1 },
    { label: "Shipped",       sub: "On the way to you",             threshold: 3 },
    { label: "Delivered",     sub: "Enjoy your piece",              threshold: 4 },
  ];
  return (
    <div className="relative">
      <div className="absolute left-[13px] top-6 bottom-6 w-px bg-border" />
      <div className="space-y-5">
        {steps.map((step, i) => {
          const done = current >= step.threshold;
          const active = done && (i === steps.length - 1 || current < steps[i + 1].threshold);
          return (
            <div key={step.label} className="flex items-start gap-4 relative">
              <div className={`relative z-10 size-7 rounded-full flex items-center justify-center border-2 shrink-0 ${done ? "bg-accent border-accent text-accent-foreground" : "bg-background border-border text-muted-foreground"} ${active ? "ring-4 ring-accent/20" : ""}`}>
                {done ? <CheckCircle2 className="size-3.5" /> : <span className="size-2 rounded-full bg-border" />}
              </div>
              <div className="pt-0.5">
                <p className={`text-sm font-medium ${done ? "text-foreground" : "text-muted-foreground"}`}>{step.label}</p>
                <p className="text-xs text-muted-foreground">{step.sub}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TotalRow({ label, value, bold, accent }: { label: string; value: string; bold?: boolean; accent?: boolean }) {
  return (
    <div className={`flex justify-between text-sm ${bold ? "font-display text-base" : ""}`}>
      <span className={accent ? "text-accent" : "text-muted-foreground"}>{label}</span>
      <span className={accent ? "text-accent" : ""}>{value}</span>
    </div>
  );
}

function OrderDetailSkeleton({ itemCount }: { itemCount: number }) {
  return (
    <div className="mt-5 space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 py-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="space-y-1.5">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </div>
      <div className="space-y-3 py-2 border-t border-border pt-4">
        {Array.from({ length: itemCount }).map((_, i) => (
          <div key={i} className="flex justify-between gap-4">
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/3" />
            </div>
            <Skeleton className="h-4 w-16 shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}

function OrderDetailExpanded({ order }: { order: OrderResponse }) {
  const date = new Date(order.created_at).toLocaleDateString("en-IN", {
    year: "numeric", month: "long", day: "numeric",
  });
  const time = new Date(order.created_at).toLocaleTimeString("en-IN", {
    hour: "2-digit", minute: "2-digit",
  });
  const methodLabel =
    order.payment_method === "razorpay" ? "Razorpay"
    : order.payment_method === "cod" ? "Cash on Delivery"
    : order.payment_method;

  return (
    <div className="mt-5 space-y-5 border-t border-border pt-5">
      {/* Badges */}
      <div className="flex flex-wrap gap-2">
        <PaymentBadge status={order.payment_status} />
        {order.tracking_number && (
          <span className="text-[10px] uppercase tracking-[0.22em] px-3 py-1 bg-secondary text-foreground">
            Tracking: {order.tracking_number}
          </span>
        )}
      </div>

      {/* Meta grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">Date</p>
          <p>{date}<br /><span className="text-muted-foreground">{time}</span></p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">Payment</p>
          <div className="flex items-center gap-1.5">
            <CreditCard className="size-3.5 text-muted-foreground" />
            <span>{methodLabel}</span>
          </div>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">Items</p>
          <p>{order.items.length} {order.items.length === 1 ? "item" : "items"}</p>
        </div>
        {order.cancellation_reason && (
          <div>
            <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">Reason</p>
            <p className="text-destructive text-xs">{order.cancellation_reason}</p>
          </div>
        )}
      </div>

      {/* Items */}
      <div className="border-t border-border pt-4 space-y-4">
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
                {item.quantity > 1 && <span className="ml-1">({formatINR(item.unit_price)} each)</span>}
              </p>
            </div>
            <p className="font-display shrink-0">{formatINR(item.line_total)}</p>
          </div>
        ))}
      </div>

      {/* Totals */}
      <div className="border-t border-border pt-4 space-y-2">
        <TotalRow label="Subtotal" value={formatINR(order.subtotal)} />
        {order.discount > 0 && (
          <TotalRow
            label={`Discount${order.coupon_code ? ` (${order.coupon_code})` : ""}`}
            value={`−${formatINR(order.discount)}`}
            accent
          />
        )}
        <TotalRow label="Tax" value={formatINR(order.tax_amount)} />
        <TotalRow
          label="Shipping"
          value={order.shipping_charge === 0 ? "Free" : formatINR(order.shipping_charge)}
        />
        <div className="pt-2 border-t border-border">
          <TotalRow label="Total" value={formatINR(order.total)} bold />
        </div>
      </div>

      {/* Timeline */}
      {order.status !== "cancelled" && (
        <div className="border-t border-border pt-4">
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground mb-4">Order status</p>
          <OrderTimeline status={order.status} />
        </div>
      )}

      {/* What's next — only for active orders */}
      {!["delivered", "cancelled"].includes(order.status) && (
        <div className="border-t border-border pt-4 space-y-3">
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">What's next</p>
          <ul className="space-y-2 text-sm">
            <li className="flex items-start gap-3">
              <CheckCircle2 className="size-4 mt-0.5 shrink-0 text-accent" />
              <span><span className="font-medium">Confirmation email sent</span> — check your inbox for order details and updates.</span>
            </li>
            <li className="flex items-start gap-3">
              <Package className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
              <span><span className="font-medium">Handcrafted for you</span> — your piece is being quality-checked before dispatch.</span>
            </li>
            <li className="flex items-start gap-3">
              <Truck className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
              <span><span className="font-medium">Estimated delivery in 5–7 business days</span> — you'll receive a tracking number once shipped.</span>
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Order card ─────────────────────────────────────────────────────────────────

function OrderCard({
  order,
  expanded,
  onToggle,
}: {
  order: OrderListResponse["items"][number];
  expanded: boolean;
  onToggle: () => void;
}) {
  const { data: detail, isLoading } = useQuery({
    queryKey: queryKeys.orders.detail(order.id),
    queryFn: () => api.get<OrderResponse>(`/orders/${order.id}`),
    enabled: expanded,
    staleTime: 5 * 60_000,
  });

  return (
    <div className="border border-border bg-card p-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-display text-lg">{order.order_number}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Placed{" "}
            {new Date(order.created_at).toLocaleDateString("en-IN", {
              year: "numeric", month: "short", day: "numeric",
            })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <OrderStatusBadge status={order.status} />
          <span className="font-display text-xl">{formatINR(order.total)}</span>
        </div>
      </div>

      {/* Toggle */}
      <button
        onClick={onToggle}
        className="mt-4 inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.18em] text-accent border-b border-accent/40 pb-0.5 hover:border-accent transition"
      >
        {expanded ? (
          <>Hide details <ChevronUp className="size-3.5" /></>
        ) : (
          <>View Order Details <ChevronDown className="size-3.5" /></>
        )}
      </button>

      {/* Expanded detail */}
      {expanded && (
        isLoading
          ? <OrderDetailSkeleton itemCount={order.item_count} />
          : detail && <OrderDetailExpanded order={detail} />
      )}
    </div>
  );
}

function AddressesTab() {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);

  const { data: addresses = [], isLoading } = useQuery({
    queryKey: queryKeys.addresses.all,
    queryFn: () => api.get<AddressResponse[]>("/me/addresses"),
  });

  const addMutation = useMutation({
    mutationFn: (body: AddressCreateRequest) =>
      api.post<AddressResponse>("/me/addresses", { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.addresses.all });
      setAdding(false);
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.delete<void>(`/me/addresses/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.addresses.all }),
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const defaultMutation = useMutation({
    mutationFn: (id: string) => api.post<void>(`/me/addresses/${id}/default`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.addresses.all }),
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body: AddressCreateRequest = {
      type: "shipping",
      full_name: String(f.get("name") ?? ""),
      phone: (() => { const p = String(f.get("phone") ?? "").replace(/\s+/g, ""); return p ? (p.startsWith("+") ? p : `+91${p.replace(/^0+/, "")}`) : ""; })(),
      line1: String(f.get("line1") ?? ""),
      line2: String(f.get("line2") ?? "") || null,
      city: String(f.get("city") ?? ""),
      state: String(f.get("state") ?? ""),
      postal_code: String(f.get("pincode") ?? ""),
      country: "IN",
      is_default: f.get("isDefault") === "on",
    };
    addMutation.mutate(body);
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-5">
        <h2 className="font-display text-2xl">Saved addresses</h2>
        <button
          onClick={() => setAdding((v) => !v)}
          className="flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] border border-foreground px-4 py-2 hover:bg-foreground hover:text-background transition"
        >
          <Plus className="size-3.5" />
          {adding ? "Cancel" : "Add Address"}
        </button>
      </div>

      {adding && (
        <form
          onSubmit={submit}
          className="border border-border bg-card p-6 grid sm:grid-cols-2 gap-4 mb-6"
        >
          <Inp name="name" placeholder="Full name" required className="sm:col-span-2" />
          <Inp name="line1" placeholder="Address line 1" required className="sm:col-span-2" />
          <Inp name="line2" placeholder="Address line 2 (optional)" className="sm:col-span-2" />
          <Inp name="city" placeholder="City" required />
          <Inp name="state" placeholder="State" required />
          <Inp name="pincode" placeholder="Pincode" required />
          <Inp name="phone" placeholder="Phone" required />
          <label className="sm:col-span-2 inline-flex items-center gap-2 text-sm">
            <input type="checkbox" name="isDefault" /> Set as default address
          </label>
          <button
            disabled={addMutation.isPending}
            className="sm:col-span-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3 disabled:opacity-50"
          >
            {addMutation.isPending ? "Saving…" : "Save Address"}
          </button>
        </form>
      )}

      {isLoading && (
        <div className="grid sm:grid-cols-2 gap-4">
          {[1, 2].map((i) => (
            <div key={i} className="border border-border bg-card p-5 h-32 animate-pulse" />
          ))}
        </div>
      )}

      {!isLoading && addresses.length === 0 && !adding && (
        <div className="border border-border bg-card p-10 text-center">
          <MapPin className="size-10 mx-auto text-muted-foreground mb-3" />
          <p className="font-display text-xl">No saved addresses</p>
          <p className="text-sm text-muted-foreground mt-1">
            Add one to checkout faster next time.
          </p>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-4">
        {addresses.map((a) => (
          <div
            key={a.id}
            className={`relative border p-5 bg-card ${a.is_default ? "border-foreground" : "border-border"}`}
          >
            <div className="flex justify-between items-start gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                  {a.type}
                  {a.is_default && " · Default"}
                </p>
                <p className="font-display text-lg mt-1">{a.full_name}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {a.line1}
                  {a.line2 ? `, ${a.line2}` : ""}
                </p>
                <p className="text-sm text-muted-foreground">
                  {a.city}, {a.state} {a.postal_code}
                </p>
                {a.phone && <p className="text-sm text-muted-foreground">{a.phone}</p>}
              </div>
              <button
                onClick={() => removeMutation.mutate(a.id)}
                disabled={removeMutation.isPending}
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="size-4" />
              </button>
            </div>
            {!a.is_default && (
              <button
                onClick={() => defaultMutation.mutate(a.id)}
                disabled={defaultMutation.isPending}
                className="mt-3 inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.18em] text-accent hover:underline"
              >
                <Star className="size-3" /> Set as default
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function WishlistTab() {
  const items = useWishlist((s) => s.items);
  const remove = useWishlist((s) => s.remove);

  if (items.length === 0) {
    return (
      <div className="border border-border bg-card p-10 text-center">
        <Heart className="size-10 mx-auto text-muted-foreground mb-3" />
        <p className="font-display text-xl">Your wishlist is empty</p>
        <Link
          to="/collections"
          className="inline-block mt-5 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
        >
          Discover Pieces
        </Link>
      </div>
    );
  }

  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {items.map((item) => (
        <div key={`${item.id}::${item.variantId ?? ""}`} className="group relative">
          <Link to="/products/$slug" params={{ slug: item.slug }} className="block">
            <div className="aspect-square bg-secondary overflow-hidden">
              <img
                src={item.image}
                alt={item.name}
                className="w-full h-full object-cover group-hover:scale-105 transition duration-500"
              />
            </div>
            <p className="text-xs mt-3 line-clamp-2">{item.name}</p>
            {item.variantName && (
              <p className="text-[11px] text-muted-foreground mt-0.5">{item.variantName}</p>
            )}
            <p className="font-display mt-1">{formatINR(item.price)}</p>
          </Link>
          <button
            onClick={() => remove(item.id, item.variantId)}
            className="absolute top-2 right-2 size-8 rounded-full bg-background/90 flex items-center justify-center text-destructive hover:bg-background transition"
            aria-label="Remove from wishlist"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}

function ProfileTab() {
  const { user } = useAuthContext();
  const { data: profile, isLoading } = useProfile();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (profile) {
      setName(profile.full_name ?? user?.user_metadata?.full_name ?? "");
      setPhone(profile.phone ?? "");
    } else if (user) {
      setName(user.user_metadata?.full_name ?? "");
    }
  }, [profile, user]);

  const updateMutation = useMutation({
    mutationFn: (data: ProfileUpdateDto) => api.patch<ProfileDto>("/me", { body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.profile.me });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    let normalizedPhone: string | null = null;
    if (phone) {
      const digits = phone.replace(/\s+/g, "");
      normalizedPhone = digits.startsWith("+") ? digits : `+91${digits.replace(/^0+/, "")}`;
    }
    updateMutation.mutate({ full_name: name, phone: normalizedPhone });
  };

  return (
    <form onSubmit={submit} className="border border-border bg-card p-6 space-y-5 max-w-lg">
      <h2 className="font-display text-2xl">Profile information</h2>
      {isLoading && <p className="text-sm text-muted-foreground">Loading profile…</p>}
      <Inp
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Full name"
        disabled={isLoading}
      />
      <Inp
        value={user?.email ?? ""}
        placeholder="Email"
        type="email"
        disabled
        className="opacity-60 cursor-not-allowed"
      />
      <Inp
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        placeholder="Phone (+919876543210)"
        type="tel"
        disabled={isLoading}
      />
      <div className="flex items-center gap-4">
        <button
          disabled={updateMutation.isPending || isLoading}
          className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-60"
        >
          {updateMutation.isPending ? "Saving…" : "Save changes"}
        </button>
        {saved && <span className="text-xs text-accent">Saved ✓</span>}
      </div>
    </form>
  );
}

function Inp({ className = "", ...rest }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={`w-full bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground transition ${className}`}
    />
  );
}
