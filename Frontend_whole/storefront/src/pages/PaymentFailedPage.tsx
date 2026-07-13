import { useNavigate } from "@tanstack/react-router";
import { PaymentFailedOopsPage } from "@/components/site/OopsPage";

export default function PaymentFailedPage() {
  const navigate = useNavigate();
  return <PaymentFailedOopsPage onRetry={() => navigate({ to: "/checkout" })} />;
}
