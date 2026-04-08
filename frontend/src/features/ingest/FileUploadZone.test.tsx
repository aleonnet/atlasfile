import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { FileUploadZone } from "./FileUploadZone";

vi.mock("../../api", () => ({
  uploadToInbox: vi.fn(),
  deleteInboxFile: vi.fn(),
  fetchInboxFiles: vi.fn().mockResolvedValue({ files: [] }),
}));

import { uploadToInbox, deleteInboxFile } from "../../api";

const mockUpload = vi.mocked(uploadToInbox);
const mockDelete = vi.mocked(deleteInboxFile);

describe("FileUploadZone", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders idle state with instructions", () => {
    render(<FileUploadZone projectId="proj" onUploadComplete={() => {}} />);
    expect(screen.getByText(/Arraste arquivos/)).toBeTruthy();
  });

  it("renders disabled state when disabled prop is true", () => {
    render(<FileUploadZone projectId="proj" onUploadComplete={() => {}} disabled />);
    expect(screen.getByText(/Selecione um projeto/)).toBeTruthy();
  });

  it("triggers file input on click", () => {
    render(<FileUploadZone projectId="proj" onUploadComplete={() => {}} />);
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    expect(input.type).toBe("file");
    expect(input.multiple).toBe(true);
  });

  it("shows done state with file list after upload", async () => {
    const onComplete = vi.fn();
    mockUpload.mockResolvedValue({
      uploaded: [
        { filename: "doc.pdf", saved_as: "doc.pdf" },
        { filename: "plan.docx", saved_as: "plan.docx" },
      ],
    });

    render(<FileUploadZone projectId="proj" onUploadComplete={onComplete} />);
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    const file1 = new File(["a"], "doc.pdf", { type: "application/pdf" });
    const file2 = new File(["b"], "plan.docx");

    fireEvent.change(input, { target: { files: [file1, file2] } });

    await waitFor(() => {
      expect(screen.getByText("doc.pdf")).toBeTruthy();
      expect(screen.getByText("plan.docx")).toBeTruthy();
    });

    expect(onComplete).toHaveBeenCalled();
  });

  it("delete button removes file from list", async () => {
    mockUpload.mockResolvedValue({
      uploaded: [
        { filename: "a.pdf", saved_as: "a.pdf" },
        { filename: "b.pdf", saved_as: "b.pdf" },
      ],
    });
    mockDelete.mockResolvedValue({ status: "ok", deleted: "a.pdf" });

    render(<FileUploadZone projectId="proj" onUploadComplete={() => {}} />);
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "a.pdf"), new File(["y"], "b.pdf")] } });

    await waitFor(() => screen.getByTestId("delete-a.pdf"));
    fireEvent.click(screen.getByTestId("delete-a.pdf"));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("proj", "a.pdf");
    });

    await waitFor(() => {
      expect(screen.queryByText("a.pdf")).toBeNull();
      expect(screen.getByText("b.pdf")).toBeTruthy();
    });
  });

  it("shows error state on upload failure", async () => {
    mockUpload.mockRejectedValue(new Error("Falha na rede"));

    render(<FileUploadZone projectId="proj" onUploadComplete={() => {}} />);
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    const file = new File(["content"], "doc.pdf");

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/Falha na rede/)).toBeTruthy();
    });
  });
});
