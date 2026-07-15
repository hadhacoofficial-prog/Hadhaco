import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Search, X, Archive, ArchiveRestore, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import type { EnquiryDto, EnquiryListResponse, EnquiryStatus } from "@/types/admin";

export const Route = createFileRoute("/admin/enquiries")({
  component: AdminEnquiries,
});

type StatusFilter = "all" | EnquiryStatus;

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "new_enquiry", label: "New" },
  { key: "contacted_customer", label: "Contacted" },
  { key: "positive_response", label: "Positive" },
  { key: "negative_response", label: "Negative" },
  { key: "closed", label: "Closed" },
];

const STATUS_LABELS: Record<EnquiryStatus, string> = {
  new_enquiry: "New Enquiry",
  contacted_customer: "Contacted",
  positive_response: "Positive",
  negative_response: "Negative",
  closed: "Closed",
};

function statusBadge(status: EnquiryStatus) {
  const styles: Record<EnquiryStatus, string> = {
    new_enquiry: "bg-amber-50 text-amber-700 border-amber-200",
    contacted_customer: "bg-blue-50 text-blue-700 border-blue-200",
    positive_response: "bg-accent/10 text-accent border-accent/20",
    negative_response: "bg-destructive/10 text-destructive border-destructive/20",
    closed: "bg-secondary text-muted-foreground border-border",
  };
  return (
    <span
      className={`text-[10px] uppercase tracking-[0.18em] px-2 py-0.5 border ${styles[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

function AdminEnquiries() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [showArchived, setShowArchived] = useState(false);
  const [selected, setSelected] = useState<EnquiryDto | null>(null);
  const [editStatus, setEditStatus] = useState<EnquiryStatus | "">("");
  const [editNotes, setEditNotes] = useState("");

  const params: Record<string, string | number | boolean> = { page, page_size: 20 };
  if (activeTab !== "all") params.status = activeTab;
  if (search.trim()) params.search = search.trim();
  if (showArchived) params.include_archived = true;

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.admin.enquiries(params),
    queryFn: () => api.get<EnquiryListResponse>("/admin/enquiries", { params }),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "enquiries"] });
  };

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: { status?: EnquiryStatus; admin_notes?: string };
    }) => api.patch<EnquiryDto>(`/admin/enquiries/${id}`, { body }),
    onSuccess: () => {
      invalidate();
      setSelected(null);
      toast.success("Enquiry updated.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const archiveMutation = useMutation({
    mutationFn: ({ id, archive }: { id: string; archive: boolean }) =>
      api.post<EnquiryDto>(`/admin/enquiries/${id}/${archive ? "archive" : "unarchive"}`),
    onSuccess: () => {
      invalidate();
      setSelected(null);
      toast.success("Enquiry updated.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/admin/enquiries/${id}`),
    onSuccess: () => {
      invalidate();
      setSelected(null);
      toast.success("Enquiry permanently deleted.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const result = data;
  const list = result?.items ?? [];
  const stats = result?.stats;
  const totalPages = result?.total_pages ?? 1;

  function openDetail(e: EnquiryDto) {
    setSelected(e);
    setEditStatus(e.status);
    setEditNotes(e.admin_notes ?? "");
  }

  function handleSave() {
    if (!selected) return;
    const body: { status?: EnquiryStatus; admin_notes?: string } = {};
    if (editStatus && editStatus !== selected.status) body.status = editStatus as EnquiryStatus;
    if (editNotes !== (selected.admin_notes ?? "")) body.admin_notes = editNotes;
    if (Object.keys(body).length === 0) return;
    updateMutation.mutate({ id: selected.id, body });
  }

  return (
    <div>
      <header className="mb-6">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Management</p>
        <h1 className="font-display text-4xl mt-1">
          Enquiries{" "}
          {stats && stats.new_enquiry > 0 && activeTab === "all" && !showArchived && (
            <span className="text-amber-600 text-2xl">({stats.new_enquiry} new)</span>
          )}
        </h1>
      </header>

      {/* Status stats bar */}
      {stats && (
        <div className="flex flex-wrap gap-4 mb-6 text-xs">
          <span className="text-muted-foreground">
            Total: <strong className="text-foreground">{stats.total}</strong>
          </span>
          <span className="text-muted-foreground">
            New: <strong className="text-amber-600">{stats.new_enquiry}</strong>
          </span>
          <span className="text-muted-foreground">
            Contacted: <strong>{stats.contacted_customer}</strong>
          </span>
          <span className="text-muted-foreground">
            Positive: <strong className="text-accent">{stats.positive_response}</strong>
          </span>
          <span className="text-muted-foreground">
            Negative: <strong className="text-destructive">{stats.negative_response}</strong>
          </span>
          <span className="text-muted-foreground">
            Closed: <strong>{stats.closed}</strong>
          </span>
          <span className="text-muted-foreground">
            Archived: <strong>{stats.archived}</strong>
          </span>
        </div>
      )}

      {/* Tabs + archived toggle */}
      <div className="flex items-center justify-between border-b border-border mb-4">
        <div className="flex gap-6">
          {STATUS_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => {
                setActiveTab(t.key);
                setPage(1);
              }}
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
        <button
          type="button"
          onClick={() => {
            setShowArchived((v) => !v);
            setPage(1);
          }}
          className={`pb-3 -mb-px text-xs uppercase tracking-[0.22em] border-b-2 transition flex items-center gap-1.5 ${
            showArchived
              ? "border-foreground text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <Archive className="size-3.5" />
          Archived
        </button>
      </div>

      {/* Search bar */}
      <div className="relative mb-6 max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search name, email, subject..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="w-full bg-background border border-border pl-9 pr-3 py-2.5 text-sm outline-none focus:border-foreground transition"
        />
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-16 bg-secondary/50 animate-pulse" />
          ))}
        </div>
      )}

      {!isLoading && list.length === 0 && (
        <p className="text-center text-muted-foreground text-sm py-12">
          No{" "}
          {showArchived
            ? "archived"
            : activeTab !== "all"
              ? STATUS_LABELS[activeTab as EnquiryStatus]?.toLowerCase()
              : ""}{" "}
          enquiries found.
        </p>
      )}

      {/* Table */}
      {!isLoading && list.length > 0 && (
        <>
          <div className="border border-border bg-background overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                  <th className="text-left px-4 py-3 font-medium">Name</th>
                  <th className="text-left px-4 py-3 font-medium">Email</th>
                  <th className="text-left px-4 py-3 font-medium">Subject</th>
                  <th className="text-left px-4 py-3 font-medium">Status</th>
                  <th className="text-left px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {list.map((e) => (
                  <tr
                    key={e.id}
                    className={`border-b border-border last:border-0 hover:bg-secondary/30 transition cursor-pointer ${e.is_archived ? "opacity-60" : ""}`}
                    onClick={() => openDetail(e)}
                  >
                    <td className="px-4 py-3 font-medium">
                      {e.name}
                      {e.user_id && (
                        <span className="ml-1.5 text-[9px] text-muted-foreground">(member)</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{e.email}</td>
                    <td className="px-4 py-3 truncate max-w-[240px]">{e.subject}</td>
                    <td className="px-4 py-3">{statusBadge(e.status)}</td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {new Date(e.created_at).toLocaleDateString("en-IN", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <MessageSquare className="size-4 text-muted-foreground" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 text-xs text-muted-foreground">
              <span>
                Page {page} of {totalPages}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="border border-border px-3 py-1.5 hover:bg-secondary disabled:opacity-50 transition"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="border border-border px-3 py-1.5 hover:bg-secondary disabled:opacity-50 transition"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Detail modal */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border border-border w-full max-w-lg max-h-[90vh] overflow-y-auto p-6 space-y-5">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-display text-xl">{selected.subject}</h2>
                <p className="text-xs text-muted-foreground mt-1">
                  From <strong>{selected.name}</strong> &lt;{selected.email}&gt;
                  {selected.phone && <> · {selected.phone}</>}
                  {selected.user_id && <span className="ml-1 text-accent">(logged-in member)</span>}
                </p>
                <p className="text-xs text-muted-foreground">
                  {new Date(selected.created_at).toLocaleString("en-IN", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                  {selected.is_archived && <span className="ml-2 text-amber-600">· Archived</span>}
                </p>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-muted-foreground hover:text-foreground transition p-1"
              >
                <X className="size-5" />
              </button>
            </div>

            <div className="border border-border p-4 bg-secondary/30">
              <p className="text-sm whitespace-pre-wrap">{selected.message}</p>
            </div>

            <div className="space-y-3">
              <label className="block">
                <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                  Status
                </span>
                <select
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value as EnquiryStatus | "")}
                  className="mt-1.5 w-full bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground transition"
                >
                  {STATUS_TABS.filter((t) => t.key !== "all").map((t) => (
                    <option key={t.key} value={t.key}>
                      {STATUS_LABELS[t.key as EnquiryStatus]}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                  Admin Notes
                </span>
                <textarea
                  rows={4}
                  value={editNotes}
                  onChange={(e) => setEditNotes(e.target.value)}
                  placeholder="Internal notes (not visible to customer)..."
                  className="mt-1.5 w-full bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground transition resize-none"
                />
              </label>
            </div>

            <div className="flex gap-3 justify-between">
              <div className="flex gap-2">
                <button
                  onClick={() =>
                    archiveMutation.mutate({
                      id: selected.id,
                      archive: !selected.is_archived,
                    })
                  }
                  disabled={archiveMutation.isPending}
                  aria-busy={archiveMutation.isPending}
                  className="inline-flex items-center gap-1.5 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-secondary disabled:opacity-50 transition"
                >
                  {archiveMutation.isPending ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : selected.is_archived ? (
                    <ArchiveRestore className="size-3.5" />
                  ) : (
                    <Archive className="size-3.5" />
                  )}
                  {archiveMutation.isPending
                    ? selected.is_archived
                      ? "Restoring..."
                      : "Archiving..."
                    : selected.is_archived
                      ? "Restore"
                      : "Archive"}
                </button>
                <button
                  onClick={() => {
                    if (confirm("Permanently delete this enquiry? This cannot be undone.")) {
                      deleteMutation.mutate(selected.id);
                    }
                  }}
                  disabled={deleteMutation.isPending}
                  aria-busy={deleteMutation.isPending}
                  className="inline-flex items-center gap-1.5 border border-border px-3 py-2 text-xs uppercase tracking-[0.18em] hover:bg-destructive hover:text-destructive-foreground hover:border-destructive disabled:opacity-50 transition"
                >
                  {deleteMutation.isPending ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="size-3.5" />
                  )}
                  {deleteMutation.isPending ? "Deleting..." : "Delete"}
                </button>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => setSelected(null)}
                  className="border border-border px-4 py-2 text-xs uppercase tracking-[0.18em] hover:bg-secondary transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={updateMutation.isPending}
                  aria-busy={updateMutation.isPending}
                  className="inline-flex items-center gap-1.5 bg-primary text-primary-foreground px-4 py-2 text-xs uppercase tracking-[0.18em] hover:bg-accent hover:text-accent-foreground disabled:opacity-50 transition"
                >
                  {updateMutation.isPending && <Loader2 className="size-3.5 animate-spin" />}
                  {updateMutation.isPending ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
