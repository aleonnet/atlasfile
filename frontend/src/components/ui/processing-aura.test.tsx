import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProcessingAura } from "./processing-aura";

describe("ProcessingAura", () => {
  it("mostra rótulo, mini-orb e tempo decorrido real", async () => {
    vi.useFakeTimers();
    const { container } = render(<ProcessingAura label="Aprovando — movendo, extraindo e indexando" />);
    expect(screen.getByText(/Aprovando — movendo, extraindo e indexando/)).toBeInTheDocument();
    expect(container.querySelector(".atlas-mini-orb")).toBeTruthy();
    expect(container.querySelector(".atlas-aura")).toBeTruthy();
    expect(screen.getByText("0s")).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByText("3s")).toBeInTheDocument();
    vi.useRealTimers();
  });
});
