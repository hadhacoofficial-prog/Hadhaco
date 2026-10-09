import { useId } from "react";

import { cn } from "@hadha/shared-utils";

export type DatePreset =
  | "any"
  | "today"
  | "yesterday"
  | "last7"
  | "last30"
  | "thisMonth"
  | "lastMonth"
  | "custom";

export interface DateRangeValue {
  preset: DatePreset;
  /** `YYYY-MM-DD`, local date — only used when preset is "custom". */
  from?: string;
  /** `YYYY-MM-DD`, local date, inclusive — only used when preset is "custom". */
  to?: string;
}

export const DATE_PRESET_LABELS: Record<DatePreset, string> = {
  any: "Any time",
  today: "Today",
  yesterday: "Yesterday",
  last7: "Last 7 days",
  last30: "Last 30 days",
  thisMonth: "This month",
  lastMonth: "Last month",
  custom: "Custom range",
};

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

function parseLocalDate(s?: string): Date | undefined {
  if (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return undefined;
  const [y, m, d] = s.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

/**
 * Resolve a preset into API bounds: `date_from` inclusive, `date_to`
 * exclusive (start of the day *after* the range), both ISO-8601 instants in
 * the admin's local timezone — so "Today" means the admin's today, not UTC's.
 */
export function resolveDateRange(
  value: DateRangeValue,
  now: Date = new Date(),
): { date_from?: string; date_to?: string } {
  const today = startOfDay(now);
  let from: Date | undefined;
  let to: Date | undefined;
  switch (value.preset) {
    case "today":
      [from, to] = [today, addDays(today, 1)];
      break;
    case "yesterday":
      [from, to] = [addDays(today, -1), today];
      break;
    case "last7":
      [from, to] = [addDays(today, -6), addDays(today, 1)];
      break;
    case "last30":
      [from, to] = [addDays(today, -29), addDays(today, 1)];
      break;
    case "thisMonth":
      [from, to] = [new Date(today.getFullYear(), today.getMonth(), 1), addDays(today, 1)];
      break;
    case "lastMonth":
      [from, to] = [
        new Date(today.getFullYear(), today.getMonth() - 1, 1),
        new Date(today.getFullYear(), today.getMonth(), 1),
      ];
      break;
    case "custom": {
      from = parseLocalDate(value.from);
      const end = parseLocalDate(value.to);
      to = end ? addDays(end, 1) : undefined;
      if (from && to && from >= to) [from, to] = [addDays(to, -1), addDays(from, 1)];
      break;
    }
    default:
      break;
  }
  return { date_from: from?.toISOString(), date_to: to?.toISOString() };
}

/** Short human label for an active-filter chip, or null when inactive. */
export function describeDateRange(value: DateRangeValue): string | null {
  if (value.preset === "any") return null;
  if (value.preset !== "custom") return DATE_PRESET_LABELS[value.preset];
  if (value.from && value.to) return `${value.from} → ${value.to}`;
  if (value.from) return `From ${value.from}`;
  if (value.to) return `Until ${value.to}`;
  return null;
}

interface DateRangeFilterProps {
  value: DateRangeValue;
  onChange: (value: DateRangeValue) => void;
  label?: string;
  className?: string;
}

export function DateRangeFilter({
  value,
  onChange,
  label = "Date",
  className,
}: DateRangeFilterProps) {
  const id = useId();
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <select
        id={id}
        value={value.preset}
        onChange={(e) => onChange({ ...value, preset: e.target.value as DatePreset })}
        className="h-9 border border-border bg-background px-3 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        {(Object.keys(DATE_PRESET_LABELS) as DatePreset[]).map((p) => (
          <option key={p} value={p}>
            {p === "any" ? `${label}: ${DATE_PRESET_LABELS[p]}` : DATE_PRESET_LABELS[p]}
          </option>
        ))}
      </select>
      {value.preset === "custom" && (
        <>
          <input
            type="date"
            aria-label={`${label} from`}
            value={value.from ?? ""}
            max={value.to || undefined}
            onChange={(e) => onChange({ ...value, from: e.target.value || undefined })}
            className="h-9 border border-border bg-background px-2 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          <span aria-hidden className="text-muted-foreground text-xs">
            to
          </span>
          <input
            type="date"
            aria-label={`${label} to`}
            value={value.to ?? ""}
            min={value.from || undefined}
            onChange={(e) => onChange({ ...value, to: e.target.value || undefined })}
            className="h-9 border border-border bg-background px-2 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </>
      )}
    </div>
  );
}
