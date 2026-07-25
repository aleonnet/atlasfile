/// <reference types="@testing-library/jest-dom/vitest" />
import { screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../test/utils";
import { SettingsProvider } from "../contexts/SettingsContext";
import { ChatPanel } from "./ChatPanel";

vi.mock("../api", () => ({
  fetchSuggestions: vi.fn(() => Promise.resolve({ suggestions: [] })),
  getFileDownloadUrl: vi.fn(() => "http://x/download"),
  // v0.45.0: o badge de estado vivo (CustomModelLiveBadge) vive dentro do
  // ChatPanel — no app real ele sempre está sob SettingsProvider
  fetchModels: vi.fn(() => Promise.resolve([])),
  validateModel: vi.fn(() => Promise.resolve({ valid: true, detail: "ok" })),
}));

function renderPanel(ui: React.ReactElement) {
  return renderWithProviders(<SettingsProvider>{ui}</SettingsProvider>);
}

// jsdom não implementa scrollTo em elementos (o thread do chat usa no autoscroll)
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "scrollTo", { value: () => {}, writable: true });
});

const BASE_PROPS = {
  agentName: "Assistente",
  messages: [],
  sending: false,
  error: null,
  canAbort: false,
  selectedModel: "openai/gpt-4o-mini",
  models: [{ provider: "openai", model: "gpt-4o-mini", label: "OpenAI gpt-4o-mini (base)" }],
  onModelChange: vi.fn(),
  onOpenSettings: vi.fn(),
  onSend: vi.fn(),
  onAbort: vi.fn(),
  onNewSession: vi.fn(),
  showThinking: false,
  onShowThinkingChange: vi.fn(),
};

describe("ChatPanel — modelos custom no seletor", () => {
  it("modelos validados pelo usuário (ex.: ollama) aparecem no select", () => {
    renderPanel(<ChatPanel {...BASE_PROPS} customModels={["ollama/gemma4:12b"]} />);
    expect(
      screen.getByRole("option", { name: /ollama\/gemma4:12b/i })
    ).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /gpt-4o-mini/i })).toBeInTheDocument();
  });

  it("custom já presente no catálogo não duplica", () => {
    renderPanel(
      <ChatPanel {...BASE_PROPS} customModels={["openai/gpt-4o-mini", "ollama/gemma4:12b"]} />
    );
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("sem catálogo mas com custom validado o select continua utilizável", () => {
    renderPanel(
      <ChatPanel {...BASE_PROPS} models={[]} selectedModel="ollama/gemma4:12b" customModels={["ollama/gemma4:12b"]} />
    );
    const select = document.getElementById("chat-panel-model");
    expect(select).not.toBeDisabled();
  });
});

describe("ChatPanel — estado vivo do modelo custom no seletor (v0.45.0)", () => {
  function seedCustomModel() {
    localStorage.setItem(
      "atlasfile-custom-models",
      JSON.stringify([{ value: "ollama/gemma4:12b", validatedAt: "2026-07-23T10:00:00Z" }])
    );
  }

  it("endpoint vivo → seletor com destaque laranja e tooltip", async () => {
    seedCustomModel();
    const { validateModel } = await import("../api");
    vi.mocked(validateModel).mockResolvedValue({ valid: true, detail: "ok" });
    renderPanel(<ChatPanel {...BASE_PROPS} selectedModel="ollama/gemma4:12b" customModels={["ollama/gemma4:12b"]} />);
    const select = document.getElementById("chat-panel-model")!;
    // ancorar no título (semântico) — "border-accent" é substring de
    // focus:border-accent das classes-base e daria falso positivo
    await vi.waitFor(() => {
      expect(select).toHaveAttribute("title", expect.stringMatching(/disponível agora/i));
    });
    expect(select.className).toContain("text-accent");
    localStorage.removeItem("atlasfile-custom-models");
  });

  it("Ollama parado → seletor esmaecido com dica no tooltip (gramática do botão de raciocínio)", async () => {
    seedCustomModel();
    const { validateModel } = await import("../api");
    const { ApiError } = await import("../lib/apiError");
    vi.mocked(validateModel).mockRejectedValue(new ApiError("falha", "OLLAMA_REQUEST_FAILED"));
    renderPanel(<ChatPanel {...BASE_PROPS} selectedModel="ollama/gemma4:12b" customModels={["ollama/gemma4:12b"]} />);
    const select = document.getElementById("chat-panel-model")!;
    await vi.waitFor(() => {
      expect(select.className).toContain("opacity-50");
    });
    expect(select).toHaveAttribute("title", expect.stringMatching(/ollama serve/i));
    expect(select).not.toBeDisabled(); // indisponível educa, não bloqueia
    localStorage.removeItem("atlasfile-custom-models");
  });

  it("modelo de catálogo → seletor neutro, sem tooltip de estado", () => {
    renderPanel(<ChatPanel {...BASE_PROPS} />);
    const select = document.getElementById("chat-panel-model")!;
    expect(select.className).not.toContain("text-accent");
    expect(select).not.toHaveAttribute("title");
  });
});
