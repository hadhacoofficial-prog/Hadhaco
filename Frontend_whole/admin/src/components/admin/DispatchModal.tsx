import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDispatchOrder } from "@/hooks/admin/useFulfillment";
import type { DispatchOrderPayload, ShippingProvider } from "@/types/fulfillment";
import { SHIPPING_PROVIDER_LABELS } from "@/types/fulfillment";

const SHIPPING_PROVIDERS: ShippingProvider[] = [
  "india_post",
  "dtdc",
  "delhivery",
  "blue_dart",
  "xpressbees",
  "shadowfax",
  "ekart",
  "other",
];

interface DispatchModalProps {
  orderId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

export function DispatchModal({ orderId, open, onOpenChange, onSuccess }: DispatchModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const dispatchMutation = useDispatchOrder();

  const form = useForm<DispatchOrderPayload>({
    defaultValues: {
      shipping_provider: "india_post",
      tracking_number: "",
      dispatch_date: new Date().toISOString().split("T")[0],
      expected_delivery_date: undefined,
      dispatch_notes: "",
    },
  });

  const onSubmit = async (data: DispatchOrderPayload) => {
    if (!data.tracking_number.trim()) {
      form.setError("tracking_number", { message: "Tracking number is required" });
      return;
    }

    setIsSubmitting(true);
    try {
      await dispatchMutation.mutateAsync({
        orderId,
        payload: data,
      });
      toast.success(`Order dispatched via ${SHIPPING_PROVIDER_LABELS[data.shipping_provider]}`);
      form.reset();
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      toast.error("Failed to dispatch order");
      console.error(error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Dispatch Order</DialogTitle>
          <DialogDescription>Enter dispatch details and tracking information</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="shipping_provider"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Shipping Provider</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {SHIPPING_PROVIDERS.map((provider) => (
                        <SelectItem key={provider} value={provider}>
                          {SHIPPING_PROVIDER_LABELS[provider]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="tracking_number"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Tracking Number / AWB</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g., AWB123456789IN" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="dispatch_date"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Dispatch Date</FormLabel>
                  <FormControl>
                    <Input type="date" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="expected_delivery_date"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Expected Delivery Date (Optional)</FormLabel>
                  <FormControl>
                    <Input type="date" {...field} value={field.value || ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="dispatch_notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Dispatch Notes (Optional)</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Any special instructions or notes..."
                      className="resize-none"
                      rows={3}
                      {...field}
                      value={field.value || ""}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex gap-2 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button type="submit" loading={isSubmitting} className="flex-1">
                {isSubmitting ? "Dispatching…" : "Dispatch Order"}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
