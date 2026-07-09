import { Grid3x3, Redo2, RotateCcw, ShieldHalf, Undo2, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@hadha/shared-ui/ui/button";
import { Separator } from "@hadha/shared-ui/ui/separator";
import { Slider } from "@hadha/shared-ui/ui/slider";
import { cn } from "@hadha/shared-utils";

interface BottomToolbarProps {
  zoom: number;
  maxZoom: number;
  onZoomChange: (zoom: number) => void;
  onZoomCommit: () => void;
  onFitToScreen: () => void;
  onActualSize: () => void;
  rotationAllowed: boolean;
  rotation: number;
  rotationMin: number;
  rotationMax: number;
  rotationStep: number;
  onRotationChange: (rotation: number) => void;
  onRotationCommit: () => void;
  showGrid: boolean;
  onToggleGrid: () => void;
  showSafeArea: boolean;
  onToggleSafeArea: () => void;
  hasSafeArea: boolean;
  onReset: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  onCancel?: () => void;
  onSave: () => void;
  onSaveAndContinue?: () => void;
  saving: boolean;
  canSave: boolean;
}

/** The one sticky control surface for the entire editor — view tools
 * (fit/actual-size/grid/safe-area), history (reset/undo/redo), adjustments
 * (zoom/rotation), and actions (cancel/save), never scrolled out of view
 * and never duplicated elsewhere in the UI. */
export function BottomToolbar({
  zoom,
  maxZoom,
  onZoomChange,
  onZoomCommit,
  onFitToScreen,
  onActualSize,
  rotationAllowed,
  rotation,
  rotationMin,
  rotationMax,
  rotationStep,
  onRotationChange,
  onRotationCommit,
  showGrid,
  onToggleGrid,
  showSafeArea,
  onToggleSafeArea,
  hasSafeArea,
  onReset,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  onCancel,
  onSave,
  onSaveAndContinue,
  saving,
  canSave,
}: BottomToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t bg-background px-3 py-2">
      <div className="flex items-center gap-0.5">
        <Button type="button" variant="ghost" size="sm" onClick={onFitToScreen} disabled={saving}>
          Fit
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onActualSize} disabled={saving}>
          100%
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={cn("size-8", showGrid && "bg-accent")}
          onClick={onToggleGrid}
          disabled={saving}
          title="Toggle grid"
        >
          <Grid3x3 className="size-4" />
        </Button>
        {hasSafeArea && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={cn("size-8", showSafeArea && "bg-accent")}
            onClick={onToggleSafeArea}
            disabled={saving}
            title="Toggle safe area guide"
          >
            <ShieldHalf className="size-4" />
          </Button>
        )}
      </div>

      <Separator orientation="vertical" className="h-6" />

      <div className="flex items-center gap-0.5">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onReset}
          disabled={saving}
          title="Reset this breakpoint's crop"
        >
          <RotateCcw className="size-3.5" />
          Reset
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8"
          onClick={onUndo}
          disabled={saving || !canUndo}
          title="Undo (Ctrl+Z)"
        >
          <Undo2 className="size-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8"
          onClick={onRedo}
          disabled={saving || !canRedo}
          title="Redo (Ctrl+Y)"
        >
          <Redo2 className="size-4" />
        </Button>
      </div>

      <Separator orientation="vertical" className="h-6" />

      <div className="flex min-w-[140px] flex-1 items-center gap-2">
        <ZoomOut className="size-3.5 shrink-0 text-muted-foreground" />
        <Slider
          min={1}
          max={maxZoom}
          step={0.05}
          value={[zoom]}
          onValueChange={([v]) => onZoomChange(v)}
          onValueCommit={onZoomCommit}
          disabled={saving}
          className="max-w-40"
        />
        <ZoomIn className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="w-10 shrink-0 text-xs text-muted-foreground">{Math.round(zoom * 100)}%</span>
      </div>

      {rotationAllowed && (
        <div className="flex min-w-[140px] flex-1 items-center gap-2">
          <span className="shrink-0 text-xs text-muted-foreground">Rotate</span>
          <Slider
            min={rotationMin}
            max={rotationMax}
            step={rotationStep}
            value={[rotation]}
            onValueChange={([v]) => onRotationChange(v)}
            onValueCommit={onRotationCommit}
            disabled={saving}
            className="max-w-40"
          />
          <span className="w-9 shrink-0 text-right text-xs text-muted-foreground">
            {Math.round(rotation)}°
          </span>
        </div>
      )}

      <div className="ml-auto flex items-center gap-2">
        {onCancel && (
          <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
        )}
        {onSaveAndContinue && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onSaveAndContinue}
            disabled={saving || !canSave}
          >
            Save & Continue
          </Button>
        )}
        <Button type="button" size="sm" onClick={onSave} disabled={saving || !canSave}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}
