import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { PaymentFailedOopsPage } from "@/components/site/OopsPage";

export const Route = createFileRoute("/checkout_/payment-failed")({
  head: () => ({ meta: [{ title: "Payment Failed · Hadha" }] }),
  component: PaymentFailedPage,
});

function PaymentFailedPage() {
  const navigate = useNavigate();
  return <PaymentFailedOopsPage onRetry={() => navigate({ to: "/checkout" })} />;
}
