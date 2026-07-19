import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchModels } from "../api";
import { qk } from "../lib/queryKeys";
import type { ModelOption } from "../types";

const THEME_STORAGE_KEY = "atlasfile-theme";
const CHAT_MODEL_STORAGE_KEY = "atlasfile-chat-model";
const TRIAGE_MODEL_STORAGE_KEY = "atlasfile-triage-model";
const CHAT_SHOW_THINKING_KEY = "atlasfile-chat-show-thinking";
const OPENAI_API_KEY_STORAGE = "atlasfile-openai-api-key";
const ANTHROPIC_API_KEY_STORAGE = "atlasfile-anthropic-api-key";
const AUTO_TITLE_LLM_KEY = "atlasfile-auto-title-llm";
const CUSTOM_MODELS_KEY = "atlasfile-custom-models";

function readCustomModels(): string[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(CUSTOM_MODELS_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

export type ThemeMode = "system" | "light" | "dark";

function readStorage(key: string, fallback = ""): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage indisponível */
  }
}

function getStoredTheme(): ThemeMode {
  const s = readStorage(THEME_STORAGE_KEY);
  return s === "system" || s === "light" || s === "dark" ? s : "system";
}

export function resolveTheme(mode: ThemeMode): "light" | "dark" {
  if (mode === "light") return "light";
  if (mode === "dark") return "dark";
  if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)")?.matches) return "dark";
  return "light";
}

type SettingsContextValue = {
  theme: ThemeMode;
  resolvedTheme: "light" | "dark";
  setTheme: (mode: ThemeMode) => void;
  models: ModelOption[];
  /** Modelos digitados/validados pelo usuário ("provider/model"), persistidos localmente. */
  customModels: string[];
  addCustomModel: (value: string) => void;
  /** Recarrega o catálogo do backend (após um refresh remoto). */
  reloadModels: () => Promise<void>;
  selectedModel: string;
  setSelectedModel: React.Dispatch<React.SetStateAction<string>>;
  selectedModelTriage: string;
  setSelectedModelTriage: React.Dispatch<React.SetStateAction<string>>;
  openaiApiKey: string;
  setOpenaiApiKey: React.Dispatch<React.SetStateAction<string>>;
  anthropicApiKey: string;
  setAnthropicApiKey: React.Dispatch<React.SetStateAction<string>>;
  showThinking: boolean;
  setShowThinking: React.Dispatch<React.SetStateAction<boolean>>;
  autoTitleLLM: boolean;
  setAutoTitleLLM: React.Dispatch<React.SetStateAction<boolean>>;
  settingsOpen: boolean;
  setSettingsOpen: React.Dispatch<React.SetStateAction<boolean>>;
};

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<ThemeMode>(getStoredTheme);
  const [customModels, setCustomModels] = useState<string[]>(readCustomModels);
  const [selectedModel, setSelectedModel] = useState<string>(() => readStorage(CHAT_MODEL_STORAGE_KEY));
  const [selectedModelTriage, setSelectedModelTriage] = useState<string>(() => readStorage(TRIAGE_MODEL_STORAGE_KEY));
  const [openaiApiKey, setOpenaiApiKey] = useState<string>(() => readStorage(OPENAI_API_KEY_STORAGE));
  const [anthropicApiKey, setAnthropicApiKey] = useState<string>(() => readStorage(ANTHROPIC_API_KEY_STORAGE));
  const [showThinking, setShowThinking] = useState<boolean>(() => readStorage(CHAT_SHOW_THINKING_KEY) === "true");
  const [autoTitleLLM, setAutoTitleLLM] = useState<boolean>(() => readStorage(AUTO_TITLE_LLM_KEY) === "true");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const resolvedTheme = useMemo(() => resolveTheme(theme), [theme]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", resolvedTheme);
  }, [resolvedTheme]);

  useEffect(() => writeStorage(THEME_STORAGE_KEY, theme), [theme]);
  useEffect(() => {
    if (selectedModel) writeStorage(CHAT_MODEL_STORAGE_KEY, selectedModel);
  }, [selectedModel]);
  useEffect(() => {
    if (selectedModelTriage !== undefined) writeStorage(TRIAGE_MODEL_STORAGE_KEY, selectedModelTriage);
  }, [selectedModelTriage]);
  useEffect(() => writeStorage(CHAT_SHOW_THINKING_KEY, String(showThinking)), [showThinking]);
  useEffect(() => writeStorage(OPENAI_API_KEY_STORAGE, openaiApiKey || null), [openaiApiKey]);
  useEffect(() => writeStorage(ANTHROPIC_API_KEY_STORAGE, anthropicApiKey || null), [anthropicApiKey]);
  useEffect(() => writeStorage(AUTO_TITLE_LLM_KEY, String(autoTitleLLM)), [autoTitleLLM]);

  const modelsQuery = useQuery({ queryKey: qk.models(), queryFn: fetchModels, staleTime: 5 * 60_000 });
  const models = modelsQuery.data ?? [];
  useEffect(() => {
    if (models.length === 0) return;
    // Modelos custom validados contam como conhecidos — sem isso a seleção
    // do usuário seria resetada para o primeiro do catálogo a cada load.
    const values = [...models.map((m) => `${m.provider}/${m.model}`), ...customModels];
    const first = values[0];
    if (first) {
      setSelectedModel((s) => (!s || !values.includes(s) ? first : s));
      setSelectedModelTriage((s) => (!s || !values.includes(s) ? first : s));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [models, customModels]);

  const addCustomModel = useMemo(
    () => (value: string) => {
      setCustomModels((prev) => {
        if (prev.includes(value)) return prev;
        const next = [...prev, value];
        writeStorage(CUSTOM_MODELS_KEY, JSON.stringify(next));
        return next;
      });
    },
    []
  );

  const reloadModels = useMemo(
    () => async () => {
      await modelsQuery.refetch();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const value = useMemo<SettingsContextValue>(
    () => ({
      theme,
      resolvedTheme,
      setTheme,
      models,
      customModels,
      addCustomModel,
      reloadModels,
      selectedModel,
      setSelectedModel,
      selectedModelTriage,
      setSelectedModelTriage,
      openaiApiKey,
      setOpenaiApiKey,
      anthropicApiKey,
      setAnthropicApiKey,
      showThinking,
      setShowThinking,
      autoTitleLLM,
      setAutoTitleLLM,
      settingsOpen,
      setSettingsOpen,
    }),
    [
      theme,
      resolvedTheme,
      models,
      customModels,
      addCustomModel,
      reloadModels,
      selectedModel,
      selectedModelTriage,
      openaiApiKey,
      anthropicApiKey,
      showThinking,
      autoTitleLLM,
      settingsOpen,
    ]
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const context = useContext(SettingsContext);
  if (!context) throw new Error("useSettings deve ser usado dentro de <SettingsProvider>");
  return context;
}
