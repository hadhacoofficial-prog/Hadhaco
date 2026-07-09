import { useCallback, useRef, useState } from "react";
import type { Breakpoint, BreakpointCropGeometry, CropGeometry, CropPreset } from "@hadha/shared-types";
import { computeSyncedCropBox, defaultCropBox, focusPointFromBox } from "../cropMath";

const MAX_HISTORY = 50;
// No explicit "drag start"/"drag end" pair exists for every input (mouse
// wheel zoom ticks have neither), so a burst of rapid changes with no gap
// longer than this is treated as one undo step; anything after this much
// idle time starts a fresh checkpoint on its next change.
const BURST_IDLE_MS = 400;

export interface SyncFraming {
  focusPoint: { x: number; y: number };
  zoom: number;
  rotation: number;
}

/** Full undo-able session state — everything about how the breakpoints
 * relate to each other, not just their pixel geometry, so undo/redo also
 * reverts "this breakpoint just went custom" the same way it reverts a pan. */
interface Session {
  geometry: CropGeometry;
  linked: Set<Breakpoint>;
  syncFraming: SyncFraming;
}

function cloneSession(s: Session): Session {
  return {
    geometry: { ...s.geometry, crops: { ...s.geometry.crops } },
    linked: new Set(s.linked),
    syncFraming: { ...s.syncFraming, focusPoint: { ...s.syncFraming.focusPoint } },
  };
}

function seedGeometry(preset: CropPreset, imageWidth: number, imageHeight: number): CropGeometry {
  const crops: CropGeometry["crops"] = {};
  for (const bp of preset.breakpoints) {
    const aspect = preset.aspectRatio[bp] ?? null;
    crops[bp] = {
      aspectRatio: aspect,
      box: defaultCropBox(imageWidth, imageHeight, aspect),
      zoom: 1,
      pan: { x: 0, y: 0 },
      rotation: 0,
    };
  }
  return {
    presetId: preset.id,
    focusPoint: { x: 0.5, y: 0.5 },
    crops,
  };
}

function deriveLinkedGeometry(
  preset: CropPreset,
  imageWidth: number,
  imageHeight: number,
  linked: Set<Breakpoint>,
  syncFraming: SyncFraming,
  prev: CropGeometry,
): CropGeometry {
  const crops = { ...prev.crops };
  for (const bp of linked) {
    const aspect = preset.aspectRatio[bp] ?? null;
    const box = computeSyncedCropBox(
      imageWidth,
      imageHeight,
      aspect,
      syncFraming.focusPoint,
      syncFraming.zoom,
      syncFraming.rotation,
    );
    crops[bp] = { aspectRatio: aspect, box, zoom: syncFraming.zoom, pan: { x: 0, y: 0 }, rotation: syncFraming.rotation };
  }
  return { ...prev, focusPoint: syncFraming.focusPoint, crops };
}

/**
 * Owns the per-breakpoint crop state for one UniversalImageEditor session,
 * including:
 *  - an undo/redo history,
 *  - "All breakpoints" sync mode: a single shared framing (focus point +
 *    zoom + rotation) that every *linked* breakpoint's box is derived from,
 *    so editing once updates desktop/tablet/mobile simultaneously even
 *    though they can have very different target aspect ratios (hero's
 *    desktop vs. mobile crop, for instance) — literally sharing box pixels
 *    only works when every breakpoint happens to share one aspect ratio.
 *  - per-breakpoint independence: editing a single breakpoint's tab directly
 *    unlinks just that one from the shared framing; the rest stay synced.
 */
