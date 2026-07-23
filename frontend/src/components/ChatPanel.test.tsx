/// <reference types="@testing-library/jest-dom/vitest" />
import { screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../test/utils";
import { ChatPanel } from "./ChatPanel";

vi.mock("../api", () => ({
  fetchSuggestions: vi.fn(() => Promise.resolve({ suggestions: [] })),
  getFileDownloadUrl: vi.fn(() => "http://x/download"),
}));

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
    renderWithProviders(<ChatPanel {...BASE_PROPS} customModels={["ollama/gemma4:12b"]} />);
    expect(
      screen.getByRole("option", { name: /ollama\/gemma4:12b/i })
    ).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /gpt-4o-mini/i })).toBeInTheDocument();
  });

  it("custom já presente no catálogo não duplica", () => {
    renderWithProviders(
      <ChatPanel {...BASE_PROPS} customModels={["openai/gpt-4o-mini", "ollama/gemma4:12b"]} />
    );
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("sem catálogo mas com custom validado o select continua utilizável", () => {
    renderWithProviders(
      <ChatPanel {...BASE_PROPS} models={[]} selectedModel="ollama/gemma4:12b" customModels={["ollama/gemma4:12b"]} />
    );
    const select = document.getElementById("chat-panel-model");
    expect(select).not.toBeDisabled();
  });
});
