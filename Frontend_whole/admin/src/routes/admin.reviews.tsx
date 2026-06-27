import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Star, Check, X, Trash2, Flag } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import type { ReviewAction, ReviewDto } from "@/types/admin";

export const Route = createFileRoute("/admin/reviews")({
  component: AdminReviews,
});

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

function AdminReviews() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<StatusFilter>("all");

  const { data: reviews, isLoading } = useQuery({
    queryKey: queryKeys.admin.reviewsAll(activeTab === "all" ? undefined : activeTab),
    queryFn: () =>
      api.get<ReviewDto[]>("/reviews/admin/reviews", {
        params: activeTab !== "all" ? { status: activeTab } : {},
      }),
    staleTime: 30_000,
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

  const list = reviews ?? [];

  const pendingCount = list.filter((r) => !r.is_approved && !r.is_rejected).length;

  return (
    <div>
      <header className="mb-6">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
          Moderation
        </p>
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

      {isLoading && <p className="text-sm text-muted-foreground">Loading reviews…</p>}

      <div className="grid gap-4">
        {list.map((r) => (
          <article
            key={r.id}
            className="bg-background border border-border p-5 flex flex-col gap-4"
          >
            {/* Header row */}
            <div className="flex flex-col md:flex-row md:items-start gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="font-medium text-sm">
                    {r.customer_name ?? "Customer"}
                  </span>
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
                {r.title && (
                  <p className="font-display text-base mt-2">{r.title}</p>
                )}
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
                    disabled={actionMutation.isPending}
                    className="inline-flex items-center gap-1 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-accent hover:text-accent-foreground hover:border-accent disabled:opacity-50 transition"
                  >
                    <Check className="size-3.5" />
                    Approve
                  </button>
                )}
                {!r.is_approved && !r.is_rejected && (
                  <button
                    onClick={() => actionMutation.mutate({ id: r.id, action: "reject" })}
                    disabled={actionMutation.isPending}
                    className="inline-flex items-center gap-1 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-destructive hover:text-destructive-foreground hover:border-destructive disabled:opacity-50 transition"
                  >
                    <X className="size-3.5" />
                    Reject
                  </button>
                )}
                <button
                  onClick={() => {
                    if (confirm("Permanently delete this review?")) {
                      deleteMutation.mutate(r.id);
                    }
                  }}
                  disabled={deleteMutation.isPending}
                  className="inline-flex items-center gap-1 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-destructive hover:text-destructive-foreground hover:border-destructive disabled:opacity-50 transition"
                >
                  <Trash2 className="size-3.5" />
                  Delete
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
                    <img
                      src={img.url}
                      alt="Review"
                      className="w-full h-full object-cover"
                    />
                  </a>
                ))}
              </div>
            )}
          </article>
        ))}
        {!isLoading && list.length === 0 && (
          <p className="text-center text-muted-foreground text-sm py-12">
            No {activeTab !== "all" ? activeTab : ""} reviews.
          </p>
        )}
      </div>
    </div>
  );
}
