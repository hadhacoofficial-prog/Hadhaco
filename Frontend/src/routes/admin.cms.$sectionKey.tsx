import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  History,
  Plus,
  Save,
  Send,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import {
  useCmsSection,
  useSaveDraft,
  usePublishSection,
  useVersionHistory,
  useRollbackVersion,
  useSectionItems,
  useCreateSectionItem,
  useUpdateSectionItem,
  useDeleteSectionItem,
  useReorderSectionItems,
} from "@/hooks/cms/useCmsSection";
import { toUserMessage } from "@/lib/api/errors";
import type { SectionItem } from "@/types/cms";

export const Route = createFileRoute("/admin/cms/$sectionKey")({
  component: SectionEditor,
});

function SectionEditor() {
  const { sectionKey } = Route.useParams();
  const { data: section, isLoading } = useCmsSection(sectionKey);
  const saveDraftMutation = useSaveDraft(sectionKey);
  const publishMutation = usePublishSection(sectionKey);
  const [showHistory, setShowHistory] = useState(false);
  const [showItems, setShowItems] = useState(false);
  const [configJson, setConfigJson] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [changeSummary, setChangeSummary] = useState("");

  useEffect(() => {
    if (section) {
      const draft = section.draft_config && Object.keys(section.draft_config).length > 0
        ? section.draft_config
        : section.config;
      setConfigJson(JSON.stringify(draft, null, 2));
    }
  }, [section]);

  function validateJson(val: string) {
    try {
      JSON.parse(val);
      setJsonError(null);
      return true;
    } catch (e: unknown) {
      setJsonError(e instanceof Error ? e.message : "Invalid JSON");
      return false;
    }
  }

  function handleSaveDraft() {
    if (!validateJson(configJson)) return;
    saveDraftMutation.mutate(
      { draft_config: JSON.parse(configJson), change_summary: changeSummary || undefined },
      {
        onSuccess: () => toast.success("Draft saved."),
        onError: (e) => toast.error(toUserMessage(e)),
      },
    );
  }

  function handlePublish() {
    if (!validateJson(configJson)) return;
    publishMutation.mutate(
      { change_summary: changeSummary || undefined },
      {
        onSuccess: () => {
          toast.success("Section published! Cache cleared.");
          setChangeSummary("");
        },
        onError: (e) => toast.error(toUserMessage(e)),
      },
    );
  }

  if (isLoading) {
    return (
      <div className="max-w-3xl">
        <div className="h-8 bg-muted animate-pulse rounded w-48 mb-4" />
        <div className="h-64 bg-muted animate-pulse rounded" />
      </div>
    );
  }

  if (!section) {
    return (
      <div className="max-w-3xl">
        <p className="text-sm text-muted-foreground">Section not found.</p>
        <Link to="/admin/cms" className="text-primary text-sm underline mt-2 inline-block">
          ← Back to CMS
        </Link>
      </div>
    );
  }

  const hasDraft =
    section.status === "draft" ||
    (section.draft_config && JSON.stringify(section.draft_config) !== JSON.stringify(section.config));

  return (
    <div className="max-w-3xl space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/admin/cms" className="hover:text-foreground transition flex items-center gap-1">
          <ArrowLeft className="size-3.5" />
          CMS
        </Link>
        <span>/</span>
        <span className="text-foreground font-medium">{section.title ?? sectionKey}</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground font-mono">
            {section.section_type}
          </p>
          <h1 className="font-display text-3xl mt-0.5">{section.title ?? sectionKey}</h1>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
            <span
              className={`px-2 py-0.5 border rounded-full ${
                section.status === "published"
                  ? "border-emerald-300 text-emerald-700 bg-emerald-50 dark:border-emerald-700 dark:text-emerald-400 dark:bg-emerald-950"
                  : section.status === "draft"
                  ? "border-amber-300 text-amber-700 bg-amber-50 dark:border-amber-700 dark:text-amber-400 dark:bg-amber-950"
                  : "border-blue-300 text-blue-700 bg-blue-50 dark:border-blue-700 dark:text-blue-400 dark:bg-blue-950"
              }`}
            >
              {section.status}
            </span>
            {section.published_at && (
              <span>
                Published {new Date(section.published_at).toLocaleDateString()}
              </span>
            )}
            <span>v{section.version_number}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {hasDraft && (
            <span className="text-[10px] uppercase tracking-widest text-amber-600 dark:text-amber-400">
              Unsaved draft
            </span>
          )}
          <button
            onClick={handleSaveDraft}
            disabled={saveDraftMutation.isPending || !!jsonError}
            className="inline-flex items-center gap-2 border border-border px-4 py-2 text-xs tracking-[0.18em] uppercase hover:bg-muted disabled:opacity-50 transition"
          >
            <Save className="size-3.5" />
            {saveDraftMutation.isPending ? "Saving…" : "Save draft"}
          </button>
          <button
            onClick={handlePublish}
            disabled={publishMutation.isPending || !!jsonError}
            className="inline-flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 text-xs tracking-[0.18em] uppercase hover:bg-primary/90 disabled:opacity-50 transition"
          >
            <Send className="size-3.5" />
            {publishMutation.isPending ? "Publishing…" : "Publish"}
          </button>
        </div>
      </div>

      {/* Config editor */}
      <div className="border border-border">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <span className="text-[11px] uppercase tracking-[0.22em] font-medium">Config (JSON)</span>
          {jsonError && (
            <span className="text-[11px] text-destructive">{jsonError}</span>
          )}
        </div>
        <textarea
          value={configJson}
          onChange={(e) => {
            setConfigJson(e.target.value);
            validateJson(e.target.value);
          }}
          spellCheck={false}
          className="w-full font-mono text-sm p-4 bg-background min-h-[320px] focus:outline-none resize-y"
          style={{ tabSize: 2 }}
        />
      </div>

      {/* Change summary */}
      <label className="grid gap-1.5">
        <span className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
          Change summary (optional)
        </span>
        <input
          value={changeSummary}
          onChange={(e) => setChangeSummary(e.target.value)}
          placeholder="What did you change?"
          className="border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:border-primary"
        />
      </label>

      {/* Section items (if applicable) */}
      <SectionItemsPanel sectionKey={sectionKey} open={showItems} onToggle={() => setShowItems((v) => !v)} />

      {/* Version history */}
      <VersionHistoryPanel sectionKey={sectionKey} open={showHistory} onToggle={() => setShowHistory((v) => !v)} />
    </div>
  );
}

