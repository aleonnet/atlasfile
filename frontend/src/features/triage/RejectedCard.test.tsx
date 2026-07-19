import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { emitDataRefresh } from "../../lib/refreshBus";
import { RejectedCard } from "./RejectedCard";

vi.mock("../../api", () => ({
  fetchRejectedTriage: vi.fn(),
  restoreRejectedTriage: vi.fn(() => Promise.resolve({ status: "restored" })),
  deleteRejectedTriage: vi.fn(() => Promise.resolve({ status: "deleted" })),
}));

import { deleteRejectedTriage, fetchRejectedTriage, restoreRejectedTriage } from "../../api";

const rejectedItem = {
  doc_id: "abc123",
  original_filename: "contrato_ruim.pdf",
  decision: "rejected",
  decision_note: "",
  processed_at: "2026-07-17T18:00:00",
  suggested_business_domain: "juridico",
  suggested_document_type: "contrato",
  file_exists: true,
};

const orphanItem = {
  ...rejectedItem,
  doc_id: "def456",
  original_filename: "fantasma.pdf",
  decision: "orphaned_missing_source",
  file_exists: false,
};

describe("RejectedCard", () => {
  beforeEach(() => {
    vi.mocked(fetchRejectedTriage).mockClear();
    vi.mocked(fetchRejectedTriage).mockResolvedValue([rejectedItem, orphanItem]);
    vi.mocked(restoreRejectedTriage).mockClear();
    vi.mocked(deleteRejectedTriage).mockClear();
  });

  it("não renderiza nada quando não há rejeitados", async () => {
    vi.mocked(fetchRejectedTriage).mockResolvedValue([]);
    const { container } = render(<RejectedCard projectId="p1" onStatus={() => {}} onChanged={() => {}} />);
    await waitFor(() => expect(fetchRejectedTriage).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("usa o CollapsibleSection padrão com contagem; órfão não tem Restaurar", async () => {
    render(<RejectedCard projectId="p1" onStatus={() => {}} onChanged={() => {}} />);
    await screen.findByText("Rejeitados");
    expect(screen.getByText("2 arquivos")).toBeInTheDocument();
    expect(screen.getByText("contrato_ruim.pdf")).toBeInTheDocument();
    expect(screen.getByText("fantasma.pdf")).toBeInTheDocument();
    expect(screen.getByText(/registro órfão/)).toBeInTheDocument();
    // só o item com arquivo tem botão Restaurar
    expect(screen.getAllByText("Restaurar")).toHaveLength(1);
  });

  it("Restaurar chama a API e notifica o Painel via onChanged", async () => {
    const onChanged = vi.fn();
    render(<RejectedCard projectId="p1" onStatus={() => {}} onChanged={onChanged} />);
    await screen.findByText("Rejeitados");
    fireEvent.click(screen.getByText("Restaurar"));
    await waitFor(() => expect(restoreRejectedTriage).toHaveBeenCalledWith("p1", "abc123"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("Excluir exige confirmação, chama a API e notifica o Painel (badge excluído sem reload)", async () => {
    const onChanged = vi.fn();
    render(<RejectedCard projectId="p1" onStatus={() => {}} onChanged={onChanged} />);
    await screen.findByText("Rejeitados");
    fireEvent.click(screen.getByLabelText("Excluir contrato_ruim.pdf definitivamente"));
    expect(deleteRejectedTriage).not.toHaveBeenCalled();
    expect(screen.getByText(/apagado do disco/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    await waitFor(() => expect(deleteRejectedTriage).toHaveBeenCalledWith("p1", "abc123"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("recarrega quando o bus de refresh emite (reatividade sem reload)", async () => {
    render(<RejectedCard projectId="p1" onStatus={() => {}} onChanged={() => {}} />);
    await waitFor(() => expect(fetchRejectedTriage).toHaveBeenCalledTimes(1));
    emitDataRefresh();
    await waitFor(() => expect(fetchRejectedTriage).toHaveBeenCalledTimes(2));
  });
});
