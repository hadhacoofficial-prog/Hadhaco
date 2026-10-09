import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/lib/api/client", () => ({ api: { get: vi.fn() } }));
vi.mock("@/providers/auth-context", () => ({
  useAuthContext: () => ({ isAuthenticated: true, initialized: true }),
}));

import { api } from "@/lib/api/client";
import { useActiveReservations } from "./useActiveReservations";

const mockedGet = api.get as unknown as ReturnType<typeof vi.fn>;

const reservation = (productId: string, variantId: string | null, quantity = 1) => ({
  reservation_number: `RES-${productId}-${variantId ?? "none"}`,
  product_id: productId,
  variant_id: variantId,
  product_name: "Silver Ring",
  variant_name: null,
  quantity,
  expires_at: new Date(Date.now() + 120_000).toISOString(),
});

async function setup(items: ReturnType<typeof reservation>[]) {
  mockedGet.mockResolvedValue({ items });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(() => useActiveReservations(), { wrapper });
  await waitFor(() => expect(hook.result.current.items.length).toBe(items.length));
  return hook.result;
}

describe("useActiveReservations — variant matching", () => {
  beforeEach(() => mockedGet.mockReset());

  // The server always reserves against a concrete variant (add-to-cart resolves
  // the product's default variant), but a cart line / product card added
  // without picking a variant has no variantId. Those lookups must still find
  // the shopper's own reservation, or their held item reads as "Sold Out".
  it("finds a variant reservation when the caller has no variant (card / unpicked cart line)", async () => {
    const result = await setup([reservation("p1", "v-default", 1)]);
    expect(result.current.isReserved("p1")).toBe(true);
    expect(result.current.isReserved("p1", null)).toBe(true);
    expect(result.current.getReservation("p1")?.variant_id).toBe("v-default");
    expect(result.current.getReservation("p1", undefined)?.quantity).toBe(1);
  });

  it("still matches an exact product + variant", async () => {
    const result = await setup([reservation("p1", "v1", 2)]);
    expect(result.current.isReserved("p1", "v1")).toBe(true);
    expect(result.current.getReservation("p1", "v1")?.quantity).toBe(2);
  });

  it("does not credit a reservation held on a different variant when a variant is given", async () => {
    const result = await setup([reservation("p1", "v1")]);
    expect(result.current.isReserved("p1", "v2")).toBe(false);
    expect(result.current.getReservation("p1", "v2")).toBeUndefined();
  });

  it("prefers the exact variant over the product-level fallback", async () => {
    const result = await setup([reservation("p1", "v1", 1), reservation("p1", "v2", 3)]);
    expect(result.current.getReservation("p1", "v2")?.quantity).toBe(3);
  });

  it("does not match another product", async () => {
    const result = await setup([reservation("p1", "v1")]);
    expect(result.current.isReserved("p2")).toBe(false);
    expect(result.current.getReservation("p2")).toBeUndefined();
  });
});
