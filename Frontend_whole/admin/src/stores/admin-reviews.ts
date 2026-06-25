import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ReviewStatus = "pending" | "approved" | "rejected";

interface ReviewsAdminState {
  status: Record<string, ReviewStatus>;
  setStatus: (id: string, status: ReviewStatus) => void;
}

export const useAdminReviews = create<ReviewsAdminState>()(
  persist(
    (set) => ({
      status: {},
      setStatus: (id, status) => set((s) => ({ status: { ...s.status, [id]: status } })),
    }),
    { name: "hadha-admin-reviews" },
  ),
);
