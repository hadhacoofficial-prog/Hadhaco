import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api/client", () => ({ api: { upload: vi.fn() } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
// Canvas decoding isn't available in jsdom; reviewPhoto has its own tests.
vi.mock("@/lib/reviewPhoto", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/reviewPhoto")>();
  return { ...actual, prepareReviewPhoto: vi.fn() };
});

import { api } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { prepareReviewPhoto, ReviewPhotoError } from "@/lib/reviewPhoto";
import { toast } from "sonner";
import { WriteReviewModal } from "@/components/site/WriteReviewModal";

const mockedUpload = api.upload as unknown as ReturnType<typeof vi.fn>;
const mockedPrepare = prepareReviewPhoto as unknown as ReturnType<typeof vi.fn>;

// jsdom's Blob lacks text() (every supported browser has it).
beforeAll(() => {
  Blob.prototype.text ??= function (this: Blob) {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(reader.error);
      reader.readAsText(this);
    });
  };
});

function renderModal() {
  const utils = render(<WriteReviewModal productId="p1" onClose={vi.fn()} onSuccess={vi.fn()} />);
  fireEvent.click(screen.getByLabelText("Rate 5 stars"));
  fireEvent.change(screen.getByPlaceholderText(/Share your experience/), {
    target: { value: "Lovely" },
  });
  const input = utils.container.querySelector('input[type="file"]') as HTMLInputElement;
  return { input };
}

const jpeg = (name: string, body = "jpeg-bytes") => new File([body], name, { type: "image/jpeg" });

function pickFiles(input: HTMLInputElement, files: File[]) {
  Object.defineProperty(input, "files", { value: files, configurable: true });
  fireEvent.change(input);
}

const submitButton = () => screen.getByRole("button", { name: /Submit Review|Attaching photos/ });
const addButton = () => screen.getByRole("button", { name: /Upload photo|Add photo/ });

async function submittedFiles(): Promise<File[]> {
  fireEvent.click(submitButton());
  await waitFor(() => expect(mockedUpload).toHaveBeenCalledTimes(1));
  return (mockedUpload.mock.calls[0][1] as FormData).getAll("images") as File[];
}

describe("WriteReviewModal photos", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    let n = 0;
    URL.createObjectURL = vi.fn(() => `blob:preview-${n++}`);
    URL.revokeObjectURL = vi.fn();
    mockedUpload.mockResolvedValue({});
    mockedPrepare.mockImplementation(async (f: File) => f);
  });

  it("blocks submit from picker open until photos are attached, then sends them", async () => {
    const { input } = renderModal();

    fireEvent.click(addButton());
    expect(submitButton()).toBeDisabled();
    expect(submitButton()).toHaveTextContent("Attaching photos…");

    pickFiles(input, [jpeg("a.jpg", "aaa"), jpeg("b.jpg", "bbb")]);
    await waitFor(() => expect(submitButton()).toBeEnabled());
    expect(screen.getAllByAltText(/Photo \d preview/)).toHaveLength(2);

    const sent = await submittedFiles();
    expect(sent.map((f) => f.name)).toEqual(["a.jpg", "b.jpg"]);
    expect(await sent[1].text()).toBe("bbb");
  });

  it("caps photos at 3 and hides the add button when full", async () => {
    const { input } = renderModal();

    fireEvent.click(addButton());
    pickFiles(input, [jpeg("1.jpg"), jpeg("2.jpg"), jpeg("3.jpg"), jpeg("4.jpg")]);

    await waitFor(() => expect(screen.getAllByAltText(/Photo \d preview/)).toHaveLength(3));
    expect(toast.error).toHaveBeenCalledWith("You can add up to 3 photos.");
    expect(screen.queryByRole("button", { name: /Upload photo|Add photo/ })).toBeNull();
    expect((await submittedFiles()).map((f) => f.name)).toEqual(["1.jpg", "2.jpg", "3.jpg"]);
  });

  it("removes a photo and frees its slot", async () => {
    const { input } = renderModal();

    fireEvent.click(addButton());
    pickFiles(input, [jpeg("1.jpg"), jpeg("2.jpg"), jpeg("3.jpg")]);
    await waitFor(() => expect(screen.getAllByAltText(/Photo \d preview/)).toHaveLength(3));

    fireEvent.click(screen.getByLabelText("Remove photo 2"));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview-1");
    expect(addButton()).toHaveTextContent("Add photo");
    expect((await submittedFiles()).map((f) => f.name)).toEqual(["1.jpg", "3.jpg"]);
  });

  it("re-enables submit when the picker is cancelled", () => {
    const { input } = renderModal();

    fireEvent.click(addButton());
    expect(submitButton()).toBeDisabled();

    fireEvent(input, new Event("cancel"));
    expect(submitButton()).toBeEnabled();
    expect(submitButton()).toHaveTextContent("Submit Review");
  });

  it("keeps readable photos and explains why one was rejected", async () => {
    const { input } = renderModal();
    const tiny = jpeg("tiny.jpg");
    mockedPrepare.mockImplementation(async (f: File) => {
      if (f === tiny) throw new ReviewPhotoError("This photo is too small.");
      return f;
    });

    fireEvent.click(addButton());
    pickFiles(input, [jpeg("ok.jpg"), tiny]);

    await waitFor(() => expect(submitButton()).toBeEnabled());
    expect(toast.error).toHaveBeenCalledWith("This photo is too small.");
    expect((await submittedFiles()).map((f) => f.name)).toEqual(["ok.jpg"]);
  });

  it("uploads with a longer timeout and shows plain-language errors", async () => {
    mockedUpload.mockRejectedValue(
      new ApiError("Not authenticated", { kind: "http", status: 401 }),
    );
    renderModal();

    fireEvent.click(submitButton());
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Please sign in to continue."));
    expect(mockedUpload.mock.calls[0][2]).toEqual({ timeoutMs: 60_000 });
  });
});
