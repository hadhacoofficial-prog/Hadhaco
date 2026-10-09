import { useEffect, useState } from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";

import { formatRupees } from "@/lib/discovery";

interface PriceRangeFilterProps {
  /** Catalogue bounds for the current result set (from facets). */
  bounds: { min: number; max: number };
  value: { min?: number; max?: number };
  onChange: (value: { min?: number; max?: number }) => void;
}

const STEP = 50;
const floorTo = (n: number) => Math.floor(n / STEP) * STEP;
const ceilTo = (n: number) => Math.ceil(n / STEP) * STEP;

/**
 * Two-thumb price slider with exact-value inputs. Dragging only updates
 * local state; the URL (and therefore the request) changes once, on
 * release / blur / Enter. A bound equal to the catalogue edge is sent as
 * "no bound", so the filter chip doesn't appear for an untouched slider.
 */
export function PriceRangeFilter({ bounds, value, onChange }: PriceRangeFilterProps) {
  const lo = floorTo(bounds.min);
  const hi = Math.max(ceilTo(bounds.max), lo + STEP);
  const [range, setRange] = useState<[number, number]>([value.min ?? lo, value.max ?? hi]);
  const [text, setText] = useState({
    min: String(value.min ?? lo),
    max: String(value.max ?? hi),
  });

  useEffect(() => {
    const next: [number, number] = [value.min ?? lo, value.max ?? hi];
    setRange(next);
    setText({ min: String(next[0]), max: String(next[1]) });
  }, [value.min, value.max, lo, hi]);

  const commit = ([a, b]: [number, number]) => {
    let min = Math.max(lo, Math.min(a, hi));
    let max = Math.max(lo, Math.min(b, hi));
    if (min > max) [min, max] = [max, min];
    const next = { min: min > lo ? min : undefined, max: max < hi ? max : undefined };
    if (next.min !== value.min || next.max !== value.max) onChange(next);
    else {
      setRange([value.min ?? lo, value.max ?? hi]);
      setText({ min: String(value.min ?? lo), max: String(value.max ?? hi) });
    }
  };

  const commitText = () => {
    const a = Number(text.min);
    const b = Number(text.max);
    commit([Number.isFinite(a) ? a : lo, Number.isFinite(b) ? b : hi]);
  };

  return (
    <div className="space-y-4">
      <SliderPrimitive.Root
        min={lo}
        max={hi}
        step={STEP}
        minStepsBetweenThumbs={1}
        value={range}
        onValueChange={(v) => {
          setRange([v[0], v[1]]);
          setText({ min: String(v[0]), max: String(v[1]) });
        }}
        onValueCommit={(v) => commit([v[0], v[1]])}
        className="relative flex w-full touch-none select-none items-center h-6"
      >
        <SliderPrimitive.Track className="relative h-[2px] w-full grow bg-border">
          <SliderPrimitive.Range className="absolute h-full bg-foreground" />
        </SliderPrimitive.Track>
        {(["Minimum price", "Maximum price"] as const).map((label, i) => (
          <SliderPrimitive.Thumb
            key={label}
            aria-label={label}
            aria-valuetext={formatRupees(range[i])}
            className="block size-5 rounded-full border border-foreground bg-background shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-grab active:cursor-grabbing"
          />
        ))}
      </SliderPrimitive.Root>

      <div className="flex items-center gap-2">
        {(["min", "max"] as const).map((key, i) => (
          <label
            key={key}
            className="flex-1 flex items-center border border-border px-2 h-10 focus-within:ring-1 focus-within:ring-ring"
          >
            <span className="text-muted-foreground text-xs mr-1" aria-hidden>
              ₹
            </span>
            <span className="sr-only">{key === "min" ? "Minimum price" : "Maximum price"}</span>
            <input
              type="number"
              inputMode="numeric"
              min={lo}
              max={hi}
              step={STEP}
              value={text[key]}
              onChange={(e) => setText((t) => ({ ...t, [key]: e.target.value }))}
              onBlur={commitText}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitText();
              }}
              className="w-full bg-transparent outline-none text-sm [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
            />
            {i === 0 && <span className="sr-only">to</span>}
          </label>
        ))}
      </div>
    </div>
  );
}
