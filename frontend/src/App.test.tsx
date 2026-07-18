/// <reference types="@testing-library/jest-dom/vitest" />
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api", () => ({
  setUnauthorizedHandler: vi.fn(),
  getApiKey: vi.fn(() => ""),
  setApiKey: vi.fn(),
  fetchHealth: vi.fn(() => Promise.resolve({ ok: true })),
  fetchSetupStatus: vi.fn(() =>
    Promise.resolve({
      app_env: "dev",
      projects_root: "/projects",
      total_project_dirs: 1,
      initialized_projects: 1,
      onboarding_suggested: false,
    })
  ),
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
  fetchTriage: vi.fn(() => Promise.resolve([])),
  fetchLabelConflicts: vi.fn(() => Promise.resolve({ total: 0, items: [] })),
  resolveLabelConflict: vi.fn(() => Promise.resolve({ status: "ok", labeled_by: "human" })),
  fetchTaxonomy: vi.fn(() => Promise.resolve({ business_domains: [], document_types: [] })),
  createTaxonomyEntry: vi.fn(() => Promise.resolve({ status: "ok", key: "x", updated_projects: [] })),
  fetchClassifierStatus: vi.fn(() =>
    Promise.resolve({
      available_modes: ["bootstrap", "sparse_logreg"],
      champion_mode: "bootstrap",
      fallback_mode: "bootstrap",
      effective_mode: "bootstrap",
      override_mode: null,
      promotion_policy: "auto_best_with_ui_override",
      project_override_allowed: true,
      promotion_gates: {
        primary_metric: "exact_match_accuracy",
        min_business_domain_accuracy: 0,
        min_document_type_accuracy: 0,
        min_exact_match_accuracy: 0,
        prefer_current_champion_on_tie: true
      },
      latest_report_id: "cycle_001",
      champion_report_id: "cycle_001",
      champion_summary: { mode: "bootstrap", total_labeled: 10, business_domain_accuracy: 0.5, document_type_accuracy: 0.8, exact_match_accuracy: 0.4 },
      latest_report_summary: { mode: "bootstrap", total_labeled: 10, business_domain_accuracy: 0.5, document_type_accuracy: 0.8, exact_match_accuracy: 0.4 },
      latest_cycle_status: "succeeded",
      latest_cycle_started_at: null,
      latest_cycle_finished_at: null,
      latest_cycle_error: null
    })
  ),
  fetchClassifierReportLatest: vi.fn(() =>
    Promise.resolve({
      report_id: "cycle_001",
      operational_classifier_mode: "bootstrap",
      dataset_integrity: { status: "ok" },
      gates: {},
      training_pool_records: 10,
      benchmarks: {
        bootstrap: {
          summary: { mode: "bootstrap", total_labeled: 10, business_domain_accuracy: 0.5, document_type_accuracy: 0.8, exact_match_accuracy: 0.4 },
          results: []
        }
      },
      champion: {
        mode: "bootstrap",
        summary: { mode: "bootstrap", total_labeled: 10, business_domain_accuracy: 0.5, document_type_accuracy: 0.8, exact_match_accuracy: 0.4 },
        promotion_policy: "auto_best_with_ui_override"
      }
    })
  ),
  fetchClassifierReports: vi.fn(() => Promise.resolve([])),
  updateClassifierOverride: vi.fn(() => Promise.resolve({ override_mode: null, effective_mode: "bootstrap", champion_mode: "bootstrap", fallback_mode: "bootstrap", available_modes: ["bootstrap", "sparse_logreg"], promotion_policy: "auto_best_with_ui_override", project_override_allowed: true, promotion_gates: { primary_metric: "exact_match_accuracy", min_business_domain_accuracy: 0, min_document_type_accuracy: 0, min_exact_match_accuracy: 0, prefer_current_champion_on_tie: true }, latest_cycle_status: "succeeded" })),
  startClassifierCycle: vi.fn(() => Promise.resolve({ status: "started" })),
  fetchClassifierCycleStatus: vi.fn(() => Promise.resolve({ last_run_started_at: null, last_run_finished_at: null, duration_seconds: null, running: false, phase: "idle", progress_current: 0, progress_total: 0, report_id: null, champion_mode: null, last_error: null })),
  getClassifierCycleStatusStreamUrl: vi.fn(() => "http://localhost/api/classifier/cycle/status/stream"),
  fetchSuggestions: vi.fn(() => Promise.resolve({ total: 0, items: [] })),
  searchDocuments: vi.fn(() =>
    Promise.resolve({ total: 0, page: 1, page_size: 20, total_pages: 0, hits: [] })
  ),
  getFileDownloadUrl: vi.fn((path: string) => `http://api/files?path=${path}`),
  fetchModels: vi.fn(() => Promise.resolve([{ provider: "openai", model: "gpt-4o-mini", label: "OpenAI gpt-4o-mini (base)" }])),
  initializeProject: vi.fn(() => Promise.resolve({ status: "ok", already_initialized: false })),
  runReconcile: vi.fn(() => Promise.resolve({ status: "started" })),
  triggerScan: vi.fn(() => Promise.resolve({ project_id: "p1", processed_count: 0, failed_count: 0, items: [], errors: [] })),
  fetchIngestHistory: vi.fn(() => Promise.resolve({ project_id: "p1", entries: [] })),
  fetchDatasetReadiness: vi.fn(() => Promise.resolve({ cycle_ready: true, splits_available: false, validation: { labeled: 3, unlabeled: 0 }, training: { records: 12, business_domain_classes: {}, document_type_classes: {} }, supervised_gate: { eligible: false, reasons: [], warnings: [] }, holdout: { enabled: true, modulus: 5, min_train_per_class: 3 }, blockers: [], suggestions: [] })),
  backfillValidation: vi.fn(() => Promise.resolve({ dry_run: false, moved: 0, per_class: {}, skipped: [], validation_labeled_total: 3, training_total: 12 })),
  fetchIngestStatus: vi.fn(() => Promise.resolve({ last_run_started_at: null, last_run_finished_at: null, duration_seconds: null, project_id: null, running: false, phase: "idle", progress_current: 0, progress_total: 0, progress_file: null, processed_count: 0, failed_count: 0, last_error: null })),
  getIngestStatusStreamUrl: vi.fn(() => "http://localhost/api/ingest/status/stream"),
  fetchProjectProfile: vi.fn(() =>
    Promise.resolve({
      profile: {
        profile_version: 2,
        project_id: "p1",
        project_label: "Projeto 1",
        project_root: "/p1",
        paths: { inbox: "_INBOX_DROP", triage: { pending: "_TRIAGE_REVIEW/pending", resolved: "_TRIAGE_REVIEW/resolved", rejected: "_TRIAGE_REVIEW/rejected" } },
        layout: { mode: "para_jd", roots: { projects: "01_PROJECTS", areas: "02_AREAS", resources: "03_RESOURCES", archive: "04_ARCHIVE" }, areas_root: "02_AREAS", business_domain_folders: [] },
        classification: {
          business_domains: [],
          document_types: [],
          routing_rules: [],
          confidence_thresholds: { auto_route_min: 0.85, triage_min: 0.5 },
          llm_policy: {
            enabled: false,
            provider: "openai",
            model: "gpt-4o-mini",
            mode: "tag_only",
            allow_override_fields: ["document_type", "tags", "confidence", "topics"],
            override_guardrails: {
              business_domain_override_only_if_rule_confidence_below: 0.65,
              require_explanation: true,
              max_business_domain_changes: 1
            }
          }
        },
        indexing: { topics_path: "config/topics_v1.yaml", extraction_max_chars: 50000, extraction_mode: "all" },
        version: 1
      },
      etag: "abc",
      version: 1
    })
  ),
  updateProjectProfile: vi.fn(() =>
    Promise.resolve({
      profile: { profile_version: 2, project_id: "p1", version: 2, classification: { llm_policy: { enabled: true } } },
      etag: "def",
      version: 2
    })
  ),
  triageDecision: vi.fn(() => Promise.resolve()),
  fetchStats: vi.fn(() =>
    Promise.resolve({
      project_id: null,
      total_documents: 5,
      by_doc_kind: [{ key: "pdf", count: 3 }, { key: "docx", count: 2 }],
      by_business_domain: [{ key: "juridico", count: 4 }],
      by_document_type: [{ key: "contrato", count: 3 }],
      by_extension: [{ key: ".pdf", count: 3 }],
      by_tags: [{ key: "juridica", count: 4 }],
      by_project_id: [{ key: "p1", count: 5 }]
    })
  )
}));

