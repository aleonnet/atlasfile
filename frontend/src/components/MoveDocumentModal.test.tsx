import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MoveDocumentModal } from "./MoveDocumentModal";
import type { ProjectArea, ProjectDocumentType } from "../types";

const bdOptions: ProjectArea[] = [
  { key: "fiscal", label: "Fiscal" },
  { key: "juridico", label: "Jurídico" },
  { key: "operacoes", label: "Operações" },
];

const dtOptions: ProjectDocumentType[] = [
  { key: "contrato", label: "Contrato" },
  { key: "parecer", label: "Parecer" },
  { key: "relatorio", label: "Relatório" },
];

describe("MoveDocumentModal", () => {
  it("does not render when open is false", () => {
    const { container } = render(
      <MoveDocumentModal
        open={false}
        filename="doc.pdf"
        currentBusinessDomain="fiscal"
        currentDocumentType="contrato"
        businessDomainOptions={bdOptions}
        documentTypeOptions={dtOptions}
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders document info and selectors when open", () => {
    render(
      <MoveDocumentModal
        open={true}
        filename="doc.pdf"
        currentBusinessDomain="fiscal"
        currentDocumentType="contrato"
        businessDomainOptions={bdOptions}
        documentTypeOptions={dtOptions}
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );
    expect(screen.getByText("doc.pdf")).toBeTruthy();
    expect(screen.getByText(/fiscal \/ contrato/)).toBeTruthy();
    expect(screen.getByLabelText("Domínio destino")).toBeTruthy();
    expect(screen.getByLabelText("Tipo documental destino")).toBeTruthy();
  });

  it("confirm button is disabled when destination equals origin", () => {
    render(
      <MoveDocumentModal
        open={true}
        filename="doc.pdf"
        currentBusinessDomain="fiscal"
        currentDocumentType="contrato"
        businessDomainOptions={bdOptions}
        documentTypeOptions={dtOptions}
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );
    const btn = screen.getByText("Confirmar");
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("calls onConfirm with selected values when changed and confirmed", () => {
    const onConfirm = vi.fn();
    render(
      <MoveDocumentModal
        open={true}
        filename="doc.pdf"
        currentBusinessDomain="fiscal"
        currentDocumentType="contrato"
        businessDomainOptions={bdOptions}
        documentTypeOptions={dtOptions}
        onCancel={() => {}}
        onConfirm={onConfirm}
      />
    );
    fireEvent.change(screen.getByLabelText("Domínio destino"), { target: { value: "juridico" } });
    fireEvent.change(screen.getByLabelText("Tipo documental destino"), { target: { value: "parecer" } });

    const btn = screen.getByText("Confirmar");
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(btn);

    expect(onConfirm).toHaveBeenCalledWith("juridico", "parecer");
  });

  it("shows move summary when destination differs from origin", () => {
    render(
      <MoveDocumentModal
        open={true}
        filename="doc.pdf"
        currentBusinessDomain="fiscal"
        currentDocumentType="contrato"
        businessDomainOptions={bdOptions}
        documentTypeOptions={dtOptions}
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );
    fireEvent.change(screen.getByLabelText("Domínio destino"), { target: { value: "juridico" } });
    expect(screen.getByText(/Mover de/)).toBeTruthy();
  });

  it("calls onCancel when cancel button clicked", () => {
    const onCancel = vi.fn();
    render(
      <MoveDocumentModal
        open={true}
        filename="doc.pdf"
        currentBusinessDomain="fiscal"
        currentDocumentType="contrato"
        businessDomainOptions={bdOptions}
        documentTypeOptions={dtOptions}
        onCancel={onCancel}
        onConfirm={() => {}}
      />
    );
    fireEvent.click(screen.getByText("Cancelar"));
    expect(onCancel).toHaveBeenCalled();
  });
});