// ── Section Items Panel ───────────────────────────────────────────────────────

function SectionItemsPanel({
  sectionKey,
  open,
  onToggle,
}: {
  sectionKey: string;
  open: boolean;
  onToggle: () => void;
}) {
  const { data: items = [], isLoading } = useSectionItems(sectionKey);
  const createMutation = useCreateSectionItem(sectionKey);
  const updateMutation = useUpdateSectionItem(sectionKey);
  const deleteMutation = useDeleteSectionItem(sectionKey);
  const reorderMutation = useReorderSectionItems(sectionKey);
  const [newItemJson, setNewItemJson] = useState("{}");
  const [addOpen, setAddOpen] = useState(false);

  function handleCreate() {
    try {
      const config = JSON.parse(newItemJson);
      createMutation.mutate(
        { config, sort_order: items.length * 10 },
        {
          onSuccess: () => {
            toast.success("Item added.");
            setNewItemJson("{}");
            setAddOpen(false);
          },
          onError: (e) => toast.error(toUserMessage(e)),
        },
      );
    } catch {
      toast.error("Invalid JSON");
    }
  }

  function moveItem(idx: number, dir: -1 | 1) {
    const next = idx + dir;
    if (next < 0 || next >= items.length) return;
    const swapped = [...items];
    [swapped[idx], swapped[next]] = [swapped[next], swapped[idx]];
    reorderMutation.mutate(
      swapped.map((it, i) => ({ id: it.id, sort_order: i * 10 })),
      { onError: (e) => toast.error(toUserMessage(e)) },
    );
  }

  return (
    <div className="border border-border">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted transition text-sm font-medium"
      >
        <span>Section Items ({items.length})</span>
        {open ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
      </button>

      {open && (
        <div className="border-t border-border p-4 space-y-3">
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

          {items.map((item, idx) => (
            <SectionItemCard
              key={item.id}
              item={item}
              idx={idx}
              total={items.length}
              onMove={(dir) => moveItem(idx, dir)}
              onToggle={() =>
                updateMutation.mutate(
                  { itemId: item.id, payload: { is_enabled: !item.is_enabled } },
                  { onError: (e) => toast.error(toUserMessage(e)) },
                )
              }
              onDelete={() =>
                deleteMutation.mutate(item.id, {
                  onSuccess: () => toast.success("Item deleted."),
                  onError: (e) => toast.error(toUserMessage(e)),
                })
              }
              onSaveConfig={(config) =>
                updateMutation.mutate(
                  { itemId: item.id, payload: { config } },
                  {
                    onSuccess: () => toast.success("Item saved."),
                    onError: (e) => toast.error(toUserMessage(e)),
                  },
                )
              }
            />
          ))}

          {/* Add item */}
          {addOpen ? (
            <div className="border border-dashed border-border p-3 space-y-2">
              <p className="text-[11px] uppercase tracking-widest text-muted-foreground">New item config (JSON)</p>
              <textarea
                value={newItemJson}
                onChange={(e) => setNewItemJson(e.target.value)}
                spellCheck={false}
                rows={4}
                className="w-full font-mono text-xs p-2 border border-border bg-background focus:outline-none resize-y"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleCreate}
                  disabled={createMutation.isPending}
                  className="text-xs bg-primary text-primary-foreground px-3 py-1.5 uppercase tracking-[0.18em] disabled:opacity-50"
                >
                  Add
                </button>
                <button onClick={() => setAddOpen(false)} className="text-xs border border-border px-3 py-1.5 hover:bg-muted">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAddOpen(true)}
              className="w-full flex items-center justify-center gap-2 border border-dashed border-border py-2 text-xs text-muted-foreground hover:text-foreground hover:border-foreground transition"
            >
              <Plus className="size-3.5" />
              Add item
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function SectionItemCard({
  item,
  idx,
  total,
  onMove,
  onToggle,
  onDelete,
  onSaveConfig,
}: {
  item: SectionItem;
  idx: number;
  total: number;
  onMove: (dir: -1 | 1) => void;
  onToggle: () => void;
  onDelete: () => void;
  onSaveConfig: (config: Record<string, unknown>) => void;
}) {
  const [open, setOpen] = useState(false);
  const [json, setJson] = useState(JSON.stringify(item.config, null, 2));

  function handleSave() {
    try {
      onSaveConfig(JSON.parse(json));
    } catch {
      toast.error("Invalid JSON");
    }
  }

  return (
    <div className={`border border-border ${!item.is_enabled ? "opacity-50" : ""}`}>
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="flex flex-col gap-0.5 shrink-0">
          <button onClick={() => onMove(-1)} disabled={idx === 0} className="hover:text-primary disabled:opacity-20 p-0.5">
            <ChevronUp className="size-3" />
          </button>
          <button onClick={() => onMove(1)} disabled={idx === total - 1} className="hover:text-primary disabled:opacity-20 p-0.5">
            <ChevronDown className="size-3" />
          </button>
        </div>
        <button onClick={() => setOpen((v) => !v)} className="flex-1 text-left text-xs font-mono truncate hover:text-primary">
          Item {idx + 1}: {JSON.stringify(item.config).slice(0, 60)}…
        </button>
        <button onClick={onToggle} className="p-1 text-xs text-muted-foreground hover:text-foreground">
          {item.is_enabled ? "Hide" : "Show"}
        </button>
        <button onClick={onDelete} className="p-1 text-destructive hover:opacity-70">
          <Trash2 className="size-3.5" />
        </button>
      </div>
      {open && (
        <div className="border-t border-border p-3 space-y-2">
          <textarea
            value={json}
            onChange={(e) => setJson(e.target.value)}
            spellCheck={false}
            rows={6}
            className="w-full font-mono text-xs p-2 border border-border bg-background focus:outline-none resize-y"
          />
          <button
            onClick={handleSave}
            className="inline-flex items-center gap-1.5 text-xs bg-primary text-primary-foreground px-3 py-1.5 uppercase tracking-[0.18em]"
          >
            <Check className="size-3" />
            Save item
          </button>
        </div>
      )}
    </div>
  );
}

// ── Version History Panel ─────────────────────────────────────────────────────

function VersionHistoryPanel({
  sectionKey,
  open,
  onToggle,
}: {
  sectionKey: string;
  open: boolean;
  onToggle: () => void;
}) {
  const { data: versions = [], isLoading } = useVersionHistory(sectionKey);
  const rollbackMutation = useRollbackVersion(sectionKey);
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="border border-border">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted transition text-sm font-medium"
      >
        <span className="flex items-center gap-2">
          <History className="size-4" />
          Version History ({versions.length})
        </span>
        {open ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
      </button>

      {open && (
        <div className="border-t border-border divide-y divide-border">
          {isLoading && <p className="text-sm text-muted-foreground p-4">Loading…</p>}
          {!isLoading && versions.length === 0 && (
            <p className="text-sm text-muted-foreground p-4">No versions yet.</p>
          )}
          {versions.map((v) => (
            <div key={v.id} className="p-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 text-sm">
                    <Clock className="size-3.5 text-muted-foreground" />
                    <span className="font-medium">v{v.version_number}</span>
                    <span className="text-muted-foreground text-xs">
                      {new Date(v.created_at).toLocaleString()}
                    </span>
                  </div>
                  {v.change_summary && (
                    <p className="text-xs text-muted-foreground mt-0.5">{v.change_summary}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setExpanded((e) => (e === v.id ? null : v.id))}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    {expanded === v.id ? "Hide" : "View"}
                  </button>
                  <button
                    onClick={() =>
                      rollbackMutation.mutate(v.id, {
                        onSuccess: () => toast.success(`Rolled back to v${v.version_number}.`),
                        onError: (e) => toast.error(toUserMessage(e)),
                      })
                    }
                    disabled={rollbackMutation.isPending}
                    className="text-xs border border-border px-2 py-1 hover:bg-muted disabled:opacity-50 transition"
                  >
                    Restore
                  </button>
                </div>
              </div>
              {expanded === v.id && (
                <pre className="mt-3 text-xs font-mono bg-muted p-3 overflow-auto max-h-48">
                  {JSON.stringify(v.config_snapshot, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
