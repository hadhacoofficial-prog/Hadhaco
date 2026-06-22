import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Star, Check, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import type { ReviewAction, ReviewDto } from "@/types/admin";

export const Route = createFileRoute("/admin/reviews")({
  component: AdminReviews,
});

function AdminReviews() {
  const queryClient = useQueryClient();

  const { data: reviews, isLoading } = useQuery({
    queryKey: queryKeys.admin.reviewsPending,
    queryFn: () => api.get<ReviewDto[]>("/reviews/admin/pending"),
    staleTime: 60_000,
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: ReviewAction }) =>
      api.post<ReviewDto>(`/reviews/admin/${id}/action`, { body: { action } }),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.reviewsPending });
      toast.success(`Review ${vars.action}d.`);
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const list = reviews ?? [];

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Moderation</p>
        <h1 className="font-display text-4xl mt-1">
          Reviews <span className="text-muted-foreground text-2xl">({list.length})</span>
        </h1>
      </header>

      {isLoading && <p className="text-sm text-muted-foreground">Loading reviews…</p>}

      <div className="grid gap-3">
        {list.map((r) => (
          <article
            key={r.id}
            className="bg-background border border-border p-5 flex flex-col md:flex-row md:items-center gap-4"
          >
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-1">
                <span className="font-display text-base">{r.title ?? "Review"}</span>
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
                {r.is_verified_purchase && (
                  <span className="text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 bg-secondary text-muted-foreground">
                    Verified
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground">{r.body}</p>
            </div>
            <div className="flex gap-2 shrink-0">
              <button
                onClick={() => actionMutation.mutate({ id: r.id, action: "approve" })}
                disabled={actionMutation.isPending}
                className="inline-flex items-center gap-1 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-accent hover:text-accent-foreground hover:border-accent disabled:opacity-50"
              >
                <Check className="size-3.5" />
                Approve
              </button>
              <button
                onClick={() => actionMutation.mutate({ id: r.id, action: "reject" })}
                disabled={actionMutation.isPending}
                className="inline-flex items-center gap-1 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-destructive hover:text-destructive-foreground hover:border-destructive disabled:opacity-50"
              >
                <X className="size-3.5" />
                Reject
              </button>
            </div>
          </article>
        ))}
        {!isLoading && list.length === 0 && (
          <p className="text-center text-muted-foreground text-sm py-12">No pending reviews.</p>
        )}
      </div>
    </div>
  );
}
