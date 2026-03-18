/// <reference types="@testing-library/jest-dom/vitest" />
import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { TemplateEditorView } from "./TemplateEditorView";
import { saveTemplate } from "../../api";

const fullProfile = {
  profile_version: 2,
  project_id: "__PROJECT_ID__",
  project_label: "__PROJECT_LABEL__",
  project_root: "__PROJECT_ROOT__",
  paths: { inbox: "_INBOX_DROP", triage: { pending: "_TRIAGE_REVIEW/pending", resolved: "_TRIAGE_REVIEW/resolved", rejected: "_TRIAGE_REVIEW/rejected" } },
  layout: {
    mode: "para_jd",
    roots: { projects: "01_PROJECTS", areas: "02_AREAS", resources: "03_RESOURCES", archive: "04_ARCHIVE" },
    areas_root: "02_AREAS",
    area_folders: [{ area_key: "fiscal", folder: "11_Fiscal" }, { area_key: "juridico", folder: "12_Juridico" }],
    business_domain_folders: [{ business_domain: "fiscal", folder: "11_Fiscal" }, { business_domain: "juridico", folder: "12_Juridico" }],
  },
  classification: {
    work_areas: [
      { key: "fiscal", jd_number: 11, aliases: ["tributario", "impostos"] },
      { key: "juridico", jd_number: 12, aliases: ["legal", "contratos"] },
    ],
    business_domains: [
      { key: "fiscal", label: "Fiscal", aliases: ["tributario", "impostos"], primary_scope: "Fiscal primary scope", subfunction_topics: ["tax_topic"] },
      { key: "juridico", label: "Jurídico", aliases: ["legal", "contratos"], primary_scope: "Legal primary scope", subfunction_topics: ["legal_topic"] },
    ],
    document_types: [
      {
        key: "relatorio",
        label: "Relatório",
        aliases: ["relatorio", "report"],
        extensions: [".pdf"],
        folder: "relatorio",
        extension_confidence_by_extension: {},
        fallback_priority: 10,
        detection_rules: [{ any_of: ["relatorio"], confidence: 0.9, reason: "structural_header" }],
      },
    ],
    document_type_priors: { relatorio: { default: "fiscal", weight: 0.4 } },
    entity_domain_affinity: { imposto: { domain: "fiscal", weight: 0.6 } },
    context_boosts: [{ business_domain: "fiscal", document_types: ["relatorio"], any_of: ["tributario"], weight: 0.2 }],
    thresholds: {
      document_type_extension_bonus: 0.08,
      document_type_alias_confidence_base: 0.35,
      document_type_alias_confidence_scale: 0.6,
      document_type_confidence_cap: 0.96,
      document_type_best_effort_confidence: 0.25,
      business_domain_lexical_scale: 0.75,
      business_domain_lexical_cap: 0.85,
      business_domain_context_boost_cap: 0.35,
      business_domain_alias_fallback_confidence: 0.2,
      business_domain_best_effort_confidence: 0.05,
      entity_boost_profiles: { default: { cap: 0.45, scale: 0.5 } },
    },
    routing_rules: [
      { when_filename_contains: ["contrato", "aditivo"], route_to: "juridico", confidence: 0.9 },
      { when_path_contains: ["output/"], route_to: "fiscal", confidence: 0.98 },
    ],
    confidence_thresholds: { auto_route_min: 0.85, triage_min: 0.5 },
    llm_policy: {
      enabled: true,
      provider: "openai",
      model: "gpt-4.1-mini",
      mode: "tag_only",
      allow_override_fields: ["document_type", "tags", "confidence", "topics"],
      override_guardrails: { area_override_only_if_rule_confidence_below: 0.65, require_explanation: true, max_area_changes: 1 },
    },
  },
  indexing: { topics_path: "config/topics_v1.yaml", extraction_max_chars: 50000, extraction_mode: "all" },
  version: 1,
};

const mockTemplateList = [
  { slug: "default", name: "M&A / Carve-out", description: "Template padrão", areas_count: 2, updated_at: "2026-03-04T10:00:00Z", source: "builtin" as const },
];

const mockTemplateData = {
  ...mockTemplateList[0],
  profile: fullProfile,
};

vi.mock("../../api", () => ({
  listTemplates: vi.fn(() => Promise.resolve(mockTemplateList)),
  getTemplate: vi.fn(() => Promise.resolve(mockTemplateData)),
  saveTemplate: vi.fn(() => Promise.resolve(mockTemplateList[0])),
  createTemplate: vi.fn(() => Promise.resolve(mockTemplateList[0])),
  deleteTemplate: vi.fn(() => Promise.resolve()),
}));

