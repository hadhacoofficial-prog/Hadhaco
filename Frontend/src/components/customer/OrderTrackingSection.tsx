import { ExternalLink, Copy, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { SHIPPING_PROVIDER_LABELS, SHIPPING_PROVIDER_URLS } from "@/types/fulfillment";
import type { ShippingProvider } from "@/types/fulfillment";
import { formatDate } from "@/lib/format";

interface TrackableOrder {
  fulfillment_status: string;
  tracking_number: string | null;
  shipping_provider: string | null;
  dispatched_at: string | null;
  estimated_delivery: string | null;
}

interface OrderTrackingSectionProps {
  order: TrackableOrder;
}

const INDIA_POST_HOMEPAGE = "https://www.indiapost.gov.in/";

export function OrderTrackingSection({ order }: OrderTrackingSectionProps) {
  const [copied, setCopied] = useState(false);
  const [showIndiaPostModal, setShowIndiaPostModal] = useState(false);
  const [modalCopied, setModalCopied] = useState(false);

  if (!order.shipping_provider || !order.tracking_number) {
    return null;
  }

  const provider = order.shipping_provider as ShippingProvider;
  const providerLabel = SHIPPING_PROVIDER_LABELS[provider] ?? order.shipping_provider;
  const isIndiaPost = order.shipping_provider === "india_post";
  const trackingUrl = isIndiaPost ? "" : (SHIPPING_PROVIDER_URLS[provider] ?? "");

  const handleCopyTracking = () => {
    if (!order.tracking_number) return;
    navigator.clipboard.writeText(order.tracking_number);
    setCopied(true);
    toast.success("Tracking number copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleModalCopy = () => {
    if (!order.tracking_number) return;
    navigator.clipboard.writeText(order.tracking_number);
    setModalCopied(true);
    toast.success("Tracking number copied");
    setTimeout(() => setModalCopied(false), 2000);
  };

  const handleTrackShipment = () => {
    if (isIndiaPost) {
      setShowIndiaPostModal(true);
      return;
    }
    if (!trackingUrl) {
      toast.info(
        `Please visit the ${providerLabel} website and enter tracking number: ${order.tracking_number}`,
      );
      return;
    }
    window.open(`${trackingUrl}?reference=${order.tracking_number}`, "_blank");
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-500" />
            Shipment Information
          </CardTitle>
          <CardDescription>Your order is on its way</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm text-muted-foreground mb-2">Shipment Status</p>
            <Badge variant="default" className="capitalize">
              {order.fulfillment_status === "dispatched" && "Dispatched"}
              {order.fulfillment_status === "in_transit" && "In Transit"}
              {order.fulfillment_status === "delivered" && "Delivered"}
            </Badge>
          </div>

          <div>
            <p className="text-sm text-muted-foreground">Carrier</p>
            <p className="font-semibold">{providerLabel}</p>
          </div>

          <div>
            <p className="text-sm text-muted-foreground mb-2">Tracking Number</p>
            <div className="flex gap-2">
              <code className="flex-1 bg-muted px-3 py-2 rounded font-mono text-sm">
                {order.tracking_number}
              </code>
              <Button size="sm" variant="ghost" onClick={handleCopyTracking} className="h-auto">
                <Copy className={`h-4 w-4 ${copied ? "text-green-500" : ""}`} />
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {order.dispatched_at && (
              <div>
                <p className="text-sm text-muted-foreground">Dispatch Date</p>
                <p className="font-semibold text-sm">{formatDate(order.dispatched_at)}</p>
              </div>
            )}
            {order.estimated_delivery && (
              <div>
                <p className="text-sm text-muted-foreground">Expected Delivery</p>
                <p className="font-semibold text-sm">{formatDate(order.estimated_delivery)}</p>
              </div>
            )}
          </div>

          <Button onClick={handleTrackShipment} className="w-full gap-2">
            {isIndiaPost ? "Track on India Post" : "Track Shipment"}
            <ExternalLink className="h-4 w-4" />
          </Button>

          {!isIndiaPost && !trackingUrl && (
            <p className="text-xs text-muted-foreground">
              Please visit the {providerLabel} website and enter the tracking number to track your
              shipment.
            </p>
          )}
        </CardContent>
      </Card>

      <Dialog open={showIndiaPostModal} onOpenChange={setShowIndiaPostModal}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Track your shipment on India Post</DialogTitle>
            <DialogDescription>
              India Post requires you to enter your tracking number and complete a CAPTCHA before
              viewing shipment details.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground mb-2">Tracking Number</p>
              <div className="flex gap-2">
                <code className="flex-1 bg-muted px-3 py-2 rounded font-mono text-sm break-all">
                  {order.tracking_number}
                </code>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleModalCopy}
                  className="h-auto shrink-0"
                >
                  <Copy className={`h-4 w-4 ${modalCopied ? "text-green-500" : ""}`} />
                </Button>
              </div>
            </div>

            <div className="flex flex-col gap-2 pt-2">
              <Button onClick={handleModalCopy} variant="outline" className="w-full gap-2">
                <Copy className="h-4 w-4" />
                {modalCopied ? "Copied!" : "Copy Tracking Number"}
              </Button>
              <Button
                onClick={() => {
                  window.open(INDIA_POST_HOMEPAGE, "_blank");
                  setShowIndiaPostModal(false);
                }}
                className="w-full gap-2"
              >
                <ExternalLink className="h-4 w-4" />
                Open India Post Website
              </Button>
              <Button
                variant="ghost"
                onClick={() => setShowIndiaPostModal(false)}
                className="w-full"
              >
                Close
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
