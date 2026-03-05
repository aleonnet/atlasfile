/// <reference types="@testing-library/jest-dom/vitest" />
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProfileLayoutWorkspace } from "./ProfileLayoutWorkspace";

const baseProfile = {
  profile_version: 2 as const,
  project_id: "proj1",
  project_label: "Projeto 1",
  project_root: "/tmp/proj1",
  paths: {
    inbox: "_INBOX_DROP",
    triage: {
      pending: "_TRIAGE_REVIEW/pending",
      resolved: "_TRIAGE_REVIEW/resolved",
      rejected: "_TRIAGE_REVIEW/rejected"
    }
  },
  layout: {
    mode: "para_jd",
    roots: {
      projects: "01_PROJECTS",
      areas: "02_AREAS",
      resources: "03_RESOURCES",
      archive: "04_ARCHIVE"
    },
    areas_root: "02_AREAS",
    area_folders: [{ area_key: "juridica", folder: "02_juridica" }]
  },
  classification: {
    work_areas: [{ key: "juridica", jd_number: 2, aliases: ["juridico"] }],
    routing_rules: [],
    confidence_thresholds: { auto_route_min: 0.85, triage_min: 0.5 },
    llm_policy: { enabled: false, provider: "openai", model: "gpt-4o-mini", mode: "tag_only", allow_override_fields: ["document_type", "tags", "confidence", "topics"], override_guardrails: { area_override_only_if_rule_confidence_below: 0.65, require_explanation: true, max_area_changes: 1 } }
  },
  indexing: {
    topics_path: "config/topics_v1.yaml",
    extraction_max_chars: 20000,
    extraction_mode: "excerpt" as const
  },
  version: 1
};

vi.mock("./api", () => ({
  getProfile: vi.fn(async () => ({ profile: baseProfile, etag: "etag-1", version: 1 })),
  getProfileHistory: vi.fn(async () => [{ entry: "h1", version: 1, updated_at: null, updated_by: "test", etag: "e1" }]),
  validateProfile: vi.fn(async (_projectRef: string, profile: unknown) => ({ valid: true, profile })),
  saveProfile: vi.fn(async () => ({ profile: { ...baseProfile, version: 2 }, etag: "etag-2", version: 2 })),
  planLayout: vi.fn(async () => ({
    plan_id: "plan-1",
    summary: { moves: 1, conflicts: 0, mkdirs: 1, ops: 2 },
    plan: {
      project_root: "/tmp/proj1",
      from_areas_root: "/tmp/proj1/02_AREAS",
      to_areas_root: "/tmp/proj1/02_AREAS",
      ops: [{ op: "move", src: "a", dst: "b", reason: "migrate" }],
      conflicts: 0,
      moves: 1,
      mkdirs: 1,
      strategy: "rename_with_suffix",
      cleanup_empty_dirs: false
    }
  })),
  applyLayout: vi.fn(async () => ({ ok: true }))
}));

describe("ProfileLayoutWorkspace", () => {
  it("mostra mensagem de projeto específico quando disabled", () => {
    render(<ProfileLayoutWorkspace projectRef="ALL_PROJECTS" disabled />);
    expect(screen.getByText(/Selecione um projeto específico/i)).toBeInTheDocument();
  });

  it("carrega, valida, planeja e aplica layout", async () => {
    const onStatus = vi.fn();
    const api = await import("./api");

    render(<ProfileLayoutWorkspace projectRef="proj1" onStatus={onStatus} />);

    await waitFor(() => {
      expect(screen.getByText(/Estrutura de Layout/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Validar/i }));
    await waitFor(() => {
      expect(vi.mocked(api.validateProfile)).toHaveBeenCalledWith("proj1", expect.any(Object));
    });
    expect(screen.getByText(/Profile válido/i)).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("02_juridica"), { target: { value: "99_juridica" } });
    fireEvent.click(screen.getByRole("button", { name: /Simular/i }));
    await waitFor(() => {
      expect(screen.getByText(/Preview: Plano de Migração/i)).toBeInTheDocument();
    });

    const confirmCheckbox = screen.getByLabelText(/Confirmo a aplicação do plano de layout/i);
    fireEvent.click(confirmCheckbox);
    fireEvent.click(screen.getByRole("button", { name: /Aplicar migração/i }));
    await waitFor(() => {
      expect(vi.mocked(api.applyLayout)).toHaveBeenCalled();
    });
    expect(onStatus).toHaveBeenCalledWith(expect.stringContaining("Layout aplicado"));
  });

  it("desabilita salvar quando não há mudança e habilita ao editar", async () => {
    render(<ProfileLayoutWorkspace projectRef="proj1" />);

    await waitFor(() => {
      expect(screen.getByText(/Estrutura de Layout/i)).toBeInTheDocument();
    });

    const saveButton = screen.getByRole("button", { name: /Salvar Profile/i });
    expect(saveButton).toBeDisabled();

    const projectLabelInput = screen.getByDisplayValue("Projeto 1");
    fireEvent.change(projectLabelInput, { target: { value: "Projeto 1 atualizado" } });
    expect(saveButton).not.toBeDisabled();
  });
});

