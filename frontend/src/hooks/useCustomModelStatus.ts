/** Estado VIVO de um modelo custom (v0.45.0): o selo "(validado por você)" era
 *  localStorage estático — validou uma vez e nunca re-verificava, deixando o
 *  usuário achar que tinha um modelo up com o Ollama parado. Este hook
 *  re-consulta o endpoint do provedor (barato: GET /v1/models local no caso
 *  Ollama) quando o modelo custom está selecionado; staleTime segura a
 *  frequência. Falha de verificação NUNCA bloqueia a UI — vira estado. */
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { validateModel } from "../api";
import { ApiError } from "../lib/apiError";
import { useSettings } from "../contexts/SettingsContext";

export type CustomModelLiveStatus =
  | "idle" // não é modelo custom — nada a verificar
  | "checking"
  | "available"
  | "model_missing" // endpoint respondeu: modelo não existe (ollama pull ...)
  | "endpoint_down" // provedor inalcançável (Ollama parado / rede)
  | "unknown"; // erro não conclusivo (ex.: chave inválida) — não afirmar nada

function useCustomModelStatus(
  providerModel: string | null | undefined
): { status: CustomModelLiveStatus; refresh: () => Promise<unknown> } {
  const { customModels, openaiApiKey, anthropicApiKey, moonshotApiKey } = useSettings();
  const isCustom = !!providerModel && customModels.includes(providerModel);

  const query = useQuery({
    queryKey: ["custom-model-live", providerModel],
    enabled: isCustom,
    // Cheque VIVO com a aba ativa (o intervalo pausa em background — certo);
    // o fluxo real do usuário é alt-tab → (des)ligar o Ollama → voltar: o
    // staleTime de 10s garante re-verificação imediata no refocus, e os 15s
    // limitam o tempo máximo de LED mentindo. Custo desprezível: GET local.
    // (Feedback de teste v0.45.0: com 60s/60s o LED ficou verde após fechar
    // o Ollama — intervalo pausado + focus refetch barrado pelo staleTime.)
    staleTime: 10_000,
    refetchInterval: 15_000,
    // O LED fica visível mesmo com a janela desfocada (usuário olhando o
    // browser enquanto mexe no terminal) — o cheque não pode pausar, senão o
    // LED congela verde com o Ollama já morto (reprodução real do teste).
    refetchIntervalInBackground: true,
    retry: false,
    refetchOnWindowFocus: true,
    queryFn: async (): Promise<CustomModelLiveStatus> => {
      const [provider, ...rest] = String(providerModel).split("/");
      try {
        const result = await validateModel(provider, rest.join("/"), {
          openai: openaiApiKey || undefined,
          anthropic: anthropicApiKey || undefined,
          moonshot: moonshotApiKey || undefined,
        });
        return result.valid ? "available" : "model_missing";
      } catch (e) {
        // backend: *_REQUEST_FAILED = provedor inalcançável (502)
        if (e instanceof ApiError && (e.code ?? "").endsWith("_REQUEST_FAILED")) return "endpoint_down";
        return "unknown";
      }
    },
  });

  const status: CustomModelLiveStatus = !isCustom
    ? "idle"
    : query.isPending
      ? "checking"
      : (query.data ?? "unknown");
  return { status, refresh: () => query.refetch() };
}

/** Status + texto pronto de tooltip — o estado vai no PRÓPRIO seletor de
 *  modelo (gramática do botão de raciocínio: esmaecido = indisponível,
 *  destaque laranja = disponível), decisão de design do usuário (v0.45.0,
 *  desenho anotado: sem ícone novo, sem LED em botão). */
export function useCustomModelStatusText(providerModel: string | null | undefined): {
  status: CustomModelLiveStatus;
  title: string | undefined;
} {
  const { t } = useTranslation();
  const { status } = useCustomModelStatus(providerModel);
  const model = String(providerModel ?? "").split("/").slice(1).join("/");
  const title =
    status === "idle"
      ? undefined
      : status === "checking"
        ? t("settings:modelStatus.checking")
        : status === "available"
          ? t("settings:modelStatus.available")
          : status === "model_missing"
            ? t("settings:modelStatus.modelMissing", { model })
            : status === "endpoint_down"
              ? t("settings:modelStatus.endpointDown")
              : t("settings:modelStatus.unknown");
  return { status, title };
}
