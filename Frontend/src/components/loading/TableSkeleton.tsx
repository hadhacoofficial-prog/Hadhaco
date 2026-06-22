import { Skeleton } from "@/components/ui/skeleton";

interface TableSkeletonProps {
  headers: string[];
  rows?: number;
  firstColWide?: boolean;
}

export function TableSkeleton({ headers, rows = 8, firstColWide = false }: TableSkeletonProps) {
  return (
    <table className="w-full text-sm">
      <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
        <tr>
          {headers.map((h) => (
            <th key={h} className="px-4 py-3">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, i) => (
          <tr key={i}>
            {headers.map((_, j) => (
              <td key={j} className="px-4 py-3">
                {j === 0 && firstColWide ? (
                  <div className="flex items-center gap-3">
                    <Skeleton className="size-10 shrink-0 rounded-none" />
                    <Skeleton className="h-4 w-40" />
                  </div>
                ) : (
                  <Skeleton
                    className={`h-4 ${j === headers.length - 1 ? "w-16 ml-auto" : j === 1 ? "w-20" : "w-24"}`}
                  />
                )}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
