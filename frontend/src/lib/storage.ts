/** Registro único e tipado das chaves de localStorage do app (F3).
 *
 *  Os NOMES das chaves são os mesmos de sempre — instalações existentes não
 *  perdem nada. Todo acesso passa por aqui: try/catch centralizado (modo
 *  privado/storage cheio) e JSON parse seguro, em vez de 15 cópias do mesmo
 *  try/catch espalhadas. */

export const STORAGE_KEYS = {
  apiKey: "atlasfile_api_key",
  selectedProject: "atlasfile_selected_project",
  theme: "atlasfile-theme",
  chatModel: "atlasfile-chat-model",
  triageModel: "atlasfile-triage-model",
  showThinking: "atlasfile-chat-show-thinking",
  openaiApiKey: "atlasfile-openai-api-key",
  anthropicApiKey: "atlasfile-anthropic-api-key",
  autoTitleLLM: "atlasfile-auto-title-llm",
  customModels: "atlasfile-custom-models",
  onboardingDone: "atlasfile-onboarding-done",
  telegramBotToken: "atlasfile-telegram-bot-token",
  configTab: "atlasfile-config-tab",
  sidebarCollapsed: "atlasfile-sidebar-collapsed",
  language: "atlasfile-language",
} as const;

export type StorageKey = (typeof STORAGE_KEYS)[keyof typeof STORAGE_KEYS];

/** Chave dinâmica dos colapsáveis (CollapsibleSection persistKey). */
export function collapseStorageKey(persistKey: string): string {
  return `atlasfile-collapse-${persistKey}`;
}

export function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function storageSet(key: string, value: string | null): void {
  try {
    if (value === null || value === "") localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage indisponível — o app segue sem persistir */
  }
}

export function storageGetJson<T>(key: string, fallback: T): T {
  const raw = storageGet(key);
  if (raw === null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function storageSetJson(key: string, value: unknown): void {
  storageSet(key, JSON.stringify(value));
}

export function storageGetBool(key: string, fallback: boolean): boolean {
  const raw = storageGet(key);
  return raw === null ? fallback : raw === "true";
}
