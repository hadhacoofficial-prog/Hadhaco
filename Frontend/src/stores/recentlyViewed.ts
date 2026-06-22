import { create } from "zustand";
import { persist } from "zustand/middleware";

interface RVState {
  ids: string[];
  push: (id: string) => void;
}

export const useRecentlyViewed = create<RVState>()(
  persist(
    (set) => ({
      ids: [],
      push: (id) => set((s) => ({ ids: [id, ...s.ids.filter((x) => x !== id)].slice(0, 8) })),
    }),
    { name: "hadha-recent" },
  ),
);
