import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { FormSkeleton } from "@/components/loading/FormSkeleton";
import { useNotificationTemplate } from "@/hooks/admin/useNotificationAdmin";
import { TemplateEditor } from "@/components/admin/notifications/TemplateEditor";
import { TemplateVersionHistory } from "@/components/admin/notifications/TemplateVersionHistory";

export const Route = createFileRoute("/admin/notifications/templates/$templateId")({
  component: TemplateDetail,
});

function TemplateDetail() {
  const { templateId } = Route.useParams();
  const { data: template, isLoading } = useNotificationTemplate(templateId);

  return (
    <div>
      <Link
        to="/admin/notifications/templates"
        className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 mb-4"
      >
        <ArrowLeft className="size-3.5" /> Back to templates
      </Link>

      {isLoading ? (
        <div className="space-y-6">
          <FormSkeleton fields={3} columns={1} showTitle />
          <FormSkeleton fields={2} columns={1} showTitle />
        </div>
      ) : !template ? (
        <p className="text-sm text-muted-foreground py-10 text-center">Template not found.</p>
      ) : (
        <div className="space-y-6">
          <TemplateEditor template={template} />
          <TemplateVersionHistory templateId={template.id} />
        </div>
      )}
    </div>
  );
}
