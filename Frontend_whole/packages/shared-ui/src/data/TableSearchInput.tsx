import { Search, X } from "lucide-react";

import { cn } from "@hadha/shared-utils";

interface TableSearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  /** Accessible name; defaults to the placeholder. */
  label?: string;
  className?: string;
}

/** Search box used by every admin table toolbar (callers debounce). */
export function TableSearchInput({
  value,
  onChange,
  placeholder,
  label,
  className,
}: TableSearchInputProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 border border-border bg-background px-3 h-9 min-w-[200px] focus-within:ring-1 focus-within:ring-ring",
        className,
      )}
    >
      <Search aria-hidden className="size-4 text-muted-foreground shrink-0" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={label ?? placeholder}
        className="flex-1 min-w-0 bg-transparent outline-none text-sm [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}
