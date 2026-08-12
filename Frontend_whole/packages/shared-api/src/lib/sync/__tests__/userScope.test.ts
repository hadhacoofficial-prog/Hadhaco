import { describe, expect, it, beforeEach, vi } from "vitest";

const { getUserId } = vi.hoisted(() => ({ getUserId: vi.fn() }));

vi.mock("../../supabase/session", () => ({ getUserId }));

import { isEventForCurrentUser } from "../userScope";

describe("isEventForCurrentUser", () => {
  beforeEach(() => {
    getUserId.mockReset();
    getUserId.mockResolvedValue("user-1");
  });

  it("treats an event with no user scope as always relevant", async () => {
    await expect(isEventForCurrentUser(undefined)).resolves.toBe(true);
    expect(getUserId).not.toHaveBeenCalled();
  });

  it("matches a single user id", async () => {
    await expect(isEventForCurrentUser("user-1")).resolves.toBe(true);
    await expect(isEventForCurrentUser("user-2")).resolves.toBe(false);
  });

  it("matches when a user id list contains the current user", async () => {
    await expect(isEventForCurrentUser(["user-2", "user-1"])).resolves.toBe(
      true,
    );
    await expect(isEventForCurrentUser(["user-2", "user-3"])).resolves.toBe(
      false,
    );
  });

  it("rejects an explicitly empty scope without reading the session", async () => {
    await expect(isEventForCurrentUser([])).resolves.toBe(false);
    await expect(isEventForCurrentUser("")).resolves.toBe(false);
    expect(getUserId).not.toHaveBeenCalled();
  });

  it("rejects a scoped event when signed out", async () => {
    getUserId.mockResolvedValue(null);
    await expect(isEventForCurrentUser("user-1")).resolves.toBe(false);
  });
});
