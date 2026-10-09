import { useId } from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@hadha/shared-utils";

export interface FilterOption<V extends string = string> {
  value: V;
  label: string;
}

interface FilterSelectProps<V extends string> {
  /** Accessible name; also shown in the "all" option, e.g. "All payment states". */
  label: string;
  value: V | "";
  onChange: (value: V | "") => void;
  options: FilterOption<V>[];
  allLabel?: string;
  className?: string;
}

/**
 * Single-select table filter. Empty string means "no filter". A native
 * `<select>` keeps full keyboard / screen-reader support and works inside
 * dense admin toolbars at any width.
 */
export function FilterSelect<V extends string>({
  label,
  value,
  onChange,
  options,
  allLabel,
  className,
}: FilterSelectProps<V>) {
  const id = useId();
  return (
    <div className={cn("relative flex items-center", className)}>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value as V | "")}
        className={cn(
          "h-9 w-full appearance-none border border-border bg-background pl-3 pr-8 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring",
          value && "border-foreground",
        )}
      >
        <option value="">{allLabel ?? `All · ${label}`}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute right-2.5 size-3.5 text-muted-foreground"
      />
    </div>
  );
}
