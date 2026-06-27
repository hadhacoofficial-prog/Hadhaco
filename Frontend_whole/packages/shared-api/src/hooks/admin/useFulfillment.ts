import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/queryKeys";
import { authHeader, buildUrl } from "../../lib/api/interceptors";
import type {
  DispatchOrderPayload,
  FulfillmentTimelineResponse,
} from "@hadha/shared-types";
import type { OrderResponse } from "@hadha/shared-types";

export const useConfirmPayment = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (orderId: string) =>
      api.patch<OrderResponse>(`/admin/orders/${orderId}/fulfillment/confirm-payment`, {}),
    onSuccess: (_, orderId) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.order(orderId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.fulfillment.timeline(orderId),
      });
    },
  });
};

export const useMarkPacking = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (orderId: string) =>
      api.patch<OrderResponse>(`/admin/orders/${orderId}/fulfillment/mark-packing`, {}),
    onSuccess: (_, orderId) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.order(orderId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.fulfillment.timeline(orderId),
      });
    },
  });
};

/**
 * Returns a blob URL for the on-demand PDF shipping label.
 * The endpoint streams PDF bytes — no R2 URL is returned.
 * Callers are responsible for revoking the blob URL after download.
 */
export const useGenerateShippingLabel = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (orderId: string): Promise<{ blobUrl: string; filename: string }> => {
      const url = buildUrl(`/admin/orders/${orderId}/fulfillment/shipping-label`, {
        format: "pdf",
      });
      const auth = await authHeader();
      const res = await fetch(url, { method: "GET", headers: auth });
      if (!res.ok) throw new Error("Failed to generate shipping label");
      const blob = await res.blob();
      return {
        blobUrl: URL.createObjectURL(blob),
        filename: `shipping-label-${orderId}.pdf`,
      };
    },
    onSuccess: (_, orderId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.order(orderId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.fulfillment.timeline(orderId),
      });
    },
  });
};

/**
 * Returns a blob URL for the on-demand PDF packing slip.
 * The endpoint streams PDF bytes — no R2 URL is returned.
 * Callers are responsible for revoking the blob URL after download.
 */
export const useGeneratePackingSlip = () => {
  return useMutation({
    mutationFn: async (orderId: string): Promise<{ blobUrl: string; filename: string }> => {
      const url = buildUrl(`/admin/orders/${orderId}/fulfillment/packing-slip`, {
        format: "pdf",
      });
      const auth = await authHeader();
      const res = await fetch(url, { method: "GET", headers: auth });
      if (!res.ok) throw new Error("Failed to generate packing slip");
      const blob = await res.blob();
      return {
        blobUrl: URL.createObjectURL(blob),
        filename: `packing-slip-${orderId}.pdf`,
      };
    },
  });
};

export const useDispatchOrder = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ orderId, payload }: { orderId: string; payload: DispatchOrderPayload }) =>
      api.patch<OrderResponse>(`/admin/orders/${orderId}/fulfillment/dispatch`, { body: payload }),
    onSuccess: (_, { orderId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.order(orderId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.fulfillment.timeline(orderId),
      });
    },
  });
};

export const useMarkInTransit = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (orderId: string) =>
      api.patch<OrderResponse>(`/admin/orders/${orderId}/fulfillment/mark-in-transit`, {}),
    onSuccess: (_, orderId) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.order(orderId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.fulfillment.timeline(orderId),
      });
    },
  });
};

export const useMarkDelivered = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (orderId: string) =>
      api.patch<OrderResponse>(`/admin/orders/${orderId}/fulfillment/mark-delivered`, {}),
    onSuccess: (_, orderId) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.order(orderId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.fulfillment.timeline(orderId),
      });
    },
  });
};

export const useFulfillmentTimeline = (orderId: string) => {
  return useQuery({
    queryKey: queryKeys.admin.fulfillment.timeline(orderId),
    queryFn: () =>
      api.get<FulfillmentTimelineResponse>(`/admin/orders/${orderId}/fulfillment/timeline`),
  });
};
