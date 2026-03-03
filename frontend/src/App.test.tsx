/// <reference types="@testing-library/jest-dom/vitest" />
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api", () => ({
  fetchHealth: vi.fn(() => Promise.resolve({ ok: true })),
  fetchProjects: vi.fn(() =>
    Promise.resolve([
      { project_id: "p1", project_label: "Projeto 1", root: "/p1", initialized: true }
    ])
  ),
  fetchReconcileStatus: vi.fn(() =>
    Promise.resolve({
      running: false,
      phase: "idle",
      summary: {},
      last_run_finished_at: null,
      progress_current: 0,
      progress_total: 0
    })
  ),
  fetchProjectAreas: vi.fn(() => Promise.resolve([])),
  fetchTriage: vi.fn(() => Promise.resolve([])),
  fetchSuggestions: vi.fn(() => Promise.resolve({ total: 0, items: [] })),
  searchDocuments: vi.fn(() =>
    Promise.resolve({ total: 0, page: 1, page_size: 20, total_pages: 0, hits: [] })
  ),
  getFileDownloadUrl: vi.fn((path: string) => `http://api/files?path=${path}`),
  initializeProject: vi.fn(() => Promise.resolve({ status: "ok", already_initialized: false })),
  runReconcile: vi.fn(() => Promise.resolve({ status: "started" })),
  triggerScan: vi.fn(() => Promise.resolve()),
  triageDecision: vi.fn(() => Promise.resolve())
}));

describe("App", () => {
  it("renders and shows main sections", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Ingestão e triagem|Ingestao e triagem/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Processar INBOX/i)).toBeInTheDocument();
  });

  it("opens search modal on Cmd+K", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Processar INBOX/i)).toBeInTheDocument();
    });
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    const searchPlaceholder = await screen.findByPlaceholderText("Search...", {}, { timeout: 3000 });
    expect(searchPlaceholder).toBeInTheDocument();
  });

  it("shows reconcile progress when running", async () => {
    const { fetchReconcileStatus } = await import("./api");
    vi.mocked(fetchReconcileStatus).mockResolvedValue({
      running: true,
      phase: "search",
      progress_current: 5,
      progress_total: 10,
      progress_file: "file.pdf",
      progress_project: "p1",
      progress_skipped: 0,
      summary: {
        project_count: 0,
        skipped_count: 0,
        rows_written: 0,
        added_rows: 0,
        removed_rows: 0,
        adjustments_applied: 0,
        indexed_docs: 0,
        skipped_docs: 0
      },
      last_run_started_at: null,
      last_run_finished_at: null,
      duration_seconds: null
    });
    render(<App />);
    await screen.findByText("file.pdf", {}, { timeout: 5000 });
    expect(screen.getByText(/5/)).toBeInTheDocument();
    expect(screen.getByText(/10/)).toBeInTheDocument();
  });

  it("formats DOCX location as pagina/paragrafo", async () => {
    const { searchDocuments } = await import("./api");
    vi.mocked(searchDocuments).mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
      hits: [
        {
          doc_id: "docx-1",
          project_id: "p1",
          area_key: "02_juridica",
          original_filename: "contrato.docx",
          canonical_filename: "contrato.docx",
          path: "/p1/_WORK/02_juridica/contrato.docx",
          score: 1.0,
          highlights: [],
          match_locations: [],
          evidences: [
            {
              location: "docx_page:135:paragraph:1",
              snippet: "Trecho com <em>Fornecedores</em>."
            }
          ],
          total_evidences: 1,
          omitted_evidences: 0,
          content_type: "docx"
        }
      ]
    });

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Processar INBOX/i)).toBeInTheDocument();
    });
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    const input = await screen.findByPlaceholderText("Search...");
    fireEvent.change(input, { target: { value: "Fornecedores" } });

    expect(await screen.findByText(/Pagina 135 \/ 1o paragrafo/i)).toBeInTheDocument();
  });
});
