import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LabelConflictsCard } from "./LabelConflictsCard";
import { renderWithProviders } from "../../test/utils";

const mockConflict = {
  sha256: "abc123",
  refs: ["v070/operacoes/contrato/20260318__taxonomia_e2e_v070__Plano Twist2__v01.pdf"],
  canonical_business_domain: "",
  canonical_document_type: "",
  labeled_by: "pending_human",
  llm_proposal: {
    business_domain: "operacoes",
    document_type: "plano",
    confidence: 0.93,
    justificativa: "Plano de trabalho com cronograma e governança.",
  },
  sources: [
    { source: "project_tree", ref: "v070/x.pdf", business_domain: "operacoes", document_type: "contrato", authoritative: false },
    { source: "project_tree", ref: "v080/x.pdf", business_domain: "operacoes", document_type: "apresentacao", authoritative: false },
  ],
};

vi.mock("../../api", () => ({
  fetchLabelConflicts: vi.fn(),
  resolveLabelConflict: vi.fn(),
  fetchTaxonomy: vi.fn(),
  createTaxonomyEntry: vi.fn(),
}));

import { createTaxonomyEntry, fetchLabelConflicts, fetchTaxonomy, resolveLabelConflict } from "../../api";

const TAXONOMY = {
  business_domains: ["operacoes", "juridico", "societario"],
  document_types: ["contrato", "apresentacao", "plano"],
};

describe("LabelConflictsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchTaxonomy).mockResolvedValue(TAXONOMY);
  });

  it("não renderiza nada sem conflitos", async () => {
    vi.mocked(fetchLabelConflicts).mockResolvedValue({ total: 0, items: [] });
    const { container } = renderWithProviders(<LabelConflictsCard />);
    await waitFor(() => expect(fetchLabelConflicts).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it("mostra conflito com fontes e proposta do LLM", async () => {
    vi.mocked(fetchLabelConflicts).mockResolvedValue({ total: 1, items: [mockConflict] });
    renderWithProviders(<LabelConflictsCard />);
    expect(await screen.findByText("Conflitos de rótulo")).toBeInTheDocument();
    expect(screen.getByText("Plano Twist2.pdf")).toBeInTheDocument();
    expect(screen.getByText("operacoes/contrato")).toBeInTheDocument();
    expect(screen.getByText("operacoes/apresentacao")).toBeInTheDocument();
    expect(screen.getByText("operacoes/plano")).toBeInTheDocument();
    expect(screen.getByText(/Plano de trabalho com cronograma/)).toBeInTheDocument();
  });

  it("aceitar proposta resolve com os rótulos do LLM e remove o item", async () => {
    vi.mocked(fetchLabelConflicts).mockResolvedValue({ total: 1, items: [mockConflict] });
    vi.mocked(resolveLabelConflict).mockResolvedValue({ status: "ok", labeled_by: "human_confirmed_llm" });
    const onResolved = vi.fn();
    renderWithProviders(<LabelConflictsCard onResolved={onResolved} />);
    // após resolver, o backend deixa de listar o conflito — o refetch da
    // invalidation traz a lista vazia (era remoção otimista local antes)
    fireEvent.click(await screen.findByText("Aceitar proposta"));
    vi.mocked(fetchLabelConflicts).mockResolvedValue({ total: 0, items: [] });
    await waitFor(() =>
      expect(resolveLabelConflict).toHaveBeenCalledWith("abc123", "operacoes", "plano")
    );
    await waitFor(() => expect(screen.queryByText("Conflitos de rótulo")).not.toBeInTheDocument());
    expect(onResolved).toHaveBeenCalled();
  });

  it("corrigir permite escolher uma das fontes", async () => {
    vi.mocked(fetchLabelConflicts).mockResolvedValue({ total: 1, items: [mockConflict] });
    vi.mocked(resolveLabelConflict).mockResolvedValue({ status: "ok", labeled_by: "human" });
    renderWithProviders(<LabelConflictsCard />);
    fireEvent.click(await screen.findByText("Corrigir"));
    fireEvent.change(screen.getByLabelText("Rótulo canônico"), { target: { value: "operacoes/apresentacao" } });
    fireEvent.click(screen.getByText("Aplicar canônico"));
    await waitFor(() =>
      expect(resolveLabelConflict).toHaveBeenCalledWith("abc123", "operacoes", "apresentacao")
    );
  });

  it("escolha fora da taxonomia abre o fluxo de criação e cria antes de resolver", async () => {
    const conflictNovoTipo = {
      ...mockConflict,
      llm_proposal: { ...mockConflict.llm_proposal, document_type: "memorando" },
    };
    vi.mocked(fetchLabelConflicts).mockResolvedValue({ total: 1, items: [conflictNovoTipo] });
    vi.mocked(createTaxonomyEntry).mockResolvedValue({ status: "ok", key: "memorando", updated_projects: ["p1"] });
    vi.mocked(resolveLabelConflict).mockResolvedValue({ status: "ok", labeled_by: "human_confirmed_llm" });
    renderWithProviders(<LabelConflictsCard />);

    expect(await screen.findByText(/usa taxonomia nova/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Aceitar proposta"));

    // diálogo de criação aparece com o tipo faltante
    expect(await screen.findByText("Criar no template e aplicar")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Aliases/), { target: { value: "memorando, memo" } });
    fireEvent.click(screen.getByText("Criar e aplicar"));

    await waitFor(() =>
      expect(createTaxonomyEntry).toHaveBeenCalledWith(
        expect.objectContaining({ kind: "document_type", key: "memorando", aliases: ["memorando", "memo"] })
      )
    );
    await waitFor(() =>
      expect(resolveLabelConflict).toHaveBeenCalledWith("abc123", "operacoes", "memorando")
    );
  });
});
