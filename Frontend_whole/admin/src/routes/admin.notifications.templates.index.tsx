import { useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Mail, MessageCircle } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useNotificationTemplates } from "@/hooks/admin/useNotificationAdmin";

export const Route = createFileRoute("/admin/notifications/templates/")({
  component: TemplatesList,
});

function TemplatesList() {
  const { data: templates, isLoading } = useNotificationTemplates();

  const grouped = useMemo(() => {
    const map = new Map<string, typeof templates>();
    for (const t of templates ?? []) {
      if (!map.has(t.event_type)) map.set(t.event_type, []);
      map.get(t.event_type)!.push(t);
    }
    return map;
  }, [templates]);

  if (isLoading) {
    return (
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="bg-background border border-border p-5 space-y-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (!templates || templates.length === 0) {
    return <p className="text-sm text-muted-foreground py-10 text-center">No templates found.</p>;
  }

  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {[...grouped.entries()].map(([eventType, group]) => (
        <div key={eventType} className="bg-background border border-border p-5">
          <p className="font-medium text-sm mb-3">{eventType.replaceAll("_", " ")}</p>
          <div className="space-y-2">
            {group?.map((tpl) => (
              <Link
                key={tpl.id}
                to="/admin/notifications/templates/$templateId"
                params={{ templateId: tpl.id }}
                className="flex items-center justify-between gap-2 text-sm px-3 py-2 rounded-md border border-border hover:bg-secondary/60 transition-colors"
              >
                <span className="flex items-center gap-2">
                  {tpl.channel === "email" ? (
                    <Mail className="size-3.5 text-accent" />
                  ) : (
                    <MessageCircle className="size-3.5 text-accent" />
                  )}
                  {tpl.channel === "email" ? "Email" : "WhatsApp"}
                </span>
                {!tpl.is_active && (
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Inactive
                  </span>
                )}
              </Link>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
