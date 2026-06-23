import { useState, useEffect, useRef } from "react";
import { createFileRoute, useNavigate, Link, redirect } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Truck, Tag, Plus, AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import {
  ReservationCountdown,
  ReservationExpiredModal,
} from "@/components/site/ReservationCountdown";
import { useCart } from "@/stores/cart";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import { supabase } from "@/lib/supabase/client";
import type {
  AddressResponse,
  AddressCreateRequest,
  CreatePaymentIntentRequest,
  CreatePaymentIntentResponse,
  VerifyPaymentRequest,
  VerifyPaymentResponse,
} from "@/types/customer";

export const Route = createFileRoute("/checkout")({
  beforeLoad: async () => {
    if (typeof window === "undefined") return;
    const { data } = await supabase.auth.getSession();
    if (!data.session) throw redirect({ to: "/account/login", search: { redirect: "/checkout" } });
  },
  head: () => ({ meta: [{ title: "Checkout · Hadha" }] }),
  component: CheckoutPage,
});

function loadRazorpayScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Razorpay SDK"));
    document.head.appendChild(script);
  });
}

type CheckoutState =
  | "idle"
  | "reserving"
  | "payment_open"
  | "verifying"
  | "payment_failed"
  | "reservation_expired";

function CheckoutPage() {
  const { lines, subtotal, clear } = useCart();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [shippingMethod, setShippingMethod] = useState<"standard" | "express">("standard");
  const [billingSame, setBillingSame] = useState(true);
  const [selectedAddressId, setSelectedAddressId] = useState<string | "new">("new");
  const [couponCode, setCouponCode] = useState("");

  // Reservation tracking
  const [checkoutState, setCheckoutState] = useState<CheckoutState>("idle");
  const [reservationStartedAt, setReservationStartedAt] = useState<number | null>(null);
  const currentIntentRef = useRef<CreatePaymentIntentResponse | null>(null);

  const { data: addresses = [] } = useQuery({
    queryKey: queryKeys.addresses.all,
    queryFn: () => api.get<AddressResponse[]>("/me/addresses"),
  });

  const addressInitialized = useRef(false);
  useEffect(() => {
    if (!addressInitialized.current && addresses.length > 0) {
      addressInitialized.current = true;
      const def = addresses.find((a) => a.is_default) ?? addresses[0];
      setSelectedAddressId(def.id);
    }
  }, [addresses]);

  const sub = subtotal();
  const ship = lines.length === 0 ? 0 : shippingMethod === "express" ? 199 : sub > 999 ? 0 : 99;
  const total = sub + ship;

  const createAddressMutation = useMutation({
    mutationFn: (data: AddressCreateRequest) =>
      api.post<AddressResponse>("/me/addresses", { body: data }),
  });

  const createPaymentMutation = useMutation({
    mutationFn: async (body: CreatePaymentIntentRequest) => {
      // Sync local cart to server before reserving
      await api.delete<void>("/cart");
      await Promise.all(
        lines.map((l) =>
          api.post<void>("/cart/items", {
            body: { product_id: l.productId, quantity: l.qty, variant_id: l.variantId ?? null },
          }),
        ),
      );
      return api.post<CreatePaymentIntentResponse>("/orders/create-payment", { body });
    },
    onSuccess: (intent) => {
      currentIntentRef.current = intent;
      setReservationStartedAt(Date.now());
      setCheckoutState("payment_open");
    },
    onError: (err) => {
      setCheckoutState("idle");
      const msg = toUserMessage(err);
      if (msg.toLowerCase().includes("available")) {
        // Stock error — backend says not enough stock
        toast.error(msg);
        navigate({ to: "/checkout/stock-changed" });
      } else {
        toast.error(msg);
      }
    },
  });

  const verifyPaymentMutation = useMutation({
    mutationFn: (body: VerifyPaymentRequest) =>
      api.post<VerifyPaymentResponse>("/orders/verify-payment", { body }),
    onSuccess: (result) => {
      clear();
      queryClient.invalidateQueries({ queryKey: queryKeys.orders.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cart.all });
      setCheckoutState("idle");
      setReservationStartedAt(null);
      navigate({
        to: "/checkout/success",
        search: { order: result.order_number, orderId: result.order_id },
      });
    },
    onError: (e) => {
      setCheckoutState("payment_failed");
      toast.error(`Payment verification failed: ${toUserMessage(e)}`);
    },
  });

  function openRazorpay(intent: CreatePaymentIntentResponse, userEmail: string, userName: string) {
    const rzp = new window.Razorpay({
      key: intent.key,
      amount: intent.amount,
      currency: intent.currency,
      name: "Hadha",
      description: "Order Payment",
      order_id: intent.razorpay_order_id,
      prefill: { name: userName, email: userEmail, contact: "" },
      theme: { color: "#000000" },
      handler: (response) => {
        setCheckoutState("verifying");
        verifyPaymentMutation.mutate({
          order_id: intent.order_id,
          razorpay_payment_id: response.razorpay_payment_id,
          razorpay_order_id: response.razorpay_order_id,
          razorpay_signature: response.razorpay_signature,
        });
      },
      modal: {
        ondismiss: () => {
          // Payment modal closed — keep reservation countdown visible so they can retry
          setCheckoutState("payment_open");
          toast.info(
            "Payment cancelled — your items are still reserved. Complete payment before the timer expires.",
          );
        },
      },
    });
    rzp.open();
  }

  const placeOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (lines.length === 0) return;
    setCheckoutState("reserving");

    let shippingAddressId = selectedAddressId !== "new" ? selectedAddressId : null;

    if (!shippingAddressId) {
      const fd = new FormData(e.currentTarget as HTMLFormElement);
      const newAddress: AddressCreateRequest = {
        type: "shipping",
        full_name: `${fd.get("firstName") ?? ""} ${fd.get("lastName") ?? ""}`.trim(),
        phone: (() => {
          const p = String(fd.get("phone") ?? "").replace(/\s+/g, "");
          return p ? (p.startsWith("+") ? p : `+91${p.replace(/^0+/, "")}`) : "";
        })(),
        line1: String(fd.get("address") ?? ""),
        line2: String(fd.get("apt") ?? "") || null,
        city: String(fd.get("city") ?? ""),
        state: String(fd.get("state") ?? ""),
        postal_code: String(fd.get("pincode") ?? ""),
        country: "IN",
        is_default: addresses.length === 0,
      };
      try {
        const created = await createAddressMutation.mutateAsync(newAddress);
        shippingAddressId = created.id;
      } catch (err) {
        toast.error(toUserMessage(err));
        setCheckoutState("idle");
        return;
      }
    }

    const intentBody: CreatePaymentIntentRequest = {
      shipping_address_id: shippingAddressId,
      coupon_code: couponCode.trim() || undefined,
    };

    let intent: CreatePaymentIntentResponse;
    try {
      intent = await createPaymentMutation.mutateAsync(intentBody);
    } catch {
      // error handled in mutation onError
      return;
    }

    try {
      await loadRazorpayScript();
    } catch {
      toast.error("Could not load payment gateway. Check your internet connection and try again.");
      setCheckoutState("idle");
      return;
    }

    const { data: sessionData } = await supabase.auth.getSession();
    const user = sessionData?.session?.user;
    openRazorpay(intent, user?.email ?? "", user?.user_metadata?.full_name ?? "");
  };

  // Retry payment with the same intent (reservation still alive)
  const retryPayment = async () => {
    const intent = currentIntentRef.current;
    if (!intent) return;
    try {
      await loadRazorpayScript();
    } catch {
      toast.error("Could not load payment gateway.");
      return;
    }
    const { data: sessionData } = await supabase.auth.getSession();
    const user = sessionData?.session?.user;
    setCheckoutState("payment_open");
    openRazorpay(intent, user?.email ?? "", user?.user_metadata?.full_name ?? "");
  };

  const handleReservationExpired = () => {
    setCheckoutState("reservation_expired");
  };

  const isReservationActive =
    checkoutState === "payment_open" ||
    checkoutState === "verifying" ||
    checkoutState === "payment_failed";

  const submitting =
    checkoutState === "reserving" ||
    checkoutState === "verifying" ||
    createAddressMutation.isPending;

  return (
    <>
      {/* Countdown bar — visible once reservation is active */}
      {isReservationActive && reservationStartedAt && (
        <ReservationCountdown
          startedAt={reservationStartedAt}
          onExpired={handleReservationExpired}
        />
      )}

      {/* Expired modal */}
      {checkoutState === "reservation_expired" && (
        <ReservationExpiredModal
          onDismiss={() => {
            setCheckoutState("idle");
            setReservationStartedAt(null);
            currentIntentRef.current = null;
            navigate({ to: "/cart" });
          }}
        />
      )}

      <SiteLayout>
        {/* Push content down when countdown bar is visible */}
        <div className={isReservationActive ? "pt-10" : ""}>
          <div className="px-4 md:px-8 py-10 max-w-6xl mx-auto">
            <Breadcrumbs
              items={[
                { label: "Home", to: "/" },
                { label: "Cart", to: "/cart" },
                { label: "Checkout" },
              ]}
            />
            <h1 className="font-display text-4xl md:text-5xl mt-6 mb-10">Checkout</h1>

            {/* Payment failed state */}
            {checkoutState === "payment_failed" && (
              <div
                className="mb-8 flex items-start gap-4 p-5 bg-destructive/5 border border-destructive/20"
                role="alert"
              >
                <AlertTriangle className="size-5 shrink-0 text-destructive mt-0.5" aria-hidden />
                <div className="flex-1">
                  <p className="font-medium text-destructive">Payment failed</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    No money was deducted. Your items are still reserved — retry before the timer
                    expires.
                  </p>
                </div>
                <button
                  onClick={retryPayment}
                  className="shrink-0 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-5 py-2.5 hover:bg-accent hover:text-accent-foreground transition"
                >
                  Retry Payment
                </button>
              </div>
            )}

            <form onSubmit={placeOrder} className="grid lg:grid-cols-[1fr_400px] gap-10">
              <div className="space-y-10">
                {/* Saved addresses */}
                {addresses.length > 0 && (
                  <Section title="Delivery address">
                    <div className="space-y-3">
                      {addresses.map((addr) => (
                        <label
                          key={addr.id}
                          className={`flex items-start gap-3 border p-4 cursor-pointer transition ${selectedAddressId === addr.id ? "border-foreground bg-secondary/40" : "border-border"}`}
                        >
                          <input
                            type="radio"
                            name="savedAddress"
                            checked={selectedAddressId === addr.id}
                            onChange={() => setSelectedAddressId(addr.id)}
                            className="mt-1"
                          />
                          <div className="text-sm leading-relaxed">
                            <p className="font-medium">
                              {addr.full_name}
                              {addr.is_default && (
                                <span className="ml-2 text-[10px] uppercase tracking-[0.16em] text-accent">
                                  default
                                </span>
                              )}
                            </p>
                            <p className="text-muted-foreground">
                              {addr.line1}
                              {addr.line2 ? `, ${addr.line2}` : ""}
                            </p>
                            <p className="text-muted-foreground">
                              {addr.city}, {addr.state} {addr.postal_code}
                            </p>
                          </div>
                        </label>
                      ))}
                      <label
                        className={`flex items-center gap-3 border p-4 cursor-pointer transition ${selectedAddressId === "new" ? "border-foreground bg-secondary/40" : "border-border"}`}
                      >
                        <input
                          type="radio"
                          name="savedAddress"
                          checked={selectedAddressId === "new"}
                          onChange={() => setSelectedAddressId("new")}
                        />
                        <Plus className="size-4" />
                        <span className="text-sm">Use a new address</span>
                      </label>
                    </div>
                  </Section>
                )}

                {/* Manual address form */}
                {selectedAddressId === "new" && (
                  <Section title={addresses.length > 0 ? "New address" : "Shipping address"}>
                    <div className="grid md:grid-cols-2 gap-4">
                      <Field label="First name" name="firstName" required />
                      <Field label="Last name" name="lastName" required />
                      <Field label="Phone" name="phone" type="tel" required />
                      <Field label="Address" name="address" className="md:col-span-2" required />
                      <Field
                        label="Apartment, suite (optional)"
                        name="apt"
                        className="md:col-span-2"
                      />
                      <Field label="City" name="city" required />
                      <Field label="State" name="state" required />
                      <Field label="Pincode" name="pincode" required />
                      <Field label="Country" defaultValue="India" readOnly />
                    </div>
                    <label className="mt-4 inline-flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={billingSame}
                        onChange={(e) => setBillingSame(e.target.checked)}
                      />
                      Billing address same as shipping
                    </label>
                  </Section>
                )}

                <Section title="Delivery method">
                  <div className="space-y-3">
                    {[
                      {
                        id: "standard" as const,
                        label: "Standard delivery",
                        note: "3–5 business days",
                        price: sub > 999 ? 0 : 99,
                      },
                      {
                        id: "express" as const,
                        label: "Express delivery",
                        note: "1–2 business days",
                        price: 199,
                      },
                    ].map((opt) => (
                      <label
                        key={opt.id}
                        className={`flex items-center gap-3 border p-4 cursor-pointer transition ${shippingMethod === opt.id ? "border-foreground bg-secondary/40" : "border-border"}`}
                      >
                        <input
                          type="radio"
                          name="ship"
                          checked={shippingMethod === opt.id}
                          onChange={() => setShippingMethod(opt.id)}
                        />
                        <Truck className="size-4" />
                        <div className="flex-1">
                          <p className="text-sm">{opt.label}</p>
                          <p className="text-xs text-muted-foreground">{opt.note}</p>
                        </div>
                        <span className="font-display">
                          {opt.price === 0 ? "Free" : formatINR(opt.price)}
                        </span>
                      </label>
                    ))}
                  </div>
                </Section>

                <Section title="Coupon">
                  <div className="flex gap-2">
                    <label className="flex-1">
                      <span className="sr-only">Coupon code</span>
                      <div className="relative">
                        <Tag className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                        <input
                          type="text"
                          value={couponCode}
                          onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
                          placeholder="Enter coupon code"
                          className="w-full bg-background border border-border pl-10 pr-3 py-2.5 text-sm outline-none focus:border-foreground transition uppercase tracking-wider"
                        />
                      </div>
                    </label>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Coupon discounts are applied at checkout.
                  </p>
                </Section>
              </div>

              <aside className="border border-border bg-card p-6 h-fit lg:sticky lg:top-28">
                <h2 className="font-display text-xl mb-4">Order summary</h2>
                <div className="divide-y divide-border max-h-72 overflow-y-auto -mx-2 px-2">
                  {lines.map((line) => (
                    <div
                      key={`${line.productId}::${line.variantId ?? ""}`}
                      className="flex gap-3 py-3"
                    >
                      <div className="relative w-16 h-16 bg-secondary overflow-hidden shrink-0">
                        {line.snapshot && (
                          <img
                            src={line.snapshot.image}
                            alt=""
                            className="w-full h-full object-cover"
                          />
                        )}
                        <span className="absolute -top-2 -right-2 bg-foreground text-background text-[10px] rounded-full size-5 flex items-center justify-center">
                          {line.qty}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs leading-snug line-clamp-2">
                          {line.snapshot?.name ?? "Product"}
                        </p>
                        {line.snapshot?.variantName && (
                          <p className="text-[11px] text-muted-foreground mt-0.5">
                            {line.snapshot.variantName}
                          </p>
                        )}
                      </div>
                      <span className="text-sm font-display whitespace-nowrap">
                        {line.snapshot ? formatINR(line.snapshot.price * line.qty) : "—"}
                      </span>
                    </div>
                  ))}
                  {lines.length === 0 && (
                    <p className="text-sm text-muted-foreground py-6 text-center">
                      Your cart is empty.
                      <br />
                      <Link to="/collections" className="underline">
                        Continue shopping
                      </Link>
                    </p>
                  )}
                </div>
                <div className="border-t border-border mt-4 pt-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Subtotal</span>
                    <span>{formatINR(sub)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Shipping</span>
                    <span>{lines.length && ship === 0 ? "Free" : formatINR(ship)}</span>
                  </div>
                  <div className="flex justify-between items-baseline border-t border-border pt-3">
                    <span className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
                      Total
                    </span>
                    <span className="font-display text-2xl">{formatINR(total)}</span>
                  </div>
                </div>
                <button
                  type="submit"
                  disabled={lines.length === 0 || submitting}
                  className="mt-5 w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {checkoutState === "reserving" && (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  )}
                  {checkoutState === "verifying"
                    ? "Confirming payment…"
                    : checkoutState === "reserving"
                      ? "Reserving your items…"
                      : checkoutState === "payment_failed"
                        ? "Try Again"
                        : "Place Order"}
                </button>
                <p className="mt-3 text-[11px] text-center text-muted-foreground">
                  Secured by Razorpay · Cards, UPI, Net Banking & more
                </p>
              </aside>
            </form>
          </div>
        </div>
      </SiteLayout>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-display text-2xl mb-5 pb-3 border-b border-border">{title}</h2>
      {children}
    </section>
  );
}

function Field({
  label,
  className = "",
  ...rest
}: { label: string; className?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={`block ${className}`}>
      <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
      <input
        {...rest}
        className="mt-1.5 w-full bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground transition"
      />
    </label>
  );
}