describe("App", () => {
  it("renders and shows main sections", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/documentos indexados/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/documentos indexados/i)).toBeInTheDocument();
  });

  it("opens search modal on Cmd+K", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/documentos indexados/i)).toBeInTheDocument();
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

  it("shows onboarding when no projects exist", async () => {
    const { fetchSetupStatus, fetchProjects } = await import("./api");
    vi.mocked(fetchSetupStatus).mockResolvedValue({
      app_env: "dev",
      projects_root: "/projects",
      total_project_dirs: 0,
      initialized_projects: 0,
      onboarding_suggested: true,
    });
    vi.mocked(fetchProjects).mockResolvedValue([]);
    localStorage.removeItem("atlasfile-onboarding-done");

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Bem-vindo ao AtlasFile/)).toBeInTheDocument();
    });
  });

  it("opens onboarding on empty backend even with done-flag in localStorage (fresh install, same origin)", async () => {
    const { fetchSetupStatus, fetchProjects } = await import("./api");
    vi.mocked(fetchSetupStatus).mockResolvedValue({
      app_env: "dev",
      projects_root: "/projects",
      total_project_dirs: 0,
      initialized_projects: 0,
      onboarding_suggested: true,
    });
    vi.mocked(fetchProjects).mockResolvedValue([]);
    localStorage.setItem("atlasfile-onboarding-done", "true");

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Bem-vindo ao AtlasFile/)).toBeInTheDocument();
    });
    localStorage.removeItem("atlasfile-onboarding-done");
  });

  it("shows dashboard when projects exist", async () => {
    const { fetchSetupStatus } = await import("./api");
    vi.mocked(fetchSetupStatus).mockResolvedValue({
      app_env: "dev",
      projects_root: "/projects",
      total_project_dirs: 1,
      initialized_projects: 1,
      onboarding_suggested: false,
    });
    localStorage.removeItem("atlasfile-onboarding-done");

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/documentos indexados/i)).toBeInTheDocument();
    });
  });

  it("replay onboarding button visible in dev mode", async () => {
    const { fetchSetupStatus } = await import("./api");
    vi.mocked(fetchSetupStatus).mockResolvedValue({
      app_env: "dev",
      projects_root: "/projects",
      total_project_dirs: 1,
      initialized_projects: 1,
      onboarding_suggested: false,
    });
    localStorage.setItem("atlasfile-onboarding-done", "true");

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/documentos indexados/i)).toBeInTheDocument();
    });
    expect(screen.getByTitle(/Replay Onboarding/)).toBeInTheDocument();
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
          business_domain: "juridico",
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
      expect(screen.getByText(/documentos indexados/i)).toBeInTheDocument();
    });
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    const input = await screen.findByPlaceholderText("Search...");
    fireEvent.change(input, { target: { value: "Fornecedores" } });

    expect(await screen.findByText(/Pagina 135 \/ 1o paragrafo/i)).toBeInTheDocument();
  });

  it("renders control card with stats and project table", async () => {
    const { fetchReconcileStatus, fetchProjects, fetchSetupStatus } = await import("./api");
    vi.mocked(fetchSetupStatus).mockResolvedValue({
      app_env: "dev", projects_root: "/projects", total_project_dirs: 1, initialized_projects: 1, onboarding_suggested: false,
    });
    vi.mocked(fetchProjects).mockResolvedValue([
      { project_id: "p1", project_label: "Projeto 1", root: "/p1", initialized: true }
    ]);
    vi.mocked(fetchReconcileStatus).mockResolvedValue({
      running: false,
      phase: "idle",
      summary: { project_count: 0, skipped_count: 0, rows_written: 0, added_rows: 0, removed_rows: 0, adjustments_applied: 0, indexed_docs: 0, skipped_docs: 0 },
      last_run_started_at: null,
      last_run_finished_at: null,
      duration_seconds: null,
      progress_current: 0,
      progress_total: 0
    });
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/projetos inicializados/)).toBeInTheDocument();
    }, { timeout: 5000 });
    expect(screen.getByText(/documentos indexados/)).toBeInTheDocument();
    expect(screen.getByText(/\.PDF/)).toBeInTheDocument();
    const miniTable = document.querySelector(".mini-table");
    expect(miniTable).toBeInTheDocument();
    expect(miniTable!.textContent).toContain("Projeto 1");
  });
});

describe("AuthGate", () => {
  it("shows the auth gate as first screen when the API returns 401", async () => {
    const { setUnauthorizedHandler } = await import("./api");
    let capturedHandler: ((status: number, detail: string) => void) | null = null;
    vi.mocked(setUnauthorizedHandler).mockImplementation((handler) => {
      capturedHandler = handler as typeof capturedHandler;
    });

    const { act } = await import("@testing-library/react");
    render(<App />);
    await waitFor(() => expect(capturedHandler).not.toBeNull());

    act(() => {
      capturedHandler!(401, "invalid api key");
    });

    await waitFor(() => {
      expect(screen.getByText(/Esta instalação exige uma API key/)).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText("atlas_sk_...")).toBeInTheDocument();
    // o gate assume a tela inteira — nada do app por trás
    expect(screen.queryByText(/documentos indexados/)).not.toBeInTheDocument();
  });
});
