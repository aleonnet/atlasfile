/// <reference types="@testing-library/jest-dom/vitest" />
import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { TemplateEditorView } from "./TemplateEditorView";

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
  },
  classification: {
    work_areas: [
      { key: "fiscal", jd_number: 11, aliases: ["tributario", "impostos"] },
      { key: "juridico", jd_number: 12, aliases: ["legal", "contratos"] },
    ],
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

const mockModels = [
  { provider: "openai", model: "gpt-4o-mini", label: "OpenAI gpt-4o-mini (base)" },
  { provider: "openai", model: "gpt-4.1", label: "OpenAI gpt-4.1 (médio)" },
  { provider: "openai", model: "gpt-4.1-mini", label: "OpenAI gpt-4.1-mini" },
  { provider: "anthropic", model: "claude-sonnet-4-6", label: "Anthropic Claude Sonnet 4.6 (médio)" },
];

vi.mock("../../api", () => ({
  listTemplates: vi.fn(() => Promise.resolve(mockTemplateList)),
  getTemplate: vi.fn(() => Promise.resolve(mockTemplateData)),
  saveTemplate: vi.fn(() => Promise.resolve(mockTemplateList[0])),
  createTemplate: vi.fn(() => Promise.resolve(mockTemplateList[0])),
  deleteTemplate: vi.fn(() => Promise.resolve()),
  fetchModels: vi.fn(() => Promise.resolve(mockModels)),
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

  it("opens editor modal with all 5 collapsible sections", async () => {
    await openEditor();
    expect(screen.getByText("Estrutura de Layout")).toBeInTheDocument();
    expect(screen.getByText("Routing Rules")).toBeInTheDocument();
    expect(screen.getByText("Confidence Thresholds")).toBeInTheDocument();
    expect(screen.getByText("LLM Policy")).toBeInTheDocument();
    expect(screen.getByText("Indexação")).toBeInTheDocument();
  });

  describe("Routing Rules section", () => {
    it("displays existing rules in the table", async () => {
      await openEditor();
      const section = screen.getByText("Routing Rules").closest("details")!;
      fireEvent.click(within(section).getByText("Routing Rules"));
      await waitFor(() => {
        expect(within(section).getByText("2 regras")).toBeInTheDocument();
      });
    });

    it("adds a new rule via button", async () => {
      await openEditor();
      const section = screen.getByText("Routing Rules").closest("details")!;
      fireEvent.click(within(section).getByText("Routing Rules"));
      await act(async () => {
        fireEvent.click(within(section).getByText("+ Adicionar regra"));
      });
      await waitFor(() => {
        expect(within(section).getByText("3 regras")).toBeInTheDocument();
      });
    });
  });

  describe("Confidence Thresholds section", () => {
    it("shows numeric inputs with default values", async () => {
      await openEditor();
      const section = screen.getByText("Confidence Thresholds").closest("details")!;
      fireEvent.click(within(section).getByText("Confidence Thresholds"));
      const autoInput = within(section).getByLabelText("Auto-route mínimo") as HTMLInputElement;
      const triageInput = within(section).getByLabelText("Triage mínimo") as HTMLInputElement;
      expect(autoInput.value).toBe("0.85");
      expect(triageInput.value).toBe("0.5");
    });

    it("updates threshold values", async () => {
      await openEditor();
      const section = screen.getByText("Confidence Thresholds").closest("details")!;
      fireEvent.click(within(section).getByText("Confidence Thresholds"));
      const autoInput = within(section).getByLabelText("Auto-route mínimo") as HTMLInputElement;
      await act(async () => {
        fireEvent.change(autoInput, { target: { value: "0.9" } });
      });
      expect(autoInput.value).toBe("0.9");
    });
  });

  describe("LLM Policy section", () => {
    it("displays toggle, combined model select, and mode select", async () => {
      await openEditor();
      const section = screen.getByText("LLM Policy").closest("details")!;
      fireEvent.click(within(section).getByText("LLM Policy"));
      expect(within(section).getByText("ativado")).toBeInTheDocument();
      expect(within(section).getByLabelText("Ativar LLM")).toBeInTheDocument();
      const modelSelect = within(section).getByLabelText("Modelo") as HTMLSelectElement;
      expect(modelSelect.value).toBe("openai/gpt-4.1-mini");
      const modeSelect = within(section).getByLabelText("Modo") as HTMLSelectElement;
      expect(modeSelect.value).toBe("tag_only");
    });

    it("toggles LLM enabled state", async () => {
      await openEditor();
      const section = screen.getByText("LLM Policy").closest("details")!;
      fireEvent.click(within(section).getByText("LLM Policy"));
      const toggle = within(section).getByLabelText("Ativar LLM");
      expect(toggle.className).toContain("active");
      await act(async () => {
        fireEvent.click(toggle);
      });
      expect(toggle.className).not.toContain("active");
    });

    it("shows guardrails sub-section", async () => {
      await openEditor();
      const section = screen.getByText("LLM Policy").closest("details")!;
      fireEvent.click(within(section).getByText("LLM Policy"));
      expect(within(section).getByText("Guardrails")).toBeInTheDocument();
      expect(within(section).getByText("Exigir explicação")).toBeInTheDocument();
      const maxChanges = within(section).getByLabelText("Max area changes") as HTMLInputElement;
      expect(maxChanges.value).toBe("1");
    });
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
});
