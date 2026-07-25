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
  Share2: () => null,
  Search: () => null,
  Palette: () => null,
}));

// Import after mocks
import { Route } from "../../routes/admin.templates";
const AdminTemplates = (Route as unknown as { options: { component: React.ComponentType } }).options
  .component;

const mockConfig = {
  name: "Hadha Jewellery",
  legal_name: "Hadha Silver Jewellery Pvt. Ltd.",
  brand_name: "Hadha",
  tagline: "The strong Decision",
  description: "Premium handcrafted 92.5 sterling silver jewellery.",
  website: "https://hadha.co",
  domain: "hadha.co",
  gstin: "22AAA0000A1Z5",
  cin: null,
  city: "Hyderabad",
  state: "Telangana",
  postal_code: "500033",
  country: "IN",
  address_line_1: "MVP Sector 1",
  address_line_2: null,
  google_maps_url: null,
  phone: "+91 98765 43210",
  alternate_phone: null,
  whatsapp: null,
  support_email: "info@hadha.com",
  sales_email: null,
  business_hours: null,
  website_url: "www.hadha.com",
  logo_url: null,
  favicon_url: null,
  packing_slip_logo_url: null,
  shipping_label_logo_url: null,
  instagram_url: null,
  facebook_url: null,
  youtube_url: null,
  twitter_x_url: null,
  linkedin_url: null,
  pinterest_url: null,
  default_meta_title: null,
  default_meta_description: null,
  organization_description: null,
  theme_color: null,
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
  it("shows skeleton when isLoading is true", () => {
    mockUseCompanyConfig.mockReturnValue({ data: null, isLoading: true });
    render(<AdminTemplates />);
    const skeleton = document.querySelector(".animate-pulse");
    expect(skeleton).not.toBeNull();
    expect(screen.queryByRole("heading", { name: /company settings/i })).toBeNull();
  });
});

describe("AdminTemplates — rendered structure", () => {
  it("renders page heading 'Company Settings'", () => {
    render(<AdminTemplates />);
    expect(screen.getByRole("heading", { name: /company settings/i })).toBeTruthy();
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
    expect(screen.getByRole("heading", { name: "Address" })).toBeTruthy();
  });

  it("renders Contact section", () => {
    render(<AdminTemplates />);
    expect(screen.getByText(/contact/i)).toBeTruthy();
  });

  it("renders Social Media section", () => {
    render(<AdminTemplates />);
    expect(screen.getByText(/social media/i)).toBeTruthy();
  });

  it("renders SEO & Meta section", () => {
    render(<AdminTemplates />);
    expect(screen.getByText(/seo & meta/i)).toBeTruthy();
  });

  it("renders Business & Compliance section", () => {
    render(<AdminTemplates />);
    expect(screen.getByText(/business & compliance/i)).toBeTruthy();
  });

  it("renders Company Name input", () => {
    render(<AdminTemplates />);
    expect(screen.getByPlaceholderText("Hadha Silver Jewellery")).toBeTruthy();
  });

  it("renders Tagline input", () => {
    render(<AdminTemplates />);
    expect(screen.getByPlaceholderText("Handcrafted 92.5 Silver Jewellery")).toBeTruthy();
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
    const nameInput = screen.getByPlaceholderText("Hadha Silver Jewellery");
    fireEvent.change(nameInput, { target: { value: "New Name" } });
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    buttons.forEach((btn) => expect(btn).not.toBeDisabled());
  });

  it("calls mutateAsync when save clicked", async () => {
    mockMutateAsync.mockResolvedValue({});
    render(<AdminTemplates />);
    const nameInput = screen.getByPlaceholderText("Hadha Silver Jewellery");
    fireEvent.change(nameInput, { target: { value: "New Name" } });
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalled());
  });

  it("shows success toast on successful save", async () => {
    mockMutateAsync.mockResolvedValue({});
    render(<AdminTemplates />);
    const nameInput = screen.getByPlaceholderText("Hadha Silver Jewellery");
    fireEvent.change(nameInput, { target: { value: "New Name" } });
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Company settings saved"));
  });

  it("shows error toast when save fails", async () => {
    mockMutateAsync.mockRejectedValue(new Error("Network error"));
    render(<AdminTemplates />);
    const nameInput = screen.getByPlaceholderText("Hadha Silver Jewellery");
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
    const taglineInput = screen.getByPlaceholderText("Handcrafted 92.5 Silver Jewellery");
    expect((taglineInput as HTMLInputElement).value).toBe("");
  });

  it("converts empty string to null in payload", async () => {
    mockMutateAsync.mockResolvedValue({});
    mockUseCompanyConfig.mockReturnValue({ data: mockConfig, isLoading: false });
    render(<AdminTemplates />);
    const taglineInput = screen.getByPlaceholderText("Handcrafted 92.5 Silver Jewellery");
    fireEvent.change(taglineInput, { target: { value: "" } });
    const buttons = screen.getAllByRole("button", { name: /save changes/i });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalled());
    const payload = mockMutateAsync.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.tagline).toBeNull();
  });
});
