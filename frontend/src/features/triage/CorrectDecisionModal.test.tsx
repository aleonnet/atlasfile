/// <reference types="@testing-library/jest-dom/vitest" />
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CorrectDecisionModal } from "./CorrectDecisionModal";

describe("CorrectDecisionModal", () => {
  it("shows warnings when suggestions are outside the project catalog", () => {
    render(
      <CorrectDecisionModal
        item={{
          doc_id: "doc-1",
          filename: "arquivo.pdf",
          project_id: "proj-1",
          suggested_business_domain: "esg",
          suggested_document_type: "minuta",
          confidence_score: 0.42,
          reason: "llm_review_divergence",
          top_candidates: [],
          source_path: "/tmp/arquivo.pdf",
          metadata_path: "/tmp/doc-1.json",
          llm_proposed_area: "sustentabilidade",
        }}
        submitting={false}
        businessDomainValue="juridico"
        businessDomainOptions={[
          { key: "juridico", label: "Jurídico" },
          { key: "financeiro", label: "Financeiro" },
        ]}
        documentTypeValue="contrato"
        documentTypeOptions={[
          { key: "contrato", label: "Contrato" },
          { key: "relatorio", label: "Relatório" },
        ]}
        onChangeBusinessDomain={vi.fn()}
        onChangeDocumentType={vi.fn()}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    expect(screen.getByText(/A sugestão de domínio/i)).toBeInTheDocument();
    expect(screen.getByText(/O domínio proposto pelo LLM/i)).toBeInTheDocument();
    expect(screen.getByText(/O tipo documental sugerido/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Ou criar novo domínio/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Ou criar novo tipo/i)).not.toBeInTheDocument();
  });

  it("submits using only configured catalog values", () => {
    const onChangeBusinessDomain = vi.fn();
    const onChangeDocumentType = vi.fn();
    const onSubmit = vi.fn();

    render(
      <CorrectDecisionModal
        item={{
          doc_id: "doc-2",
          filename: "arquivo.pdf",
          project_id: "proj-1",
          confidence_score: 0.88,
          reason: "triage_pending",
          top_candidates: [],
          source_path: "/tmp/arquivo.pdf",
          metadata_path: "/tmp/doc-2.json",
        }}
        submitting={false}
        businessDomainValue="juridico"
        businessDomainOptions={[
          { key: "juridico", label: "Jurídico" },
          { key: "financeiro", label: "Financeiro" },
        ]}
        documentTypeValue="contrato"
        documentTypeOptions={[
          { key: "contrato", label: "Contrato" },
          { key: "relatorio", label: "Relatório" },
        ]}
        onChangeBusinessDomain={onChangeBusinessDomain}
        onChangeDocumentType={onChangeDocumentType}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />
    );

    fireEvent.change(screen.getByLabelText(/Domínio destino/i), { target: { value: "financeiro" } });
    fireEvent.change(screen.getByLabelText(/Tipo documental/i), { target: { value: "relatorio" } });
    fireEvent.click(screen.getByRole("button", { name: /Aprovar e mover/i }));

    expect(onChangeBusinessDomain).toHaveBeenCalledWith("financeiro");
    expect(onChangeDocumentType).toHaveBeenCalledWith("relatorio");
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});
