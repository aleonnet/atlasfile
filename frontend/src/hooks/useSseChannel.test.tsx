/**
 * v0.50.1 — regressão do achado do usuário: run iniciado pelo SERVIDOR
 * (auto-ingest) era invisível para a UI até um reload, porque o canal só
 * abria SSE/poll quando já via running=true. O idlePollMs vigia o status em
 * idle e o runStamp detecta um run inteiro que rodou entre dois polls (curto
 * demais para aparecer como running).
 */
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createTestQueryClient } from "../test/utils";
import { QueryClientProvider } from "@tanstack/react-query";
import { useSseChannel } from "./useSseChannel";

type Status = { running: boolean; last_run_finished_at: string | null };

function setup(fetchSnapshot: () => Promise<Status>, onFinished: ReturnType<typeof vi.fn>) {
  const client = createTestQueryClient();
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(
    () =>
      useSseChannel<Status>({
        queryKey: ["test-status"],
        fetchSnapshot,
        streamUrl: () => "http://localhost/stream",
        isActive: (s) => s.running,
        onFinished,
        idlePollMs: 25,
        runStamp: (s) => s.last_run_finished_at,
      }),
    { wrapper }
  );
}

describe("useSseChannel — vigia de runs do servidor (v0.50.1)", () => {
  it("boot com snapshot de run ANTIGO não conta como término observado", async () => {
    const onFinished = vi.fn();
    const fetchSnapshot = vi.fn(() =>
      Promise.resolve({ running: false, last_run_finished_at: "2026-07-25T10:00:00Z" })
    );
    setup(fetchSnapshot, onFinished);
    await waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(onFinished.mock.calls[0][1]).toEqual({ observedTransition: false });
  });

  it("runStamp mudando em idle = run inteiro entre polls → término OBSERVADO", async () => {
    const onFinished = vi.fn();
    let stamp = "2026-07-25T10:00:00Z";
    const fetchSnapshot = vi.fn(() => Promise.resolve({ running: false, last_run_finished_at: stamp }));
    setup(fetchSnapshot, onFinished);
    await waitFor(() => expect(onFinished).toHaveBeenCalledTimes(1));

    // O auto-ingest rodou e terminou no servidor entre dois polls
    stamp = "2026-07-25T10:05:00Z";
    await waitFor(() => expect(onFinished).toHaveBeenCalledTimes(2), { timeout: 3000 });
    expect(onFinished.mock.calls[1][0].last_run_finished_at).toBe("2026-07-25T10:05:00Z");
    expect(onFinished.mock.calls[1][1]).toEqual({ observedTransition: true });
  });

  it("idlePollMs mantém o snapshot vivo: running=true do servidor ativa o canal", async () => {
    const onFinished = vi.fn();
    let running = false;
    const fetchSnapshot = vi.fn(() => Promise.resolve({ running, last_run_finished_at: null }));
    const { result } = setup(fetchSnapshot, onFinished);
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.active).toBe(false);

    running = true; // scan disparado pelo watcher no backend
    await waitFor(() => expect(result.current.active).toBe(true), { timeout: 3000 });
  });
});
