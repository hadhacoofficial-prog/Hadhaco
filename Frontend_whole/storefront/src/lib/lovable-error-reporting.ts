import * as Sentry from "@sentry/react";

type LovableErrorOptions = {
  mechanism?: "manual" | "onerror" | "unhandledrejection" | "react_error_boundary";
  handled?: boolean;
  severity?: "error" | "warning" | "info";
};

type LovableEvents = {
  captureException?: (
    error: unknown,
    context?: Record<string, unknown>,
    options?: LovableErrorOptions,
  ) => void;
};

declare global {
  interface Window {
    __lovableEvents?: LovableEvents;
  }
}

export function reportLovableError(error: unknown, context: Record<string, unknown> = {}) {
  if (typeof window === "undefined") return;

  // Send to Sentry/GlitchTip
  Sentry.withScope((scope) => {
    scope.setTag("source", "react_error_boundary");
    scope.setTag("route", window.location.pathname);
    scope.setLevel("error");
    Sentry.captureException(error);
  });

  // Send to Lovable platform (if available)
  window.__lovableEvents?.captureException?.(
    error,
    {
      source: "react_error_boundary",
      route: window.location.pathname,
      ...context,
    },
    {
      mechanism: "react_error_boundary",
      handled: false,
      severity: "error",
    },
  );
}

export function reportUnhandledError(error: unknown) {
  if (typeof window === "undefined") return;
  Sentry.withScope((scope) => {
    scope.setTag("source", "unhandled");
    scope.setTag("route", window.location.pathname);
    scope.setLevel("error");
    Sentry.captureException(error);
  });
}
