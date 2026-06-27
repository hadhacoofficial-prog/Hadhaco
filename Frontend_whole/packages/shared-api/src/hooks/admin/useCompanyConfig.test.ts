import { api } from "../../lib/api/client";
import { useCompanyConfig, useUpdateCompanyConfig } from "./useCompanyConfig";

const mockUseQuery = vi.fn();
const mockUseMutation = vi.fn();
const mockUseQueryClient = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
  useQueryClient: () => mockUseQueryClient(),
}));

vi.mock("../../lib/api/client", () => ({
  api: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock("../../lib/api/queryKeys", () => ({
  queryKeys: {
    admin: {
      companyConfig: ["admin", "company-config"],
    },
  },
}));

vi.mock("@hadha/shared-types", () => ({}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useCompanyConfig", () => {
  it("calls useQuery with correct queryKey", () => {
    mockUseQuery.mockReturnValue({ data: null, isLoading: false });
    useCompanyConfig();
    expect(mockUseQuery).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["admin", "company-config"] })
    );
  });

  it("calls useQuery with staleTime of 30000", () => {
    mockUseQuery.mockReturnValue({ data: null, isLoading: false });
    useCompanyConfig();
    expect(mockUseQuery).toHaveBeenCalledWith(
      expect.objectContaining({ staleTime: 30_000 })
    );
  });

  it("uses api.get('/admin/company') as queryFn", async () => {
    mockUseQuery.mockReturnValue({ data: null, isLoading: false });
    useCompanyConfig();
    const call = mockUseQuery.mock.calls[0][0] as { queryFn: () => unknown };
    await call.queryFn();
    expect(api.get).toHaveBeenCalledWith("/admin/company");
  });
});

describe("useUpdateCompanyConfig", () => {
  it("calls useMutation", () => {
    const queryClient = { invalidateQueries: vi.fn() };
    mockUseQueryClient.mockReturnValue(queryClient);
    mockUseMutation.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    useUpdateCompanyConfig();
    expect(mockUseMutation).toHaveBeenCalled();
  });

  it("calls useMutation with mutationFn calling api.patch", async () => {
    const queryClient = { invalidateQueries: vi.fn() };
    mockUseQueryClient.mockReturnValue(queryClient);
    mockUseMutation.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    useUpdateCompanyConfig();
    const call = mockUseMutation.mock.calls[0][0] as {
      mutationFn: (data: unknown) => unknown;
    };
    const sampleData = { name: "Hadha Jewellery" };
    await call.mutationFn(sampleData);
    expect(api.patch).toHaveBeenCalledWith("/admin/company", { body: sampleData });
  });

  it("invalidates companyConfig queryKey on success", () => {
    const queryClient = { invalidateQueries: vi.fn() };
    mockUseQueryClient.mockReturnValue(queryClient);
    mockUseMutation.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    useUpdateCompanyConfig();
    const call = mockUseMutation.mock.calls[0][0] as { onSuccess: () => void };
    call.onSuccess();
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["admin", "company-config"],
    });
  });
});
