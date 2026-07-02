import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import type { AdminUserListResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/customers")({
  component: AdminCustomers,
});

function AdminCustomers() {
  const [search, setSearch] = useState("");

  const params = { page: 1, page_size: 50, search: search || undefined };

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.admin.customers(params),
    queryFn: () => api.get<AdminUserListResponse>("/admin/users", { params }),
    staleTime: 60_000,
  });

  const customers = data?.items ?? [];

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Audience</p>
        <h1 className="font-display text-4xl mt-1">
          Customers <span className="text-muted-foreground text-2xl">({data?.total ?? 0})</span>
        </h1>
      </header>

      <div className="bg-background border border-border p-4 flex items-center gap-2 mb-4 max-w-sm">
        <Search className="size-4 text-muted-foreground shrink-0" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by email or name…"
          className="flex-1 bg-transparent outline-none text-sm"
        />
      </div>

      <div className="bg-background border border-border overflow-x-auto">
        {isLoading ? (
          <TableSkeleton headers={["Email", "Name", "Role", "Status", "Joined"]} rows={8} />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Joined</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {customers.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-3">{c.email}</td>
                  <td className="px-4 py-3">{c.full_name ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                        c.role === "super_admin"
                          ? "bg-destructive/15 text-destructive"
                          : c.role === "admin"
                            ? "bg-accent/15 text-accent"
                            : "bg-secondary text-muted-foreground"
                      }`}
                    >
                      {c.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                        c.is_active
                          ? "bg-accent/15 text-accent"
                          : "bg-destructive/15 text-destructive"
                      }`}
                    >
                      {c.is_active ? "Active" : "Suspended"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(c.created_at).toLocaleDateString("en-IN")}
                  </td>
                </tr>
              ))}
              {customers.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground text-sm">
                    No customers found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
