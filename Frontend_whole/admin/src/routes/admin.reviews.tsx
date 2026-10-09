import { useCallback, useMemo } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Star, Check, X, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { ReviewListSkeleton } from "@/components/loading/ReviewCardSkeleton";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { TableSearchInput } from "@hadha/shared-ui/data/TableSearchInput";
import { FilterSelect } from "@hadha/shared-ui/data/FilterSelect";
import {
  DateRangeFilter,
  describeDateRange,
  resolveDateRange,
  type DateRangeValue,
} from "@hadha/shared-ui/data/DateRangeFilter";
import { ActiveFilterChips, type FilterChip } from "@hadha/shared-ui/data/ActiveFilterChips";
import { TablePagination } from "@hadha/shared-ui/data/TablePagination";
import {
  dateRangeFields,
  dateRangeFromSearch,
  dateRangeToSearch,
  patchSearch,
  useClampPage,
  urlBool,
  urlEnum,
  urlPage,
  urlText,
  useUrlSearchText,
} from "@/lib/tableUrlState";
import type { ReviewAction, ReviewDto, ReviewListResponse } from "@/types/admin";

type StatusFilter = "all" | "pending" | "approved" | "rejected";

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
];

function statusBadge(r: ReviewDto) {
  if (r.is_approved) {
    return (
      <span className="text-[10px] uppercase tracking-[0.18em] px-2 py-0.5 bg-accent/10 text-accent border border-accent/20">
        Approved
      </span>
    );
  }
  if (r.is_rejected) {
    return (
      <span className="text-[10px] uppercase tracking-[0.18em] px-2 py-0.5 bg-destructive/10 text-destructive border border-destructive/20">
        Rejected
      </span>
    );
  }
  return (
    <span className="text-[10px] uppercase tracking-[0.18em] px-2 py-0.5 bg-amber-50 text-amber-700 border border-amber-200">
      Pending
    </span>
  );
}

// Combined sort options — a card list has no column headers to click.
const SORT_OPTIONS = [
  { value: "created_at:desc", label: "Newest first" },
  { value: "created_at:asc", label: "Oldest first" },
  { value: "rating:desc", label: "Highest rating" },
  { value: "rating:asc", label: "Lowest rating" },
  { value: "helpful_count:desc", label: "Most helpful" },
  { value: "product_name:asc", label: "Product A–Z" },
] as const;
type SortValue = (typeof SORT_OPTIONS)[number]["value"];
const DEFAULT_SORT: SortValue = "created_at:desc";

const reviewsSearchSchema = z.object({
  status: urlEnum(["pending", "approved", "rejected"]),
  q: urlText,
  rating: z.coerce.number().int().min(1).max(5).optional().catch(undefined),
  verified: urlBool,
  ...dateRangeFields,
  sort: urlEnum([
    "created_at:desc",
    "created_at:asc",
    "rating:desc",
    "rating:asc",
    "helpful_count:desc",
    "product_name:asc",
  ]),
  page: urlPage,
});
type ReviewsSearch = z.infer<typeof reviewsSearchSchema>;

export const Route = createFileRoute("/admin/reviews")({
  validateSearch: reviewsSearchSchema,
  component: AdminReviews,
});

const RATING_OPTIONS = [5, 4, 3, 2, 1].map((n) => ({ value: String(n), label: `${n} ★` }));
const VERIFIED_OPTIONS = [
  { value: "true", label: "Verified purchase" },
  { value: "false", label: "Not verified" },
];

