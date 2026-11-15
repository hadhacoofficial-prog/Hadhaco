import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../config/env", () => ({
  ENV: {
    apiBaseUrl: "https://api.example.com/v1",
    isDev: false,
    isProd: false,
  },
  hasApi: () => true,
}));

import { api } from "../../api/client";
import { csrfHeader } from "../../api/interceptors";
import { signOut, signInWithPassword } from "../actions";
import { ensureCsrfToken, refreshSession } from "../refresh";
import { getSession } from "../session";
import {
  __resetAuthStore,
  getCachedSession,
  getCsrfToken,
  hasSessionHint,
  setSession,
} from "../store";
import type { AuthSession } from "../types";

const session: AuthSession = {
  user: {
    id: "u1",
    email: "a@b.co",
    full_name: "A B",
    role: "customer",
    is_verified: true,
    created_at: null,
  },
  csrfToken: "csrf-1",
  hasPassword: true,
};

const payload = (csrf = "csrf-2") => ({
  data: {
    user: session.user,
    csrf_token: csrf,
    expires_in: 900,
    has_password: true,
  },
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn();

beforeEach(() => {
  __resetAuthStore();
  localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("csrfHeader", () => {
  it("adds nothing for safe methods", () => {
    setSession(session);
    expect(csrfHeader("GET")).toEqual({});
    expect(csrfHeader("HEAD")).toEqual({});
  });

  it("adds the token to writes once signed in", () => {
    setSession(session);
    for (const m of ["POST", "PATCH", "PUT", "DELETE"]) {
      expect(csrfHeader(m)).toEqual({ "X-CSRF-Token": "csrf-1" });
    }
  });

  it("adds nothing when signed out", () => {
    expect(csrfHeader("POST")).toEqual({});
  });
});

describe("session store hint", () => {
  it("is set by a session and cleared by sign-out", () => {
    expect(hasSessionHint()).toBe(false);
    setSession(session);
    expect(hasSessionHint()).toBe(true);
    setSession(null);
    expect(hasSessionHint()).toBe(false);
  });
});

describe("getSession", () => {
  it("makes no request for an anonymous browser", async () => {
    await expect(getSession()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("loads once and caches when the browser has a session hint", async () => {
    localStorage.setItem("hadha:session-hint", "1");
    fetchMock.mockResolvedValue(json(payload("c")));
    const first = await getSession();
    const second = await getSession();
    expect(first?.csrfToken).toBe("c");
    expect(second).toBe(first);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      credentials: "include",
    });
  });

  it("clears the hint when the backend says signed out", async () => {
    localStorage.setItem("hadha:session-hint", "1");
    // /auth/session -> 401, then the automatic refresh -> 401
    fetchMock.mockResolvedValue(
      json({ success: false, code: "ERROR", message: "x" }, 401),
    );
    await expect(getSession()).resolves.toBeNull();
    expect(localStorage.getItem("hadha:session-hint")).toBeNull();
  });
});

describe("refreshSession", () => {
  it("shares one request between concurrent callers (rotating tokens)", async () => {
    setSession(session);
    fetchMock.mockResolvedValue(json(payload("fresh")));
    const [a, b] = await Promise.all([refreshSession(), refreshSession()]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
    expect(getCsrfToken()).toBe("fresh");
  });

  it("signs out locally when the refresh token is rejected", async () => {
    setSession(session);
    fetchMock.mockResolvedValue(json({ detail: "no" }, 401));
    await expect(refreshSession()).resolves.toBeNull();
    expect(getCachedSession()).toBeNull();
  });

  it("keeps the session on a network failure", async () => {
    setSession(session);
    fetchMock.mockRejectedValue(new TypeError("offline"));
    await expect(refreshSession()).resolves.toBeNull();
    expect(getCachedSession()).toBe(session);
  });

  it("keeps the session when the token was rotated away by another tab", async () => {
    setSession(session);
    fetchMock.mockResolvedValue(
      json({ code: "SESSION_UNKNOWN", message: "x" }, 401),
    );
    await expect(refreshSession()).resolves.toBeNull();
    expect(getCachedSession()).toBe(session);
  });

  it("does not treat a 403 (e.g. CSRF/origin) as signed out", async () => {
    setSession(session);
    fetchMock.mockResolvedValue(
      json({ code: "CSRF_FAILED", message: "x" }, 403),
    );
    await expect(refreshSession()).resolves.toBeNull();
    expect(getCachedSession()).toBe(session);
  });

  it("does nothing for a browser that never signed in", async () => {
    await expect(refreshSession()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("api client session handling", () => {
  it("sends credentials and the CSRF header on writes", async () => {
    setSession(session);
    fetchMock.mockResolvedValue(
      json({ success: true, code: "OK", message: "", data: { ok: 1 } }),
    );
    await api.post("/orders", { body: { a: 1 } });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe(
      "csrf-1",
    );
    expect(
      (init.headers as Record<string, string>).Authorization,
    ).toBeUndefined();
  });

  it("refreshes once on 401 and retries with the new CSRF token", async () => {
    setSession(session);
    fetchMock
      .mockResolvedValueOnce(
        json({ success: false, code: "ERROR", message: "expired" }, 401),
      )
      .mockResolvedValueOnce(json(payload("rotated"))) // POST /auth/refresh
      .mockResolvedValueOnce(
        json({ success: true, code: "OK", message: "", data: { ok: 1 } }),
      );
    const result = await api.post<{ ok: number }>("/orders", { body: {} });
    expect(result).toEqual({ ok: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1][0])).toContain("/auth/refresh");
    const retryHeaders = fetchMock.mock.calls[2][1].headers as Record<
      string,
      string
    >;
    expect(retryHeaders["X-CSRF-Token"]).toBe("rotated");
  });

  it("does not loop when the retry is also 401", async () => {
    setSession(session);
    fetchMock
      .mockResolvedValueOnce(
        json({ success: false, code: "ERROR", message: "x" }, 401),
      )
      .mockResolvedValueOnce(json(payload("r")))
      .mockResolvedValueOnce(
        json({ success: false, code: "ERROR", message: "x" }, 401),
      );
    await expect(api.get("/me")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("skipAuth requests neither refresh nor carry the CSRF header", async () => {
    setSession(session);
    fetchMock.mockResolvedValue(
      json({ success: false, code: "X", message: "nope" }, 401),
    );
    await expect(
      api.post("/auth/login", { body: {}, skipAuth: true }),
    ).rejects.toMatchObject({
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(
      (fetchMock.mock.calls[0][1].headers as Record<string, string>)[
        "X-CSRF-Token"
      ],
    ).toBeUndefined();
  });
});

describe("auth actions", () => {
  it("signInWithPassword stores the session returned by the backend", async () => {
    fetchMock.mockResolvedValue(json(payload("login-csrf")));
    const s = await signInWithPassword("a@b.co", "pw");
    expect(s.csrfToken).toBe("login-csrf");
    expect(getCachedSession()).toEqual(s);
    expect(hasSessionHint()).toBe(true);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({
      email: "a@b.co",
      password: "pw",
    });
  });

  it("signOut treats 401 (cookies already gone) as success", async () => {
    setSession(session);
    fetchMock.mockResolvedValue(json({ detail: "Not authenticated" }, 401));
    await expect(signOut()).resolves.toBeUndefined();
    expect(getCachedSession()).toBeNull();
  });

  it("signOut clears local state even when the request fails", async () => {
    setSession(session);
    fetchMock.mockRejectedValue(new TypeError("offline"));
    await expect(signOut()).rejects.toBeDefined();
    expect(getCachedSession()).toBeNull();
  });
});

describe("CSRF token availability", () => {
  it("loads the token before the first write after a reload", async () => {
    localStorage.setItem("hadha:session-hint", "1");
    fetchMock
      .mockResolvedValueOnce(json(payload("loaded"))) // GET /auth/session
      .mockResolvedValueOnce(
        json({ success: true, code: "OK", message: "", data: { ok: 1 } }),
      );
    await api.post("/cart/items", { body: {} });
    expect(String(fetchMock.mock.calls[0][0])).toContain("/auth/session");
    const headers = fetchMock.mock.calls[1][1].headers as Record<
      string,
      string
    >;
    expect(headers["X-CSRF-Token"]).toBe("loaded");
  });

  it("does not hit the backend for an anonymous browser", async () => {
    await ensureCsrfToken();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("re-reads the token and retries once on 403 CSRF_FAILED", async () => {
    setSession(session);
    fetchMock
      .mockResolvedValueOnce(
        json({ success: false, code: "CSRF_FAILED", message: "x" }, 403),
      )
      .mockResolvedValueOnce(json(payload("fresh"))) // GET /auth/session
      .mockResolvedValueOnce(
        json({ success: true, code: "OK", message: "", data: { ok: 1 } }),
      );
    await expect(api.post("/orders", { body: {} })).resolves.toEqual({ ok: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const retryHeaders = fetchMock.mock.calls[2][1].headers as Record<
      string,
      string
    >;
    expect(retryHeaders["X-CSRF-Token"]).toBe("fresh");
  });

  it("does not retry other 403s", async () => {
    setSession(session);
    fetchMock.mockResolvedValue(
      json({ success: false, code: "FORBIDDEN", message: "x" }, 403),
    );
    await expect(api.post("/orders", { body: {} })).rejects.toMatchObject({
      status: 403,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
