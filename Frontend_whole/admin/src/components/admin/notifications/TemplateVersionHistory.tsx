import { Fragment, useState } from "react";
import { toast } from "sonner";
import { History, GitCompare, Undo2 } from "lucide-react";
import { toUserMessage } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useNotificationTemplateVersions,
  useRestoreTemplateVersion,
} from "@/hooks/admin/useNotificationAdmin";
import type { NotificationTemplateVersionOut } from "@hadha/shared-types";

function diffLines(a: string, b: string) {
  const linesA = a.split("\n");
  const linesB = b.split("\n");
  const max = Math.max(linesA.length, linesB.length);
  const rows: { a: string; b: string; changed: boolean }[] = [];
  for (let i = 0; i < max; i++) {
    const lineA = linesA[i] ?? "";
    const lineB = linesB[i] ?? "";
    rows.push({ a: lineA, b: lineB, changed: lineA !== lineB });
  }
  return rows;
}

export function TemplateVersionHistory({ templateId }: { templateId: string }) {
  const { data: versions, isLoading } = useNotificationTemplateVersions(templateId);
  const restore = useRestoreTemplateVersion();
  const [compareSelection, setCompareSelection] = useState<NotificationTemplateVersionOut[]>([]);
  const [confirmRestore, setConfirmRestore] = useState<NotificationTemplateVersionOut | null>(null);

  const toggleCompare = (version: NotificationTemplateVersionOut) => {
    setCompareSelection((prev) => {
      const exists = prev.find((v) => v.id === version.id);
      if (exists) return prev.filter((v) => v.id !== version.id);
      if (prev.length >= 2) return [prev[1], version];
      return [...prev, version];
    });
  };

  const handleRestore = () => {
    if (!confirmRestore) return;
    restore.mutate(
      { templateId, version: confirmRestore.version },
      {
        onSuccess: () => {
          toast.success(`Restored to version ${confirmRestore.version}`);
          setConfirmRestore(null);
        },
        onError: (e) => toast.error(toUserMessage(e)),
      },
    );
  };

  if (isLoading) {
    return (
      <div className="bg-background border border-border p-6">
        <h3 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground mb-3 flex items-center gap-2">
          <History className="size-3.5" /> Version History
        </h3>
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <Skeleton className="h-4 w-4" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 flex-1" />
              <Skeleton className="h-7 w-16" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-background border border-border p-6">
      <h3 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground mb-3 flex items-center gap-2">
        <History className="size-3.5" /> Version History
      </h3>

      {!versions || versions.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4">
          No prior versions — this template hasn't been edited yet.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {versions.map((v) => (
            <li key={v.id} className="py-3 flex items-center justify-between gap-3 text-sm">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!compareSelection.find((c) => c.id === v.id)}
                  onChange={() => toggleCompare(v)}
                  aria-label={`Select version ${v.version} for comparison`}
                />
                <span>Version {v.version}</span>
              </label>
              <span className="text-xs text-muted-foreground flex-1">
                {new Date(v.created_at).toLocaleString()}
              </span>
              <Button variant="outline" size="sm" onClick={() => setConfirmRestore(v)}>
                <Undo2 className="size-3.5 mr-1.5" /> Restore
              </Button>
            </li>
          ))}
        </ul>
      )}

      {compareSelection.length === 2 && (
        <div className="mt-6">
          <p className="text-xs uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
            <GitCompare className="size-3.5" /> Comparing version {compareSelection[0].version} vs{" "}
            {compareSelection[1].version}
          </p>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono border border-border rounded-md overflow-hidden">
            {diffLines(compareSelection[0].template_body, compareSelection[1].template_body).map(
              (row, i) => (
                <Fragment key={i}>
                  <div
                    className={`px-2 py-1 whitespace-pre-wrap break-all ${row.changed ? "bg-red-50" : ""}`}
                  >
                    {row.a || " "}
                  </div>
                  <div
                    className={`px-2 py-1 whitespace-pre-wrap break-all border-l border-border ${row.changed ? "bg-emerald-50" : ""}`}
                  >
                    {row.b || " "}
                  </div>
                </Fragment>
              ),
            )}
          </div>
        </div>
      )}

      <Dialog open={!!confirmRestore} onOpenChange={(open) => !open && setConfirmRestore(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Restore version {confirmRestore?.version}?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This replaces the live template's content with version {confirmRestore?.version}'s
            content. The current content is preserved as a new version in history.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRestore(null)}>
              Cancel
            </Button>
            <Button onClick={handleRestore} disabled={restore.isPending}>
              Restore
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
