import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Loader2, Upload, X } from "lucide-react";
import { Button } from "@hadha/shared-ui/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@hadha/shared-ui/ui/dialog";
import type { Breakpoint, BreakpointCropGeometry, CropGeometry, CropPreset } from "@hadha/shared-types";
import { validateFileResolution } from "../cropMath";
import { BottomToolbar } from "./BottomToolbar";
import { CropCanvas } from "./CropCanvas";
import { RightPreviewPanel } from "./RightPreviewPanel";
import { TopBar } from "./TopBar";
import { useCropGeometry } from "./useCropGeometry";

export type SaveIntent = "save" | "save-and-continue";

export interface UniversalImageEditorSaveResult {
  /** Null when re-editing an existing image's crop with no new file chosen —
   * the caller should PATCH the new geometry onto the existing image id
   * rather than uploading, since the server always re-derives from the
   * already-stored original anyway (architecture doc §4). */
  file: File | null;
  geometry: CropGeometry;
}

export interface UniversalImageEditorProps {
  /** Controls dialog visibility — the editor owns its own Dialog/DialogContent
   * shell so every consumer gets identical sizing/layout/keyboard handling
   * instead of each form re-implementing the wrapper. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preset: CropPreset;
  /** Existing image URL to start from (re-edit flow); omit for a fresh upload. */
  existingImageSrc?: string;
  /** Seeds the crop editor from a previously-saved geometry (re-edit flow) —
   * without this, re-opening the editor always starts from a fresh centered
   * crop, losing the admin's earlier framing choice. */
  initialCrops?: Partial<Record<Breakpoint, BreakpointCropGeometry>>;
  saving?: boolean;
  onCancel?: () => void;
  onSave: (result: UniversalImageEditorSaveResult, intent: SaveIntent) => void | Promise<void>;
  /** Renders a "Delete image" action in the overflow menu when provided
   * (only meaningful once an image already exists server-side). */
  onDelete?: () => void;
  /** Current alt text (re-edit flow only — a fresh upload has no image id
   * to PATCH onto yet, so the field only appears once `onAltTextCommit` is
   * provided). */
  initialAltText?: string | null;
  /** Persists the alt text immediately (independent of crop save, since it's
   * not part of crop geometry) — fired on blur, not on every keystroke. */
  onAltTextCommit?: (altText: string) => void | Promise<void>;
  /** Renders a "Regenerate variants" action in the overflow menu when
   * provided (only meaningful once an image already exists server-side). */
  onRegenerate?: () => void;
  regenerating?: boolean;
}

const KEY_NUDGE = 10;
const KEY_NUDGE_LARGE = 40;
const KEY_ZOOM_STEP = 0.1;
const PREVIEW_PANEL_WIDTH = "w-[220px] xl:w-[260px]";

/**
 * The single upload/crop/preview component every module consumes — driven
 * entirely by *preset*, never by module-specific logic (architecture doc §11,
 * §14). Upload -> per-breakpoint Crop -> simultaneous Preview -> Save.
 *
 * The canvas is the interface: no permanent sidebars. Which breakpoint is
 * active is a top-bar segmented control, image metadata and file actions
 * collapse into an info popover / overflow menu, and the live preview is a
 * narrow, togglable column — every control that isn't the crop surface
 * itself has to justify the width it takes from the canvas.
 */
