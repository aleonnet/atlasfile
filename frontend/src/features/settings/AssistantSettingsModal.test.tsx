/// <reference types="@testing-library/jest-dom/vitest" />
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
  validateModel: vi.fn(() => Promise.resolve({ valid: true, detail: "ok" })),
  validateProviderKey: vi.fn(() => Promise.resolve({ valid: true, detail: "ok" }))
}));

beforeEach(() => {
  vi.clearAllMocks();
});

const MOONSHOT_MODEL = { provider: "moonshot", model: "kimi-k3", label: "Moonshot Kimi K3" };

function renderModal(overrides: Record<string, unknown> = {}) {
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
    moonshotApiKey: "",
    autoTitleLLM: false,
    onChangeModelTriage: vi.fn(),
    onChangeModel: vi.fn(),
    onChangeOpenAiKey: vi.fn(),
    onChangeAnthropicKey: vi.fn(),
    onChangeMoonshotKey: vi.fn(),
    onChangeAutoTitleLLM: vi.fn(),
    onClose: vi.fn(),
    ...overrides
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

describe("ApiKeyField (validação automática de chave — padrão do wizard)", () => {
  it("digitar no campo propaga para o estado do App (campo controlado)", async () => {
    const props = renderModal({ openaiApiKey: "" });
    const input = await screen.findByLabelText(/OpenAI API Key/i);
    fireEvent.change(input, { target: { value: "sk-proj-nova123" } });
    expect(props.onChangeOpenAiKey).toHaveBeenCalledWith("sk-proj-nova123");
  });

  it("chave armazenada é validada ao abrir (debounce 700ms) e mostra ✓", async () => {
    const api = await import("../../api");
    renderModal({ openaiApiKey: "sk-guardada" });
    await waitFor(
      () => expect(api.validateProviderKey).toHaveBeenCalledWith("openai", "sk-guardada"),
      { timeout: 3000 }
    );
    expect(await screen.findByText(/✓ Chave válida/)).toBeInTheDocument();
  });

  it("chave inválida mostra ✗ sem bloquear nada", async () => {
    const api = await import("../../api");
    vi.mocked(api.validateProviderKey).mockResolvedValue({ valid: false, detail: "invalid" });
    renderModal({ openaiApiKey: "sk-errada" });
    expect(await screen.findByText(/✗ Chave inválida/, undefined, { timeout: 3000 })).toBeInTheDocument();
  });

  it("erro de rede vira 'unreachable', distinto de inválida", async () => {
    const api = await import("../../api");
    vi.mocked(api.validateProviderKey).mockRejectedValue(new Error("net down"));
    renderModal({ openaiApiKey: "sk-qualquer" });
    expect(
      await screen.findByText(/Não foi possível verificar a chave agora/, undefined, { timeout: 3000 })
    ).toBeInTheDocument();
    expect(screen.queryByText(/✗ Chave inválida/)).not.toBeInTheDocument();
  });

  it("modelo moonshot selecionado exibe o campo de chave Moonshot e valida nele", async () => {
    const api = await import("../../api");
    renderModal({
      selectedModel: "moonshot/kimi-k3",
      models: [MOONSHOT_MODEL],
      openaiApiKey: "",
      moonshotApiKey: "sk-moon",
    });
    expect(await screen.findByLabelText(/Moonshot API Key/i)).toBeInTheDocument();
    await waitFor(
      () => expect(api.validateProviderKey).toHaveBeenCalledWith("moonshot", "sk-moon"),
      { timeout: 3000 }
    );
  });

  it("modelo ollama não pede chave — só o hint de execução local", async () => {
    renderModal({
      selectedModel: "ollama/gemma4:12b",
      selectedModelTriage: "ollama/gemma4:12b",
      models: [],
      openaiApiKey: "",
    });
    expect(await screen.findByText(/Ollama roda localmente/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/API Key/i)).not.toBeInTheDocument();
  });
});
