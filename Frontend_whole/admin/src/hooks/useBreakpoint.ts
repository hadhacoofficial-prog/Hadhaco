import { useEffect, useState } from "react";

type Breakpoint = "mobile" | "tablet" | "desktop";

const BREAKPOINTS: Array<{ max: number; bp: Breakpoint }> = [
  { max: 639, bp: "mobile" },
  { max: 1023, bp: "tablet" },
  { max: Infinity, bp: "desktop" },
];

export function useBreakpoint(): Breakpoint {
  const [bp, setBp] = useState<Breakpoint>(() => {
    if (typeof window === "undefined") return "desktop";
    return resolveBp(window.innerWidth);
  });

  useEffect(() => {
    function handleResize() {
      setBp(resolveBp(window.innerWidth));
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return bp;
}

function resolveBp(width: number): Breakpoint {
  for (const { max, bp } of BREAKPOINTS) {
    if (width <= max) return bp;
  }
  return "desktop";
}
