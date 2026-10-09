import { ChevronLeft, ChevronRight } from "lucide-react";

interface TablePaginationProps {
  page: number;
  totalPages: number;
  total: number;
  /** Plural noun for the count line, e.g. "orders". */
  noun: string;
  onPageChange: (page: number) => void;
}

/** Admin table footer: "Page 2 of 9 · 128 orders" with prev / next. */
export function TablePagination({
  page,
  totalPages,
  total,
  noun,
  onPageChange,
}: TablePaginationProps) {
  if (totalPages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between mt-4">
      <p className="text-sm text-muted-foreground" aria-live="polite">
        Page {page} of {totalPages} · {total} {noun}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          aria-label="Previous page"
          className="p-2 border border-border hover:bg-secondary disabled:opacity-50"
        >
          <ChevronLeft className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={page >= totalPages}
          aria-label="Next page"
          className="p-2 border border-border hover:bg-secondary disabled:opacity-50"
        >
          <ChevronRight className="size-4" />
        </button>
      </div>
    </nav>
  );
}
