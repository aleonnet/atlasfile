import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test/utils";
import { RootRecoveryModal } from "./RootRecoveryModal";

vi.mock("../../api", () => ({
  restartSystem: vi.fn(() => Promise.resolve({ status: "restarting" })),
  fetchHealth: vi.fn(() => Promise.resolve({ ok: true })),
  runReconcile: vi.fn(() => Promise.resolve({})),
  fetchReconcileStatus: vi.fn(() =>
    Promise.resolve({ running: false, last_run_finished_at: "2026-07-23T00:00:00Z" })
  ),
}));

describe("RootRecoveryModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fechado quando open=false", () => {
    renderWithProviders(<RootRecoveryModal open={false} onRevalidate={vi.fn()} />);
    expect(screen.queryByText(/Pasta de projetos excluída/i)).not.toBeInTheDocument();
  });

  it("explica o estado, mostra a pasta e oferece as duas ações", () => {
    renderWithProviders(
      <RootRecoveryModal open hostRoot="/Users/x/AtlasFileProjects" onRevalidate={vi.fn()} />
    );
    expect(screen.getByText(/Pasta de projetos excluída/i)).toBeInTheDocument();
    expect(screen.getByText("/Users/x/AtlasFileProjects")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Recriar pasta e reiniciar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /revalidar/i })).toBeInTheDocument();
  });

  it("revalidar chama o callback sem reiniciar", () => {
    const onRevalidate = vi.fn();
    renderWithProviders(<RootRecoveryModal open onRevalidate={onRevalidate} />);
    fireEvent.click(screen.getByRole("button", { name: /revalidar/i }));
    expect(onRevalidate).toHaveBeenCalledOnce();
  });

  it("reiniciar dispara o restart e entra em espera com ações travadas", async () => {
    const api = await import("../../api");
    renderWithProviders(<RootRecoveryModal open onRevalidate={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Recriar pasta e reiniciar/i }));
    await waitFor(() => {
      expect(api.restartSystem).toHaveBeenCalledOnce();
    });
    expect(screen.getByText(/aguardando a aplicação voltar/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Recriar pasta e reiniciar/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /revalidar/i })).toBeDisabled();
  });
});
