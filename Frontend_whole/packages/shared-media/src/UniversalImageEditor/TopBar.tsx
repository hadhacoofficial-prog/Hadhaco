import { Columns2, MoreVertical, RefreshCw, Trash2, Upload } from "lucide-react";
import { Button } from "@hadha/shared-ui/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@hadha/shared-ui/ui/dropdown-menu";
import { cn } from "@hadha/shared-utils";
import type { Breakpoint, CropPreset } from "@hadha/shared-types";
import { BreakpointTabs } from "./BreakpointTabs";
import { ImageInfoPopover } from "./ImageInfoPopover";
import { SyncControls } from "./SyncControls";

interface TopBarProps {
  preset: CropPreset;
  imageWidth: number;
  imageHeight: number;
  activeBreakpoint: Breakpoint;
  viewingAll: boolean;
  linked: Set<Breakpoint>;
  onSelectAll: () => void;
  onSelectBreakpoint: (breakpoint: Breakpoint) => void;
  onCopy: (source: Breakpoint, target: Breakpoint) => void;
  onCopyAllFrom: (source: Breakpoint) => void;
  onResetAllToShared: () => void;
  onReplaceFile: () => void;
  onDelete?: () => void;
  /** Re-derives every breakpoint's variants from the stored crop geometry —
   * only meaningful once an image already exists server-side. Surfaced for
   * recovering from a partial/failed generation without re-cropping
   * (docs audit MF-4). */
  onRegenerate?: () => void;
  regenerating?: boolean;
  previewOpen: boolean;
  onTogglePreview: () => void;
  disabled?: boolean;
  altText?: string;
  onAltTextChange?: (value: string) => void;
  onAltTextCommit?: () => void;
}

/** Thin top toolbar — everything about *which* breakpoint and *which* image
 * is being edited, kept to icons and a segmented control instead of a
 * sidebar. Replace/Delete are one click away in the overflow menu rather
 * than permanently-visible buttons, since they're used once per session at
 * most, not during the actual crop/zoom/pan work. */
export function TopBar({
  preset,
  imageWidth,
  imageHeight,
  activeBreakpoint,
  viewingAll,
  linked,
  onSelectAll,
  onSelectBreakpoint,
  onCopy,
  onCopyAllFrom,
  onResetAllToShared,
  onReplaceFile,
  onDelete,
  onRegenerate,
  regenerating,
  previewOpen,
  onTogglePreview,
  disabled,
  altText,
  onAltTextChange,
  onAltTextCommit,
}: TopBarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b px-3 py-2 pr-12">
      <div className="flex flex-wrap items-center gap-3">
        <span className="whitespace-nowrap text-sm font-medium">{preset.label} image</span>
        <BreakpointTabs
          breakpoints={preset.breakpoints}
          active={activeBreakpoint}
          viewingAll={viewingAll}
          linked={linked}
          onSelectAll={onSelectAll}
          onSelectBreakpoint={onSelectBreakpoint}
          disabled={disabled}
        />
        <SyncControls
          breakpoints={preset.breakpoints}
          activeBreakpoint={activeBreakpoint}
          viewingAll={viewingAll}
          linked={linked}
          onCopy={onCopy}
          onCopyAllFrom={onCopyAllFrom}
          onResetAllToShared={onResetAllToShared}
          disabled={disabled}
        />
      </div>

      <div className="flex items-center gap-1">
        <ImageInfoPopover
          preset={preset}
          imageWidth={imageWidth}
          imageHeight={imageHeight}
          activeBreakpoint={activeBreakpoint}
          altText={altText}
          onAltTextChange={onAltTextChange}
          onAltTextCommit={onAltTextCommit}
        />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={cn("size-8", previewOpen && "bg-accent")}
          onClick={onTogglePreview}
          title={previewOpen ? "Hide live preview" : "Show live preview"}
        >
          <Columns2 className="size-4" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-8"
              disabled={disabled}
              title="More actions"
            >
              <MoreVertical className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onReplaceFile}>
              <Upload className="size-4" />
              Replace image
            </DropdownMenuItem>
            {onRegenerate && (
              <DropdownMenuItem onClick={onRegenerate} disabled={regenerating}>
                <RefreshCw className={cn("size-4", regenerating && "animate-spin")} />
                Regenerate variants
              </DropdownMenuItem>
            )}
            {onDelete && (
              <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
                <Trash2 className="size-4" />
                Delete image
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
