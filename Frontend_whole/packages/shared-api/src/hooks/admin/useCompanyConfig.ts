import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/queryKeys";
import type { CompanyConfig, CompanyConfigUpdate } from "@hadha/shared-types";

export const useCompanyConfig = () =>
  useQuery({
    queryKey: queryKeys.admin.companyConfig,
    queryFn: () => api.get<CompanyConfig>("/admin/company"),
    staleTime: 30_000,
  });

export const useUpdateCompanyConfig = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CompanyConfigUpdate) =>
      api.patch<CompanyConfig>("/admin/company", { body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.companyConfig });
    },
  });
};