async function openEditor() {
  await act(async () => {
    render(<TemplateEditorView />);
  });
  await waitFor(() => expect(screen.getByText("M&A / Carve-out")).toBeInTheDocument());
  await act(async () => {
    fireEvent.click(screen.getByText("Editar"));
  });
  await waitFor(() => expect(screen.getByLabelText("Editar template")).toBeInTheDocument());
}

describe("TemplateEditorView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders template list on mount", async () => {
    await act(async () => {
      render(<TemplateEditorView />);
    });
    await waitFor(() => {
      expect(screen.getByText("M&A / Carve-out")).toBeInTheDocument();
      expect(screen.getByText("builtin")).toBeInTheDocument();
    });
  });

  it("opens editor modal with the simplified operator surface", async () => {
    await openEditor();
    expect(screen.getByText("Naming (formato canônico)")).toBeInTheDocument();
    expect(screen.getByText("Estrutura de Layout")).toBeInTheDocument();
    expect(screen.getByText("Tipos documentais")).toBeInTheDocument();
    expect(screen.getByText("Catálogo de entidades")).toBeInTheDocument();
    expect(screen.getByText("Indexação")).toBeInTheDocument();
  });

  describe("Indexação section", () => {
    it("displays topics path, max chars, and extraction mode", async () => {
      await openEditor();
      const section = screen.getByText("Indexação").closest("details")!;
      fireEvent.click(within(section).getByText("Indexação"));
      const topicsInput = within(section).getByLabelText("Topics path") as HTMLInputElement;
      expect(topicsInput.value).toBe("config/topics_v1.yaml");
      const maxCharsInput = within(section).getByLabelText("Max chars extração") as HTMLInputElement;
      expect(maxCharsInput.value).toBe("50000");
      const modeSelect = within(section).getByLabelText("Modo extração") as HTMLSelectElement;
      expect(modeSelect.value).toBe("all");
    });

    it("updates extraction mode", async () => {
      await openEditor();
      const section = screen.getByText("Indexação").closest("details")!;
      fireEvent.click(within(section).getByText("Indexação"));
      const modeSelect = within(section).getByLabelText("Modo extração") as HTMLSelectElement;
      await act(async () => {
        fireEvent.change(modeSelect, { target: { value: "excerpt" } });
      });
      expect(modeSelect.value).toBe("excerpt");
    });
  });

  it("adds entries to the optional entity catalog", async () => {
    await openEditor();
    const section = screen.getByText("Catálogo de entidades").closest("details")!;
    fireEvent.click(within(section).getByText("Catálogo de entidades"));

    await act(async () => {
      fireEvent.click(within(section).getByText("+ Adicionar entidade"));
    });

    await waitFor(() => {
      expect(within(section).getByText("1 entidades")).toBeInTheDocument();
    });
  });

  it("saves only the minimal human contract and strips legacy/operator-heavy fields", async () => {
    await openEditor();
    const section = screen.getByText("Estrutura de Layout").closest("details")!;
    const fiscalKeyInput = within(section).getByDisplayValue("fiscal");
    const fiscalRow = fiscalKeyInput.closest("tr");
    expect(fiscalRow).not.toBeNull();
    const fiscalLabelInput = within(fiscalRow as HTMLTableRowElement).getByDisplayValue("Fiscal") as HTMLInputElement;

    await act(async () => {
      fireEvent.change(fiscalLabelInput, { target: { value: "Fiscal Atualizado" } });
      fireEvent.click(screen.getByText("Salvar template"));
    });

    await waitFor(() => expect(saveTemplate).toHaveBeenCalled());
    const payload = vi.mocked(saveTemplate).mock.calls[0][1] as Record<string, unknown>;
    const classification = payload.classification as Record<string, unknown>;
    const layout = payload.layout as Record<string, unknown>;
    const savedDomains = classification.business_domains as Array<Record<string, unknown>>;
    const fiscalDomain = savedDomains.find((row) => row.key === "fiscal");

    expect(fiscalDomain?.label).toBe("Fiscal Atualizado");
    expect(fiscalDomain?.primary_scope).toBe("Fiscal primary scope");
    expect(fiscalDomain?.subfunction_topics).toEqual(["tax_topic"]);
    expect(classification).not.toHaveProperty("work_areas");
    expect(classification).not.toHaveProperty("document_type_priors");
    expect(classification).not.toHaveProperty("entity_domain_affinity");
    expect(classification).not.toHaveProperty("context_boosts");
    expect(classification).not.toHaveProperty("thresholds");
    expect(classification).not.toHaveProperty("routing_rules");
    expect(classification).not.toHaveProperty("confidence_thresholds");
    expect(classification).not.toHaveProperty("llm_policy");
    expect(layout).not.toHaveProperty("area_folders");
    expect(layout).toHaveProperty("business_domain_folders");
  });
});
