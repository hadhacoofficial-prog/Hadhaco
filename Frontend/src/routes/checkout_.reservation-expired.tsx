import { createFileRoute } from "@tanstack/react-router";
import { ReservationExpiredOopsPage } from "@/components/site/OopsPage";

export const Route = createFileRoute("/checkout_/reservation-expired")({
  head: () => ({ meta: [{ title: "Reservation Expired · Hadha" }] }),
  component: ReservationExpiredOopsPage,
});
