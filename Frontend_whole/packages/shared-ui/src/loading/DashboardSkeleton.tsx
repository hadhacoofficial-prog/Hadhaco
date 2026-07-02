import { Skeleton } from "../ui/skeleton";

export function DashboardKPISkeleton({
  count = 4,
  cols = 4,
  showIcon = true,
  showTrend = true,
}: {
  count?: number;
  cols?: 3 | 4;
  showIcon?: boolean;
  showTrend?: boolean;
}) {
  return (
    <div
      className={`grid sm:grid-cols-2 gap-4 ${cols === 3 ? "lg:grid-cols-3" : "lg:grid-cols-4"}`}
    >
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-background border border-border p-5">
          <div className="flex items-center justify-between">
            <Skeleton className="h-3 w-28" />
            {showIcon && <Skeleton className="size-5 rounded-sm" />}
          </div>
          <Skeleton className="h-8 w-20 mt-3" />
          {showTrend && <Skeleton className="h-3 w-24 mt-2" />}
        </div>
      ))}
    </div>
  );
}

export function DashboardListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <ul className="divide-y divide-border">
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i} className="py-3 flex items-center gap-3">
          <Skeleton className="size-10 shrink-0 rounded-none" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-4 w-16 shrink-0" />
        </li>
      ))}
    </ul>
  );
}

export function ChartSkeleton() {
  return (
    <div className="flex items-end gap-2 h-40">
      {Array.from({ length: 12 }).map((_, i) => (
        <Skeleton
          key={i}
          className="flex-1 rounded-none"
          style={{ height: `${30 + ((i * 37) % 70)}%` }}
        />
      ))}
    </div>
  );
}
