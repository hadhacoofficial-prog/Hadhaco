import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  useReservationStore,
  RESERVATION_TTL_MS,
  RESERVATION_URGENT_THRESHOLD_S,
} from "@/stores/reservation";

describe("ReservationStore", () => {
  beforeEach(() => {
    useReservationStore.getState().clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("createReservation", () => {
    it("creates a reservation with correct expiry", () => {
      const now = Date.now();
      vi.setSystemTime(now);

      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 2,
      });

      const entry = useReservationStore.getState().reservation;
      expect(entry).not.toBeNull();
      expect(entry?.reservationId).toBe("r1");
      expect(entry?.productId).toBe("p1");
      expect(entry?.quantity).toBe(2);
      expect(entry?.expiresAt).toBe(now + RESERVATION_TTL_MS);
      expect(entry?.status).toBe("active");
      expect(entry?.isOwn).toBe(true);
    });

    it("starts countdown timer", () => {
      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      // Timer should be running
      expect(useReservationStore.getState()._timerId).not.toBeNull();
    });

    it("replaces existing reservation when creating new one", () => {
      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      useReservationStore.getState().createReservation({
        reservationId: "r2",
        ownerUserId: "u1",
        productId: "p2",
        variantId: "v1",
        quantity: 3,
      });

      const entry = useReservationStore.getState().reservation;
      expect(entry?.reservationId).toBe("r2");
      expect(entry?.productId).toBe("p2");
    });
  });

  describe("tick", () => {
    it("decrements remaining seconds", () => {
      const now = Date.now();
      vi.setSystemTime(now);

      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      const initialSeconds = useReservationStore.getState().reservation?.remainingSeconds;

      // Advance 1 second
      vi.setSystemTime(now + 1_000);
      useReservationStore.getState()._tick();

      const afterTick = useReservationStore.getState().reservation?.remainingSeconds;
      expect(afterTick).toBe(initialSeconds! - 1);
    });

    it("marks as expired when remaining reaches 0", () => {
      const now = Date.now();
      vi.setSystemTime(now);

      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      // Fast-forward to expiry
      vi.setSystemTime(now + RESERVATION_TTL_MS + 1_000);
      useReservationStore.getState()._tick();

      const entry = useReservationStore.getState().reservation;
      expect(entry?.status).toBe("expired");
      expect(entry?.remainingSeconds).toBe(0);

      // Timer should be stopped
      expect(useReservationStore.getState()._timerId).toBeNull();
    });

    it("marks as expiring in last 60 seconds", () => {
      const now = Date.now();
      vi.setSystemTime(now);

      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      // Fast-forward to 59 seconds before expiry
      vi.setSystemTime(now + RESERVATION_TTL_MS - 59_000);
      useReservationStore.getState()._tick();

      const entry = useReservationStore.getState().reservation;
      expect(entry?.status).toBe("expiring");
    });
  });

  describe("markConverted", () => {
    it("sets status to converted and stops timer", () => {
      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      useReservationStore.getState().markConverted();

      const entry = useReservationStore.getState().reservation;
      expect(entry?.status).toBe("converted");
      expect(entry?.remainingSeconds).toBe(0);
      expect(useReservationStore.getState()._timerId).toBeNull();
    });
  });

  describe("expire", () => {
    it("sets status to expired and stops timer", () => {
      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      useReservationStore.getState().expire();

      const entry = useReservationStore.getState().reservation;
      expect(entry?.status).toBe("expired");
      expect(entry?.remainingSeconds).toBe(0);
      expect(useReservationStore.getState()._timerId).toBeNull();
    });
  });

  describe("clear", () => {
    it("removes reservation and stops timer", () => {
      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      useReservationStore.getState().clear();

      expect(useReservationStore.getState().reservation).toBeNull();
      expect(useReservationStore.getState()._timerId).toBeNull();
    });
  });

  describe("selectors", () => {
    it("selectCountdown returns MM:SS format", () => {
      const now = Date.now();
      vi.setSystemTime(now);

      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      const state = useReservationStore.getState();
      const countdown = selectCountdown()(state);
      expect(countdown).toMatch(/^\d{2}:\d{2}$/);
    });

    it("selectCountdown returns null when no reservation", () => {
      const state = useReservationStore.getState();
      expect(selectCountdown()(state)).toBeNull();
    });

    it("selectCanCheckout returns true with active reservation", () => {
      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });

      const state = useReservationStore.getState();
      expect(selectCanCheckout()(state)).toBe(true);
    });

    it("selectCanCheckout returns false with expired reservation", () => {
      useReservationStore.getState().createReservation({
        reservationId: "r1",
        ownerUserId: "u1",
        productId: "p1",
        variantId: null,
        quantity: 1,
      });
      useReservationStore.getState().expire();

      const state = useReservationStore.getState();
      expect(selectCanCheckout()(state)).toBe(false);
    });

    it("selectCanCheckout returns true with no reservation", () => {
      const state = useReservationStore.getState();
      expect(selectCanCheckout()(state)).toBe(true);
    });
  });
});

import { selectCountdown, selectCanCheckout } from "@/stores/reservation";
