import { describe, expect, it, vi } from "vitest";
import { handleSeoRequest, robotsTxt } from "../seo-routes";

const req = (path: string, method = "GET") => new Request(`https://hadha.co${path}`, { method });

describe("handleSeoRequest", () => {
  it("serves a real robots.txt with the sitemap line", async () => {
    const res = await handleSeoRequest(req("/robots.txt"));
    expect(res?.status).toBe(200);
    expect(res?.headers.get("content-type")).toContain("text/plain");
    const body = await res!.text();
    expect(body).toBe(robotsTxt());
    expect(body).toContain("Sitemap: https://hadha.co/sitemap.xml");
    expect(body).toContain("Disallow: /checkout");
    expect(body.toLowerCase()).not.toContain("<html");
  });

  it("proxies a valid sitemap from the API", async () => {
    const xml = '<?xml version="1.0"?><urlset></urlset>';
    const fetchImpl = vi.fn().mockResolvedValue(new Response(xml, { status: 200 }));

    const res = await handleSeoRequest(req("/sitemap.xml"), {
      fetchImpl: fetchImpl as unknown as typeof fetch,
      apiBase: "http://hadha-backend:8000/api/v1",
    });

    expect(fetchImpl.mock.calls[0][0]).toBe("http://hadha-backend:8000/api/v1/sitemap.xml");
    expect(res?.status).toBe(200);
    expect(res?.headers.get("content-type")).toContain("application/xml");
    expect(await res!.text()).toBe(xml);
  });

  it("never forwards a corrupted (compressed/binary) body", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response("\u0001x\u009cÝ]", { status: 200 }));
    const res = await handleSeoRequest(req("/sitemap.xml"), {
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(res?.status).toBe(503);
    expect(res?.headers.get("retry-after")).toBe("300");
  });

  it("returns 503 when the API call fails", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error("boom"));
    const res = await handleSeoRequest(req("/sitemap.xml"), {
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(res?.status).toBe(503);
  });

  it("ignores everything else and non-GET methods", async () => {
    expect(await handleSeoRequest(req("/products"))).toBeNull();
    expect(await handleSeoRequest(req("/robots.txt", "POST"))).toBeNull();
  });
});
