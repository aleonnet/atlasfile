/// <reference types="@testing-library/jest-dom/vitest" />
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InboxScanCard } from "./InboxScanCard";

vi.mock("../../api", () => ({
  triggerScan: vi.fn(() =>
    Promise.resolve({ project_id: "p1", processed_count: 1, failed_count: 0, items: [], errors: [] })
  ),
  fetchIngestStatus: vi.fn(() =>
    Promise.resolve({
      last_run_started_at: null,
      last_run_finished_at: null,
      duration_seconds: null,
      project_id: null,
      running: false,
      phase: "idle",
      progress_current: 0,
      progress_total: 0,
      progress_file: null,
      processed_count: 0,
      failed_count: 0,
      last_error: null
    })
  ),
  getIngestStatusStreamUrl: vi.fn(() => "http://localhost/api/ingest/status/stream")
}));

function defaultProps() {
  return {
    selectedProject: "p1",
    projects: [{ project_id: "p1", project_label: "Projeto 1", root: "/p1", initialized: true }],
    onStatus: vi.fn(),
    onScanComplete: vi.fn()
  };
}

describe("InboxScanCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls triggerScan on button click and notifies completion", async () => {
    const props = defaultProps();
    render(<InboxScanCard {...props} />);

    await act(async () => {
      fireEvent.click(screen.getByText(/Processar INBOX/i));
    });

    const { triggerScan } = await import("../../api");
    await waitFor(() => {
      expect(vi.mocked(triggerScan)).toHaveBeenCalledWith("p1");
    });
    await waitFor(() => {
      expect(props.onScanComplete).toHaveBeenCalled();
    });
    expect(props.onStatus).toHaveBeenCalledWith(expect.stringContaining("Inbox processado"));
  });

  it("shows live progress while the scan runs", async () => {
    const originalEventSource = window.EventSource;
    Object.defineProperty(window, "EventSource", { configurable: true, value: undefined });
    const idle = {
      last_run_started_at: null,
      last_run_finished_at: null,
      duration_seconds: null,
      project_id: null,
      running: false,
      phase: "idle",
      progress_current: 0,
      progress_total: 0,
      progress_file: null,
      processed_count: 0,
      failed_count: 0,
      last_error: null
    };
    try {
      const running = {
        ...idle,
        project_id: "p1",
        running: true,
        phase: "processing",
        progress_current: 2,
        progress_total: 6,
        progress_file: "arquivo.pdf",
        processed_count: 1
      };
      let resolveScan: (v: unknown) => void = () => {};
      const scanPromise = new Promise((resolve) => {
        resolveScan = resolve;
      });
      const { triggerScan, fetchIngestStatus } = await import("../../api");
      vi.mocked(triggerScan).mockReturnValue(scanPromise as never);
      vi.mocked(fetchIngestStatus).mockResolvedValue({ ...idle, phase: "completed" } as never);
      vi.mocked(fetchIngestStatus)
        .mockResolvedValueOnce(idle as never)
        .mockResolvedValueOnce(running as never);

      render(<InboxScanCard {...defaultProps()} />);
      await act(async () => {
        fireEvent.click(screen.getByText(/Processar INBOX/i));
      });

      await waitFor(() => {
        expect(screen.getByText(/Processando arquivos/i)).toBeInTheDocument();
      }, { timeout: 3000 });
      expect(screen.getByText(/2 \/ 6 arquivo/i)).toBeInTheDocument();
      expect(screen.getByText(/arquivo\.pdf/i)).toBeInTheDocument();

      await act(async () => {
        resolveScan({ project_id: "p1", processed_count: 6, failed_count: 0, items: [], errors: [] });
        await Promise.resolve();
      });
      await waitFor(() => {
        expect(screen.queryByText(/Processando arquivos/i)).not.toBeInTheDocument();
      }, { timeout: 3000 });
    } finally {
      Object.defineProperty(window, "EventSource", { configurable: true, value: originalEventSource });
    }
  });
});