export function useCropGeometry(preset: CropPreset) {
  const [geometry, setGeometry] = useState<CropGeometry | null>(null);
  const [activeBreakpoint, setActiveBreakpointState] = useState<Breakpoint>(preset.breakpoints[0]);
  const [viewingAll, setViewingAll] = useState(preset.breakpoints.length > 1);
  const [linked, setLinked] = useState<Set<Breakpoint>>(new Set(preset.breakpoints));
  const [syncFraming, setSyncFraming] = useState<SyncFraming>({
    focusPoint: { x: 0.5, y: 0.5 },
    zoom: 1,
    rotation: 0,
  });
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const sessionRef = useRef<Session | null>(null);
  const imageSizeRef = useRef({ width: 0, height: 0 });
  sessionRef.current = geometry ? { geometry, linked, syncFraming } : null;

  const historyRef = useRef<Session[]>([]);
  const futureRef = useRef<Session[]>([]);
  const burstActiveRef = useRef(false);
  const burstTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const syncFlags = useCallback(() => {
    setCanUndo(historyRef.current.length > 0);
    setCanRedo(futureRef.current.length > 0);
  }, []);

  /** Closes the current undo burst so the next change starts a new one —
   * call on drag-end / slider-release ("commit") events. */
  const commit = useCallback(() => {
    if (burstTimerRef.current) clearTimeout(burstTimerRef.current);
    burstActiveRef.current = false;
  }, []);

  const checkpoint = useCallback(() => {
    if (burstActiveRef.current || !sessionRef.current) return;
    burstActiveRef.current = true;
    historyRef.current = [...historyRef.current, cloneSession(sessionRef.current)].slice(
      -MAX_HISTORY,
    );
    futureRef.current = [];
    syncFlags();
    if (burstTimerRef.current) clearTimeout(burstTimerRef.current);
    burstTimerRef.current = setTimeout(commit, BURST_IDLE_MS);
  }, [commit, syncFlags]);

  const applySession = useCallback((next: Session) => {
    setGeometry(next.geometry);
    setLinked(next.linked);
    setSyncFraming(next.syncFraming);
  }, []);

  const initialize = useCallback(
    (
      imageWidth: number,
      imageHeight: number,
      initialCrops?: Partial<Record<Breakpoint, BreakpointCropGeometry>>,
    ) => {
      imageSizeRef.current = { width: imageWidth, height: imageHeight };
      const seeded = seedGeometry(preset, imageWidth, imageHeight);

      if (initialCrops) {
        // Re-editing an already-saved image: respect whatever was persisted
        // per breakpoint rather than guessing at its sync history — start
        // every breakpoint independent so nothing gets silently overwritten.
        for (const bp of Object.keys(initialCrops) as Breakpoint[]) {
          const override = initialCrops[bp];
          if (override) seeded.crops[bp] = override;
        }
        const first = seeded.crops[preset.breakpoints[0]];
        setSyncFraming(
          first
            ? {
                focusPoint: focusPointFromBox(imageWidth, imageHeight, first.rotation, first.box),
                zoom: first.zoom,
                rotation: first.rotation,
              }
            : { focusPoint: { x: 0.5, y: 0.5 }, zoom: 1, rotation: 0 },
        );
        setLinked(new Set());
        setViewingAll(false);
        setActiveBreakpointState(preset.breakpoints[0]);
      } else {
        // Fresh upload: every breakpoint starts linked to one shared crop —
        // the common case is the same framing works everywhere, so this
        // minimizes work instead of demanding N separate crops up front.
        setSyncFraming({ focusPoint: { x: 0.5, y: 0.5 }, zoom: 1, rotation: 0 });
        setLinked(new Set(preset.breakpoints));
        setViewingAll(preset.breakpoints.length > 1);
        setActiveBreakpointState(preset.breakpoints[0]);
      }

      setGeometry(seeded);
      historyRef.current = [];
      futureRef.current = [];
      burstActiveRef.current = false;
      syncFlags();
    },
    [preset, syncFlags],
  );

  /** Called from the crop canvas with the freshly-interacted breakpoint's
   * new geometry. In "All" view this updates the shared framing and
   * re-derives every other *linked* breakpoint; in individual view it
   * either unlinks this breakpoint (first edit while still linked) or just
   * updates it directly (already independent). */
  const updateBreakpoint = useCallback(
    (breakpoint: Breakpoint, next: BreakpointCropGeometry) => {
      if (
        !Number.isFinite(next.zoom) ||
        !Number.isFinite(next.rotation) ||
        !Number.isFinite(next.pan.x) ||
        !Number.isFinite(next.pan.y) ||
        !Number.isFinite(next.box.x) ||
        !Number.isFinite(next.box.y) ||
        !Number.isFinite(next.box.width) ||
        !Number.isFinite(next.box.height)
      ) {
        // Guards against NaN/Infinity cascades from a transiently
        // zero-size canvas container feeding back into react-easy-crop's
        // internal measurement loop (NaN !== NaN would otherwise
        // re-trigger forever — see CropCanvas/git history).
        return;
      }
      const current = sessionRef.current;
      if (!current) return;
      checkpoint();

      const { width, height } = imageSizeRef.current;

      if (viewingAll) {
        const nextFraming: SyncFraming = {
          zoom: next.zoom,
          rotation: next.rotation,
          focusPoint: focusPointFromBox(width, height, next.rotation, next.box),
        };
        const derived = deriveLinkedGeometry(
          preset,
          width,
          height,
          current.linked,
          nextFraming,
          current.geometry,
        );
        // The breakpoint actually being dragged keeps react-easy-crop's
        // exact reported value (pan included) for interaction continuity
        // — everything else uses the freshly-derived synced box.
        setSyncFraming(nextFraming);
        setGeometry({ ...derived, crops: { ...derived.crops, [breakpoint]: next } });
        return;
      }

      if (current.linked.has(breakpoint)) {
        const nextLinked = new Set(current.linked);
        nextLinked.delete(breakpoint);
        setLinked(nextLinked);
      }
      setGeometry({ ...current.geometry, crops: { ...current.geometry.crops, [breakpoint]: next } });
    },
    [checkpoint, viewingAll, preset],
  );

  const selectBreakpoint = useCallback((breakpoint: Breakpoint) => {
    setViewingAll(false);
    setActiveBreakpointState(breakpoint);
  }, []);

  const selectAll = useCallback(() => {
    setViewingAll(true);
    setActiveBreakpointState(preset.breakpoints[0]);
  }, [preset.breakpoints]);

  const copyBreakpoint = useCallback(
    (source: Breakpoint, target: Breakpoint) => {
      checkpoint();
      setGeometry((prev) => {
        if (!prev) return prev;
        const sourceGeometry = prev.crops[source];
        if (!sourceGeometry) return prev;
        return { ...prev, crops: { ...prev.crops, [target]: { ...sourceGeometry } } };
      });
      setLinked((prev) => {
        const next = new Set(prev);
        next.delete(target);
        return next;
      });
      commit();
    },
    [checkpoint, commit],
  );

  /** One-time snapshot: every other breakpoint adopts *source*'s current
   * center-of-interest + zoom + rotation (each still cropped to its own
   * aspect ratio), then goes independent — distinct from re-linking, which
   * would keep following future edits to the shared framing too. */
  const copyAllFrom = useCallback(
    (source: Breakpoint) => {
      checkpoint();
      const { width, height } = imageSizeRef.current;
      setGeometry((prev) => {
        if (!prev) return prev;
        const sourceGeometry = prev.crops[source];
        if (!sourceGeometry) return prev;
        const framing: SyncFraming = {
          zoom: sourceGeometry.zoom,
          rotation: sourceGeometry.rotation,
          focusPoint: focusPointFromBox(width, height, sourceGeometry.rotation, sourceGeometry.box),
        };
        const crops = { ...prev.crops };
        for (const bp of preset.breakpoints) {
          if (bp === source) continue;
          const aspect = preset.aspectRatio[bp] ?? null;
          const box = computeSyncedCropBox(width, height, aspect, framing.focusPoint, framing.zoom, framing.rotation);
          crops[bp] = { aspectRatio: aspect, box, zoom: framing.zoom, pan: { x: 0, y: 0 }, rotation: framing.rotation };
        }
        return { ...prev, crops };
      });
      setLinked(new Set([source]));
      commit();
    },
    [checkpoint, commit, preset],
  );

  const resetAllToShared = useCallback(() => {
    checkpoint();
    const { width, height } = imageSizeRef.current;
    const allLinked = new Set(preset.breakpoints);
    setGeometry((prev) => (prev ? deriveLinkedGeometry(preset, width, height, allLinked, syncFraming, prev) : prev));
    setLinked(allLinked);
    setViewingAll(true);
    commit();
  }, [checkpoint, commit, preset, syncFraming]);

  const resetBreakpoint = useCallback(
    (breakpoint: Breakpoint, imageWidth: number, imageHeight: number) => {
      const current = sessionRef.current;
      if (!current) return;
      checkpoint();

      if (viewingAll) {
        // Resetting while "All" is active must reset the *shared* framing
        // and re-derive every linked breakpoint from it — resetting only
        // the representative breakpoint's box would leave the others
        // linked but silently out of sync with it.
        const defaultFraming: SyncFraming = { focusPoint: { x: 0.5, y: 0.5 }, zoom: 1, rotation: 0 };
        setSyncFraming(defaultFraming);
        setGeometry(
          deriveLinkedGeometry(preset, imageWidth, imageHeight, current.linked, defaultFraming, current.geometry),
        );
        commit();
        return;
      }

      const aspect = preset.aspectRatio[breakpoint] ?? null;
      setGeometry({
        ...current.geometry,
        crops: {
          ...current.geometry.crops,
          [breakpoint]: {
            aspectRatio: aspect,
            box: defaultCropBox(imageWidth, imageHeight, aspect),
            zoom: 1,
            pan: { x: 0, y: 0 },
            rotation: 0,
          },
        },
      });
      if (current.linked.has(breakpoint)) {
        const nextLinked = new Set(current.linked);
        nextLinked.delete(breakpoint);
        setLinked(nextLinked);
      }
      commit();
    },
    [preset, checkpoint, commit, viewingAll],
  );

  const undo = useCallback(() => {
    commit();
    const prevSnapshot = historyRef.current[historyRef.current.length - 1];
    if (!prevSnapshot || !sessionRef.current) return;
    historyRef.current = historyRef.current.slice(0, -1);
    futureRef.current = [...futureRef.current, cloneSession(sessionRef.current)].slice(-MAX_HISTORY);
    applySession(prevSnapshot);
    syncFlags();
  }, [commit, applySession, syncFlags]);

  const redo = useCallback(() => {
    commit();
    const nextSnapshot = futureRef.current[futureRef.current.length - 1];
    if (!nextSnapshot || !sessionRef.current) return;
    futureRef.current = futureRef.current.slice(0, -1);
    historyRef.current = [...historyRef.current, cloneSession(sessionRef.current)].slice(-MAX_HISTORY);
    applySession(nextSnapshot);
    syncFlags();
  }, [commit, applySession, syncFlags]);

  const reset = useCallback(() => setGeometry(null), []);

  return {
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
    reset,
  };
}
