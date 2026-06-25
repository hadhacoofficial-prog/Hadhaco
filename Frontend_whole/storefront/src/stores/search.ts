import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SearchState {
  recent: string[];
  push: (q: string) => void;
  clear: () => void;
}

export const useRecentSearches = create<SearchState>()(
  persist(
    (set) => ({
      recent: [],
      push: (q) =>
        set((s) => {
          const t = q.trim();
          if (!t) return s;
          return { recent: [t, ...s.recent.filter((x) => x !== t)].slice(0, 6) };
        }),
      clear: () => set({ recent: [] }),
    }),
    { name: "hadha-recent-search" },
  ),
);
