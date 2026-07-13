import { useEffect, useRef, useState } from "react";
import { createFileRoute, Link, redirect, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import {
  User,
  Package,
  MapPin,
  LogOut,
  Heart,
  Plus,
  Trash2,
  Star,
  CheckCircle2,
  Truck,
  CreditCard,
  ChevronDown,
  ChevronUp,
  Shield,
  Menu,
  ArrowRight,
  Eye,
  EyeOff,
  Camera,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

import { SiteLayout } from "@/components/site/SiteLayout";
import { PageLoader } from "@/components/common/PageLoader";
import { OrderTrackingSection } from "@/components/customer/OrderTrackingSection";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { queryKeys } from "@/lib/api/queryKeys";
import { getSession } from "@/lib/supabase/session";
import { supabase } from "@/lib/supabase/client";
import { useAuthContext } from "@/providers/auth-context";
import { Field, PhoneField, isValidIndianMobile } from "@/components/common/FormField";
import { useWishlist } from "@/stores/wishlist";
import { formatINR } from "@/lib/format";
import { useProfile } from "@/hooks/auth/useProfile";
import type { ProfileDto, ProfileUpdateDto } from "@/types/profile";
import type {
  AddressResponse,
  AddressCreateRequest,
  OrderListResponse,
  CustomerOrderResponse,
} from "@/types/customer";

const TAB_VALUES = ["overview", "orders", "addresses", "wishlist", "profile", "security"] as const;
type Tab = (typeof TAB_VALUES)[number];

export const Route = createFileRoute("/account/")({
  validateSearch: z.object({
    tab: z.enum(TAB_VALUES).optional(),
  }),
  beforeLoad: async () => {
    if (typeof window === "undefined") return;
    const session = await getSession();
    if (!session) throw redirect({ to: "/account/login", search: { redirect: "/account" } });
  },
  head: () => ({ meta: [{ title: "My Account · Hadha" }] }),
  component: AccountPage,
});

// ── Sidebar nav items ─────────────────────────────────────────────────────────

const NAV_ITEMS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "overview", label: "Overview", icon: <User className="size-4" /> },
  { id: "orders", label: "Orders", icon: <Package className="size-4" /> },
  { id: "addresses", label: "Addresses", icon: <MapPin className="size-4" /> },
  { id: "wishlist", label: "Wishlist", icon: <Heart className="size-4" /> },
  { id: "profile", label: "Profile", icon: <User className="size-4" /> },
  { id: "security", label: "Security", icon: <Shield className="size-4" /> },
];

// ── Sidebar ───────────────────────────────────────────────────────────────────

