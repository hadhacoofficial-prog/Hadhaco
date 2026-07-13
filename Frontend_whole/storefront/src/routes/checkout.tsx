import { useState, useEffect, useRef } from "react";
import { createFileRoute, useNavigate, Link, redirect } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Truck, Tag, Plus, AlertTriangle, Loader2, Gift, X, Check } from "lucide-react";
import { toast } from "sonner";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import {
  ReservationCountdown,
  ReservationExpiredModal,
} from "@/components/site/ReservationCountdown";
import { Field, PhoneField, isValidIndianMobile } from "@/components/common/FormField";
import { useCart } from "@/stores/cart";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import { supabase } from "@/lib/supabase/client";
import hadhaLogo from "@/assets/hadha-logo.png";
import type {
  AddressResponse,
  AddressCreateRequest,
  CreatePaymentIntentRequest,
  CreatePaymentIntentResponse,
  VerifyPaymentRequest,
  VerifyPaymentResponse,
  ComplimentaryGift,
} from "@/types/customer";

const GIFT_OPTIONS: { value: ComplimentaryGift; emoji: string; label: string }[] = [
  { value: "Traditional Sweet", emoji: "🍬", label: "Traditional Sweet" },
  { value: "Traditional Hot Snack", emoji: "🌶️", label: "Traditional Hot Snack" },
];

