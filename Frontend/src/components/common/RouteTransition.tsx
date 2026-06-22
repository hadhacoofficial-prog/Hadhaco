import { useEffect, useState, type ReactNode } from "react";
import { useRouterState } from "@tanstack/react-router";
import { PageLoader } from "./PageLoader";

/**
 * Shows the Hadha branded loader during route transitions
 * (pending / loading state) up to ~500ms feel.
 */
export function RouteTransition({ children }: { children: ReactNode }) {
  const status = useRouterState({ select: (s) => s.status });
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (status === "pending") {
      setVisible(true);
      return;
    }
    const t = setTimeout(() => setVisible(false), 220);
    return () => clearTimeout(t);
  }, [status]);

  return (
    <>
      {children}
      <div
        aria-hidden={!visible}
        className={`pointer-events-none transition-opacity duration-300 ${
          visible ? "opacity-100" : "opacity-0"
        }`}
      >
        {visible && <PageLoader />}
      </div>
    </>
  );
}
