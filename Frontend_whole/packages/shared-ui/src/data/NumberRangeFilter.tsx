import { useEffect, useState } from "react";

import { cn } from "@hadha/shared-utils";

export interface NumberRange {
  min?: number;
  max?: number;
}

interface NumberRangeFilterProps {
  value: NumberRange;
  onChange: (value: NumberRange) => void;
  /** Accessible name of the range, e.g. "Order total". */
  label: string;
  prefix?: string;
  className?: string;
}

const toNum = (s: string): number | undefined => {
  if (s.trim() === "") return undefined;
  const n = Number(s);
  return Number.isFinite(n) && n >= 0 ? n : undefined;
};

/**
 * Min / max inputs that commit on blur or Enter (not on every keystroke), so
 * typing "1500" fires one request instead of four. Swapped bounds are
 * normalised before committing.
 */
export function NumberRangeFilter({
  value,
  onChange,
  label,
  prefix,
  className,
}: NumberRangeFilterProps) {
  const [draft, setDraft] = useState({
    min: value.min?.toString() ?? "",
    max: value.max?.toString() ?? "",
  });

  useEffect(() => {
    setDraft({
      min: value.min?.toString() ?? "",
      max: value.max?.toString() ?? "",
    });
  }, [value.min, value.max]);

  const commit = () => {
    let min = toNum(draft.min);
    let max = toNum(draft.max);
    if (min !== undefined && max !== undefined && min > max) [min, max] = [max, min];
    if (min !== value.min || max !== value.max) onChange({ min, max });
  };

  const input = (key: "min" | "max") => (
    <div className="flex items-center border border-border bg-background h-9 px-2 w-28 focus-within:ring-1 focus-within:ring-ring">
      {prefix && (
        <span aria-hidden className="text-muted-foreground text-xs mr-1">
          {prefix}
        </span>
      )}
      <input
        type="number"
        inputMode="decimal"
        min={0}
        aria-label={`${label} ${key === "min" ? "minimum" : "maximum"}`}
        placeholder={key === "min" ? "Min" : "Max"}
        value={draft[key]}
        onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
        }}
        className="w-full bg-transparent outline-none text-sm [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
      />
    </div>
  );

  return (
    <div role="group" aria-label={label} className={cn("flex items-center gap-2", className)}>
      {input("min")}
      <span aria-hidden className="text-muted-foreground text-xs">
        –
      </span>
      {input("max")}
    </div>
  );
}
