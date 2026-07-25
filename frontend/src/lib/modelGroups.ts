/** Agrupamento provedor → modelos para os seletores RÁPIDOS de modelo (v0.46.0).
 *
 *  Decisão de benchmarking (ChatGPT/Claude.ai expõem ~5 modelos; Cursor mostra
 *  recentes + busca): o combo rápido do chat/triagem mostra POUCOS — modelo
 *  atual + usados recentemente + customs validados — agrupados por provedor
 *  via <optgroup>; a lista completa do catálogo (68+ modelos) com busca já
 *  vive no settings, atrás da engrenagem ao lado de cada combo. A entrada
 *  sentinela ALL_MODELS_OPTION abre esse settings a partir do próprio combo. */
import type { ModelOption } from "../types";
import { PROVIDERS } from "./providers";

export const ALL_MODELS_OPTION = "__all_models__";

export interface QuickModelOption {
  value: string;
  label: string;
}

export interface QuickModelGroup {
  provider: string;
  options: QuickModelOption[];
}

/** Rótulo da opção dentro do grupo: sem a marca redundante na frente —
 *  o catálogo rotula como "OpenAI gpt-4-turbo" (fato verificado na API) e o
 *  optgroup já diz o provedor. Strip só quando o prefixo bate exatamente. */
function optionLabel(value: string, catalogByValue: Map<string, ModelOption>): string {
  const fallback = value.split("/").slice(1).join("/") || value;
  const entry = catalogByValue.get(value);
  if (!entry) return fallback;
  const [firstWord, ...rest] = entry.label.split(" ");
  if (rest.length > 0 && firstWord.toLowerCase() === entry.provider.toLowerCase()) return rest.join(" ");
  return entry.label;
}

/** Monta os grupos do combo rápido a partir dos values na ordem dada
 *  (atual → recentes → customs), com dedup; grupos seguem a ordem do registro
 *  de providers, desconhecidos ao final em ordem alfabética. */
export function groupQuickModelValues(values: Array<string | null | undefined>, catalog: ModelOption[]): QuickModelGroup[] {
  const catalogByValue = new Map(catalog.map((m) => [`${m.provider}/${m.model}`, m]));
  const seen = new Set<string>();
  const byProvider = new Map<string, QuickModelOption[]>();
  for (const raw of values) {
    const value = (raw ?? "").trim();
    if (!value || !value.includes("/") || seen.has(value)) continue;
    seen.add(value);
    const provider = value.split("/")[0];
    if (!byProvider.has(provider)) byProvider.set(provider, []);
    byProvider.get(provider)!.push({ value, label: optionLabel(value, catalogByValue) });
  }
  const known = PROVIDERS.filter((p) => byProvider.has(p)) as string[];
  const unknown = [...byProvider.keys()].filter((p) => !(PROVIDERS as readonly string[]).includes(p)).sort();
  return [...known, ...unknown].map((provider) => ({ provider, options: byProvider.get(provider)! }));
}
