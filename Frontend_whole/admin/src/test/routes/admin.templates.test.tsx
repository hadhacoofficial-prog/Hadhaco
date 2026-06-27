import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { toast } from "sonner";

const mockMutateAsync = vi.fn();
const mockUseCompanyConfig = vi.fn();
const mockUseUpdateCompanyConfig = vi.fn();

vi.mock("@hadha/shared-api", () => ({
  useCompanyConfig: () => mockUseCompanyConfig(),
  useUpdateCompanyConfig: () => mockUseUpdateCompanyConfig(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: React.ComponentType }) => ({
    options,
  }),
}));

vi.mock("lucide-react", () => ({
  Save: () => null,
  Settings2: () => null,
  Building2: () => null,
  Phone: () => null,
  Globe: () => null,
  Mail: () => null,
  MapPin: () => null,
  FileText: () => null,
  Tag: () => null,
}));

// Import after mocks
import { Route } from "../../routes/admin.templates";
const AdminTemplates = (Route as unknown as { options: { component: React.ComponentType } }).options
  .component;

const mockConfig = {
  name: "Hadha Jewellery",
  tagline: "The strong Decision",
  gstin: "22AAA0000A1Z5",
  address_line1: "Plot 42",
  address_line2: null,
  city: "Hyderabad",
  state: "Telangana",
  postal_code: "500033",
  country: "IN",
  phone: "+91 98765 43210",
  support_email: "info@hadha.com",
  website: "www.hadha.com",
  logo_url: null,
  instagram_url: null,
  facebook_url: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCompanyConfig.mockReturnValue({ data: null, isLoading: false });
  mockUseUpdateCompanyConfig.mockReturnValue({
    mutateAsync: mockMutateAsync,
    isPending: false,
  });
});

describe("AdminTemplates — loading state", () => {
  it("shows spinner when isLoading is true", () => {
    mockUseCompanyConfig.mockReturnValue({ data: null, isLoading: true });
    render(<AdminTemplates />);
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).not.toBeNull();
    expect(screen.queryByRole("heading", { name: /template settings/i })).toBeNull();
  });
});

describe("AdminTemplates — rendered structure", () => {
  it("renders page heading 'Template Settings'", () => {
    render(<AdminTemplates />);
    expect(screen.getByRole("heading", { name: /template settings/i })).toBeTruthy();
  });

  it("renders Save Changes button", () => {
    render(<AdminTemplates />);
    expect(screen.getAllByRole("button", { name: /save changes/i }).length).toBeGreaterThan(0);
  });

  it("renders Brand Identity section", () => {
    render(<AdminTemplates />);
    expect(screen.getByText(/brand identity/i)).toBeTruthy();
  });

  it("renders Address section", () => {
    render(<AdminTemplates />);
    expect(screen.getByText(/^address$/i)).toBeTruthy();
  });

  it("renders Contact section", () => {
    render(<AdminTemplates />);
    expect(screen.getByText(/^contact$/i)).toBeTruthy();
  });

  it("renders Document Templates info section", () => {
    render(<AdminTemplates />);
    expect(screen.getByText(/document templates/i)).toBeTruthy();
  });

  it("renders Company Name input", () => {
    render(<AdminTemplates />);
    expect(screen.getByPlaceholderText(/hadha jewellery/i)).toBeTruthy();
  });

  it("renders Tagline input", () => {
    render(<AdminTemplates />);
    expect(screen.getByPlaceholderText(/strong decision/i)).toBeTruthy();
  });
});

describe("AdminTemplates — pre-populated form", () => {
  it("populates form inputs from config", () => {
    mockUseCompanyConfig.mockReturnValue({ data: mockConfig, isLoading: false });
    render(<AdminTemplates />);
    const input = screen.getByDisplayValue("Hadha Jewellery");
    expect(input).toBeTruthy();
  });

  it("populates phone field from config", () => {
    mockUseCompanyConfig.mockReturnValue({ data: mockConfig, isLoading: false });
    render(<AdminTemplates />);
    expect(screen.getByDisplayValue("+91 98765 43210")).toBeTruthy();
  });

  it("populates city field from config", () => {
    mockUseCompanyConfig.mockReturnValue({ data: mockConfig, isLoading: false });
    render(<AdminTemplates />);
    expect(screen.getByDisplayValue("Hyderabad")).toBeTruthy();
  });
});

describe("AdminTemplates — Save Changes", () => {
  it("Save button is disabled initially", () => {
    render(<AdminTemplates />);
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    buttons.forEach((btn) => expect(btn).toBeDisabled());
  });

  it("Save button enables after user types in a field", () => {
    render(<AdminTemplates />);
    const nameInput = screen.getByPlaceholderText(/hadha jewellery/i);
    fireEvent.change(nameInput, { target: { value: "New Name" } });
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    buttons.forEach((btn) => expect(btn).not.toBeDisabled());
  });

  it("calls mutateAsync when save clicked", async () => {
    mockMutateAsync.mockResolvedValue({});
    render(<AdminTemplates />);
    const nameInput = screen.getByPlaceholderText(/hadha jewellery/i);
    fireEvent.change(nameInput, { target: { value: "New Name" } });
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalled());
  });

  it("shows success toast on successful save", async () => {
    mockMutateAsync.mockResolvedValue({});
    render(<AdminTemplates />);
    const nameInput = screen.getByPlaceholderText(/hadha jewellery/i);
    fireEvent.change(nameInput, { target: { value: "New Name" } });
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Company settings saved"));
  });

  it("shows error toast when save fails", async () => {
    mockMutateAsync.mockRejectedValue(new Error("Network error"));
    render(<AdminTemplates />);
    const nameInput = screen.getByPlaceholderText(/hadha jewellery/i);
    fireEvent.change(nameInput, { target: { value: "New Name" } });
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Failed to save settings"));
  });

  it("Save button shows 'Saving' text when isPending is true", () => {
    mockUseUpdateCompanyConfig.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: true,
    });
    render(<AdminTemplates />);
    expect(screen.getAllByText(/saving/i).length).toBeGreaterThan(0);
  });
});

describe("AdminTemplates — null config fields become empty strings", () => {
  it("renders empty string for null tagline", () => {
    mockUseCompanyConfig.mockReturnValue({
      data: { ...mockConfig, tagline: null },
      isLoading: false,
    });
    render(<AdminTemplates />);
    const taglineInput = screen.getByPlaceholderText(/strong decision/i);
    expect((taglineInput as HTMLInputElement).value).toBe("");
  });

  it("converts empty string to null in payload", async () => {
    mockMutateAsync.mockResolvedValue({});
    mockUseCompanyConfig.mockReturnValue({ data: mockConfig, isLoading: false });
    render(<AdminTemplates />);
    // Clear the tagline field to an empty string
    const taglineInput = screen.getByPlaceholderText(/strong decision/i);
    fireEvent.change(taglineInput, { target: { value: "" } });
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalled());
    const payload = mockMutateAsync.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.tagline).toBeNull();
  });
});
