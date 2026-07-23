/// <reference types="@testing-library/jest-dom/vitest" />
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IngestTriageCard } from "./IngestTriageCard";
import { renderWithProviders } from "../../test/utils";

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
  fetchDatasetReadiness: vi.fn(() => Promise.resolve({ cycle_ready: true, splits_available: false, validation: { labeled: 3, unlabeled: 0 }, training: { records: 12, business_domain_classes: {}, document_type_classes: {} }, supervised_gate: { eligible: false, reasons: [], warnings: [] }, holdout: { enabled: true, modulus: 5, min_train_per_class: 3 }, blockers: [], suggestions: [] })),
  fetchModels: vi.fn(() =>
    Promise.resolve([
      { provider: "openai", model: "gpt-4o-mini", label: "OpenAI gpt-4o-mini (base)" },
      { provider: "openai", model: "gpt-4.1", label: "OpenAI gpt-4.1 (médio)" }
    ])
  ),
  fetchAliasSuggestions: vi.fn(() =>
    Promise.resolve({
      suggestions: [
        {
          kind: "business_domain",
          key: "juridico",
          label: "Jurídico",
          terms: [{ term: "escritura", support: 2, precision: 1.0, sample_docs: ["a.txt", "b.txt"] }]
        }
      ],
      corpus: { resolved_total: 4, analyzed_total: 4, corrected_total: 2, distinct_labels: 2 }
    })
  ),
  addTaxonomyAliases: vi.fn(() =>
    Promise.resolve({ status: "ok", key: "juridico", aliases: ["escritura"], updated_projects: ["p1"] })
  ),
  dismissAliasSuggestion: vi.fn(() => Promise.resolve({ status: "ok", dismissed: ["business_domain:juridico:escritura"] }))
}));

function defaultProps(overrides: Partial<React.ComponentProps<typeof IngestTriageCard>> = {}) {
  return {
    selectedProject: "p1",
    selectedProjectLabel: "Projeto 1",
    triageItems: [],
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

  it("renders header without operational scan button (config-only card)", async () => {
    renderWithProviders(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/^Classificador$/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Processar INBOX/i)).not.toBeInTheDocument();
  });

  it("shows Classificação LLM collapsible for single project", async () => {
    renderWithProviders(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Classificação LLM/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/desativado/i)).toBeInTheDocument();
  });

  it("renders classifier section with benchmark summary", async () => {
    renderWithProviders(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Classificador operacional/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Benchmark oficial/i)).toBeInTheDocument();
    expect(screen.getAllByText(/bootstrap/i).length).toBeGreaterThan(0);
  });

  it("mostra sugestões de aliases mineradas e aprova com um clique", async () => {
    const api = await import("../../api");
    const onStatus = vi.fn();
    renderWithProviders(<IngestTriageCard {...defaultProps({ onStatus })} />);
    await waitFor(() => {
      expect(screen.getByText(/Sugestões de aliases/i)).toBeInTheDocument();
    });
    expect(screen.getByText("escritura")).toBeInTheDocument();
    expect(screen.getByText(/2 docs · precisão/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Aprovar/i }));
    await waitFor(() => {
      expect(api.addTaxonomyAliases).toHaveBeenCalledWith({
        kind: "business_domain",
        key: "juridico",
        aliases: ["escritura"],
        created_from: "alias-suggest:p1",
      });
    });
    expect(onStatus).toHaveBeenCalledWith(expect.stringContaining("escritura"));
  });

  it("dispensa uma sugestão sem aplicá-la", async () => {
    const api = await import("../../api");
    renderWithProviders(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText("escritura")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /Dispensar/i }));
    await waitFor(() => {
      expect(api.dismissAliasSuggestion).toHaveBeenCalledWith("p1", {
        kind: "business_domain",
        key: "juridico",
        term: "escritura",
      });
    });
    expect(api.addTaxonomyAliases).not.toHaveBeenCalled();
  });

  // Fica por último entre os testes de alias: o mockResolvedValue substitui o
  // default da factory para o restante do arquivo (clearAllMocks não restaura)
  it("sem sugestões a seção explica o pré-requisito em vez de sumir (v0.39.2)", async () => {
    const api = await import("../../api");
    // 2 correções, mas todos os docs com o MESMO rótulo final → sem contraste
    vi.mocked(api.fetchAliasSuggestions).mockResolvedValue({
      suggestions: [],
      corpus: { resolved_total: 2, analyzed_total: 2, corrected_total: 2, distinct_labels: 1 },
    });
    renderWithProviders(<IngestTriageCard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Sugestões de aliases/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/2 correções registradas — aguardando documentos de outras classes/)).toBeInTheDocument();
  });

  it("shows empty state when all projects selected", async () => {
    renderWithProviders(<IngestTriageCard {...defaultProps({ selectedProject: "__all__" })} />);
    await waitFor(() => {
      expect(screen.getByText(/Nenhum projeto selecionado/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Classificação LLM/i)).not.toBeInTheDocument();
  });

  it("toggles LLM and opens settings modal when no key", async () => {
    const onOpenSettings = vi.fn();
    renderWithProviders(
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
    renderWithProviders(<IngestTriageCard {...defaultProps()} />);
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
    renderWithProviders(<IngestTriageCard {...defaultProps()} />);
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

  it("updates the classifier cycle to completion without needing reload", async () => {
    const originalEventSource = window.EventSource;
    Object.defineProperty(window, "EventSource", { configurable: true, value: undefined });
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
      const { fetchClassifierCycleStatus, startClassifierCycle } = await import("../../api");
      vi.mocked(fetchClassifierCycleStatus).mockResolvedValue(completedCycle);
      vi.mocked(fetchClassifierCycleStatus)
        .mockResolvedValueOnce(idleCycle)
        .mockResolvedValueOnce(runningCycle);

      renderWithProviders(<IngestTriageCard {...defaultProps()} />);
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
      const { fetchClassifierCycleStatus } = await import("../../api");
      vi.mocked(fetchClassifierCycleStatus).mockResolvedValue(idleCycle);
      Object.defineProperty(window, "EventSource", { configurable: true, value: originalEventSource });
    }
  });

  // History table tests moved to IngestHistoryCard

});
