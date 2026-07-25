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

function CustomModelsProbe() {
  const { customModels, customModelsMeta, addCustomModel } = useSettings();
  return (
    <div>
      <span data-testid="values">{customModels.join(",")}</span>
      <span data-testid="meta">{JSON.stringify(customModelsMeta)}</span>
      <button onClick={() => addCustomModel("ollama/novo:1b")}>add</button>
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

describe("SettingsContext — modelos custom com data de validação (v0.45.0)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("migra formato legado (string[]) sem perder o modelo; data fica null", async () => {
    localStorage.setItem("atlasfile-custom-models", JSON.stringify(["ollama/gemma4:12b"]));
    renderWithProviders(
      <SettingsProvider>
        <CustomModelsProbe />
      </SettingsProvider>
    );
    expect(screen.getByTestId("values")).toHaveTextContent("ollama/gemma4:12b");
    expect(screen.getByTestId("meta")).toHaveTextContent('{"ollama/gemma4:12b":null}');
  });

  it("addCustomModel persiste no formato novo com validatedAt", async () => {
    renderWithProviders(
      <SettingsProvider>
        <CustomModelsProbe />
      </SettingsProvider>
    );
    screen.getByRole("button", { name: "add" }).click();
    await waitFor(() => {
      expect(screen.getByTestId("values")).toHaveTextContent("ollama/novo:1b");
    });
    const stored = JSON.parse(localStorage.getItem("atlasfile-custom-models") ?? "[]");
    expect(stored).toHaveLength(1);
    expect(stored[0].value).toBe("ollama/novo:1b");
    expect(typeof stored[0].validatedAt).toBe("string");
  });
});