function AdminReviews() {
  const queryClient = useQueryClient();

  // All view state lives in the URL (refresh / back / shared links keep it).
  const urlSearch = Route.useSearch();
  const navigate = Route.useNavigate();
  const update = useCallback(
    (patch: Partial<ReviewsSearch>, replace = false) =>
      navigate({ search: (prev) => patchSearch(prev, patch), replace }),
    [navigate],
  );

  const [search, setSearch] = useUrlSearchText(urlSearch.q, (q) => update({ q }));
  const debouncedSearch = urlSearch.q ?? "";
  const activeTab: StatusFilter = urlSearch.status ?? "all";
  const rating = urlSearch.rating ? String(urlSearch.rating) : "";
  const verified = urlSearch.verified === undefined ? "" : String(urlSearch.verified);
  const posted = dateRangeFromSearch(urlSearch);
  const sort: SortValue = urlSearch.sort ?? DEFAULT_SORT;
  const page = urlSearch.page ?? 1;

  const setActiveTab = (t: StatusFilter) => update({ status: t === "all" ? undefined : t });
  const setRating = (v: string) => update({ rating: v ? Number(v) : undefined });
  const setVerified = (v: string) => update({ verified: v ? v === "true" : undefined });
  const setPosted = (v: DateRangeValue) => update(dateRangeToSearch(v));
  const setSort = (v: SortValue) => update({ sort: v === DEFAULT_SORT ? undefined : v });
  const setPage = (p: number) => update({ page: p > 1 ? p : undefined });

  const filters = useMemo(() => {
    const [sort_by, sort_dir] = (urlSearch.sort ?? DEFAULT_SORT).split(":");
    return {
      search: urlSearch.q,
      rating: urlSearch.rating,
      verified: urlSearch.verified,
      sort_by,
      sort_dir,
      ...resolveDateRange(dateRangeFromSearch(urlSearch)),
    };
  }, [urlSearch]);

  const { data, isLoading, isPlaceholderData } = useQuery({
    // Extends reviewsAll(...) so the existing ["admin","reviews"] invalidation still matches.
    queryKey: [
      ...queryKeys.admin.reviewsAll(activeTab === "all" ? undefined : activeTab, page),
      filters,
    ],
    queryFn: () =>
      api.get<ReviewListResponse>("/reviews/admin/reviews", {
        params: {
          page,
          page_size: 15,
          ...(activeTab !== "all" ? { status: activeTab } : {}),
          ...filters,
        },
      }),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const chips: FilterChip[] = [];
  if (debouncedSearch)
    chips.push({
      key: "q",
      label: `Search: "${debouncedSearch}"`,
      onRemove: () => update({ q: undefined }),
    });
  if (rating)
    chips.push({ key: "rating", label: `Rating: ${rating}★`, onRemove: () => setRating("") });
  if (verified)
    chips.push({
      key: "verified",
      label: verified === "true" ? "Verified purchase" : "Not verified",
      onRemove: () => setVerified(""),
    });
  const postedLabel = describeDateRange(posted);
  if (postedLabel)
    chips.push({
      key: "posted",
      label: `Posted: ${postedLabel}`,
      onRemove: () => setPosted({ preset: "any" }),
    });
  // One navigation; keeps the status tab and sort.
  const clearAll = () =>
    update({
      q: undefined,
      rating: undefined,
      verified: undefined,
      date: undefined,
      from: undefined,
      to: undefined,
    });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "reviews"] });
  };

  const actionMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: Exclude<ReviewAction, "delete"> }) =>
      api.post<ReviewDto>(`/reviews/admin/${id}/action`, { body: { action } }),
    onSuccess: (_, vars) => {
      invalidate();
      toast.success(`Review ${vars.action}d successfully.`);
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/reviews/admin/${id}`),
    onSuccess: () => {
      invalidate();
      toast.success("Review deleted.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const list = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  useClampPage(
    page,
    data ? { itemCount: list.length, totalPages } : undefined,
    isPlaceholderData,
    (last) => update({ page: last > 1 ? last : undefined }, true),
  );
  const total = data?.total ?? 0;

  const pendingCount = list.filter((r) => !r.is_approved && !r.is_rejected).length;

  return (
    <div>
      <header className="mb-6">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Moderation</p>
        <h1 className="font-display text-4xl mt-1">
          Reviews{" "}
          {pendingCount > 0 && activeTab === "all" && (
            <span className="text-amber-600 text-2xl">({pendingCount} pending)</span>
          )}
        </h1>
      </header>

      {/* Tabs */}
      <div className="flex gap-6 border-b border-border mb-6">
        {STATUS_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActiveTab(t.key)}
            className={`pb-3 -mb-px text-xs uppercase tracking-[0.22em] border-b-2 transition ${
              activeTab === t.key
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="bg-background border border-border p-4 flex flex-wrap items-center gap-3 mb-3">
        <TableSearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search product, customer, title or text…"
          className="flex-1"
        />
        <FilterSelect
          label="Rating"
          allLabel="All ratings"
          value={rating}
          onChange={setRating}
          options={RATING_OPTIONS}
          className="w-36"
        />
        <FilterSelect
          label="Purchase"
          allLabel="Any purchase status"
          value={verified}
          onChange={setVerified}
          options={VERIFIED_OPTIONS}
          className="w-48"
        />
        <DateRangeFilter label="Posted" value={posted} onChange={setPosted} />
        <label className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
          Sort
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortValue)}
            className="h-9 border border-border bg-background px-2 text-sm normal-case tracking-normal text-foreground"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ActiveFilterChips chips={chips} onClearAll={clearAll} className="mb-4" />

      {isLoading && <ReviewListSkeleton count={4} />}

      <div
        className={`grid gap-4 transition-opacity ${isPlaceholderData ? "opacity-60" : ""}`}
        aria-busy={isPlaceholderData}
      >
        {!isLoading &&
          list.map((r) => {
            const isActionPending =
              actionMutation.isPending && actionMutation.variables?.id === r.id;
            const isApprovePending =
              isActionPending && actionMutation.variables?.action === "approve";
            const isRejectPending =
              isActionPending && actionMutation.variables?.action === "reject";
            const isDeletePending = deleteMutation.isPending && deleteMutation.variables === r.id;
            return (
              <article
                key={r.id}
                className="bg-background border border-border p-5 flex flex-col gap-4"
              >
                {/* Header row */}
                <div className="flex flex-col md:flex-row md:items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="font-medium text-sm">{r.customer_name ?? "Customer"}</span>
                      {statusBadge(r)}
                      {r.is_verified_purchase && (
                        <span className="text-[10px] uppercase tracking-[0.18em] px-2 py-0.5 bg-secondary text-muted-foreground border border-border">
                          Verified
                        </span>
                      )}
                      {r.is_flagged && (
                        <span className="text-[10px] uppercase tracking-[0.18em] px-2 py-0.5 bg-orange-50 text-orange-700 border border-orange-200">
                          Flagged
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="inline-flex">
                        {Array.from({ length: 5 }).map((_, i) => (
                          <Star
                            key={i}
                            className={`size-3.5 ${
                              i < r.rating ? "fill-accent text-accent" : "text-muted-foreground"
                            }`}
                          />
                        ))}
                      </span>
                      {r.product_name && (
                        <span className="text-xs text-muted-foreground truncate max-w-xs">
                          {r.product_name}
                        </span>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {new Date(r.created_at).toLocaleDateString("en-IN", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </span>
                    </div>
                    {r.title && <p className="font-display text-base mt-2">{r.title}</p>}
                    {r.body && (
                      <p className="text-sm text-muted-foreground mt-1 line-clamp-3">{r.body}</p>
                    )}
                    {r.approved_at && r.approved_by && (
                      <p className="text-[11px] text-muted-foreground/60 mt-2">
                        Approved on{" "}
                        {new Date(r.approved_at).toLocaleDateString("en-IN", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 shrink-0 flex-wrap">
                    {!r.is_approved && (
                      <button
                        onClick={() => actionMutation.mutate({ id: r.id, action: "approve" })}
                        disabled={isActionPending}
                        aria-busy={isApprovePending}
                        className="inline-flex items-center gap-1 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-accent hover:text-accent-foreground hover:border-accent disabled:opacity-50 transition"
                      >
                        {isApprovePending ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <Check className="size-3.5" />
                        )}
                        {isApprovePending ? "Approving..." : "Approve"}
                      </button>
                    )}
                    {!r.is_approved && !r.is_rejected && (
                      <button
                        onClick={() => actionMutation.mutate({ id: r.id, action: "reject" })}
                        disabled={isActionPending}
                        aria-busy={isRejectPending}
                        className="inline-flex items-center gap-1 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-destructive hover:text-destructive-foreground hover:border-destructive disabled:opacity-50 transition"
                      >
                        {isRejectPending ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <X className="size-3.5" />
                        )}
                        {isRejectPending ? "Rejecting..." : "Reject"}
                      </button>
                    )}
                    <button
                      onClick={() => {
                        if (confirm("Permanently delete this review?")) {
                          deleteMutation.mutate(r.id);
                        }
                      }}
                      disabled={isDeletePending}
                      aria-busy={isDeletePending}
                      className="inline-flex items-center gap-1 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-destructive hover:text-destructive-foreground hover:border-destructive disabled:opacity-50 transition"
                    >
                      {isDeletePending ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="size-3.5" />
                      )}
                      {isDeletePending ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                </div>

                {/* Images */}
                {r.images.length > 0 && (
                  <div className="flex gap-2 flex-wrap">
                    {r.images.map((img) => (
                      <a
                        key={img.id}
                        href={img.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="size-16 border border-border overflow-hidden block hover:border-foreground transition"
                      >
                        <ImageWithFallback src={img.url} alt="Review" className="size-full" />
                      </a>
                    ))}
                  </div>
                )}
              </article>
            );
          })}
        {!isLoading && list.length === 0 && (
          <p className="text-center text-muted-foreground text-sm py-12">
            No {activeTab !== "all" ? activeTab : ""} reviews
            {chips.length ? " match these filters" : ""}.{" "}
            {chips.length > 0 && (
              <button
                type="button"
                onClick={clearAll}
                className="underline underline-offset-4 text-foreground"
              >
                Clear filters
              </button>
            )}
          </p>
        )}
      </div>

      <TablePagination
        page={page}
        totalPages={totalPages}
        total={total}
        noun="reviews"
        onPageChange={setPage}
      />
    </div>
  );
}
