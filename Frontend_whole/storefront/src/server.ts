import "./lib/error-capture";

import { AsyncLocalStorage } from "node:async_hooks";
import * as Sentry from "@sentry/react";
import { cspHeader, generateNonce, type CspRequestContext } from "./lib/csp";
import { consumeLastCapturedError } from "./lib/error-capture";
import { renderErrorPage } from "./lib/error-page";
import { handleSeoRequest } from "./lib/seo-routes";

// Initialize Sentry on the server side (SSR)
const sentryDsn = process.env.SENTRY_DSN;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: process.env.NODE_ENV || "production",
    release: process.env.APP_VERSION || "unknown",
    tracesSampleRate: 0.1,
  });
}

// Publish the per-request nonce store for getRouter() (router.tsx), which has no
// access to the Request. Must be set before the first request is handled.
const cspStore = new AsyncLocalStorage<CspRequestContext>();
globalThis.__hadhaCspStore = cspStore;

function withCsp(response: Response, nonce: string): Response {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/html")) return response;
  const csp = cspHeader(nonce);
  if (!csp) return response;
  // Responses from the handler can have immutable headers; copy before setting.
  const headers = new Headers(response.headers);
  headers.set(csp.name, csp.value);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

type ServerEntry = {
  fetch: (request: Request, env: unknown, ctx: unknown) => Promise<Response> | Response;
};

let serverEntryPromise: Promise<ServerEntry> | undefined;

async function getServerEntry(): Promise<ServerEntry> {
  if (!serverEntryPromise) {
    serverEntryPromise = import("@tanstack/react-start/server-entry").then(
      (m) => (m.default ?? m) as ServerEntry,
    );
  }
  return serverEntryPromise;
}

// h3 swallows in-handler throws into a normal 500 Response with body
// {"unhandled":true,"message":"HTTPError"} — try/catch alone never fires for those.
async function normalizeCatastrophicSsrResponse(response: Response): Promise<Response> {
  if (response.status < 500) return response;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return response;

  const body = await response.clone().text();
  if (!body.includes('"unhandled":true') || !body.includes('"message":"HTTPError"')) {
    return response;
  }

  console.error(consumeLastCapturedError() ?? new Error(`h3 swallowed SSR error: ${body}`));
  return new Response(renderErrorPage(), {
    status: 500,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

export default {
  async fetch(request: Request, env: unknown, ctx: unknown) {
    // robots.txt / sitemap.xml are not app routes; answer them before SSR.
    const seoResponse = await handleSeoRequest(request);
    if (seoResponse) return seoResponse;

    const nonce = generateNonce();
    try {
      const handler = await getServerEntry();
      const response = await cspStore.run({ nonce }, () => handler.fetch(request, env, ctx));
      return withCsp(await normalizeCatastrophicSsrResponse(response), nonce);
    } catch (error) {
      console.error(error);
      Sentry.captureException(error);
      return new Response(renderErrorPage(), {
        status: 500,
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }
  },
};
