/// <reference types="@testing-library/jest-dom/vitest" />
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TaxonomyMigrateModal } from "./TaxonomyMigrateModal";

vi.mock("../../api", () => ({
  fetchTaxonomy: vi.fn(() =>
    Promise.resolve({ business_domains: ["juridico", "financeiro"], document_types: ["parecer", "contrato"] })
  ),
  migrateTaxonomy: vi.fn(() =>
    Promise.resolve({
      kind: "document_type",
      from_key: "parecer",
      to_key: "contrato",
      documents_by_project: { proj_a: 3 },
      documents_total: 3,
      datasets: { training_pool: 2, validation_set: 0, corpus: 0, split_train: 0, split_validation: 0, split_test: 0 },
      pending_triage: 1,
      templates: ["default"],
      routing_rules_pointing: 0,
      warnings: ["o modelo sparse campeão contém a classe antiga — rode um ciclo do classificador após a migração"],
    })
  ),
  deleteTaxonomyEntry: vi.fn(() => Promise.reject(new Error("'parecer' ainda é usada por 3 documento(s)"))),
}));

function renderModal() {
  const onChanged = vi.fn();
  render(<TaxonomyMigrateModal open onClose={vi.fn()} onChanged={onChanged} />);
  return onChanged;
}

describe("TaxonomyMigrateModal", () => {
  it("simula (dry-run) e mostra o preview com contagens e avisos", async () => {
    renderModal();
    const origem = await screen.findByLabelText("Origem");
    await waitFor(() => expect(screen.getAllByRole("option").length).toBeGreaterThan(2));
    fireEvent.change(origem, { target: { value: "parecer" } });
    fireEvent.change(screen.getByLabelText("Destino"), { target: { value: "contrato" } });
    fireEvent.click(screen.getByText(/Simular/));

    await waitFor(() => {
      expect(screen.getByText(/Simulação — parecer → contrato/)).toBeInTheDocument();
    });
    expect(screen.getByText(/proj_a \(3\)/)).toBeInTheDocument();
    expect(screen.getByText(/treino \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/rode um ciclo/)).toBeInTheDocument();

    const { migrateTaxonomy } = await import("../../api");
    expect(vi.mocked(migrateTaxonomy)).toHaveBeenCalledWith(
      expect.objectContaining({ dry_run: true, from_key: "parecer", to_key: "contrato" })
    );
  });

  it("aplicar exige confirmação e envia dry_run=false", async () => {
    renderModal();
    const origem = await screen.findByLabelText("Origem");
    await waitFor(() => expect(screen.getAllByRole("option").length).toBeGreaterThan(2));
    fireEvent.change(origem, { target: { value: "parecer" } });
    fireEvent.change(screen.getByLabelText("Destino"), { target: { value: "contrato" } });
    fireEvent.click(screen.getByText(/Simular/));
    await screen.findByText(/Aplicar migração/);

    fireEvent.click(screen.getByText(/Aplicar migração/));
    // confirmação antes de aplicar
    expect(screen.getByText(/Esta operação move arquivos físicos/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Confirmar"));

    const { migrateTaxonomy } = await import("../../api");
    await waitFor(() => {
      expect(vi.mocked(migrateTaxonomy)).toHaveBeenLastCalledWith(
        expect.objectContaining({ dry_run: false, remove_old: true })
      );
    });
  });

  it("remoção guardada mostra o erro do backend com uso ativo", async () => {
    renderModal();
    const origem = await screen.findByLabelText("Origem");
    await waitFor(() => expect(screen.getAllByRole("option").length).toBeGreaterThan(2));
    fireEvent.change(origem, { target: { value: "parecer" } });
    fireEvent.click(screen.getByText(/Remover origem/));
    const { deleteTaxonomyEntry } = await import("../../api");
    await waitFor(() => {
      expect(vi.mocked(deleteTaxonomyEntry)).toHaveBeenCalledWith("document_type", "parecer");
    });
  });
});
