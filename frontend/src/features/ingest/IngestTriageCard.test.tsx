/// <reference types="@testing-library/jest-dom/vitest" />
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
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
      area_folders: []
    },
    classification: {
      work_areas: [],
      routing_rules: [],
      confidence_thresholds: { auto_route_min: 0.85, triage_min: 0.5 },
      llm_policy: {
        enabled: false,
        provider: "openai",
        model: "gpt-4o-mini",
        mode: "tag_only",
        allow_override_fields: ["document_type", "tags", "confidence", "topics"],
        override_guardrails: { area_override_only_if_rule_confidence_below: 0.65, require_explanation: true, max_area_changes: 1 }
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
    { doc_id: "d1", project_id: "p1", area_key: "fiscal", title: "relatorio", original_filename: "relatorio.pdf", canonical_filename: "relatorio.pdf", path: "/p1/02_AREAS/fiscal/relatorio.pdf", decision: "auto" as const, confidence_score: 0.92, sha256: "abc", tags: ["fiscal"] },
    { doc_id: "d2", project_id: "p1", area_key: "juridico", title: "contrato", original_filename: "contrato.docx", canonical_filename: "contrato.docx", path: "/p1/_TRIAGE_REVIEW/pending/contrato.docx", decision: "triage_pending" as const, confidence_score: 0.61, sha256: "def", tags: ["juridico"], topics_source: "llm_policy" },
    { doc_id: "d3", project_id: "p1", area_key: "unclassified", title: "duplicado", original_filename: "duplicado.pdf", canonical_filename: "", path: "/p1/_TRIAGE_REVIEW/rejected/duplicado.pdf", decision: "duplicate" as const, confidence_score: 0.0, sha256: "ghi", tags: [] }
  ],
  errors: []
};

const mockHistoryEntry = {
  timestamp: "2026-03-04T10:00:00+00:00",
  ...mockScanResult
};

vi.mock("../../api", () => ({
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
    const toggle = screen.getByRole("button", { name: /Ativar classificação LLM/i });
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
      const toggle = screen.getByRole("button", { name: /Ativar classificação LLM/i });
      fireEvent.click(toggle);
    });

    const { updateProjectProfile } = await import("../../api");
    await waitFor(() => {
      expect(vi.mocked(updateProjectProfile)).toHaveBeenCalled();
    });

    expect(screen.getByLabelText(/Modo/i)).toBeInTheDocument();
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
        suggested_area: "fiscal",
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
    expect(screen.getByText("Área / Pasta")).toBeInTheDocument();
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
          rule_area_key: "contratos_comunicacao",
          rule_confidence: 0.33,
          llm_explanation: "Resumo financeiro com EBITDA",
          area_key: "financeiro",
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

  it("shows LLM context and approve-with-proposed-area button on triage items", async () => {
    const triageItems = [
      {
        doc_id: "t2",
        filename: "esg-report.pdf",
        project_id: "p1",
        suggested_area: "contratos_comunicacao",
        confidence_score: 0.45,
        reason: "llm_review_divergence",
        top_candidates: [],
        source_path: "/p1/_TRIAGE_REVIEW/pending/esg-report.pdf",
        metadata_path: "/p1/_TRIAGE_REVIEW/pending/t2.json",
        llm_explanation: "Relatorio ESG sem area existente",
        llm_proposed_area: "esg_sustentabilidade",
        rule_area_key: "contratos_comunicacao",
        rule_confidence: 0.12,
      }
    ];
    render(<IngestTriageCard {...defaultProps({ triageItems })} />);

    await waitFor(() => {
      expect(screen.getByText(/esg-report\.pdf/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Relatorio ESG sem area existente/i)).toBeInTheDocument();
    expect(screen.getAllByText(/esg_sustentabilidade/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Aprovar: esg_sustentabilidade/i)).toBeInTheDocument();
  });
});
