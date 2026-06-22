import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import type { CouponDto, CreateCouponDto } from "@/types/admin";

export const Route = createFileRoute("/admin/coupons")({
  component: AdminCoupons,
});

const EMPTY: CreateCouponDto = { code: "", coupon_type: "percentage", value: 10, description: "" };

function AdminCoupons() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<CreateCouponDto>(EMPTY);

  const { data: coupons } = useQuery({
    queryKey: queryKeys.admin.coupons({}),
    queryFn: () => api.get<CouponDto[]>("/admin/coupons"),
    staleTime: 60_000,
  });

  const createMutation = useMutation({
    mutationFn: (body: CreateCouponDto) => api.post<CouponDto>("/admin/coupons", { body }),
    onSuccess: (c) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "coupons"] });
      toast.success(`Saved ${c.code.toUpperCase()}`);
      setDraft(EMPTY);
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete<void>(`/admin/coupons/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "coupons"] });
      toast.success("Coupon deleted.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const submit = () => {
    if (!draft.code.trim()) return toast.error("Coupon code is required");
    if (draft.value <= 0) return toast.error("Value must be greater than 0");
    createMutation.mutate({ ...draft, code: draft.code.toUpperCase() });
  };

  const list = coupons ?? [];

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Promotions</p>
        <h1 className="font-display text-4xl mt-1">
          Coupons <span className="text-muted-foreground text-2xl">({list.length})</span>
        </h1>
      </header>

      <div className="grid lg:grid-cols-[1fr_360px] gap-6">
        <div className="bg-background border border-border overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Value</th>
                <th className="px-4 py-3">Min order</th>
                <th className="px-4 py-3">Uses</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-3 font-mono">{c.code}</td>
                  <td className="px-4 py-3 capitalize">{c.coupon_type.replace("_", " ")}</td>
                  <td className="px-4 py-3 font-display">
                    {c.coupon_type === "percentage" ? `${c.value}%` : `₹${c.value}`}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {c.min_order_amount ? `₹${c.min_order_amount}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {c.usage_count}
                    {c.usage_limit ? `/${c.usage_limit}` : ""}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                        c.is_active
                          ? "bg-accent/15 text-accent"
                          : "bg-secondary text-muted-foreground"
                      }`}
                    >
                      {c.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => deleteMutation.mutate(c.id)}
                      disabled={deleteMutation.isPending}
                      className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </td>
                </tr>
              ))}
              {list.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-muted-foreground text-sm">
                    No coupons yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <aside className="bg-background border border-border p-5 h-fit">
          <h2 className="font-display text-xl mb-4">New coupon</h2>
          <div className="grid gap-3">
            <F label="Code">
              <input
                value={draft.code}
                onChange={(e) => setDraft({ ...draft, code: e.target.value.toUpperCase() })}
                className="border border-border bg-background px-3 py-2 text-sm font-mono uppercase w-full"
              />
            </F>
            <F label="Type">
              <select
                value={draft.coupon_type}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    coupon_type: e.target.value as CreateCouponDto["coupon_type"],
                  })
                }
                className="border border-border bg-background px-3 py-2 text-sm w-full"
              >
                <option value="percentage">Percentage %</option>
                <option value="fixed_amount">Fixed Amount ₹</option>
                <option value="free_shipping">Free Shipping</option>
              </select>
            </F>
            <F label="Value">
              <input
                type="number"
                min={1}
                value={draft.value}
                onChange={(e) => setDraft({ ...draft, value: Number(e.target.value) })}
                className="border border-border bg-background px-3 py-2 text-sm w-full"
              />
            </F>
            <F label="Min order (optional)">
              <input
                type="number"
                min={0}
                value={draft.min_order_amount ?? ""}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    min_order_amount: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                className="border border-border bg-background px-3 py-2 text-sm w-full"
              />
            </F>
            <F label="Description">
              <input
                value={draft.description ?? ""}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                className="border border-border bg-background px-3 py-2 text-sm w-full"
              />
            </F>
            <button
              onClick={submit}
              disabled={createMutation.isPending}
              className="mt-2 inline-flex items-center justify-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-5 py-3 disabled:opacity-60"
            >
              <Plus className="size-3.5" />
              {createMutation.isPending ? "Saving…" : "Save coupon"}
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}

function F({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1">
      <span className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}
