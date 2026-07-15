import { create } from "zustand";
import { persist } from "zustand/middleware";

export type CheckoutStep =
  | "idle"
  | "reserving"
  | "payment_open"
  | "verifying"
  | "payment_failed"
  | "reservation_expired";

export interface AppliedCoupon {
  code: string;
  discount: number;
  type: string;
  description: string | null;
}

interface CheckoutFormState {
  shippingMethod: "standard" | "express";
  billingSame: boolean;
  selectedAddressId: string | "new";
  phone: string;
  altPhone: string;
  couponCode: string;
  appliedCoupon: AppliedCoupon | null;
  checkoutStep: CheckoutStep;
  reservationStartedAt: number | null;

  setShippingMethod: (m: "standard" | "express") => void;
  setBillingSame: (v: boolean) => void;
  setSelectedAddressId: (id: string | "new") => void;
  setPhone: (v: string) => void;
  setAltPhone: (v: string) => void;
  setCouponCode: (v: string) => void;
  setAppliedCoupon: (c: AppliedCoupon | null) => void;
  setCheckoutStep: (s: CheckoutStep) => void;
  setReservationStartedAt: (t: number | null) => void;
  reset: () => void;
}

const INITIAL_STATE = {
  shippingMethod: "standard" as const,
  billingSame: true,
  selectedAddressId: "new" as const,
  phone: "",
  altPhone: "",
  couponCode: "",
  appliedCoupon: null,
  checkoutStep: "idle" as const,
  reservationStartedAt: null,
};

/**
 * Zustand store for checkout form state.
 *
 * Persists safe fields (address selection, shipping method, coupon) to
 * localStorage so they survive a full page refresh during checkout.
 * Transient fields (checkoutStep, reservationStartedAt) are intentionally
 * excluded — they reset on page reload, which is correct behavior since
 * a server-side reservation would need to be re-established anyway.
 */
export const useCheckoutStore = create<CheckoutFormState>()(
  persist(
    (set) => ({
      ...INITIAL_STATE,

      setShippingMethod: (m) => set({ shippingMethod: m }),
      setBillingSame: (v) => set({ billingSame: v }),
      setSelectedAddressId: (id) => set({ selectedAddressId: id }),
      setPhone: (v) => set({ phone: v }),
      setAltPhone: (v) => set({ altPhone: v }),
      setCouponCode: (v) => set({ couponCode: v }),
      setAppliedCoupon: (c) => set({ appliedCoupon: c }),
      setCheckoutStep: (s) => set({ checkoutStep: s }),
      setReservationStartedAt: (t) => set({ reservationStartedAt: t }),
      reset: () => set(INITIAL_STATE),
    }),
    {
      name: "hadha-checkout",
      partialize: (state) => ({
        shippingMethod: state.shippingMethod,
        billingSame: state.billingSame,
        selectedAddressId: state.selectedAddressId,
        couponCode: state.couponCode,
        appliedCoupon: state.appliedCoupon,
      }),
    },
  ),
);
