import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import {
  dateRangeFields,
  dateRangeFromSearch,
  dateRangeToSearch,
  patchSearch,
  sortFromSearch,
  sortToSearch,
  urlBool,
  urlDir,
  urlEnum,
  urlFlag,
  urlId,
  urlPage,
  urlText,
  useClampPage,
  useUrlSearchText,
} from "@/lib/tableUrlState";

const schema = z.object({
  q: urlText,
  status: urlEnum(["paid", "pending"]),
  active: urlBool,
  archived: urlFlag,
  category: urlId,
  ...dateRangeFields,
  sort: urlEnum(["total", "created_at"]),
  dir: urlDir,
  page: urlPage,
});

describe("search schema helpers", () => {
  it("drops each invalid field instead of failing the whole parse", () => {
    expect(
      schema.parse({
        q: "  hdh  ",
        status: "bogus",
        active: "maybe",
        archived: "no",
        category: "not-a-uuid",
        date: "forever",
        from: "2026-13",
        sort: "password",
        dir: "up",
        page: 0,
      }),
    ).toEqual({ q: "hdh" });
  });

  it("parses JSON-typed and string-typed values alike", () => {
    expect(
      schema.parse({
        active: false,
        archived: "true",
        page: "3",
        date: "custom",
        from: "2026-10-01",
      }),
    ).toEqual({ active: false, archived: true, page: 3, date: "custom", from: "2026-10-01" });
  });
});

describe("patchSearch", () => {
  it("resets page on any filter change and strips cleared values", () => {
    expect(patchSearch({ q: "a", status: "paid", page: 4 }, { status: undefined })).toEqual({
      q: "a",
    });
  });

  it("keeps the page when the patch sets it, and keeps false", () => {
    expect(patchSearch({ active: false, page: 2 }, { page: 3 })).toEqual({
      active: false,
      page: 3,
    });
  });
});

describe("date range ↔ URL", () => {
  it("stores the preset, not resolved instants", () => {
    expect(dateRangeToSearch({ preset: "last7" })).toEqual({
      date: "last7",
      from: undefined,
      to: undefined,
    });
    expect(dateRangeToSearch({ preset: "any" }).date).toBeUndefined();
  });

  it("only keeps custom days for the custom preset and round-trips", () => {
    const custom = { preset: "custom" as const, from: "2026-10-01", to: "2026-10-07" };
    expect(dateRangeFromSearch(dateRangeToSearch(custom))).toEqual(custom);
    expect(dateRangeFromSearch({ date: "today", from: "2026-01-01" })).toEqual({ preset: "today" });
    expect(dateRangeFromSearch({})).toEqual({ preset: "any" });
  });
});

describe("sort ↔ URL", () => {
  const fallback = { sortBy: "created_at" as const, sortDir: "desc" as const };

  it("writes nothing for the default sort", () => {
    expect(sortToSearch(fallback, fallback)).toEqual({ sort: undefined, dir: undefined });
  });

  it("round-trips a non-default sort", () => {
    const next = { sortBy: "total" as const, sortDir: "asc" as const };
    expect(sortFromSearch(sortToSearch(next, fallback), fallback)).toEqual(next);
    // Default key, flipped direction: only `dir` is written.
    expect(sortToSearch({ sortBy: "created_at", sortDir: "asc" }, fallback)).toEqual({
      sort: undefined,
      dir: "asc",
    });
  });
});

describe("useUrlSearchText", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("commits once after typing settles", () => {
    const commit = vi.fn();
    const { result } = renderHook(({ url }) => useUrlSearchText(url, commit), {
      initialProps: { url: undefined as string | undefined },
    });
    act(() => result.current[1]("h"));
    act(() => result.current[1]("hd"));
    act(() => result.current[1]("hdh"));
    expect(commit).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(300));
    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit).toHaveBeenCalledWith("hdh");
  });

  it("follows external URL changes (back/forward, chip removal)", () => {
    const commit = vi.fn();
    const { result, rerender } = renderHook(({ url }) => useUrlSearchText(url, commit), {
      initialProps: { url: "rings" as string | undefined },
    });
    expect(result.current[0]).toBe("rings");
    rerender({ url: undefined });
    expect(result.current[0]).toBe("");
    act(() => vi.advanceTimersByTime(300));
    // The settling debounce of the external change must not write back.
    expect(commit).not.toHaveBeenCalled();
  });

  it("does not commit when typing returns to the current value", () => {
    const commit = vi.fn();
    const { result } = renderHook(() => useUrlSearchText("ab", commit));
    act(() => result.current[1]("abc"));
    act(() => result.current[1]("ab"));
    act(() => vi.advanceTimersByTime(300));
    expect(commit).not.toHaveBeenCalled();
  });
});

describe("useClampPage", () => {
  it("snaps an out-of-range page back to the last page", () => {
    const clamp = vi.fn();
    renderHook(() => useClampPage(9, { itemCount: 0, totalPages: 3 }, false, clamp));
    expect(clamp).toHaveBeenCalledWith(3);
  });

  it("goes to page 1 when the whole result set is empty", () => {
    const clamp = vi.fn();
    renderHook(() => useClampPage(4, { itemCount: 0, totalPages: 0 }, false, clamp));
    expect(clamp).toHaveBeenCalledWith(1);
  });

  it("waits for real data and leaves valid pages alone", () => {
    const clamp = vi.fn();
    renderHook(() => useClampPage(9, { itemCount: 0, totalPages: 3 }, true, clamp));
    renderHook(() => useClampPage(2, { itemCount: 15, totalPages: 3 }, false, clamp));
    renderHook(() => useClampPage(1, { itemCount: 0, totalPages: 0 }, false, clamp));
    renderHook(() => useClampPage(5, undefined, false, clamp));
    expect(clamp).not.toHaveBeenCalled();
  });
});
