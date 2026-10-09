/**
 * URL-backed admin table state.
 *
 * Every admin list keeps its filters / sort / page in the route's search
 * params so refresh, back/forward and shared links reproduce the exact
 * view. Conventions (shared by every list page):
 *
 *   ?q=…&page=2&sort=total&dir=asc&date=custom&from=2026-10-01&to=2026-10-07
 *
 * - Each field is validated with `.catch(undefined)`: a malformed or stale
 *   link silently drops that one filter instead of erroring.
 * - Defaults are never written (default sort, page 1, "any" date), so URLs
 *   stay short and a page with no filters has a clean URL.
 * - Any filter / sort change resets to page 1 (`patchSearch`).
 * - Date ranges store the preset (and the custom days), never resolved ISO
 *   instants — "Last 7 days" stays relative when the link is reopened.
 */
import { useEffect, useRef, useState } from "react";
import { z } from "zod";

import { useDebounce } from "@hadha/shared-ui/common/use-debounce";
import type { DatePreset, DateRangeValue } from "@hadha/shared-ui/data/DateRangeFilter";
import type { SortDir, SortState } from "@hadha/shared-ui/data/SortableHeader";

// ─── Field schemas ──────────────────────────────────────────────────────────

export const urlText = z.string().trim().max(200).optional().catch(undefined);
export const urlId = z.string().uuid().optional().catch(undefined);
export const urlPage = z.coerce.number().int().min(1).optional().catch(undefined);
export const urlDir = z.enum(["asc", "desc"]).optional().catch(undefined);
export const urlAmount = z.coerce.number().min(0).max(100_000_000).optional().catch(undefined);
export const urlFlag = z
  .preprocess((v) => (v === true || v === "true" ? true : undefined), z.literal(true).optional())
  .catch(undefined);
/** true / false / absent — for tri-state filters like "Active / Inactive / All". */
export const urlBool = z
  .preprocess(
    (v) => (v === true || v === "true" ? true : v === false || v === "false" ? false : undefined),
    z.boolean().optional(),
  )
  .catch(undefined);

/** Optional enum param — unknown values are dropped. */
export const urlEnum = <const T extends readonly [string, ...string[]]>(values: T) =>
  z.enum(values).optional().catch(undefined);

const DATE_PRESETS = [
  "today",
  "yesterday",
  "last7",
  "last30",
  "thisMonth",
  "lastMonth",
  "custom",
] as const satisfies readonly Exclude<DatePreset, "any">[];
const isoDay = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/)
  .optional()
  .catch(undefined);

/** `date`, `from`, `to` — spread into a page's search schema. */
export const dateRangeFields = {
  date: urlEnum(DATE_PRESETS),
  from: isoDay,
  to: isoDay,
};

// ─── Conversions ────────────────────────────────────────────────────────────

export function dateRangeFromSearch(s: {
  date?: Exclude<DatePreset, "any">;
  from?: string;
  to?: string;
}): DateRangeValue {
  if (!s.date) return { preset: "any" };
  return s.date === "custom" ? { preset: "custom", from: s.from, to: s.to } : { preset: s.date };
}

export function dateRangeToSearch(v: DateRangeValue) {
  return {
    date: v.preset === "any" ? undefined : v.preset,
    from: v.preset === "custom" ? v.from : undefined,
    to: v.preset === "custom" ? v.to : undefined,
  };
}

export function sortFromSearch<K extends string>(
  s: { sort?: K; dir?: SortDir },
  fallback: SortState<K>,
): SortState<K> {
  if (!s.sort) return { sortBy: fallback.sortBy, sortDir: s.dir ?? fallback.sortDir };
  return { sortBy: s.sort, sortDir: s.dir ?? fallback.sortDir };
}

/** Writes nothing for the default sort so unsorted pages keep clean URLs. */
export function sortToSearch<K extends string>(next: SortState<K>, fallback: SortState<K>) {
  return {
    sort: next.sortBy === fallback.sortBy ? undefined : next.sortBy,
    dir: next.sortDir === fallback.sortDir ? undefined : next.sortDir,
  };
}

/**
 * Merge a patch into the current search: resets `page` unless the patch
 * sets it, and strips empty values ("" / null / undefined) so cleared
 * filters disappear from the URL. `false` is kept (it's a real filter value).
 */
export function patchSearch<T extends object>(prev: T, patch: Partial<T>): T {
  const merged: Record<string, unknown> = {
    ...prev,
    ...("page" in patch ? {} : { page: undefined }),
    ...patch,
  };
  for (const [k, v] of Object.entries(merged)) {
    if (v === undefined || v === null || v === "") delete merged[k];
  }
  return merged as T;
}

// ─── Page clamping ──────────────────────────────────────────────────────────

/**
 * With the page in the URL, a stale link (or deleting the last row of the
 * last page) can point past the end, which would render a misleading "no
 * results" state. Once real (non-placeholder) data shows an empty page
 * beyond the first, snap back to the last page that exists.
 */
export function useClampPage(
  page: number,
  result: { itemCount: number; totalPages: number } | undefined,
  isPlaceholder: boolean,
  clamp: (lastPage: number) => void,
) {
  const itemCount = result?.itemCount;
  const totalPages = result?.totalPages;
  useEffect(() => {
    if (isPlaceholder || itemCount === undefined || totalPages === undefined) return;
    const last = Math.max(1, totalPages);
    if (itemCount === 0 && page > 1 && page !== last) clamp(last);
    // `clamp` is recreated each render by callers; the inputs above decide.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, itemCount, totalPages, isPlaceholder]);
}

// ─── Debounced search text ──────────────────────────────────────────────────

/**
 * Text-input state for a URL `q` param. Keystrokes stay local; the value is
 * committed to the URL once typing pauses (300 ms) — one history entry per
 * search, not per keystroke. URL changes from elsewhere (back/forward, chip
 * removal, "Clear all") flow back into the input, and a pending debounce
 * never overwrites them because only user-typed text is ever committed.
 */
export function useUrlSearchText(
  urlValue: string | undefined,
  commit: (value: string | undefined) => void,
): [string, (value: string) => void] {
  const [input, setInput] = useState(urlValue ?? "");
  const typing = useRef(false);
  const debounced = useDebounce(input, 300);

  useEffect(() => {
    if (!typing.current) setInput(urlValue ?? "");
  }, [urlValue]);

  useEffect(() => {
    if (!typing.current) return;
    typing.current = false;
    const next = debounced.trim() || undefined;
    if (next !== (urlValue || undefined)) commit(next);
    // Only a settled keystroke should commit — not URL / commit identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  const onChange = (value: string) => {
    // Typing back to the committed value is not a pending edit (the debounced
    // value never changes, so nothing would clear the flag otherwise).
    typing.current = (value.trim() || undefined) !== (urlValue || undefined);
    setInput(value);
  };
  return [input, onChange];
}
