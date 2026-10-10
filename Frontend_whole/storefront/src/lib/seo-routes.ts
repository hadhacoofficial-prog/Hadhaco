/**
 * Crawler files served straight from the SSR entry (before the app router).
 *
 * Previously /robots.txt returned the SPA HTML shell with a 200 and
 * /sitemap.xml was a 404 on hadha.co (the sitemap only existed on the API
 * host), so search engines had nothing valid to read.
 */

export const SITE_URL = "https://hadha.co";

const DEFAULT_API_BASE = "https://api.hadha.co/api/v1";

export function robotsTxt(): string {
  return [
    "User-agent: *",
    "Allow: /",
    "Disallow: /cart",
    "Disallow: /checkout",
    "Disallow: /account",
    "Disallow: /wishlist",
    "Disallow: /search",
    "",
    `Sitemap: ${SITE_URL}/sitemap.xml`,
    "",
  ].join("\n");
}

function plain(status: number, body: string, extra: Record<string, string> = {}): Response {
  return new Response(body, {
    status,
    headers: { "content-type": "text/plain; charset=utf-8", ...extra },
  });
}

async function sitemapResponse(
  fetchImpl: typeof fetch,
  apiBase: string,
  method: string,
): Promise<Response> {
  try {
    const upstream = await fetchImpl(`${apiBase.replace(/\/$/, "")}/sitemap.xml`, {
      headers: { accept: "application/xml" },
      signal: AbortSignal.timeout(8000),
    });
    const xml = await upstream.text();
    // Guard against ever forwarding an error page or a corrupted/binary body.
    if (!upstream.ok || !xml.trimStart().startsWith("<?xml")) {
      return plain(503, "Sitemap temporarily unavailable", { "retry-after": "300" });
    }
    return new Response(method === "HEAD" ? null : xml, {
      status: 200,
      headers: {
        "content-type": "application/xml; charset=utf-8",
        "cache-control": "public, max-age=3600",
      },
    });
  } catch {
    return plain(503, "Sitemap temporarily unavailable", { "retry-after": "300" });
  }
}

/**
 * Returns a Response for /robots.txt and /sitemap.xml, or null so the caller
 * falls through to the normal app handler.
 */
export async function handleSeoRequest(
  request: Request,
  opts: { fetchImpl?: typeof fetch; apiBase?: string } = {},
): Promise<Response | null> {
  if (request.method !== "GET" && request.method !== "HEAD") return null;
  const { pathname } = new URL(request.url);

  if (pathname === "/robots.txt") {
    return plain(200, request.method === "HEAD" ? "" : robotsTxt(), {
      "cache-control": "public, max-age=3600",
    });
  }

  if (pathname === "/sitemap.xml") {
    return sitemapResponse(
      opts.fetchImpl ?? fetch,
      opts.apiBase ?? process.env.SERVER_API_BASE_URL ?? DEFAULT_API_BASE,
      request.method,
    );
  }

  return null;
}