export function UniversalImageEditor({
  open,
  onOpenChange,
  preset,
  existingImageSrc,
  initialCrops,
  saving = false,
  onCancel,
  onSave,
  onDelete,
  initialAltText,
  onAltTextCommit,
  onRegenerate,
  regenerating,
}: UniversalImageEditorProps) {
  const [file, setFile] = useState<File | null>(null);
  const [imageSrc, setImageSrc] = useState<string | null>(existingImageSrc ?? null);
  const [imageElement, setImageElement] = useState<HTMLImageElement | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [showSafeArea, setShowSafeArea] = useState(true);
  const [previewOpen, setPreviewOpen] = useState(true);
  const [altText, setAltText] = useState(initialAltText ?? "");
  // Shown inline (not a toast, which can be missed/auto-dismissed) when a
  // picked file fails the preset's minimum-resolution requirement — checked
  // client-side so this surfaces immediately, before the upload round-trip
  // that would otherwise 422 with the same message.
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  // Tracks the blob: URL created for a locally-picked replacement file (as
  // opposed to `existingImageSrc`, a real server URL) so it can be revoked
  // once superseded or the dialog closes — otherwise every "Replace image"
  // pick leaks the previous blob for the lifetime of the tab (docs audit LP-9).
  const objectUrlRef = useRef<string | null>(null);

  const {
    geometry,
    activeBreakpoint,
    viewingAll,
    linked,
    selectBreakpoint,
    selectAll,
    initialize,
    updateBreakpoint,
    copyBreakpoint,
    copyAllFrom,
    resetAllToShared,
    resetBreakpoint,
    commit,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useCropGeometry(preset);

  // Re-sync local image state whenever the dialog is (re)opened for a
  // (possibly different) image, since this component instance is reused
  // across open/close cycles by the call sites.
  useEffect(() => {
    if (open) {
      // A file picked in a previous open (or a previous replace within this
      // same open) that's now being discarded in favor of `existingImageSrc`.
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      setFile(null);
      setImageSrc(existingImageSrc ?? null);
      setAltText(initialAltText ?? "");
      setFileError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, existingImageSrc, initialAltText]);

  // Covers the close-without-reopening and unmount cases the effect above
  // can't — it only fires on the *next* open.
  useEffect(() => {
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  const handleAltTextCommit = useCallback(() => {
    onAltTextCommit?.(altText);
  }, [onAltTextCommit, altText]);

  useEffect(() => {
    if (!imageSrc) return;
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      setImageElement(img);
      // Only seed from the previously-saved crop when we're still showing
      // the original existing image — a freshly-picked replacement file
      // should always start from a fresh centered crop.
      const seedFromExisting = imageSrc === existingImageSrc ? initialCrops : undefined;
      initialize(img.naturalWidth, img.naturalHeight, seedFromExisting);
    };
    img.src = imageSrc;
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageSrc]);

  const handleFileSelected = useCallback(
    async (selected: File) => {
      setFileError(null);
      const error = await validateFileResolution(selected, preset);
      if (error) {
        setFileError(error);
        return;
      }
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      const url = URL.createObjectURL(selected);
      objectUrlRef.current = url;
      setFile(selected);
      setImageSrc(url);
    },
    [preset],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files?.[0];
      // Reset so re-picking the same (rejected) file still fires onChange.
      e.target.value = "";
      if (selected) void handleFileSelected(selected);
    },
    [handleFileSelected],
  );

  const handleSave = useCallback(
    async (intent: SaveIntent) => {
      if (!geometry) return;
      await onSave({ file, geometry }, intent);
      // The picked file has now been uploaded (or this was a crop-only save
      // with no file at all) — either way it's consumed. "Save & Continue"
      // keeps the dialog open for further edits, so without this, the next
      // save in the same session would resend the same File and the caller
      // would upload a *second* image instead of cropping the one it just
      // created.
      setFile(null);
      // Advancing through individual breakpoints only makes sense once
      // they're actually separate crops — while "All" is active there's
      // just the one shared edit to save.
      if (intent === "save-and-continue" && !viewingAll) {
        const idx = preset.breakpoints.indexOf(activeBreakpoint);
        const next = preset.breakpoints[idx + 1];
        if (next) selectBreakpoint(next);
      }
    },
    [file, geometry, onSave, preset.breakpoints, activeBreakpoint, viewingAll, selectBreakpoint],
  );

  const activeGeometry = geometry?.crops[activeBreakpoint];
  const aspect = activeGeometry?.aspectRatio ?? undefined;
  const hasNextBreakpoint =
    !viewingAll && preset.breakpoints.indexOf(activeBreakpoint) < preset.breakpoints.length - 1;
  const hasSafeArea =
    preset.safeArea.top > 0 ||
    preset.safeArea.right > 0 ||
    preset.safeArea.bottom > 0 ||
    preset.safeArea.left > 0;

  const handleFitToScreen = useCallback(() => {
    if (!activeGeometry) return;
    updateBreakpoint(activeBreakpoint, { ...activeGeometry, zoom: 1, pan: { x: 0, y: 0 } });
    commit();
  }, [activeGeometry, activeBreakpoint, updateBreakpoint, commit]);

  const handleActualSize = useCallback(() => {
    if (!activeGeometry || !imageElement || !canvasContainerRef.current) return;
    const rect = canvasContainerRef.current.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const containerAspect = rect.width / rect.height;
    const mediaAspect = imageElement.naturalWidth / imageElement.naturalHeight;
    // Mirrors react-easy-crop's own "contain" sizing math (see CropCanvas
    // comment) so this lands on the same baseline it's zooming from.
    const renderedWidth = containerAspect > mediaAspect ? rect.height * mediaAspect : rect.width;
    const zoom = Math.min(preset.maxZoom, Math.max(1, imageElement.naturalWidth / renderedWidth));
    updateBreakpoint(activeBreakpoint, { ...activeGeometry, zoom });
    commit();
  }, [activeGeometry, imageElement, preset.maxZoom, activeBreakpoint, updateBreakpoint, commit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Dialog-level shortcuts (arrows to nudge, +/- to zoom, ctrl+z to
      // undo) must not hijack typing in an in-dialog field — e.g. the alt
      // text input in ImageInfoPopover, where ArrowLeft/ArrowRight are
      // meant to move the text cursor, not pan the crop (docs audit MP-7).
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
        return;
      }
      if (mod && e.key.toLowerCase() === "y") {
        e.preventDefault();
        redo();
        return;
      }
      if (!activeGeometry) return;
      const delta = e.shiftKey ? KEY_NUDGE_LARGE : KEY_NUDGE;
      switch (e.key) {
        case "ArrowLeft":
          e.preventDefault();
          updateBreakpoint(activeBreakpoint, {
            ...activeGeometry,
            pan: { ...activeGeometry.pan, x: activeGeometry.pan.x - delta },
          });
          commit();
          break;
        case "ArrowRight":
          e.preventDefault();
          updateBreakpoint(activeBreakpoint, {
            ...activeGeometry,
            pan: { ...activeGeometry.pan, x: activeGeometry.pan.x + delta },
          });
          commit();
          break;
        case "ArrowUp":
          e.preventDefault();
          updateBreakpoint(activeBreakpoint, {
            ...activeGeometry,
            pan: { ...activeGeometry.pan, y: activeGeometry.pan.y - delta },
          });
          commit();
          break;
        case "ArrowDown":
          e.preventDefault();
          updateBreakpoint(activeBreakpoint, {
            ...activeGeometry,
            pan: { ...activeGeometry.pan, y: activeGeometry.pan.y + delta },
          });
          commit();
          break;
        case "+":
        case "=":
          e.preventDefault();
          updateBreakpoint(activeBreakpoint, {
            ...activeGeometry,
            zoom: Math.min(preset.maxZoom, activeGeometry.zoom + KEY_ZOOM_STEP),
          });
          commit();
          break;
        case "-":
        case "_":
          e.preventDefault();
          updateBreakpoint(activeBreakpoint, {
            ...activeGeometry,
            zoom: Math.max(1, activeGeometry.zoom - KEY_ZOOM_STEP),
          });
          commit();
          break;
      }
    },
    [activeGeometry, activeBreakpoint, updateBreakpoint, commit, undo, redo, preset.maxZoom],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onKeyDown={handleKeyDown}
        className="fixed left-8 right-8 top-8 bottom-8 z-50 grid h-auto w-auto max-w-none translate-x-0 translate-y-0 grid-rows-[auto_1fr_auto] gap-0 overflow-hidden rounded-lg border bg-background p-0 shadow-2xl max-sm:inset-3"
      >
        <DialogTitle className="sr-only">{preset.label} image editor</DialogTitle>

        {fileError && (
          <div className="absolute top-3 left-1/2 z-50 flex max-w-md -translate-x-1/2 items-start gap-2 rounded-sm border border-destructive bg-destructive px-3 py-2 text-xs text-destructive-foreground shadow-lg">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
            <span>{fileError}</span>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setFileError(null)}
              className="ml-1 shrink-0 opacity-80 hover:opacity-100"
            >
              <X className="size-3.5" />
            </button>
          </div>
        )}

        {!imageSrc ? (
          <div className="flex flex-col items-center justify-center gap-3 p-10">
            <p className="text-sm text-muted-foreground">
              Upload an image for &ldquo;{preset.label}&rdquo;
            </p>
            <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()}>
              <Upload className="size-4" />
              Choose file
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept={preset.storageRules.allowedMime.join(",")}
              className="hidden"
              onChange={handleInputChange}
            />
          </div>
        ) : (
          <>
            <TopBar
              preset={preset}
              imageWidth={imageElement?.naturalWidth ?? 0}
              imageHeight={imageElement?.naturalHeight ?? 0}
              activeBreakpoint={activeBreakpoint}
              viewingAll={viewingAll}
              linked={linked}
              onSelectAll={selectAll}
              onSelectBreakpoint={selectBreakpoint}
              onCopy={copyBreakpoint}
              onCopyAllFrom={copyAllFrom}
              onResetAllToShared={resetAllToShared}
              onReplaceFile={() => fileInputRef.current?.click()}
              onDelete={onDelete}
              onRegenerate={onRegenerate}
              regenerating={regenerating}
              previewOpen={previewOpen}
              onTogglePreview={() => setPreviewOpen((v) => !v)}
              disabled={saving}
              altText={altText}
              onAltTextChange={onAltTextCommit ? setAltText : undefined}
              onAltTextCommit={handleAltTextCommit}
            />

            <div className="relative flex min-h-0">
              {activeGeometry ? (
                <CropCanvas
                  imageSrc={imageSrc}
                  preset={preset}
                  aspect={aspect}
                  geometry={activeGeometry}
                  imageNaturalWidth={imageElement?.naturalWidth ?? 0}
                  imageNaturalHeight={imageElement?.naturalHeight ?? 0}
                  onChange={(next) => updateBreakpoint(activeBreakpoint, next)}
                  onInteractionEnd={commit}
                  showGrid={showGrid}
                  showSafeArea={showSafeArea}
                  containerRef={canvasContainerRef}
                />
              ) : (
                <div className="flex flex-1 items-center justify-center bg-neutral-950 text-white/60">
                  <Loader2 className="size-6 animate-spin" />
                </div>
              )}

              {previewOpen && (
                <div className={`hidden shrink-0 border-l lg:block ${PREVIEW_PANEL_WIDTH}`}>
                  <RightPreviewPanel
                    preset={preset}
                    imageElement={imageElement}
                    crops={geometry?.crops}
                  />
                </div>
              )}

              <input
                ref={fileInputRef}
                type="file"
                accept={preset.storageRules.allowedMime.join(",")}
                className="hidden"
                onChange={handleInputChange}
              />

              {/* Below `lg` the preview becomes an on-demand overlay instead
                  of a column, so the canvas keeps the full viewport width —
                  there's no room to spare for a permanent side panel. */}
              {previewOpen && (
                <div className="absolute inset-0 z-40 flex bg-black/40 lg:hidden">
                  <div className="ml-auto h-full w-72 max-w-[80vw] bg-background shadow-xl">
                    <div className="flex items-center justify-between border-b px-3 py-2">
                      <span className="text-sm font-medium">Live preview</span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="size-7"
                        onClick={() => setPreviewOpen(false)}
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                    <RightPreviewPanel
                      preset={preset}
                      imageElement={imageElement}
                      crops={geometry?.crops}
                    />
                  </div>
                  <button
                    type="button"
                    aria-label="Close preview"
                    className="flex-1"
                    onClick={() => setPreviewOpen(false)}
                  />
                </div>
              )}
            </div>

            <BottomToolbar
              zoom={activeGeometry?.zoom ?? 1}
              maxZoom={preset.maxZoom}
              onZoomChange={(zoom) =>
                activeGeometry && updateBreakpoint(activeBreakpoint, { ...activeGeometry, zoom })
              }
              onZoomCommit={commit}
              onFitToScreen={handleFitToScreen}
              onActualSize={handleActualSize}
              rotationAllowed={preset.rotation.allowed !== "none"}
              rotation={activeGeometry?.rotation ?? 0}
              rotationMin={preset.rotation.minDegrees}
              rotationMax={preset.rotation.maxDegrees}
              rotationStep={preset.rotation.stepDegrees}
              onRotationChange={(rotation) =>
                activeGeometry && updateBreakpoint(activeBreakpoint, { ...activeGeometry, rotation })
              }
              onRotationCommit={commit}
              showGrid={showGrid}
              onToggleGrid={() => setShowGrid((v) => !v)}
              showSafeArea={showSafeArea}
              onToggleSafeArea={() => setShowSafeArea((v) => !v)}
              hasSafeArea={hasSafeArea}
              onReset={() =>
                imageElement &&
                resetBreakpoint(activeBreakpoint, imageElement.naturalWidth, imageElement.naturalHeight)
              }
              onUndo={undo}
              onRedo={redo}
              canUndo={canUndo}
              canRedo={canRedo}
              onCancel={onCancel}
              onSave={() => handleSave("save")}
              onSaveAndContinue={hasNextBreakpoint ? () => handleSave("save-and-continue") : undefined}
              saving={saving}
              canSave={!!geometry}
            />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
