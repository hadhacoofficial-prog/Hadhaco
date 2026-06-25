import { formatDistanceToNow } from "date-fns";
import { Check, Circle } from "lucide-react";
import type { OrderResponse } from "@/types/admin";
import type { FulfillmentTimelineEntry } from "@/types/fulfillment";

interface OrderTimelineComponentProps {
  order?: OrderResponse;
  timeline?: FulfillmentTimelineEntry[];
}

const TIMELINE_STEPS = [
  { key: "placed", label: "Order Placed", color: "bg-green-500" },
  { key: "payment", label: "Payment Received", color: "bg-green-500" },
  { key: "confirmed", label: "Confirmed", color: "bg-green-500" },
  { key: "packing", label: "Packing", color: "bg-blue-500" },
  { key: "label", label: "Shipment Label", color: "bg-blue-500" },
  { key: "dispatched", label: "Dispatched", color: "bg-blue-500" },
  { key: "in_transit", label: "In Transit", color: "bg-amber-500" },
  { key: "delivered", label: "Delivered", color: "bg-green-500" },
];

export function OrderTimelineComponent({ order, timeline }: OrderTimelineComponentProps) {
  if (!order) return null;

  const getStepStatus = (stepKey: string): "completed" | "current" | "pending" => {
    switch (stepKey) {
      case "placed":
        return "completed";
      case "payment":
        return order.payment_status === "paid" ? "completed" : "pending";
      case "confirmed":
        return order.status === "confirmed" ? "completed" : "pending";
      case "packing":
        return ["packing", "label_generated", "dispatched", "in_transit", "delivered"].includes(
          order.fulfillment_status,
        )
          ? "completed"
          : "pending";
      case "label":
        return ["label_generated", "dispatched", "in_transit", "delivered"].includes(
          order.fulfillment_status,
        )
          ? "completed"
          : "pending";
      case "dispatched":
        return ["dispatched", "in_transit", "delivered"].includes(order.fulfillment_status)
          ? "completed"
          : "pending";
      case "in_transit":
        return ["in_transit", "delivered"].includes(order.fulfillment_status)
          ? "completed"
          : "pending";
      case "delivered":
        return order.fulfillment_status === "delivered" ? "completed" : "pending";
      default:
        return "pending";
    }
  };

  const getStepTimestamp = (stepKey: string): string | null => {
    if (!timeline || timeline.length === 0) return null;

    const actionMap: Record<string, string> = {
      placed: "order_placed",
      payment: "confirm_payment",
      confirmed: "confirm_payment",
      packing: "mark_packing",
      label: "generate_label",
      dispatched: "dispatch",
      in_transit: "mark_in_transit",
      delivered: "mark_delivered",
    };

    const action = actionMap[stepKey];
    const entry = timeline.find((e) => e.action === action);
    return entry?.created_at || null;
  };

  return (
    <div className="space-y-4">
      <h3 className="font-semibold text-sm text-foreground">Order Timeline</h3>
      <div className="relative space-y-4">
        {TIMELINE_STEPS.map((step, index) => {
          const status = getStepStatus(step.key);
          const timestamp = getStepTimestamp(step.key);

          return (
            <div key={step.key} className="flex gap-3">
              {/* Timeline dot */}
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full border-2 border-border ${
                    status === "completed" ? step.color : "bg-muted"
                  }`}
                >
                  {status === "completed" ? (
                    <Check className="h-4 w-4 text-white" />
                  ) : (
                    <Circle className={`h-3 w-3 ${status === "current" ? "fill-current" : ""}`} />
                  )}
                </div>
                {index < TIMELINE_STEPS.length - 1 && (
                  <div
                    className={`h-8 w-0.5 ${status === "completed" ? step.color : "bg-muted"}`}
                  />
                )}
              </div>

              {/* Step content */}
              <div className="flex-1 pt-1 pb-4">
                <p
                  className={`text-sm font-medium ${
                    status === "completed" ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  {step.label}
                </p>
                {timestamp && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {formatDistanceToNow(new Date(timestamp), { addSuffix: true })}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
