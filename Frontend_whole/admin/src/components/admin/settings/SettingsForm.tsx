import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import type { FeatureFlagOut } from "@/types/admin";

// Human-readable labels for known flag keys — falls back to the raw key for
// any flag seeded later that this page hasn't been told a nicer label for.
const FLAG_LABELS: Record<string, string> = {
  complimentary_gift_enabled: "Complimentary Gift",
};

export function SettingsForm() {
  const queryClient = useQueryClient();

  const { data: flags, isLoading } = useQuery({
    queryKey: queryKeys.admin.settings,
    queryFn: () => api.get<FeatureFlagOut[]>("/admin/settings/flags"),
  });

  const mutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: boolean }) =>
      api.put<FeatureFlagOut>(`/admin/settings/flags/${key}`, { body: { value } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.settings });
      toast.success("Setting updated");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Store</p>
        <h1 className="font-display text-3xl mt-0.5">Store Settings</h1>
      </header>

      <section className="bg-background border border-border p-6 space-y-4 max-w-xl">
        <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
          Feature Flags
        </h2>

        {isLoading && (
          <p className="text-sm text-muted-foreground flex items-center gap-2">
            <Loader2 className="size-3.5 animate-spin" /> Loading…
          </p>
        )}

        {!isLoading && (flags?.length ?? 0) === 0 && (
          <p className="text-sm text-muted-foreground">No feature flags configured yet.</p>
        )}

        {(flags ?? []).map((flag) => (
          <div key={flag.key} className="flex items-center justify-between gap-4 py-1">
            <div>
              <Label htmlFor={flag.key} className="text-sm cursor-pointer">
                {FLAG_LABELS[flag.key] ?? flag.key}
              </Label>
              {flag.description && (
                <p className="text-xs text-muted-foreground mt-0.5">{flag.description}</p>
              )}
            </div>
            <Switch
              id={flag.key}
              checked={flag.value}
              disabled={mutation.isPending && mutation.variables?.key === flag.key}
              aria-busy={mutation.isPending && mutation.variables?.key === flag.key}
              onCheckedChange={(checked) => mutation.mutate({ key: flag.key, value: checked })}
            />
          </div>
        ))}
      </section>
    </div>
  );
}
