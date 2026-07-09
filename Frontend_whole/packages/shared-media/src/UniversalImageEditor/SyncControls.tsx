import { Check, ChevronDown, Copy, Pencil, RefreshCw } from "lucide-react";
import { Button } from "@hadha/shared-ui/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@hadha/shared-ui/ui/dropdown-menu";
import { cn } from "@hadha/shared-utils";
import type { Breakpoint } from "@hadha/shared-types";

const BREAKPOINT_LABEL: Record<Breakpoint, string> = {
  desktop: "Desktop",
  tablet: "Tablet",
  mobile: "Mobile",
  all: "Crop",
};

interface SyncControlsProps {
  breakpoints: Breakpoint[];
  activeBreakpoint: Breakpoint;
  viewingAll: boolean;
  linked: Set<Breakpoint>;
  onCopy: (source: Breakpoint, target: Breakpoint) => void;
  onCopyAllFrom: (source: Breakpoint) => void;
  onResetAllToShared: () => void;
  disabled?: boolean;
}

/** Sync-state badge + quick-fix menu for reconciling breakpoints once
 * they've diverged. The badge alone answers "is what I'm looking at shared
 * or did I customize it"; the menu only offers actions that make sense for
 * the current state instead of always showing all five. */
export function SyncControls({
  breakpoints,
  activeBreakpoint,
  viewingAll,
  linked,
  onCopy,
  onCopyAllFrom,
  onResetAllToShared,
  disabled,
}: SyncControlsProps) {
  if (breakpoints.length <= 1) return null;

  const allLinked = linked.size === breakpoints.length;
  const anyCustom = linked.size < breakpoints.length;
  const isActiveLinked = linked.has(activeBreakpoint);
  const primary = breakpoints[0];

  const badge = viewingAll ? (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        allLinked ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700",
      )}
    >
      {allLinked ? <Check className="size-3" /> : <Pencil className="size-3" />}
      {allLinked ? "All breakpoints linked" : "Some breakpoints customized"}
    </span>
  ) : (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        isActiveLinked ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700",
      )}
    >
      {isActiveLinked ? <Check className="size-3" /> : <Pencil className="size-3" />}
      {isActiveLinked ? "Synced" : "Custom crop"}
    </span>
  );

  // Cascading pairs (Desktop→Tablet, Tablet→Mobile, …) plus "copy from the
  // primary breakpoint" for every other one — matches how divergence
  // actually happens (someone nudges one breakpoint) without listing every
  // possible N×N pair.
  const cascadePairs: [Breakpoint, Breakpoint][] = breakpoints
    .slice(0, -1)
    .map((bp, i) => [bp, breakpoints[i + 1]]);

  return (
    <div className="flex items-center gap-2">
      {badge}
      {anyCustom && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="sm" disabled={disabled} className="gap-1">
              <Copy className="size-3.5" />
              Copy
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Reconcile breakpoints</DropdownMenuLabel>
            {cascadePairs.map(([source, target]) => (
              <DropdownMenuItem key={`${source}-${target}`} onClick={() => onCopy(source, target)}>
                Copy {BREAKPOINT_LABEL[source]} → {BREAKPOINT_LABEL[target]}
              </DropdownMenuItem>
            ))}
            <DropdownMenuItem onClick={() => onCopyAllFrom(primary)}>
              Copy all from {BREAKPOINT_LABEL[primary]}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onResetAllToShared}>
              <RefreshCw className="size-3.5" />
              Reset all to shared crop
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}
