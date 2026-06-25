import { createFileRoute } from "@tanstack/react-router";
import { StockChangedOopsPage } from "@/components/site/OopsPage";

export const Route = createFileRoute("/checkout_/stock-changed")({
  head: () => ({ meta: [{ title: "Stock Changed · Hadha" }] }),
  component: StockChangedOopsPage,
});