const GIFT_ELIGIBILITY_THRESHOLD = 2000;

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
  const [phone, setPhone] = useState("");
  const [altPhone, setAltPhone] = useState("");
  const [phoneError, setPhoneError] = useState<string | undefined>();
  const [altPhoneError, setAltPhoneError] = useState<string | undefined>();
  const [couponCode, setCouponCode] = useState("");
  const [appliedCoupon, setAppliedCoupon] = useState<{
    code: string;
    discount: number;
    type: string;
    description: string | null;
  } | null>(null);
  const [giftPopup, setGiftPopup] = useState<{
    orderId: string;
    orderNumber: string;
  } | null>(null);
  const [selectedGift, setSelectedGift] = useState<ComplimentaryGift | null>(null);
  const pendingNavigationRef = useRef<{
    orderId: string;
    orderNumber: string;
  } | null>(null);

  // Reservation tracking
  const [checkoutState, setCheckoutState] = useState<CheckoutState>("idle");
  const [reservationStartedAt, setReservationStartedAt] = useState<number | null>(null);
  const currentIntentRef = useRef<CreatePaymentIntentResponse | null>(null);

  const { data: addresses = [] } = useQuery({
    queryKey: queryKeys.addresses.all,
    queryFn: () => api.get<AddressResponse[]>("/me/addresses"),
  });

  const { data: giftFlag } = useQuery({
    queryKey: ["settings", "flags", "complimentary_gift_enabled"] as const,
    queryFn: () => api.get<{ value: boolean }>("/settings/flags/complimentary_gift_enabled"),
    staleTime: 60_000,
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
  const ship =
    lines.length === 0
      ? 0
      : shippingMethod === "express"
        ? appliedCoupon?.type === "free_shipping"
          ? 0
          : 199
        : sub > 999
          ? 0
          : appliedCoupon?.type === "free_shipping"
            ? 0
            : 99;
  const couponDiscount =
    appliedCoupon?.type === "free_shipping"
      ? shippingMethod === "express"
        ? 199
        : 99
      : (appliedCoupon?.discount ?? 0);
  const total = Math.max(
    sub + ship - (appliedCoupon?.type !== "free_shipping" ? couponDiscount : 0),
    0,
  );

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

  const saveGiftMutation = useMutation({
    mutationFn: ({ orderId, gift }: { orderId: string; gift: ComplimentaryGift }) =>
      api.patch<unknown>(`/orders/${orderId}/complimentary-gift`, { body: { gift } }),
  });

  const verifyPaymentMutation = useMutation({
    mutationFn: (body: VerifyPaymentRequest) =>
      api.post<VerifyPaymentResponse>("/orders/verify-payment", { body }),
    onSuccess: (result) => {
      clear();
      queryClient.invalidateQueries({ queryKey: queryKeys.orders.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cart.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.products.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventory.cartStock([]) });
      queryClient.invalidateQueries({ queryKey: queryKeys.collections.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cms.homepage });
      queryClient.invalidateQueries({ queryKey: queryKeys.search.all });
      setCheckoutState("idle");
      setReservationStartedAt(null);

      const destination = { orderId: result.order_id, orderNumber: result.order_number };
      // Check eligibility using the total captured at render time
      if (giftFlag?.value && total >= GIFT_ELIGIBILITY_THRESHOLD) {
        pendingNavigationRef.current = destination;
        setSelectedGift(null);
        setGiftPopup(destination);
      } else {
        navigate({
          to: "/checkout/success",
          search: { order: result.order_number, orderId: result.order_id },
        });
      }
    },
    onError: (e) => {
      setCheckoutState("payment_failed");
      toast.error(`Payment verification failed: ${toUserMessage(e)}`);
    },
  });

  const handleGiftConfirm = async () => {
    if (!selectedGift || !giftPopup) return;
    try {
      await saveGiftMutation.mutateAsync({ orderId: giftPopup.orderId, gift: selectedGift });
    } catch {
      // Gift save failed — non-critical, proceed to success anyway
    }
    const dest = pendingNavigationRef.current!;
    setGiftPopup(null);
    pendingNavigationRef.current = null;
    navigate({
      to: "/checkout/success",
      search: { order: dest.orderNumber, orderId: dest.orderId },
    });
  };

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

    let shippingAddressId = selectedAddressId !== "new" ? selectedAddressId : null;

    if (!shippingAddressId) {
      const phoneValid = isValidIndianMobile(phone);
      const altPhoneValid = altPhone === "" || isValidIndianMobile(altPhone);
      setPhoneError(phoneValid ? undefined : "Enter a valid 10-digit mobile number");
      setAltPhoneError(altPhoneValid ? undefined : "Enter a valid 10-digit mobile number");
      if (!phoneValid || !altPhoneValid) return;
    }

    setCheckoutState("reserving");

    if (!shippingAddressId) {
      const fd = new FormData(e.currentTarget as HTMLFormElement);
      const newAddress: AddressCreateRequest = {
        type: "shipping",
        full_name: `${fd.get("firstName") ?? ""} ${fd.get("lastName") ?? ""}`.trim(),
        phone: `+91${phone}`,
        line1: String(fd.get("address") ?? ""),
        line2: String(fd.get("apt") ?? "") || null,
        landmark: String(fd.get("landmark") ?? "") || null,
        alternate_phone: altPhone ? `+91${altPhone}` : null,
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
      coupon_code: appliedCoupon?.code || undefined,
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

      {/* ── Complimentary Gift Popup ── */}
      {giftPopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="relative bg-background w-full max-w-md p-8 shadow-2xl">
            {/* Logo */}
            <div className="flex justify-center mb-6">
              <img src={hadhaLogo} alt="Hadha" className="h-10 object-contain" />
            </div>

            {/* Title */}
            <div className="text-center mb-6">
              <div className="inline-flex items-center gap-2 mb-3">
                <Gift className="size-5 text-accent" />
                <p className="text-[11px] uppercase tracking-[0.3em] text-accent">
                  Complimentary Gift
                </p>
              </div>
              <p className="text-sm text-muted-foreground max-w-xs mx-auto">
                Congratulations! Your order qualifies for a complimentary gift. Please choose one
                gift before completing your order.
              </p>
            </div>

            {/* Gift options */}
            <div className="space-y-3 mb-8">
              {GIFT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setSelectedGift(opt.value)}
                  className={`w-full flex items-center gap-4 border p-4 text-left transition ${
                    selectedGift === opt.value
                      ? "border-foreground bg-secondary"
                      : "border-border hover:border-foreground/50"
                  }`}
                >
                  <span className="text-2xl">{opt.emoji}</span>
                  <span className="font-medium text-sm flex-1">{opt.label}</span>
                  <span
                    className={`size-5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                      selectedGift === opt.value
                        ? "border-foreground bg-foreground"
                        : "border-border"
                    }`}
                  >
                    {selectedGift === opt.value && (
                      <span className="size-2 rounded-full bg-background" />
                    )}
                  </span>
                </button>
              ))}
            </div>

            {/* Confirm button */}
            <button
              type="button"
              onClick={handleGiftConfirm}
              disabled={!selectedGift || saveGiftMutation.isPending}
              className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {saveGiftMutation.isPending && (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              )}
              Continue to Order Summary
            </button>
          </div>
        </div>
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
                            {addr.landmark && (
                              <p className="text-muted-foreground">Landmark: {addr.landmark}</p>
                            )}
                            <p className="text-muted-foreground">
                              {addr.city}, {addr.state} {addr.postal_code}
                            </p>
                            {addr.alternate_phone && (
                              <p className="text-muted-foreground">Alt: {addr.alternate_phone}</p>
                            )}
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
                        placeholder="Alternative contact number"
                        value={altPhone}
                        onValueChange={(digits) => {
                          setAltPhone(digits);
                          setAltPhoneError(undefined);
                        }}
                        error={altPhoneError}
                      />
                      <Field label="Address" name="address" className="md:col-span-2" required />
                      <Field
                        label="Apartment, suite (optional)"
                        name="apt"
                        className="md:col-span-2"
                      />
                      <Field
                        label="Landmark (optional)"
                        name="landmark"
                        className="md:col-span-2"
                        placeholder="Near SBI Bank, Opposite Temple"
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
                        label: "Standard Delivery",
                        note:
                          sub > 999 ? "Free delivery on orders above ₹999" : "3–5 business days",
                        price: sub > 999 ? 0 : 99,
                      },
                      {
                        id: "express" as const,
                        label: "Express Delivery",
                        note: "Express Delivery available in Metro Cities.",
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
                        <span className="font-sans font-bold">
                          {opt.price === 0 ? "Free" : formatINR(opt.price)}
                        </span>
                      </label>
                    ))}
                  </div>
                </Section>

                <Section title="Coupons & Offers">
                  <CouponSection
                    subtotal={sub}
                    appliedCoupon={appliedCoupon}
                    onApply={setAppliedCoupon}
                    onRemove={() => {
                      setAppliedCoupon(null);
                      setCouponCode("");
                    }}
                    couponCode={couponCode}
                    setCouponCode={setCouponCode}
                    ctx={{
                      cartProductIds: lines.map((l) => l.productId),
                      shippingMethod,
                      deliveryState: addresses.find((a) => a.id === selectedAddressId)?.state,
                      deliveryCity: addresses.find((a) => a.id === selectedAddressId)?.city,
                      deliveryPincode: addresses.find((a) => a.id === selectedAddressId)
                        ?.postal_code,
                    }}
                  />
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
                      <span className="text-sm font-sans font-bold whitespace-nowrap">
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
                    <span>{ship === 0 ? "Free" : formatINR(ship)}</span>
                  </div>
                  {appliedCoupon && couponDiscount > 0 && (
                    <div className="flex justify-between text-green-700 dark:text-green-400">
                      <span className="flex items-center gap-1">
                        <Tag className="size-3" />
                        {appliedCoupon.code}
                      </span>
                      <span>−{formatINR(couponDiscount)}</span>
                    </div>
                  )}
                  <div className="flex justify-between items-baseline border-t border-border pt-3">
                    <span className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
                      Total
                    </span>
                    <span className="font-sans font-bold text-2xl">{formatINR(total)}</span>
                  </div>
                  {appliedCoupon && couponDiscount > 0 && (
                    <p className="text-[11px] text-green-700 dark:text-green-400 text-right">
                      You save {formatINR(couponDiscount)} with this order
                    </p>
                  )}
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

