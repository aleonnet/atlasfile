import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LabelConflictsCard } from "./LabelConflictsCard";

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
}));

import { fetchLabelConflicts, resolveLabelConflict } from "../../api";

describe("LabelConflictsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("não renderiza nada sem conflitos", async () => {
    vi.mocked(fetchLabelConflicts).mockResolvedValue({ total: 0, items: [] });
    const { container } = render(<LabelConflictsCard />);
    await waitFor(() => expect(fetchLabelConflicts).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it("mostra conflito com fontes e proposta do LLM", async () => {
    vi.mocked(fetchLabelConflicts).mockResolvedValue({ total: 1, items: [mockConflict] });
    render(<LabelConflictsCard />);
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
    render(<LabelConflictsCard onResolved={onResolved} />);
    fireEvent.click(await screen.findByText("Aceitar proposta"));
    await waitFor(() =>
      expect(resolveLabelConflict).toHaveBeenCalledWith("abc123", "operacoes", "plano")
    );
    await waitFor(() => expect(screen.queryByText("Conflitos de rótulo")).not.toBeInTheDocument());
    expect(onResolved).toHaveBeenCalled();
  });

  it("corrigir permite escolher uma das fontes", async () => {
    vi.mocked(fetchLabelConflicts).mockResolvedValue({ total: 1, items: [mockConflict] });
    vi.mocked(resolveLabelConflict).mockResolvedValue({ status: "ok", labeled_by: "human" });
    render(<LabelConflictsCard />);
    fireEvent.click(await screen.findByText("Corrigir"));
    fireEvent.change(screen.getByLabelText("Rótulo canônico"), { target: { value: "operacoes/apresentacao" } });
    fireEvent.click(screen.getByText("Aplicar canônico"));
    await waitFor(() =>
      expect(resolveLabelConflict).toHaveBeenCalledWith("abc123", "operacoes", "apresentacao")
    );
  });
});
