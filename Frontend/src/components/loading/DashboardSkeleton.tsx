import { Skeleton } from "@/components/ui/skeleton";

export function DashboardKPISkeleton() {
  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="bg-background border border-border p-5">
          <div className="flex items-center justify-between">
            <Skeleton className="h-3 w-28" />
            <Skeleton className="size-5 rounded-sm" />
          </div>
          <Skeleton className="h-8 w-20 mt-3" />
          <Skeleton className="h-3 w-24 mt-2" />
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
