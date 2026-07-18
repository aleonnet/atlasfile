import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TriageItem } from "../../types";
import { TriageQueue } from "./TriageQueue";

const baseItem: TriageItem = {
  doc_id: "t1",
  filename: "documento_ambiguo.docx",
  project_id: "p1",
  suggested_business_domain: "juridico",
  suggested_document_type: "contrato",
  suggested_path: null,
  confidence_score: 0.42,
  business_domain_confidence: 0.5,
  document_type_confidence: 0.4,
  reason: "low_confidence",
  top_candidates: [],
  top_document_type_candidates: [],
  source_path: "/p1/_TRIAGE_REVIEW/pending/doc.docx",
  metadata_path: "/p1/_TRIAGE_REVIEW/pending/doc.json",
  classifier_mode: "bootstrap",
  classifier_requested_mode: null,
  classifier_fallback_reason: null,
  llm_explanation: null,
  llm_proposed_business_domain: null,
  rule_business_domain: null,
  rule_confidence: null,
};

describe("TriageQueue", () => {
  it("não renderiza nada sem pendências", () => {
    const { container } = render(
      <TriageQueue triageItems={[]} projectLabelById={new Map()} onDecision={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renderiza item com sugestão, scores e dispara as três decisões", async () => {
    const onDecision = vi.fn();
    render(
      <TriageQueue
        triageItems={[baseItem]}
        projectLabelById={new Map([["p1", "Projeto 1"]])}
        onDecision={onDecision}
      />
    );

    expect(screen.getByText("Triagem pendente")).toBeInTheDocument();
    expect(screen.getByText("documento_ambiguo.docx")).toBeInTheDocument();
    expect(screen.getByText(/Projeto 1/)).toBeInTheDocument();
    expect(screen.getByText(/domínio 50.0%/)).toBeInTheDocument();

    // O guard anti duplo-clique bloqueia decisões enquanto uma está em voo —
    // aguardar cada decisão concluir antes do próximo clique
    fireEvent.click(screen.getByRole("button", { name: /Aprovar/ }));
    await waitFor(() => expect(onDecision).toHaveBeenNthCalledWith(1, baseItem, "approve"));
    fireEvent.click(screen.getByRole("button", { name: /Corrigir/ }));
    await waitFor(() => expect(onDecision).toHaveBeenNthCalledWith(2, baseItem, "correct"));
    fireEvent.click(screen.getByRole("button", { name: /Rejeitar/ }));
    await waitFor(() => expect(onDecision).toHaveBeenNthCalledWith(3, baseItem, "reject"));
  });

  it("desabilita Aprovar sem sugestão de domínio", () => {
    render(
      <TriageQueue
        triageItems={[{ ...baseItem, suggested_business_domain: null }]}
        projectLabelById={new Map()}
        onDecision={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: /Aprovar/ })).toBeDisabled();
  });
});
