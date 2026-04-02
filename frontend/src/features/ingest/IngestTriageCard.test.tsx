/// <reference types="@testing-library/jest-dom/vitest" />
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IngestTriageCard } from "./IngestTriageCard";

const mockProfile = {
  profile: {
    profile_version: 2,
    project_id: "p1",
    project_label: "Projeto 1",
    project_root: "/p1",
    paths: {
      inbox: "_INBOX_DROP",
      triage: { pending: "_TRIAGE_REVIEW/pending", resolved: "_TRIAGE_REVIEW/resolved", rejected: "_TRIAGE_REVIEW/rejected" }
    },
    layout: {
      mode: "para_jd",
      roots: { projects: "01_PROJECTS", areas: "02_AREAS", resources: "03_RESOURCES", archive: "04_ARCHIVE" },
      areas_root: "02_AREAS",
      business_domain_folders: []
    },
    classification: {
      business_domains: [],
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
};

const mockScanResult = {
  project_id: "p1",
  processed_count: 3,
  failed_count: 0,
  items: [
    { doc_id: "d1", project_id: "p1", business_domain: "fiscal", title: "relatorio", original_filename: "relatorio.pdf", canonical_filename: "relatorio.pdf", path: "/p1/02_AREAS/fiscal/relatorio.pdf", decision: "auto" as const, confidence_score: 0.92, sha256: "abc", tags: ["fiscal"] },
    { doc_id: "d2", project_id: "p1", business_domain: "juridico", title: "contrato", original_filename: "contrato.docx", canonical_filename: "contrato.docx", path: "/p1/_TRIAGE_REVIEW/pending/contrato.docx", decision: "triage_pending" as const, confidence_score: 0.61, sha256: "def", tags: ["juridico"], topics_source: "llm_policy" },
    { doc_id: "d3", project_id: "p1", business_domain: "unclassified", title: "duplicado", original_filename: "duplicado.pdf", canonical_filename: "", path: "/p1/_TRIAGE_REVIEW/rejected/duplicado.pdf", decision: "duplicate" as const, confidence_score: 0.0, sha256: "ghi", tags: [] }
  ],
  errors: []
};

const mockHistoryEntry = {
  timestamp: "2026-03-04T10:00:00+00:00",
  ...mockScanResult
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const mockClassifierStatus = {
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
  latest_report_id: "cycle_20260319_120000",
  champion_report_id: "cycle_20260319_120000",
  champion_summary: {
    mode: "bootstrap",
    total_labeled: 50,
    business_domain_accuracy: 0.52,
    document_type_accuracy: 0.8,
    exact_match_accuracy: 0.48
  },
  latest_report_summary: {
    mode: "bootstrap",
    total_labeled: 50,
    business_domain_accuracy: 0.52,
    document_type_accuracy: 0.8,
    exact_match_accuracy: 0.48
  },
  latest_cycle_status: "succeeded",
  latest_cycle_started_at: null,
  latest_cycle_finished_at: null,
  latest_cycle_error: null
};

const mockClassifierReport = {
  report_id: "cycle_20260319_120000",
  operational_classifier_mode: "bootstrap",
  dataset_integrity: { status: "ok" },
  gates: {},
  training_pool_records: 50,
  benchmarks: {
    bootstrap: {
      summary: {
        mode: "bootstrap",
        total_labeled: 50,
        business_domain_accuracy: 0.52,
        document_type_accuracy: 0.8,
        exact_match_accuracy: 0.48
      },
      results: []
    },
    sparse_logreg: {
      summary: {
        mode: "sparse_logreg",
        total_labeled: 50,
        business_domain_accuracy: 0.58,
        document_type_accuracy: 0.82,
        exact_match_accuracy: 0.5
      },
      results: []
    }
  },
  champion: {
    mode: "bootstrap",
    summary: {
      mode: "bootstrap",
      total_labeled: 50,
      business_domain_accuracy: 0.52,
      document_type_accuracy: 0.8,
      exact_match_accuracy: 0.48
    },
    promotion_policy: "auto_best_with_ui_override"
  }
};

vi.mock("../../api", () => ({
  fetchClassifierStatus: vi.fn(() => Promise.resolve(mockClassifierStatus)),
  fetchClassifierReportLatest: vi.fn(() => Promise.resolve(mockClassifierReport)),
  fetchClassifierReports: vi.fn(() => Promise.resolve([{ report_id: "cycle_20260319_120000", champion_mode: "bootstrap", champion_summary: mockClassifierStatus.champion_summary }])),
  updateClassifierOverride: vi.fn(() => Promise.resolve(mockClassifierStatus)),
  startClassifierCycle: vi.fn(() => Promise.resolve({ status: "started" })),
  fetchClassifierCycleStatus: vi.fn(() => Promise.resolve({ last_run_started_at: null, last_run_finished_at: null, duration_seconds: null, running: false, phase: "idle", progress_current: 0, progress_total: 0, report_id: null, champion_mode: null, last_error: null })),
  getClassifierCycleStatusStreamUrl: vi.fn(() => "http://localhost/api/classifier/cycle/status/stream"),
  fetchProjectProfile: vi.fn(() => Promise.resolve(mockProfile)),
  updateProjectProfile: vi.fn(() =>
    Promise.resolve({
      profile: {
        ...mockProfile.profile,
        version: 2,
        classification: {
          ...mockProfile.profile.classification,
          llm_policy: { ...mockProfile.profile.classification.llm_policy, enabled: true }
        }
      },
      etag: "def",
      version: 2
    })
  ),
  triggerScan: vi.fn(() => Promise.resolve(mockScanResult)),
  fetchIngestHistory: vi.fn(() => Promise.resolve({ project_id: "p1", entries: [] })),
  fetchIngestStatus: vi.fn(() => Promise.resolve({ last_run_started_at: null, last_run_finished_at: null, duration_seconds: null, project_id: null, running: false, phase: "idle", progress_current: 0, progress_total: 0, progress_file: null, processed_count: 0, failed_count: 0, last_error: null })),
  getIngestStatusStreamUrl: vi.fn(() => "http://localhost/api/ingest/status/stream"),
  fetchModels: vi.fn(() =>
    Promise.resolve([
      { provider: "openai", model: "gpt-4o-mini", label: "OpenAI gpt-4o-mini (base)" },
      { provider: "openai", model: "gpt-4.1", label: "OpenAI gpt-4.1 (médio)" }
    ])
  )
}));

function defaultProps(overrides: Partial<React.ComponentProps<typeof IngestTriageCard>> = {}) {
  return {
    selectedProject: "p1",
    selectedProjectLabel: "Projeto 1",
    projects: [{ project_id: "p1", project_label: "Projeto 1", root: "/p1", initialized: true }],
    projectLabelById: new Map([["p1", "Projeto 1"]]),
    triageItems: [],
    initializingProjectId: null,
    onDecision: vi.fn(() => Promise.resolve()),
    onLoadTriage: vi.fn(() => Promise.resolve()),
    onStatus: vi.fn(),
    openaiApiKey: "sk-test-key",
    anthropicApiKey: "",
    onOpenSettings: vi.fn(),
    ...overrides
  };
}

describe("IngestTriageCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders header and Processar INBOX button", async () => {
    render(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Ingestão e triagem/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Processar INBOX/i)).toBeInTheDocument();
  });

  it("shows Classificação LLM collapsible for single project", async () => {
    render(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Classificação LLM/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/desativado/i)).toBeInTheDocument();
  });

  it("renders classifier section with benchmark summary", async () => {
    render(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Classificador operacional/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Benchmark oficial/i)).toBeInTheDocument();
    expect(screen.getAllByText(/bootstrap/i).length).toBeGreaterThan(0);
  });

  it("hides LLM section when all projects selected", async () => {
    render(<IngestTriageCard {...defaultProps({ selectedProject: "__all__" })} />);
    await waitFor(() => {
      expect(screen.getByText(/Processar INBOX/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Classificação LLM/i)).not.toBeInTheDocument();
  });

  it("toggles LLM and opens settings modal when no key", async () => {
    const onOpenSettings = vi.fn();
    render(
      <IngestTriageCard {...defaultProps({ openaiApiKey: "", onOpenSettings })} />
    );
    await waitFor(() => {
      expect(screen.getByText(/Classificação LLM/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/Classificação LLM/i));
    const toggle = screen.getByLabelText(/LLM ativado/i);
    fireEvent.click(toggle);

    expect(onOpenSettings).toHaveBeenCalledTimes(1);
  });

  it("toggles LLM on when key is available and shows mode selector", async () => {
    render(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Classificação LLM/i)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText(/Classificação LLM/i));
      const toggle = screen.getByLabelText(/LLM ativado/i);
      fireEvent.click(toggle);
    });

    const { updateProjectProfile } = await import("../../api");
    await waitFor(() => {
      expect(vi.mocked(updateProjectProfile)).toHaveBeenCalled();
    });

    expect(screen.getByLabelText(/Modo/i)).toBeInTheDocument();
  });

  it("saves manual classifier override", async () => {
    render(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/Override do classificador/i)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/Override do classificador/i), {
        target: { value: "sparse_logreg" }
      });
    });

    const { updateClassifierOverride } = await import("../../api");
    await waitFor(() => {
      expect(vi.mocked(updateClassifierOverride)).toHaveBeenCalledWith("p1", "sparse_logreg");
    });
  });

  it("calls triggerScan and shows files in flat table", async () => {
    const { fetchIngestHistory } = await import("../../api");
    vi.mocked(fetchIngestHistory)
      .mockResolvedValueOnce({ project_id: "p1", entries: [] })
      .mockResolvedValueOnce({ project_id: "p1", entries: [mockHistoryEntry] });

    const onStatus = vi.fn();
    render(<IngestTriageCard {...defaultProps({ onStatus })} />);
    await waitFor(() => {
      expect(screen.getByText(/Processar INBOX/i)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText(/Processar INBOX/i));
    });

    const { triggerScan } = await import("../../api");
    await waitFor(() => {
      expect(vi.mocked(triggerScan)).toHaveBeenCalledWith("p1");
    });

    await waitFor(() => {
      expect(screen.getByText(/relatorio\.pdf/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/contrato\.docx/i)).toBeInTheDocument();
    expect(screen.getByText(/duplicado\.pdf/i)).toBeInTheDocument();
  });

  it("shows live inbox progress after the scan starts from an idle status", async () => {
    const originalEventSource = window.EventSource;
    Object.defineProperty(window, "EventSource", { configurable: true, value: undefined });
    const idleStatus = {
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
      const runningStatus = {
        ...idleStatus,
        project_id: "p1",
        running: true,
        phase: "processing",
        progress_current: 2,
        progress_total: 6,
        progress_file: "arquivo.pdf",
        processed_count: 1
      };
      const completedStatus = {
        ...idleStatus,
        project_id: "p1",
        phase: "completed",
        progress_current: 6,
        progress_total: 6,
        processed_count: 6
      };
      const scanDeferred = deferred<typeof mockScanResult>();
      const { triggerScan, fetchIngestStatus, fetchIngestHistory } = await import("../../api");
      vi.mocked(triggerScan).mockReturnValue(scanDeferred.promise);
      vi.mocked(fetchIngestHistory)
        .mockResolvedValueOnce({ project_id: "p1", entries: [] })
        .mockResolvedValueOnce({ project_id: "p1", entries: [] });
      vi.mocked(fetchIngestStatus).mockResolvedValue(completedStatus);
      vi.mocked(fetchIngestStatus)
        .mockResolvedValueOnce(idleStatus)
        .mockResolvedValueOnce(idleStatus)
        .mockResolvedValueOnce(runningStatus);

      render(<IngestTriageCard {...defaultProps()} />);
      await waitFor(() => {
        expect(screen.getByText(/Processar INBOX/i)).toBeInTheDocument();
      });

      await act(async () => {
        fireEvent.click(screen.getByText(/Processar INBOX/i));
      });

      await waitFor(() => {
        expect(screen.getByText(/Processando arquivos/i)).toBeInTheDocument();
      }, { timeout: 3000 });
      expect(screen.getByText(/2 \/ 6 arquivo/i)).toBeInTheDocument();
      expect(screen.getByText(/arquivo\.pdf/i)).toBeInTheDocument();

      await act(async () => {
        scanDeferred.resolve({
          ...mockScanResult,
          processed_count: 6,
          items: mockScanResult.items
        });
        await Promise.resolve();
      });

      await waitFor(() => {
        expect(screen.queryByText(/Processando arquivos/i)).not.toBeInTheDocument();
      }, { timeout: 3000 });
    } finally {
      const { triggerScan, fetchIngestStatus, fetchIngestHistory } = await import("../../api");
      vi.mocked(triggerScan).mockResolvedValue(mockScanResult);
      vi.mocked(fetchIngestStatus).mockResolvedValue(idleStatus);
      vi.mocked(fetchIngestHistory).mockResolvedValue({ project_id: "p1", entries: [] });
      Object.defineProperty(window, "EventSource", { configurable: true, value: originalEventSource });
    }
  });

  it("updates the classifier cycle to completion without needing reload", async () => {
    const originalEventSource = window.EventSource;
    Object.defineProperty(window, "EventSource", { configurable: true, value: undefined });
    const idleIngestStatus = {
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
    const idleCycle = {
      last_run_started_at: null,
      last_run_finished_at: null,
      duration_seconds: null,
      running: false,
      phase: "idle",
      progress_current: 0,
      progress_total: 0,
      report_id: null,
      champion_mode: null,
      last_error: null
    };
    try {
      const runningCycle = {
        ...idleCycle,
        running: true,
        phase: "baseline:bootstrap",
        progress_current: 1,
        progress_total: 3
      };
      const completedCycle = {
        ...idleCycle,
        phase: "completed",
        progress_current: 3,
        progress_total: 3,
        report_id: "cycle_20260320_010000",
        champion_mode: "bootstrap"
      };
      const { fetchClassifierCycleStatus, fetchIngestStatus, startClassifierCycle } = await import("../../api");
      vi.mocked(fetchIngestStatus).mockResolvedValue(idleIngestStatus);
      vi.mocked(fetchClassifierCycleStatus).mockResolvedValue(completedCycle);
      vi.mocked(fetchClassifierCycleStatus)
        .mockResolvedValueOnce(idleCycle)
        .mockResolvedValueOnce(runningCycle);

      render(<IngestTriageCard {...defaultProps()} />);
      await waitFor(() => {
        expect(screen.getByText(/Rodar ciclo/i)).toBeInTheDocument();
      });

      await act(async () => {
        fireEvent.click(screen.getByText(/Rodar ciclo/i));
      });

      expect(vi.mocked(startClassifierCycle)).toHaveBeenCalledTimes(1);

      await waitFor(() => {
        expect(screen.getByText(/Baseline bootstrap/i)).toBeInTheDocument();
      }, { timeout: 3000 });
      expect(screen.getByText(/1 \/ 3/)).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.queryByText(/Baseline bootstrap/i)).not.toBeInTheDocument();
      }, { timeout: 3000 });
      expect(screen.getByText(/Rodar ciclo/i)).toBeInTheDocument();
    } finally {
      const { fetchClassifierCycleStatus, fetchIngestStatus } = await import("../../api");
      vi.mocked(fetchClassifierCycleStatus).mockResolvedValue(idleCycle);
      vi.mocked(fetchIngestStatus).mockResolvedValue(idleIngestStatus);
      Object.defineProperty(window, "EventSource", { configurable: true, value: originalEventSource });
    }
  });

  it("shows LLM indicator for files classified with LLM", async () => {
    const { fetchIngestHistory } = await import("../../api");
    vi.mocked(fetchIngestHistory).mockResolvedValue({
      project_id: "p1",
      entries: [mockHistoryEntry]
    });

    render(<IngestTriageCard {...defaultProps()} />);

    await waitFor(() => {
      expect(screen.getByText("🤖")).toBeInTheDocument();
    });
  });

  it("renders triage items with action buttons", async () => {
    const triageItems = [
      {
        doc_id: "t1",
        filename: "pending-file.pdf",
        project_id: "p1",
        suggested_business_domain: "fiscal",
        confidence_score: 0.72,
        reason: "triage_pending",
        top_candidates: [],
        source_path: "/p1/_TRIAGE_REVIEW/pending/pending-file.pdf",
        metadata_path: "/p1/_TRIAGE_REVIEW/pending/t1.json"
      }
    ];
    render(<IngestTriageCard {...defaultProps({ triageItems })} />);
    await waitFor(() => {
      expect(screen.getByText(/pending-file\.pdf/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Aprovar/i)).toBeInTheDocument();
    expect(screen.getByText(/Corrigir/i)).toBeInTheDocument();
    expect(screen.getByText(/Rejeitar/i)).toBeInTheDocument();
  });

  it("shows empty state when no items and no history", async () => {
    render(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Nenhum item pendente/i)).toBeInTheDocument();
    });
  });

  it("shows Data / Hora column header and Processamentos section", async () => {
    const { fetchIngestHistory } = await import("../../api");
    vi.mocked(fetchIngestHistory).mockResolvedValue({
      project_id: "p1",
      entries: [mockHistoryEntry]
    });

    render(<IngestTriageCard {...defaultProps()} />);

    await waitFor(() => {
      expect(screen.getByText("Data / Hora")).toBeInTheDocument();
    });
    expect(screen.getByText("Arquivo")).toBeInTheDocument();
    expect(screen.getByText("Domínio / Tipo")).toBeInTheDocument();
    expect(screen.getByText("Decisão")).toBeInTheDocument();
    expect(screen.getByText("Conf.")).toBeInTheDocument();
    expect(screen.getByText(/Processamentos/i)).toBeInTheDocument();
  });

  it("restores scan history from backend on mount", async () => {
    const { fetchIngestHistory } = await import("../../api");
    vi.mocked(fetchIngestHistory).mockResolvedValue({
      project_id: "p1",
      entries: [mockHistoryEntry]
    });

    render(<IngestTriageCard {...defaultProps()} />);

    await waitFor(() => {
      expect(screen.getByText(/relatorio\.pdf/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/3 arquivo/i)).toBeInTheDocument();
  });

  it("flattens multiple entries into single table", async () => {
    const { fetchIngestHistory } = await import("../../api");
    const olderEntry = {
      ...mockHistoryEntry,
      timestamp: "2026-03-03T08:00:00+00:00",
      items: [mockHistoryEntry.items[0]]
    };
    vi.mocked(fetchIngestHistory).mockResolvedValue({
      project_id: "p1",
      entries: [mockHistoryEntry, olderEntry]
    });

    render(<IngestTriageCard {...defaultProps()} />);

    await waitFor(() => {
      expect(screen.getByText(/4 arquivo/i)).toBeInTheDocument();
    });
  });

  it("shows LLM detail card when expanding a row with llm_explanation", async () => {
    const llmEntry = {
      ...mockHistoryEntry,
      items: [
        {
          ...mockHistoryEntry.items[0],
          rule_business_domain: "contratos_comunicacao",
          rule_confidence: 0.33,
          llm_explanation: "Resumo financeiro com EBITDA",
          business_domain: "financeiro",
          confidence_score: 0.85,
        }
      ]
    };
    const { fetchIngestHistory } = await import("../../api");
    vi.mocked(fetchIngestHistory).mockResolvedValue({
      project_id: "p1",
      entries: [llmEntry]
    });

    render(<IngestTriageCard {...defaultProps()} />);

    await waitFor(() => {
      expect(screen.getByText(/relatorio\.pdf/i)).toBeInTheDocument();
    });

    const row = screen.getByText(/relatorio\.pdf/i).closest("tr");
    expect(row).toBeTruthy();
    await act(async () => {
      fireEvent.click(row!);
    });

    await waitFor(() => {
      expect(screen.getByText(/Resumo financeiro com EBITDA/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Regra:/)).toBeInTheDocument();
  });

  it("shows LLM context on triage items without auto-create shortcut", async () => {
    const triageItems = [
      {
        doc_id: "t2",
        filename: "esg-report.pdf",
        project_id: "p1",
        suggested_business_domain: "contratos_comunicacao",
        confidence_score: 0.45,
        reason: "llm_review_divergence",
        top_candidates: [],
        source_path: "/p1/_TRIAGE_REVIEW/pending/esg-report.pdf",
        metadata_path: "/p1/_TRIAGE_REVIEW/pending/t2.json",
        llm_explanation: "Relatorio ESG sem area existente",
        llm_proposed_business_domain: "esg_sustentabilidade",
        rule_business_domain: "contratos_comunicacao",
        rule_confidence: 0.12,
      }
    ];
    render(<IngestTriageCard {...defaultProps({ triageItems })} />);

    await waitFor(() => {
      expect(screen.getByText(/esg-report\.pdf/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Relatorio ESG sem area existente/i)).toBeInTheDocument();
    expect(screen.getAllByText(/esg_sustentabilidade/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/Aprovar: esg_sustentabilidade/i)).not.toBeInTheDocument();
  });
});
