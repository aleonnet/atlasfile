import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { fetchModels } from "../api";
import type { ModelOption } from "../types";

const THEME_STORAGE_KEY = "atlasfile-theme";
const CHAT_MODEL_STORAGE_KEY = "atlasfile-chat-model";
const TRIAGE_MODEL_STORAGE_KEY = "atlasfile-triage-model";
const CHAT_SHOW_THINKING_KEY = "atlasfile-chat-show-thinking";
const OPENAI_API_KEY_STORAGE = "atlasfile-openai-api-key";
const ANTHROPIC_API_KEY_STORAGE = "atlasfile-anthropic-api-key";
const AUTO_TITLE_LLM_KEY = "atlasfile-auto-title-llm";

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
  const [models, setModels] = useState<ModelOption[]>([]);
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

  useEffect(() => {
    if (models.length > 0) return;
    fetchModels()
      .then((list) => {
        setModels(list);
        const values = list.map((m) => `${m.provider}/${m.model}`);
        const first = values[0];
        if (first) {
          setSelectedModel((s) => (!s || !values.includes(s) ? first : s));
          setSelectedModelTriage((s) => (!s || !values.includes(s) ? first : s));
        }
      })
      .catch(() => setModels([]));
  }, [models.length]);

  const value = useMemo<SettingsContextValue>(
    () => ({
      theme,
      resolvedTheme,
      setTheme,
      models,
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
