import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProcessingAura } from "./processing-aura";

describe("ProcessingAura", () => {
  it("mostra rótulo, orb blackhole, respiração accent e tempo decorrido real", async () => {
    vi.useFakeTimers();
    const { container } = render(<ProcessingAura label="Aprovando — movendo, extraindo e indexando" />);
    expect(screen.getByText(/Aprovando — movendo, extraindo e indexando/)).toBeInTheDocument();
    // v0.47.0 (design iterado com o usuário): shader backdrop + orb (2 canvas),
    // borda accent em respiração e cursor "progress". SEM véu global: os botões
    // já desabilitam e o backend serializa (análise factual 2026-07-25)
    expect(container.querySelectorAll("canvas").length).toBe(2);
    expect(container.querySelector('[class*="atlas-breathe"]')).toBeTruthy();
    expect(container.querySelector('[class*="fixed"]')).toBeNull();
    expect(document.body.style.cursor).toBe("progress");
    expect(container.querySelector(".atlas-aura")).toBeNull();
    expect(screen.getByText("0s")).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByText("3s")).toBeInTheDocument();
    vi.useRealTimers();
  });
});
