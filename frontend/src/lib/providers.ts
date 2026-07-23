/** Registro único de providers LLM no frontend — espelho do backend
 *  (backend/app/llm_providers.py). Adicionar um provider novo = 1 entrada aqui
 *  + campo de chave no SettingsContext se `providerNeedsKey`. */

export const PROVIDERS = ["openai", "anthropic", "moonshot", "ollama"] as const;

export type ProviderId = (typeof PROVIDERS)[number];

/** Header HTTP da chave transiente; null = provider local sem chave (Ollama). */
export const PROVIDER_KEY_HEADER: Record<ProviderId, string | null> = {
  openai: "X-OpenAI-API-Key",
  anthropic: "X-Anthropic-API-Key",
  moonshot: "X-Moonshot-API-Key",
  ollama: null,
};

export function isProviderId(value: string): value is ProviderId {
  return (PROVIDERS as readonly string[]).includes(value);
}

export function providerNeedsKey(provider: string): boolean {
  return isProviderId(provider) && PROVIDER_KEY_HEADER[provider] !== null;
}
