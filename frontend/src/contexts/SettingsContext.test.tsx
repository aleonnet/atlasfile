import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../test/utils";
import { SettingsProvider, useSettings } from "./SettingsContext";

vi.mock("../api", () => ({
  fetchModels: vi.fn(() =>
    Promise.resolve([
      // ordem do catálogo propositalmente com o modelo caro primeiro
      { provider: "anthropic", model: "claude-fable-5", label: "Anthropic Fable 5" },
      { provider: "anthropic", model: "claude-sonnet-5", label: "Anthropic Sonnet 5" },
      { provider: "openai", model: "gpt-4o-mini", label: "OpenAI gpt-4o-mini" },
      { provider: "openai", model: "gpt-5.1", label: "OpenAI gpt-5.1" },
    ])
  ),
}));

function Probe() {
  const { selectedModel, selectedModelTriage } = useSettings();
  return (
    <div>
      <span data-testid="chat">{selectedModel}</span>
      <span data-testid="triage">{selectedModelTriage}</span>
    </div>
  );
}

describe("SettingsContext — modelo default de instância nova", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("prefere openai/gpt-5.1 como default de chat e triagem, nunca o primeiro (caro) da lista", async () => {
    renderWithProviders(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );
    await waitFor(() => {
      expect(screen.getByTestId("chat")).toHaveTextContent("openai/gpt-5.1");
    });
    expect(screen.getByTestId("triage")).toHaveTextContent("openai/gpt-5.1");
  });

  it("seleção salva do usuário não é sobrescrita pelo default", async () => {
    localStorage.setItem("atlasfile-chat-model", "anthropic/claude-sonnet-5");
    renderWithProviders(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );
    await waitFor(() => {
      expect(screen.getByTestId("chat")).toHaveTextContent("anthropic/claude-sonnet-5");
    });
  });
});