function Sidebar({
  tab,
  setTab,
  onSignOut,
}: {
  tab: Tab;
  setTab: (t: Tab) => void;
  onSignOut: () => void;
}) {
  return (
    <nav className="space-y-1">
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          onClick={() => setTab(item.id)}
          className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm rounded-xl text-left transition-all duration-150 ${
            tab === item.id
              ? "bg-[#1a2744] text-white font-medium shadow-sm"
              : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground"
          }`}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
      <div className="pt-3 mt-3 border-t border-border">
        <button
          onClick={onSignOut}
          className="w-full flex items-center gap-3 px-4 py-2.5 text-sm rounded-xl text-left text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-all duration-150"
        >
          <LogOut className="size-4" />
          Sign Out
        </button>
      </div>
    </nav>
  );
}

// ── Root page ─────────────────────────────────────────────────────────────────

function AccountPage() {
  const navigate = useNavigate();
  const { tab: initialTab } = Route.useSearch();
  const { user, status, logout } = useAuthContext();
  const [tab, setTab] = useState<Tab>(initialTab ?? "overview");

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
  const firstName = displayName.split(" ")[0];

  const handleSignOut = async () => {
    await logout();
    navigate({ to: "/" });
  };

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-6xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Account" }]} />

        {/* Header */}
        <div className="mt-6 mb-8 flex items-end justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
              Welcome back
            </p>
            <h1 className="font-display text-4xl md:text-5xl mt-1">Hello, {firstName}</h1>
          </div>
          {/* Mobile menu trigger */}
          <Sheet>
            <SheetTrigger asChild>
              <button className="lg:hidden flex items-center gap-2 border border-border rounded-xl px-4 py-2 text-sm text-muted-foreground hover:border-foreground transition">
                <Menu className="size-4" />
                Menu
              </button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 pt-12">
              <SheetTitle className="sr-only">My Account Navigation</SheetTitle>
              <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground mb-1 px-4">
                My Account
              </p>
              <p className="font-display text-xl px-4 mb-6">{firstName}</p>
              <Sidebar tab={tab} setTab={setTab} onSignOut={handleSignOut} />
            </SheetContent>
          </Sheet>
        </div>

        <div className="grid lg:grid-cols-[220px_1fr] gap-8">
          {/* Desktop sidebar */}
          <aside className="hidden lg:block">
            <div className="sticky top-24 bg-card border border-border rounded-2xl p-4 shadow-sm">
              <Sidebar tab={tab} setTab={setTab} onSignOut={handleSignOut} />
            </div>
          </aside>

          {/* Main content */}
          <main className="min-w-0">
            {tab === "overview" && <OverviewTab onNavigate={setTab} user={user} />}
            {tab === "orders" && <OrdersTab />}
            {tab === "addresses" && <AddressesTab />}
            {tab === "wishlist" && <WishlistTab />}
            {tab === "profile" && <ProfileTab />}
            {tab === "security" && <SecurityTab />}
          </main>
        </div>
      </div>
    </SiteLayout>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  onClick,
}: {
  label: string;
  value: string | number;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="bg-card border border-border rounded-2xl p-5 text-left hover:border-foreground hover:shadow-sm transition-all duration-150 group"
    >
      <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">{label}</p>
      <p className="font-display text-3xl mt-2 group-hover:text-accent transition-colors">
        {value}
      </p>
    </button>
  );
}

// ── Overview tab ──────────────────────────────────────────────────────────────

function OverviewTab({
  onNavigate,
  user,
}: {
  onNavigate: (t: Tab) => void;
  user: { created_at?: string; user_metadata?: Record<string, unknown> };
}) {
  const { data: ordersData, isLoading: ordersLoading } = useQuery({
    queryKey: queryKeys.orders.list({}),
    queryFn: () => api.get<OrderListResponse>("/orders", { params: { page: 1, page_size: 3 } }),
    staleTime: 60_000,
  });
  const { data: addresses = [] } = useQuery({
    queryKey: queryKeys.addresses.all,
    queryFn: () => api.get<AddressResponse[]>("/me/addresses"),
    staleTime: 60_000,
  });
  const wishlistItems = useWishlist((s) => s.items);

  const memberSince = user.created_at
    ? new Date(user.created_at).toLocaleDateString("en-IN", { month: "long", year: "numeric" })
    : "—";

  const recentOrders = ordersData?.items ?? [];
  const latestOrder = recentOrders[0];
  const defaultAddress = addresses.find((a) => a.is_default) ?? addresses[0];

  return (
    <div className="space-y-8">
      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Member Since" value={memberSince} />
        <StatCard
          label="Orders"
          value={ordersLoading ? "—" : (ordersData?.total ?? 0)}
          onClick={() => onNavigate("orders")}
        />
        <StatCard
          label="Wishlist"
          value={wishlistItems.length}
          onClick={() => onNavigate("wishlist")}
        />
        <StatCard
          label="Addresses"
          value={addresses.length}
          onClick={() => onNavigate("addresses")}
        />
      </div>

      {/* Latest order status */}
      {latestOrder && (
        <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <p className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
              Latest Order
            </p>
            <button
              onClick={() => onNavigate("orders")}
              className="text-[11px] uppercase tracking-[0.22em] text-accent flex items-center gap-1 hover:gap-2 transition-all"
            >
              View all <ArrowRight className="size-3" />
            </button>
          </div>
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="font-medium text-sm">{latestOrder.order_number}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {new Date(latestOrder.created_at).toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <FulfillmentStatusBadge status={latestOrder.fulfillment_status} />
              <span className="font-sans font-bold text-lg">{formatINR(latestOrder.total)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Recent orders */}
      {recentOrders.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-xl">Recent Orders</h2>
            <button
              onClick={() => onNavigate("orders")}
              className="text-[11px] uppercase tracking-[0.22em] text-accent flex items-center gap-1 hover:gap-2 transition-all"
            >
              View all <ArrowRight className="size-3" />
            </button>
          </div>
          <div className="space-y-3">
            {recentOrders.slice(0, 3).map((o) => (
              <MiniOrderCard key={o.id} order={o} />
            ))}
          </div>
        </section>
      )}

      {/* Default address preview */}
      {defaultAddress && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-xl">Default Address</h2>
            <button
              onClick={() => onNavigate("addresses")}
              className="text-[11px] uppercase tracking-[0.22em] text-accent flex items-center gap-1 hover:gap-2 transition-all"
            >
              Manage <ArrowRight className="size-3" />
            </button>
          </div>
          <div className="bg-card border border-border rounded-2xl p-5 shadow-sm text-sm space-y-0.5">
            <p className="font-medium">{defaultAddress.full_name}</p>
            <p className="text-muted-foreground">{defaultAddress.line1}</p>
            {defaultAddress.line2 && (
              <p className="text-muted-foreground">{defaultAddress.line2}</p>
            )}
            <p className="text-muted-foreground">
              {defaultAddress.city}, {defaultAddress.state} {defaultAddress.postal_code}
            </p>
          </div>
        </section>
      )}

      {/* Wishlist preview */}
      {wishlistItems.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-xl">Wishlist</h2>
            <button
              onClick={() => onNavigate("wishlist")}
              className="text-[11px] uppercase tracking-[0.22em] text-accent flex items-center gap-1 hover:gap-2 transition-all"
            >
              View all <ArrowRight className="size-3" />
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {wishlistItems.slice(0, 4).map((item) => (
              <Link
                key={`${item.id}::${item.variantId ?? ""}`}
                to="/products/$slug"
                params={{ slug: item.slug }}
                className="group"
              >
                <div className="aspect-square bg-secondary rounded-xl overflow-hidden">
                  <img
                    src={item.image}
                    alt={item.name}
                    className="w-full h-full object-cover group-hover:scale-105 transition duration-500"
                  />
                </div>
                <p className="text-xs mt-2 line-clamp-1">{item.name}</p>
                <p className="font-sans font-bold text-sm mt-0.5">{formatINR(item.price)}</p>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ── Mini order card (used in overview) ────────────────────────────────────────

function MiniOrderCard({ order }: { order: OrderListResponse["items"][number] }) {
  return (
    <div className="bg-card border border-border rounded-2xl p-4 flex items-center justify-between gap-4 hover:border-foreground/30 transition shadow-sm">
      <div className="flex items-center gap-3 min-w-0">
        <div className="size-10 rounded-xl bg-secondary flex items-center justify-center shrink-0">
          <Package className="size-4 text-muted-foreground" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{order.order_number}</p>
          <p className="text-xs text-muted-foreground">
            {new Date(order.created_at).toLocaleDateString("en-IN", {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <FulfillmentStatusBadge status={order.fulfillment_status} />
        <span className="font-sans font-bold text-base">{formatINR(order.total)}</span>
      </div>
    </div>
  );
}

// ── Status badges ─────────────────────────────────────────────────────────────

function FulfillmentStatusBadge({ status }: { status: string }) {
  const cfg: Record<string, string> = {
    pending: "bg-secondary text-muted-foreground",
    packing: "bg-blue-100 text-blue-700",
    label_generated: "bg-indigo-100 text-indigo-700",
    dispatched: "bg-amber-100 text-amber-700",
    in_transit: "bg-orange-100 text-orange-700",
    delivered: "bg-emerald-100 text-emerald-700",
    cancelled: "bg-red-100 text-red-700",
  };
  const cls = cfg[status.toLowerCase()] ?? "bg-secondary text-muted-foreground";
  const label = status.replace(/_/g, " ");
  return (
    <span
      className={`text-[10px] uppercase tracking-[0.2em] px-2.5 py-1 rounded-full font-medium ${cls}`}
    >
      {label}
    </span>
  );
}

function OrderStatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const cls =
    s === "delivered"
      ? "bg-emerald-100 text-emerald-700"
      : s === "shipped"
        ? "bg-blue-100 text-blue-700"
        : s === "cancelled"
          ? "bg-red-100 text-red-700"
          : "bg-secondary text-muted-foreground";
  return (
    <span
      className={`text-[10px] uppercase tracking-[0.2em] px-2.5 py-1 rounded-full font-medium ${cls}`}
    >
      {status}
    </span>
  );
}

function PaymentBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const cls =
    s === "paid"
      ? "bg-emerald-100 text-emerald-700"
      : s === "failed"
        ? "bg-red-100 text-red-700"
        : "bg-secondary text-muted-foreground";
  return (
    <span
      className={`text-[10px] uppercase tracking-[0.2em] px-2.5 py-1 rounded-full font-medium ${cls}`}
    >
      {status}
    </span>
  );
}

// ── Order timeline ─────────────────────────────────────────────────────────────

const FULFILLMENT_STEP: Record<string, number> = {
  pending: 0,
  packing: 1,
  label_generated: 1,
  dispatched: 2,
  in_transit: 2,
  delivered: 3,
};

function OrderTimeline({ fulfillmentStatus }: { fulfillmentStatus: string }) {
  const current = FULFILLMENT_STEP[fulfillmentStatus.toLowerCase()] ?? 0;
  const steps = [
    { label: "Order placed", sub: "Payment received" },
    { label: "Processing", sub: "Handcrafted & quality-checked" },
    { label: "Shipped", sub: "On the way to you" },
    { label: "Delivered", sub: "Enjoy your piece" },
  ];
  return (
    <div className="relative">
      <div className="absolute left-[13px] top-6 bottom-6 w-px bg-border" />
      <div className="space-y-5">
        {steps.map((step, i) => {
          const done = current >= i;
          const active = done && (i === steps.length - 1 || current < i + 1);
          return (
            <div key={step.label} className="flex items-start gap-4 relative">
              <div
                className={`relative z-10 size-7 rounded-full flex items-center justify-center border-2 shrink-0 transition-colors ${
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

// ── TotalRow ──────────────────────────────────────────────────────────────────

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
    <div className="flex justify-between text-sm">
      <span className={accent ? "text-accent" : "text-muted-foreground"}>{label}</span>
      <span
        className={`${accent ? "text-accent" : ""} ${bold ? "font-semibold text-foreground" : ""}`.trim()}
      >
        {value}
      </span>
    </div>
  );
}

// ── Order detail (expanded) ────────────────────────────────────────────────────

function OrderDetailExpanded({ order }: { order: CustomerOrderResponse }) {
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
    <div className="mt-5 space-y-5 border-t border-border pt-5">
      <div className="flex flex-wrap gap-2">
        <PaymentBadge status={order.payment_status} />
      </div>

      {order.tracking_number && order.shipping_provider && <OrderTrackingSection order={order} />}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">Date</p>
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
        {order.cancellation_reason && (
          <div>
            <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground mb-1">
              Reason
            </p>
            <p className="text-destructive text-xs">{order.cancellation_reason}</p>
          </div>
        )}
      </div>

      <div className="border-t border-border pt-4 space-y-3">
        <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">Items</p>
        {order.items.map((item) => (
          <div key={item.id} className="flex items-start gap-3 text-sm">
            {item.image_url ? (
              <img
                src={item.image_url}
                alt={item.product_name}
                className="w-12 h-12 object-cover rounded-xl shrink-0 border border-border"
              />
            ) : (
              <div className="w-12 h-12 bg-secondary rounded-xl shrink-0 flex items-center justify-center border border-border">
                <Package className="w-5 h-5 text-muted-foreground" />
              </div>
            )}
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
            <p className="text-sm shrink-0">{formatINR(item.unit_price * item.quantity)}</p>
          </div>
        ))}
      </div>

      <div className="border-t border-border pt-4 space-y-2">
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
        <div className="pt-2 border-t border-border">
          <TotalRow label="Total" value={formatINR(order.total)} bold />
        </div>
      </div>

      {order.status !== "cancelled" && (
        <div className="border-t border-border pt-4">
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground mb-4">
            Order status
          </p>
          <OrderTimeline fulfillmentStatus={order.fulfillment_status} />
        </div>
      )}

      {!["delivered", "cancelled"].includes(order.status) && (
        <div className="border-t border-border pt-4 space-y-3">
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
            What's next
          </p>
          <ul className="space-y-2 text-sm">
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
                <span className="font-medium">Estimated delivery in 5–7 business days</span> —
                you'll receive a tracking number once shipped.
              </span>
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
    queryFn: () => api.get<CustomerOrderResponse>(`/orders/${order.id}`),
    enabled: expanded,
    staleTime: 5 * 60_000,
  });

  return (
    <div className="bg-card border border-border rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="size-11 rounded-xl bg-secondary flex items-center justify-center shrink-0">
            <Package className="size-5 text-muted-foreground" />
          </div>
          <div>
            <p className="font-medium text-base">{order.order_number}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {new Date(order.created_at).toLocaleDateString("en-IN", {
                year: "numeric",
                month: "short",
                day: "numeric",
              })}
              {" · "}
              {order.item_count} {order.item_count === 1 ? "item" : "items"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <OrderStatusBadge status={order.status} />
          <FulfillmentStatusBadge status={order.fulfillment_status} />
          <span className="font-sans font-bold text-xl ml-1">{formatINR(order.total)}</span>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between">
        <button
          onClick={onToggle}
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.18em] text-accent hover:text-accent/80 transition"
        >
          {expanded ? (
            <>
              Hide details <ChevronUp className="size-3.5" />
            </>
          ) : (
            <>
              View order details <ChevronDown className="size-3.5" />
            </>
          )}
        </button>
      </div>

      {expanded &&
        (isLoading ? (
          <div className="mt-5 space-y-3 border-t border-border pt-5">
            {Array.from({ length: order.item_count }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="w-12 h-12 rounded-xl shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          detail && <OrderDetailExpanded order={detail} />
        ))}
    </div>
  );
}

// ── Orders tab ─────────────────────────────────────────────────────────────────

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
          <div key={i} className="bg-card border border-border rounded-2xl p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <Skeleton className="size-11 rounded-xl" />
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-24" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  const orders = data?.items ?? [];

  if (orders.length === 0) {
    return (
      <div className="bg-card border border-border rounded-2xl p-12 text-center shadow-sm">
        <div className="size-16 rounded-2xl bg-secondary flex items-center justify-center mx-auto mb-4">
          <Package className="size-7 text-muted-foreground" />
        </div>
        <p className="font-display text-xl">No orders yet</p>
        <p className="text-sm text-muted-foreground mt-1 mb-6">
          Once you place an order it will show up here.
        </p>
        <Link
          to="/collections"
          className="inline-block bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3 rounded-xl"
        >
          Start Shopping
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-display text-2xl">Your Orders</h2>
        <span className="text-sm text-muted-foreground">{data?.total ?? 0} orders</span>
      </div>
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

// ── Addresses tab ──────────────────────────────────────────────────────────────

function AddressesTab() {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [phone, setPhone] = useState("");
  const [altPhone, setAltPhone] = useState("");
  const [phoneError, setPhoneError] = useState<string | undefined>();
  const [altPhoneError, setAltPhoneError] = useState<string | undefined>();

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
      setPhone("");
      setAltPhone("");
      toast.success("Address saved");
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
    const phoneValid = isValidIndianMobile(phone);
    const altPhoneValid = altPhone === "" || isValidIndianMobile(altPhone);
    setPhoneError(phoneValid ? undefined : "Enter a valid 10-digit mobile number");
    setAltPhoneError(altPhoneValid ? undefined : "Enter a valid 10-digit mobile number");
    if (!phoneValid || !altPhoneValid) return;

    const f = new FormData(e.currentTarget);
    const body: AddressCreateRequest = {
      type: "shipping",
      full_name: String(f.get("name") ?? ""),
      phone: `+91${phone}`,
      line1: String(f.get("line1") ?? ""),
      line2: String(f.get("line2") ?? "") || null,
      landmark: String(f.get("landmark") ?? "") || null,
      alternate_phone: altPhone ? `+91${altPhone}` : null,
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
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-display text-2xl">Saved Addresses</h2>
        <button
          onClick={() => setAdding((v) => !v)}
          className="flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] border border-foreground rounded-xl px-4 py-2.5 hover:bg-foreground hover:text-background transition"
        >
          <Plus className="size-3.5" />
          {adding ? "Cancel" : "Add Address"}
        </button>
      </div>

      {adding && (
        <form
          onSubmit={submit}
          className="bg-card border border-border rounded-2xl p-6 grid sm:grid-cols-2 gap-4 mb-6 shadow-sm"
        >
          <Field label="Full name" name="name" required className="sm:col-span-2" />
          <Field label="Address line 1" name="line1" required className="sm:col-span-2" />
          <Field label="Address line 2 (optional)" name="line2" className="sm:col-span-2" />
          <Field
            label="Landmark (optional)"
            name="landmark"
            placeholder="Near SBI Bank, Opposite Temple"
            className="sm:col-span-2"
          />
          <Field label="City" name="city" required />
          <Field label="State" name="state" required />
          <Field label="Pincode" name="pincode" required />
          <PhoneField
            label="Phone"
            name="phone"
            required
            value={phone}
            onValueChange={(digits) => {
              setPhone(digits);
              setPhoneError(undefined);
            }}
            error={phoneError}
          />
          <PhoneField
            label="Alternative phone (optional)"
            name="alternate_phone"
            value={altPhone}
            onValueChange={(digits) => {
              setAltPhone(digits);
              setAltPhoneError(undefined);
            }}
            error={altPhoneError}
          />
          <label className="sm:col-span-2 inline-flex items-center gap-2 text-sm">
            <input type="checkbox" name="isDefault" className="rounded" />
            Set as default address
          </label>
          <button
            disabled={addMutation.isPending}
            className="sm:col-span-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3 rounded-xl disabled:opacity-50 hover:bg-accent hover:text-accent-foreground transition"
          >
            {addMutation.isPending ? "Saving…" : "Save Address"}
          </button>
        </form>
      )}

      {isLoading && (
        <div className="grid sm:grid-cols-2 gap-4">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="bg-card border border-border rounded-2xl p-5 h-36 animate-pulse"
            />
          ))}
        </div>
      )}

      {!isLoading && addresses.length === 0 && !adding && (
        <div className="bg-card border border-border rounded-2xl p-12 text-center shadow-sm">
          <div className="size-16 rounded-2xl bg-secondary flex items-center justify-center mx-auto mb-4">
            <MapPin className="size-7 text-muted-foreground" />
          </div>
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
            className={`relative bg-card border rounded-2xl p-5 shadow-sm transition ${
              a.is_default ? "border-foreground ring-1 ring-foreground/10" : "border-border"
            }`}
          >
            <div className="flex justify-between items-start gap-3">
              <div>
                {a.is_default && (
                  <span className="text-[10px] uppercase tracking-[0.22em] bg-foreground text-background px-2 py-0.5 rounded-full inline-block mb-2">
                    Default
                  </span>
                )}
                <p className="font-medium">{a.full_name}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {a.line1}
                  {a.line2 ? `, ${a.line2}` : ""}
                </p>
                {a.landmark && (
                  <p className="text-sm text-muted-foreground">Landmark: {a.landmark}</p>
                )}
                <p className="text-sm text-muted-foreground">
                  {a.city}, {a.state} {a.postal_code}
                </p>
                {a.phone && <p className="text-sm text-muted-foreground mt-0.5">{a.phone}</p>}
                {a.alternate_phone && (
                  <p className="text-sm text-muted-foreground">Alt: {a.alternate_phone}</p>
                )}
              </div>
              <button
                onClick={() => removeMutation.mutate(a.id)}
                disabled={removeMutation.isPending}
                className="text-muted-foreground hover:text-destructive transition p-1 rounded-lg hover:bg-destructive/10"
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

// ── Wishlist tab ───────────────────────────────────────────────────────────────

function WishlistTab() {
  const items = useWishlist((s) => s.items);
  const remove = useWishlist((s) => s.remove);

  if (items.length === 0) {
    return (
      <div className="bg-card border border-border rounded-2xl p-12 text-center shadow-sm">
        <div className="size-16 rounded-2xl bg-secondary flex items-center justify-center mx-auto mb-4">
          <Heart className="size-7 text-muted-foreground" />
        </div>
        <p className="font-display text-xl">Your wishlist is empty</p>
        <p className="text-sm text-muted-foreground mt-1 mb-6">Save pieces you love for later.</p>
        <Link
          to="/collections"
          className="inline-block bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3 rounded-xl"
        >
          Discover Pieces
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-display text-2xl">Wishlist</h2>
        <span className="text-sm text-muted-foreground">{items.length} items</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {items.map((item) => (
          <div key={`${item.id}::${item.variantId ?? ""}`} className="group relative">
            <Link to="/products/$slug" params={{ slug: item.slug }} className="block">
              <div className="aspect-square bg-secondary rounded-2xl overflow-hidden">
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
              <p className="font-sans font-bold mt-1">{formatINR(item.price)}</p>
            </Link>
            <button
              onClick={() => remove(item.id, item.variantId)}
              className="absolute top-2 right-2 size-8 rounded-full bg-background/90 flex items-center justify-center text-destructive hover:bg-background transition shadow-sm"
              aria-label="Remove from wishlist"
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Profile tab ────────────────────────────────────────────────────────────────

function ProfileTab() {
  const { user } = useAuthContext();
  const { data: profile, isLoading } = useProfile();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [saved, setSaved] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
      toast.success("Profile updated");
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const avatarMutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.patch<ProfileDto>("/me/avatar", { body: form });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.profile.me });
      toast.success("Avatar updated");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error("Image must be under 5 MB");
      return;
    }
    avatarMutation.mutate(file);
    e.target.value = "";
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    let normalizedPhone: string | null = null;
    if (phone) {
      const digits = phone.replace(/\s+/g, "");
      normalizedPhone = digits.startsWith("+") ? digits : `+91${digits.replace(/^0+/, "")}`;
    }
    updateMutation.mutate({ full_name: name, phone: normalizedPhone });
  };

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString("en-IN", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });

  const initials = (profile?.full_name ?? user?.email ?? "?")
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="max-w-lg space-y-6">
      <h2 className="font-display text-2xl">Profile Information</h2>

      {/* Avatar + identity card */}
      <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex items-center gap-5">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={handleAvatarChange}
        />

        {/* Clickable avatar */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={avatarMutation.isPending || isLoading}
          className="relative size-20 rounded-full shrink-0 group focus:outline-none"
          title="Change avatar"
        >
          {isLoading ? (
            <Skeleton className="size-20 rounded-full" />
          ) : profile?.avatar_url ? (
            <img
              src={profile.avatar_url}
              alt={profile.full_name ?? "Avatar"}
              className="size-20 rounded-full object-cover border-2 border-border"
            />
          ) : (
            <div className="size-20 rounded-full bg-[#1a2744] flex items-center justify-center text-white font-display text-xl select-none">
              {initials}
            </div>
          )}

          {/* Uploading spinner overlay */}
          {avatarMutation.isPending ? (
            <div className="absolute inset-0 rounded-full bg-black/50 flex items-center justify-center">
              <Loader2 className="size-5 text-white animate-spin" />
            </div>
          ) : (
            /* Camera overlay on hover */
            <div className="absolute inset-0 rounded-full bg-black/40 flex flex-col items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
              <Camera className="size-5 text-white" />
              <span className="text-white text-[10px] mt-1">Change</span>
            </div>
          )}
        </button>
        <div className="min-w-0">
          <p className="font-medium text-base truncate">
            {isLoading ? (
              <Skeleton className="h-4 w-32" />
            ) : (
              (profile?.full_name ?? user?.email ?? "—")
            )}
          </p>
          <p className="text-sm text-muted-foreground mt-0.5 truncate">
            {isLoading ? <Skeleton className="h-3 w-40 mt-1" /> : (profile?.email ?? user?.email)}
          </p>
          {!isLoading && (
            <div className="flex flex-wrap gap-2 mt-2">
              <span
                className={`text-[10px] uppercase tracking-[0.2em] px-2.5 py-0.5 rounded-full font-medium ${
                  profile?.is_active ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                }`}
              >
                {profile?.is_active ? "Active" : "Inactive"}
              </span>
              <span
                className={`text-[10px] uppercase tracking-[0.2em] px-2.5 py-0.5 rounded-full font-medium ${
                  profile?.is_verified ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"
                }`}
              >
                {profile?.is_verified ? "Verified" : "Not Verified"}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Editable fields */}
      <form
        onSubmit={submit}
        className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-5"
      >
        <p className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
          Edit Profile
        </p>
        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-11 w-full rounded-xl" />
            <Skeleton className="h-11 w-full rounded-xl" />
            <Skeleton className="h-11 w-full rounded-xl" />
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              <label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Full Name
              </label>
              <Field
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Full name"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Email
                <span className="ml-2 normal-case tracking-normal text-muted-foreground/60">
                  (read-only)
                </span>
              </label>
              <Field
                value={profile?.email ?? user?.email ?? ""}
                type="email"
                disabled
                className="opacity-60 cursor-not-allowed"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Phone
              </label>
              <Field
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91 98765 43210"
                type="tel"
              />
            </div>
          </>
        )}
        <div className="flex items-center gap-4 pt-1">
          <button
            disabled={updateMutation.isPending || isLoading}
            className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3 rounded-xl hover:bg-accent hover:text-accent-foreground transition disabled:opacity-60"
          >
            {updateMutation.isPending ? "Saving…" : "Save Changes"}
          </button>
          {saved && <span className="text-xs text-accent font-medium">Saved ✓</span>}
        </div>
      </form>

      {/* Read-only account details */}
      <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
        <p className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground mb-4">
          Account Details
        </p>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="flex justify-between">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-3 w-32" />
              </div>
            ))}
          </div>
        ) : (
          <dl className="space-y-3 text-sm">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">Account Status</dt>
              <dd>
                <span
                  className={`text-[10px] uppercase tracking-[0.2em] px-2.5 py-1 rounded-full font-medium ${
                    profile?.is_active
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-red-100 text-red-700"
                  }`}
                >
                  {profile?.is_active ? "Active" : "Inactive"}
                </span>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">Verification</dt>
              <dd>
                <span
                  className={`text-[10px] uppercase tracking-[0.2em] px-2.5 py-1 rounded-full font-medium ${
                    profile?.is_verified
                      ? "bg-blue-100 text-blue-700"
                      : "bg-amber-100 text-amber-700"
                  }`}
                >
                  {profile?.is_verified ? "Verified" : "Not Verified"}
                </span>
              </dd>
            </div>
            <div className="h-px bg-border" />
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">Member Since</dt>
              <dd>{profile?.created_at ? fmtDate(profile.created_at) : "—"}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">Last Updated</dt>
              <dd>{profile?.updated_at ? fmtDate(profile.updated_at) : "—"}</dd>
            </div>
          </dl>
        )}
      </div>
    </div>
  );
}

// ── Security tab ───────────────────────────────────────────────────────────────

function SecurityTab() {
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPw !== confirmPw) {
      toast.error("New passwords do not match");
      return;
    }
    if (newPw.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setLoading(true);
    try {
      const { error } = await supabase.auth.updateUser({ password: newPw });
      if (error) throw error;
      toast.success("Password updated successfully");
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update password";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-lg">
      <h2 className="font-display text-2xl mb-6">Security</h2>
      <form
        onSubmit={submit}
        className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-5"
      >
        <div className="space-y-1.5">
          <label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Current Password
          </label>
          <div className="relative">
            <Field
              type={showCurrent ? "text" : "password"}
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              placeholder="Current password"
              required
            />
            <button
              type="button"
              onClick={() => setShowCurrent((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition"
            >
              {showCurrent ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            New Password
          </label>
          <div className="relative">
            <Field
              type={showNew ? "text" : "password"}
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              placeholder="New password (min 8 characters)"
              required
            />
            <button
              type="button"
              onClick={() => setShowNew((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition"
            >
              {showNew ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Confirm New Password
          </label>
          <div className="relative">
            <Field
              type={showConfirm ? "text" : "password"}
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              placeholder="Confirm new password"
              required
            />
            <button
              type="button"
              onClick={() => setShowConfirm((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition"
            >
              {showConfirm ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
          {newPw && confirmPw && newPw !== confirmPw && (
            <p className="text-xs text-destructive mt-1">Passwords do not match</p>
          )}
        </div>

        <button
          disabled={loading}
          className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3 rounded-xl hover:bg-accent hover:text-accent-foreground transition disabled:opacity-60"
        >
          {loading ? "Updating…" : "Update Password"}
        </button>
      </form>
    </div>
  );
}
