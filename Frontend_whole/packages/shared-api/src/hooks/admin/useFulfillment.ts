import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/queryKeys";
import type {
  DispatchOrderPayload,
  FulfillmentTimelineResponse,
  PackingSlipResponse,
  ShippingLabelResponse,
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

export const useGenerateShippingLabel = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (orderId: string) =>
      api.post<ShippingLabelResponse>(`/admin/orders/${orderId}/fulfillment/shipping-label`, {}),
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

export const useGeneratePackingSlip = () => {
  return useMutation({
    mutationFn: async (orderId: string) =>
      api.post<PackingSlipResponse>(`/admin/orders/${orderId}/fulfillment/packing-slip`, {}),
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
