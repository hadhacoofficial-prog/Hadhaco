import { useCallback, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { cn } from "@hadha/shared-utils";

export type SortDir = "asc" | "desc";

export interface SortState<K extends string = string> {
  sortBy: K;
  sortDir: SortDir;
}

/**
 * The header-click rule: clicking the active column flips direction;
 * clicking a new column starts at that column's natural first direction
 * (text A→Z ascending, dates / amounts newest-or-largest first).
 */
export function nextSort<K extends string>(
  prev: SortState<K>,
  key: K,
  firstDir: Partial<Record<K, SortDir>> = {},
): SortState<K> {
  return prev.sortBy === key
    ? { sortBy: key, sortDir: prev.sortDir === "asc" ? "desc" : "asc" }
    : { sortBy: key, sortDir: firstDir[key] ?? "desc" };
}

/** Column-header sort state held in React state (see `nextSort`). */
export function useTableSort<K extends string>(
  initial: SortState<K>,
  firstDir: Partial<Record<K, SortDir>> = {},
) {
  const [sort, setSort] = useState<SortState<K>>(initial);
  const onSort = useCallback(
    (key: K) => setSort((prev) => nextSort(prev, key, firstDir)),
    // firstDir is a static config object at every call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  return { ...sort, onSort, setSort };
}

interface SortableHeaderProps<K extends string> {
  label: string;
  sortKey: K;
  sort: SortState<K>;
  onSort: (key: K) => void;
  className?: string;
  align?: "left" | "right";
}

/**
 * `<th>` with a sort toggle. Exposes `aria-sort` on the header cell and a
 * direction icon plus visually-hidden text, so the state is never conveyed
 * by the icon alone.
 */
export function SortableHeader<K extends string>({
  label,
  sortKey,
  sort,
  onSort,
  className,
  align = "left",
}: SortableHeaderProps<K>) {
  const active = sort.sortBy === sortKey;
  const ariaSort = active ? (sort.sortDir === "asc" ? "ascending" : "descending") : "none";
  const Icon = !active ? ArrowUpDown : sort.sortDir === "asc" ? ArrowUp : ArrowDown;

  return (
    <th className={cn("px-4 py-3", className)} aria-sort={ariaSort} scope="col">
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "group inline-flex items-center gap-1.5 uppercase tracking-[0.18em] hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
          align === "right" && "flex-row-reverse",
          active && "text-foreground",
        )}
      >
        {label}
        <Icon
          aria-hidden
          className={cn(
            "size-3 shrink-0 transition-opacity",
            active ? "opacity-100" : "opacity-40 group-hover:opacity-80",
          )}
        />
        <span className="sr-only">
          {active
            ? `, sorted ${ariaSort}. Activate to sort ${sort.sortDir === "asc" ? "descending" : "ascending"}.`
            : ", activate to sort."}
        </span>
      </button>
    </th>
  );
}