// ── Coupon Section ─────────────────────────────────────────────────────────────

interface AppliedCoupon {
  code: string;
  discount: number;
  type: string;
  description: string | null;
}

interface AppliedCouponValidateCtx {
  cartProductIds: string[];
  shippingMethod: string;
  deliveryState?: string;
  deliveryCity?: string;
  deliveryPincode?: string;
}

interface CouponSectionProps {
  subtotal: number;
  appliedCoupon: AppliedCoupon | null;
  onApply: (c: AppliedCoupon) => void;
  onRemove: () => void;
  couponCode: string;
  setCouponCode: (v: string) => void;
  ctx?: AppliedCouponValidateCtx;
}

function CouponSection({
  subtotal,
  appliedCoupon,
  onApply,
  onRemove,
  couponCode,
  setCouponCode,
  ctx,
}: CouponSectionProps) {
  const [error, setError] = useState<string | null>(null);

  const validateMutation = useMutation({
    mutationFn: (code: string) =>
      api.post<{
        valid: boolean;
        discount_amount: number;
        message: string;
        stackable?: boolean;
        coupon?: { code: string; coupon_type: string; description: string | null };
      }>("/coupons/validate", {
        body: {
          code: code.toUpperCase(),
          order_subtotal: subtotal,
          cart_product_ids: ctx?.cartProductIds ?? [],
          shipping_method: ctx?.shippingMethod,
          delivery_state: ctx?.deliveryState,
          delivery_city: ctx?.deliveryCity,
          delivery_pincode: ctx?.deliveryPincode,
        },
      }),
    onSuccess: (res, code) => {
      if (res.valid) {
        setError(null);
        onApply({
          code: res.coupon?.code ?? code.toUpperCase(),
          discount: res.discount_amount,
          type: res.coupon?.coupon_type ?? "fixed_amount",
          description: res.coupon?.description ?? null,
        });
      } else {
        setError(res.message);
      }
    },
    onError: () => setError("Could not validate coupon. Please try again."),
  });

  const handleApply = (code = couponCode) => {
    const c = code.trim().toUpperCase();
    if (!c) return;
    setError(null);
    validateMutation.mutate(c);
  };

  return (
    <div className="space-y-4">
      {/* Applied coupon chip */}
      {appliedCoupon ? (
        <div className="flex items-center justify-between gap-3 border border-green-300 bg-green-50 dark:bg-green-950/30 dark:border-green-800 px-4 py-3">
          <div className="flex items-center gap-2">
            <Check className="size-4 text-green-600 shrink-0" />
            <div>
              <p className="text-sm font-medium text-green-800 dark:text-green-300">
                {appliedCoupon.code} applied!
              </p>
              <p className="text-xs text-green-700 dark:text-green-400">
                {appliedCoupon.type === "free_shipping"
                  ? "Free shipping unlocked"
                  : `You save ₹${appliedCoupon.discount.toFixed(2)}`}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onRemove}
            className="shrink-0 text-green-700 dark:text-green-400 hover:text-destructive transition"
            aria-label="Remove coupon"
          >
            <X className="size-4" />
          </button>
        </div>
      ) : (
        <>
          {/* Input row */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Tag className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <input
                type="text"
                value={couponCode}
                onChange={(e) => {
                  setCouponCode(e.target.value.toUpperCase());
                  setError(null);
                }}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleApply())}
                placeholder="Enter coupon code"
                className="w-full bg-background border border-border pl-10 pr-3 py-2.5 text-sm outline-none focus:border-foreground transition uppercase tracking-wider"
                disabled={validateMutation.isPending}
              />
            </div>
            <button
              type="button"
              onClick={() => handleApply()}
              disabled={!couponCode.trim() || validateMutation.isPending}
              className="px-5 py-2.5 bg-foreground text-background text-[11px] uppercase tracking-[0.2em] hover:bg-primary transition disabled:opacity-40 whitespace-nowrap flex items-center gap-2"
            >
              {validateMutation.isPending && <Loader2 className="size-3.5 animate-spin" />}
              Apply
            </button>
          </div>

          {/* Error message */}
          {error && (
            <p className="flex items-center gap-1.5 text-xs text-destructive">
              <AlertTriangle className="size-3.5 shrink-0" />
              {error}
            </p>
          )}
        </>
      )}
    </div>
  );
}
