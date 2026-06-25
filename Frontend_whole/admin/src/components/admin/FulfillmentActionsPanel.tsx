import { useState } from "react";
import { Loader2, Download, Send, CheckCircle, Truck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import type { OrderResponse } from "@/types/admin";
import {
  useConfirmPayment,
  useMarkPacking,
  useGenerateShippingLabel,
  useGeneratePackingSlip,
  useDispatchOrder,
  useMarkInTransit,
  useMarkDelivered,
} from "@/hooks/admin/useFulfillment";
import { DispatchModal } from "./DispatchModal";

interface FulfillmentActionsPanelProps {
  order: OrderResponse;
  orderId: string;
}

async function downloadFile(url: string, filename: string) {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error("Failed to download file");

    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  } catch (error) {
    toast.error("Failed to download file");
    console.error(error);
  }
}

export function FulfillmentActionsPanel({ order, orderId }: FulfillmentActionsPanelProps) {
  const [showDispatchModal, setShowDispatchModal] = useState(false);

  const confirmPaymentMutation = useConfirmPayment();
  const markPackingMutation = useMarkPacking();
  const generateLabelMutation = useGenerateShippingLabel();
  const generateSlipMutation = useGeneratePackingSlip();
  const dispatchMutation = useDispatchOrder();
  const markInTransitMutation = useMarkInTransit();
  const markDeliveredMutation = useMarkDelivered();

  const handleConfirmPayment = async () => {
    try {
      await confirmPaymentMutation.mutateAsync(orderId);
      toast.success("Payment confirmed");
    } catch (error) {
      toast.error("Failed to confirm payment");
    }
  };

  const handleMarkPacking = async () => {
    try {
      await markPackingMutation.mutateAsync(orderId);
      toast.success("Order marked for packing");
    } catch (error) {
      toast.error("Failed to mark order for packing");
    }
  };

  const handleDownloadLabel = async () => {
    try {
      const response = await generateLabelMutation.mutateAsync(orderId);
      await downloadFile(response.label_url, `shipping-label-${order.order_number}.pdf`);
      toast.success("Shipping label downloaded");
    } catch (error) {
      toast.error("Failed to generate shipping label");
    }
  };

  const handleDownloadSlip = async () => {
    try {
      const response = await generateSlipMutation.mutateAsync(orderId);
      await downloadFile(response.slip_url, `packing-slip-${order.order_number}.pdf`);
      toast.success("Packing slip downloaded");
    } catch (error) {
      toast.error("Failed to generate packing slip");
    }
  };

  const handleMarkInTransit = async () => {
    try {
      await markInTransitMutation.mutateAsync(orderId);
      toast.success("Order marked as in transit");
    } catch (error) {
      toast.error("Failed to mark order as in transit");
    }
  };

  const handleMarkDelivered = async () => {
    try {
      await markDeliveredMutation.mutateAsync(orderId);
      toast.success("Order marked as delivered");
    } catch (error) {
      toast.error("Failed to mark order as delivered");
    }
  };

  const canConfirmPayment = order.payment_status === "pending";
  const canMarkPacking = order.status === "confirmed" && order.fulfillment_status === "pending";
  const canGeneratePDF = [
    "packing",
    "label_generated",
    "dispatched",
    "in_transit",
    "delivered",
  ].includes(order.fulfillment_status);
  const canDispatch = ["packing", "label_generated"].includes(order.fulfillment_status);
  const canMarkInTransit = order.fulfillment_status === "dispatched";
  const canMarkDelivered = order.fulfillment_status === "in_transit";

  return (
    <>
      <div className="space-y-2">
        <h3 className="font-semibold text-sm text-foreground">Actions</h3>
        <div className="flex flex-col gap-2">
          {canConfirmPayment && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleConfirmPayment}
              disabled={confirmPaymentMutation.isPending}
              className="w-full justify-start"
            >
              {confirmPaymentMutation.isPending && (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              )}
              Confirm Payment
            </Button>
          )}

          {canMarkPacking && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleMarkPacking}
              disabled={markPackingMutation.isPending}
              className="w-full justify-start"
            >
              {markPackingMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Mark Packing
            </Button>
          )}

          {canGeneratePDF && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={handleDownloadLabel}
                disabled={generateLabelMutation.isPending}
                className="w-full justify-start"
              >
                {generateLabelMutation.isPending && (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                )}
                {!generateLabelMutation.isPending && <Download className="h-4 w-4 mr-2" />}
                Download Label
              </Button>

              <Button
                size="sm"
                variant="outline"
                onClick={handleDownloadSlip}
                disabled={generateSlipMutation.isPending}
                className="w-full justify-start"
              >
                {generateSlipMutation.isPending && (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                )}
                {!generateSlipMutation.isPending && <Download className="h-4 w-4 mr-2" />}
                Download Slip
              </Button>
            </>
          )}

          {canDispatch && (
            <Button
              size="sm"
              variant="default"
              onClick={() => setShowDispatchModal(true)}
              className="w-full justify-start"
            >
              <Send className="h-4 w-4 mr-2" />
              Dispatch Order
            </Button>
          )}

          {canMarkInTransit && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleMarkInTransit}
              disabled={markInTransitMutation.isPending}
              className="w-full justify-start"
            >
              {markInTransitMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <Truck className="h-4 w-4 mr-2" />
              Mark In Transit
            </Button>
          )}

          {canMarkDelivered && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleMarkDelivered}
              disabled={markDeliveredMutation.isPending}
              className="w-full justify-start"
            >
              {markDeliveredMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <CheckCircle className="h-4 w-4 mr-2" />
              Mark Delivered
            </Button>
          )}
        </div>
      </div>

      <DispatchModal
        orderId={orderId}
        open={showDispatchModal}
        onOpenChange={setShowDispatchModal}
        onSuccess={() => setShowDispatchModal(false)}
      />
    </>
  );
}
