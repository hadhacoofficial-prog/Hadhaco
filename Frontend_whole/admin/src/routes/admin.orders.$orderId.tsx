import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { OrderTimelineComponent } from "@/components/admin/OrderTimelineComponent";
import { FulfillmentActionsPanel } from "@/components/admin/FulfillmentActionsPanel";
import { useFulfillmentTimeline } from "@/hooks/admin/useFulfillment";
import type { OrderResponse, OrderItem } from "@/types/admin";
import { formatCurrency, formatDate } from "@/lib/format";

export const Route = createFileRoute("/admin/orders/$orderId")({
  component: OrderDetailPage,
});

function OrderDetailPage() {
  const { orderId } = Route.useParams();
  const navigate = Route.useNavigate();

  const orderQuery = useQuery({
    queryKey: queryKeys.admin.order(orderId),
    queryFn: () => api.get<OrderResponse>(`/admin/orders/${orderId}`),
  });

  const timelineQuery = useFulfillmentTimeline(orderId);

  const order = orderQuery.data;
  const timeline = timelineQuery.data?.timeline;

  if (orderQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-40" />
        <div className="grid grid-cols-3 gap-4">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </div>
    );
  }

  if (!order) {
    return <div className="text-center py-8 text-muted-foreground">Order not found</div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate({ to: "/admin/orders" })}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">Order {order.order_number}</h1>
          <div className="flex gap-2 mt-2">
            <Badge variant={order.status === "confirmed" ? "default" : "secondary"}>
              {order.status}
            </Badge>
            <Badge variant={order.payment_status === "paid" ? "default" : "secondary"}>
              {order.payment_status}
            </Badge>
            <Badge variant="outline">{order.fulfillment_status}</Badge>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="col-span-2 space-y-6">
          {/* Order Information */}
          <Card>
            <CardHeader>
              <CardTitle>Order Information</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Order Number</p>
                <p className="font-semibold">{order.order_number}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Order Date</p>
                <p className="font-semibold">{formatDate(order.created_at)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Payment Method</p>
                <p className="font-semibold capitalize">{order.payment_method || "—"}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Payment Status</p>
                <p className="font-semibold capitalize">{order.payment_status}</p>
              </div>
              {order.razorpay_payment_id && (
                <div>
                  <p className="text-sm text-muted-foreground">Razorpay Payment ID</p>
                  <p className="font-semibold text-xs">{order.razorpay_payment_id}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Customer Details */}
          <Card>
            <CardHeader>
              <CardTitle>Customer Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <p className="text-sm text-muted-foreground">Name</p>
                <p className="font-semibold">{order.shipping_full_name}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Phone</p>
                <p className="font-semibold">{order.shipping_phone || "—"}</p>
              </div>
              {order.shipping_alternate_phone && (
                <div>
                  <p className="text-sm text-muted-foreground">Alt Phone</p>
                  <p className="font-semibold">{order.shipping_alternate_phone}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Shipping Address */}
          <Card>
            <CardHeader>
              <CardTitle>Shipping Address</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-sm space-y-1">
                <p className="font-semibold">{order.shipping_full_name}</p>
                <p>{order.shipping_line1}</p>
                {order.shipping_line2 && <p>{order.shipping_line2}</p>}
                {order.shipping_landmark && (
                  <p className="text-muted-foreground">Landmark: {order.shipping_landmark}</p>
                )}
                <p>
                  {order.shipping_city}, {order.shipping_state} {order.shipping_postal}
                </p>
                {order.shipping_phone && <p>Phone: {order.shipping_phone}</p>}
                {order.shipping_alternate_phone && (
                  <p>Alt Phone: {order.shipping_alternate_phone}</p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Order Items */}
          <Card>
            <CardHeader>
              <CardTitle>Ordered Products</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="divide-y">
                {order.items.map((item: OrderItem) => (
                  <div key={item.id} className="py-3 flex justify-between">
                    <div className="flex-1">
                      <p className="font-semibold text-sm">{item.product_name}</p>
                      <p className="text-xs text-muted-foreground">
                        SKU: {item.product_sku} {item.variant_name && `• ${item.variant_name}`}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold">
                        {formatCurrency(item.unit_price)} × {item.quantity}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatCurrency(item.line_total)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Price Summary */}
          <Card>
            <CardHeader>
              <CardTitle>Price Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Subtotal</span>
                <span>{formatCurrency(order.subtotal)}</span>
              </div>
              {order.tax_amount > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Tax</span>
                  <span>{formatCurrency(order.tax_amount)}</span>
                </div>
              )}
              {order.shipping_charge > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Shipping</span>
                  <span>{formatCurrency(order.shipping_charge)}</span>
                </div>
              )}
              {order.discount > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Discount</span>
                  <span>-{formatCurrency(order.discount)}</span>
                </div>
              )}
              <div className="flex justify-between text-base font-semibold pt-2 border-t">
                <span>Grand Total</span>
                <span>{formatCurrency(order.total)}</span>
              </div>
              {order.complimentary_gift && (
                <div className="flex items-center gap-2 pt-3 border-t text-sm">
                  <span className="text-lg">
                    {order.complimentary_gift === "Traditional Sweet" ? "🍬" : "🌶️"}
                  </span>
                  <span className="text-muted-foreground">Complimentary Gift</span>
                  <span className="font-medium ml-auto">{order.complimentary_gift}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <OrderTimelineComponent order={order} timeline={timeline} />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <FulfillmentActionsPanel order={order} orderId={orderId} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
