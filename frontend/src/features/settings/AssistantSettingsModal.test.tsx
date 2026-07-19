/// <reference types="@testing-library/jest-dom/vitest" />
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/utils";
import { describe, expect, it, vi } from "vitest";
import { NavigationProvider } from "../../contexts/NavigationContext";
import { ProjectProvider } from "../../contexts/ProjectContext";
import { SettingsProvider } from "../../contexts/SettingsContext";
import { AssistantSettingsModal } from "./AssistantSettingsModal";

vi.mock("../../api", () => ({
  fetchProjects: vi.fn(() => Promise.resolve([])),
  fetchModels: vi.fn(() =>
    Promise.resolve([
      { provider: "openai", model: "gpt-4o-mini", label: "OpenAI gpt-4o-mini (base)" },
      { provider: "anthropic", model: "claude-haiku-4-5", label: "Anthropic Claude Haiku 4.5 (base)" }
    ])
  ),
  fetchChannelConfig: vi.fn(() =>
    Promise.resolve({ channels_enabled: false, telegram: { enabled: false, bot_token: "", mirror_responses: false } })
  ),
  fetchChannelStatus: vi.fn(() => Promise.resolve({ channels: [] })),
  updateChannelConfig: vi.fn(),
  refreshModelCatalog: vi.fn(),
  fetchCatalogConfig: vi.fn(() => Promise.resolve({ url: "https://x", default_url: "https://x", refreshed_at: null })),
  fetchModelCatalogDetail: vi.fn(() => Promise.resolve({ refreshed_at: null, source_url: "https://x", models: [] })),
  updateCatalogConfig: vi.fn(),
  fetchProjectProfile: vi.fn(),
  updateProjectProfile: vi.fn(),
  validateModel: vi.fn(() => Promise.resolve({ valid: true, detail: "ok" }))
}));

function renderModal() {
  const props = {
    open: true,
    selectedModelTriage: "openai/gpt-4o-mini",
    selectedModel: "openai/gpt-4o-mini",
    models: [
      { provider: "openai", model: "gpt-4o-mini", label: "OpenAI gpt-4o-mini (base)" },
      { provider: "anthropic", model: "claude-haiku-4-5", label: "Anthropic Claude Haiku 4.5 (base)" }
    ],
    openaiApiKey: "sk-x",
    anthropicApiKey: "",
    autoTitleLLM: false,
    onChangeModelTriage: vi.fn(),
    onChangeModel: vi.fn(),
    onChangeOpenAiKey: vi.fn(),
    onChangeAnthropicKey: vi.fn(),
    onChangeAutoTitleLLM: vi.fn(),
    onClose: vi.fn()
  };
  renderWithProviders(
    <SettingsProvider>
      <ProjectProvider>
        <NavigationProvider>
          <AssistantSettingsModal {...props} />
        </NavigationProvider>
      </ProjectProvider>
    </SettingsProvider>
  );
  return props;
}

describe("ModelCombobox (dropdown próprio, sem datalist)", () => {
  it("abre a lista no foco com as opções do catálogo", async () => {
    renderModal();
    const input = await screen.findByRole("combobox", { name: /modelo chat/i });
    fireEvent.focus(input);
    const listbox = await screen.findByRole("listbox");
    expect(listbox).toBeInTheDocument();
    expect(screen.getByText("openai/gpt-4o-mini")).toBeInTheDocument();
    expect(screen.getByText("anthropic/claude-haiku-4-5")).toBeInTheDocument();
  });

  it("filtra ao digitar e seleciona com mousedown", async () => {
    const props = renderModal();
    const input = await screen.findByRole("combobox", { name: /modelo chat/i });
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "claude" } });
    await waitFor(() => {
      expect(screen.queryByText("openai/gpt-4o-mini")).not.toBeInTheDocument();
    });
    fireEvent.mouseDown(screen.getByText("anthropic/claude-haiku-4-5"));
    expect(props.onChangeModel).toHaveBeenCalledWith("anthropic/claude-haiku-4-5");
  });

  it("não usa datalist (imune ao gerenciador de senhas do Firefox)", async () => {
    renderModal();
    expect(document.querySelector("datalist")).not.toBeInTheDocument();
    const input = await screen.findByRole("combobox", { name: /modelo chat/i });
    expect(input).toHaveAttribute("type", "search");
  });
});
