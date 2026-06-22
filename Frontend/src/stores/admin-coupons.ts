import { create } from "zustand";
import { persist } from "zustand/middleware";
import { SITE } from "@/config/site";
import type { Coupon } from "@/types/shop";

const seed: Coupon[] = Object.entries(SITE.coupons).map(([code, c]) => ({
  code,
  type: c.type as Coupon["type"],
  value: c.value,
  description: c.description,
}));

interface CouponsAdminState {
  coupons: Coupon[];
  upsert: (c: Coupon) => void;
  remove: (code: string) => void;
}

export const useAdminCoupons = create<CouponsAdminState>()(
  persist(
    (set) => ({
      coupons: seed,
      upsert: (c) =>
        set((s) => {
          const code = c.code.trim().toUpperCase();
          const next = s.coupons.filter((x) => x.code.toUpperCase() !== code);
          return { coupons: [...next, { ...c, code }] };
        }),
      remove: (code) =>
        set((s) => ({
          coupons: s.coupons.filter((c) => c.code.toUpperCase() !== code.toUpperCase()),
        })),
    }),
    { name: "hadha-admin-coupons" },
  ),
);
