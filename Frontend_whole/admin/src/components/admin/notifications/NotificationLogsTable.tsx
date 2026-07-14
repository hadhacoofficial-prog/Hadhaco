import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Download, RotateCcw, Search } from "lucide-react";
import { toUserMessage } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import {
  useNotificationLogs,
  useNotificationRules,
  useRetryNotificationLogs,
} from "@/hooks/admin/useNotificationAdmin";
import { NotificationDetailDrawer } from "./NotificationDetailDrawer";
import type { NotificationLogOut, NotificationLogsFilter } from "@hadha/shared-types";

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-secondary text-muted-foreground",
  retrying: "bg-amber-50 text-amber-700",
  sent: "bg-blue-50 text-blue-700",
  delivered: "bg-emerald-50 text-emerald-700",
  read: "bg-accent/10 text-accent",
  failed: "bg-red-50 text-red-700",
};

const PAGE_SIZE = 25;

export function NotificationLogsTable() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string>("all");
  const [channel, setChannel] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detailLog, setDetailLog] = useState<NotificationLogOut | null>(null);

  const filters: NotificationLogsFilter = {
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
  if (status !== "all") filters.status = status;
  if (channel !== "all") filters.channel = channel;
  if (search.trim()) filters.search = search.trim();

  const { data, isLoading, isFetching } = useNotificationLogs(filters);
  const { data: rules } = useNotificationRules();
  const retryLogs = useRetryNotificationLogs();

  const eventLabel = (eventType: string) =>
    rules?.find((r) => r.event_type === eventType)?.display_name ?? eventType;

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleRetry = (logIds: string[]) => {
    retryLogs.mutate(logIds, {
      onSuccess: (result) => {
        toast.success(`Retried ${result.retried} of ${result.requested} notification(s)`);
        setSelected(new Set());
      },
      onError: (e) => toast.error(toUserMessage(e)),
    });
  };

  const exportCsv = () => {
    if (!data || data.items.length === 0) return;
    const header = ["id", "event", "channel", "recipient", "status", "provider", "created_at"];
    const rows = data.items.map((log) => [
      log.id,
      eventLabel(log.event_type),
      log.channel,
      log.recipient,
      log.status,
      log.provider ?? "",
      log.created_at,
    ]);
    const csv = [header, ...rows]
      .map((r) => r.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `notification-logs-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const failedSelected = useMemo(
    () =>
      [...selected].filter((id) => data?.items.some((l) => l.id === id && l.status === "failed")),
    [selected, data],
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
          <Input
            placeholder="Search recipient, order number, notification ID…"
            className="pl-8"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <Select
          value={status}
          onValueChange={(v) => {
            setStatus(v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="retrying">Retrying</SelectItem>
            <SelectItem value="sent">Sent</SelectItem>
            <SelectItem value="delivered">Delivered</SelectItem>
            <SelectItem value="read">Read</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={channel}
          onValueChange={(v) => {
            setChannel(v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-32">
            <SelectValue placeholder="Channel" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All channels</SelectItem>
            <SelectItem value="email">Email</SelectItem>
            <SelectItem value="whatsapp">WhatsApp</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={exportCsv} disabled={!data?.items.length}>
          <Download className="size-3.5 mr-1.5" /> Export CSV
        </Button>
        {failedSelected.length > 0 && (
          <Button onClick={() => handleRetry(failedSelected)} disabled={retryLogs.isPending}>
            <RotateCcw className="size-3.5 mr-1.5" /> Retry selected ({failedSelected.length})
          </Button>
        )}
      </div>

      <div className="bg-background border border-border overflow-x-auto">
        {isLoading ? (
          <TableSkeleton
            headers={["Event", "Channel", "Recipient", "Status", "Attempts", "Created"]}
            rows={8}
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-3 w-8" />
                <th className="px-3 py-3 font-medium">Event</th>
                <th className="px-3 py-3 font-medium">Channel</th>
                <th className="px-3 py-3 font-medium">Recipient</th>
                <th className="px-3 py-3 font-medium">Status</th>
                <th className="px-3 py-3 font-medium">Attempts</th>
                <th className="px-3 py-3 font-medium">Created</th>
                <th className="px-3 py-3 font-medium" />
              </tr>
            </thead>
            <tbody className={`divide-y divide-border ${isFetching ? "opacity-60" : ""}`}>
              {!data || data.items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-3 py-10 text-center text-muted-foreground">
                    No notifications match these filters.
                  </td>
                </tr>
              ) : (
                data.items.map((log) => (
                  <tr
                    key={log.id}
                    className="hover:bg-secondary/40 cursor-pointer"
                    onClick={() => setDetailLog(log)}
                  >
                    <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                      {log.status === "failed" && (
                        <input
                          type="checkbox"
                          checked={selected.has(log.id)}
                          onChange={() => toggleSelected(log.id)}
                          aria-label={`Select notification ${log.id}`}
                        />
                      )}
                    </td>
                    <td className="px-3 py-2.5 max-w-[220px] truncate">
                      {eventLabel(log.event_type)}
                    </td>
                    <td className="px-3 py-2.5 uppercase text-xs text-muted-foreground">
                      {log.channel}
                    </td>
                    <td className="px-3 py-2.5 max-w-[180px] truncate">{log.recipient}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full ${
                          STATUS_STYLES[log.status] ?? "bg-secondary text-muted-foreground"
                        }`}
                      >
                        {log.status}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground">
                      {log.attempt_count}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                      {log.status === "failed" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRetry([log.id])}
                          disabled={retryLogs.isPending}
                        >
                          <RotateCcw className="size-3.5" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between mt-4 text-sm">
          <p className="text-muted-foreground">
            Page {page} of {totalPages} · {data.total} total
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <NotificationDetailDrawer
        log={detailLog}
        onClose={() => setDetailLog(null)}
        onRetry={(id) => handleRetry([id])}
        retrying={retryLogs.isPending}
      />
    </div>
  );
}
