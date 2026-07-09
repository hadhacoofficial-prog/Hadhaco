import { Check, Crop as CropIcon, Link2, Monitor, Smartphone, Tablet } from "lucide-react";
import type { Breakpoint } from "@hadha/shared-types";
import { cn } from "@hadha/shared-utils";

const BREAKPOINT_LABEL: Record<Breakpoint, string> = {
  desktop: "Desktop",
  tablet: "Tablet",
  mobile: "Mobile",
  all: "Crop",
};

const BREAKPOINT_ICON: Record<Breakpoint, typeof Monitor> = {
  desktop: Monitor,
  tablet: Tablet,
  mobile: Smartphone,
  all: CropIcon,
};

interface BreakpointTabsProps {
  breakpoints: Breakpoint[];
  active: Breakpoint;
  viewingAll: boolean;
  linked: Set<Breakpoint>;
  onSelectAll: () => void;
  onSelectBreakpoint: (breakpoint: Breakpoint) => void;
  disabled?: boolean;
}

/** Compact segmented control for switching which breakpoint's crop is being
 * edited — lives in the top bar, not a sidebar, since which breakpoint is
 * active is a frequent, lightweight switch, not a whole editing panel.
 * A leading "All" tab edits every linked breakpoint's shared framing at
 * once; each individual tab shows a small dot once it's gone independent.
 * Renders nothing for single-breakpoint presets (nothing to switch between). */
export function BreakpointTabs({
  breakpoints,
  active,
  viewingAll,
  linked,
  onSelectAll,
  onSelectBreakpoint,
  disabled,
}: BreakpointTabsProps) {
  if (breakpoints.length <= 1) return null;

  return (
    <div className="flex items-center gap-0.5 rounded-md bg-muted p-0.5">
      <button
        type="button"
        onClick={onSelectAll}
        disabled={disabled}
        className={cn(
          "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50",
          viewingAll
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        <Link2 className="size-3.5" />
        All
      </button>
      {breakpoints.map((bp) => {
        const Icon = BREAKPOINT_ICON[bp];
        const isActive = !viewingAll && bp === active;
        const isLinked = linked.has(bp);
        return (
          <button
            key={bp}
            type="button"
            onClick={() => onSelectBreakpoint(bp)}
            disabled={disabled}
            className={cn(
              "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50",
              isActive
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
            title={isLinked ? `${BREAKPOINT_LABEL[bp]} — synced` : `${BREAKPOINT_LABEL[bp]} — custom crop`}
          >
            <Icon className="size-3.5" />
            {BREAKPOINT_LABEL[bp]}
            {isLinked ? (
              <Check className="size-3 text-emerald-600" />
            ) : (
              <span className="size-1.5 rounded-full bg-amber-500" />
            )}
          </button>
        );
      })}
    </div>
  );
}
