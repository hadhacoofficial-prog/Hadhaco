import { Tabs, TabsList, TabsTrigger } from "@hadha/shared-ui/ui/tabs";
import { Button } from "@hadha/shared-ui/ui/button";
import type { Breakpoint } from "@hadha/shared-types";

const BREAKPOINT_LABEL: Record<Breakpoint, string> = {
  desktop: "Desktop",
  tablet: "Tablet",
  mobile: "Mobile",
  all: "Crop",
};

interface BreakpointTabsProps {
  breakpoints: Breakpoint[];
  active: Breakpoint;
  onChange: (breakpoint: Breakpoint) => void;
  onCopyFromDesktop?: () => void;
}

/** Only rendered when a preset previews/crops more than one breakpoint. */
export function BreakpointTabs({
  breakpoints,
  active,
  onChange,
  onCopyFromDesktop,
}: BreakpointTabsProps) {
  if (breakpoints.length <= 1) return null;

  return (
    <div className="flex items-center justify-between gap-2">
      <Tabs value={active} onValueChange={(v) => onChange(v as Breakpoint)}>
        <TabsList>
          {breakpoints.map((bp) => (
            <TabsTrigger key={bp} value={bp}>
              {BREAKPOINT_LABEL[bp]}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {active !== "desktop" && breakpoints.includes("desktop") && onCopyFromDesktop && (
        <Button type="button" variant="ghost" size="sm" onClick={onCopyFromDesktop}>
          Copy from Desktop
        </Button>
      )}
    </div>
  );
}
