import { useCallback, useEffect, useRef, useState } from "react";
import { BadgeCheck, ChevronRight, Eye, EyeOff, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import {
  fetchCatalogConfig,
  fetchChannelConfig,
  fetchChannelStatus,
  fetchModelCatalogDetail,
  fetchProjectProfile,
  refreshModelCatalog,
  updateCatalogConfig,
  updateChannelConfig,
  updateProjectProfile,
  validateModel,
  type CatalogConfig,
  type ModelCatalogDetail,
} from "../../api";
import { Button } from "../../components/ui/button";
import { DataTable, TableWrap } from "../../components/ui/data-table";
import { Input } from "../../components/ui/input";
import { toast } from "../../components/ui/sonner";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "../../components/ui/modal-shell";
import { useSettings } from "../../contexts/SettingsContext";
import { ALL_PROJECTS, useProject } from "../../contexts/ProjectContext";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { cn } from "../../lib/utils";
import type { ChannelConfig, ChannelStatusResponse, ModelOption, ProjectProfileV2 } from "../../types";

type InputLikeEvent = { target: { value: string } };

type Props = {
  open: boolean;
  selectedModelTriage: string;
  selectedModel: string;
  models: ModelOption[];
  openaiApiKey: string;
  anthropicApiKey: string;
  autoTitleLLM: boolean;
  onChangeModelTriage: (value: string) => void;
  onChangeModel: (value: string) => void;
  onChangeOpenAiKey: (value: string) => void;
  onChangeAnthropicKey: (value: string) => void;
  onChangeAutoTitleLLM: (value: boolean) => void;
  onClose: () => void;
};

const DEFAULT_TG_CONFIG: ChannelConfig = {
  channels_enabled: false,
  telegram: { enabled: false, bot_token: "", mirror_responses: false },
};

const TG_TOKEN_STORAGE_KEY = "atlasfile-telegram-bot-token";

function loadTgToken(): string {
  try { return localStorage.getItem(TG_TOKEN_STORAGE_KEY) || ""; } catch { return ""; }
}
function saveTgToken(token: string) {
  try {
    if (token) localStorage.setItem(TG_TOKEN_STORAGE_KEY, token);
    else localStorage.removeItem(TG_TOKEN_STORAGE_KEY);
  } catch { /* ignore */ }
}

const channelCardClass = "rounded-lg border border-border bg-card p-3.5";
const hintClass = "mt-1 block text-[0.72rem] text-tertiary";

/** "gpt-5.2" → "openai/gpt-5.2"; "claude-x" → "anthropic/claude-x"; já com "/" fica como está. */
function normalizeModelValue(raw: string): string {
  const value = raw.trim();
  if (!value || value.includes("/")) return value;
  return value.toLowerCase().startsWith("claude") ? `anthropic/${value}` : `openai/${value}`;
}

type ValidationState = { status: "idle" | "validating" | "valid" | "invalid"; detail?: string };

function formatRefreshedAt(iso: string | null | undefined): string {
  if (!iso) return "nunca";
  try {
    return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

const fmt1m = (v: number | null) => (v == null ? "—" : `$${v.toFixed(2)}`);

/** Aba Catálogo: fonte (URL editável com validação dry-run) + tabela de modelos/preços. */
function CatalogTab({ onCatalogChanged }: { onCatalogChanged: () => Promise<void> }) {
  const [config, setConfig] = useState<CatalogConfig | null>(null);
  const [detail, setDetail] = useState<ModelCatalogDetail | null>(null);
  const [urlDraft, setUrlDraft] = useState("");
  const [busy, setBusy] = useState<"" | "test" | "save" | "refresh">("");

  const load = useCallback(async () => {
    try {
      const [cfg, det] = await Promise.all([fetchCatalogConfig(), fetchModelCatalogDetail()]);
      setConfig(cfg);
      setDetail(det);
      setUrlDraft(cfg.url);
    } catch {
      toast.error("Falha ao carregar o catálogo");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleTestUrl() {
    setBusy("test");
    try {
      const r = await refreshModelCatalog({ dryRun: true, url: urlDraft.trim() || undefined });
      toast.success(`Fonte válida: ${r.models_total} modelos (${r.openai} OpenAI, ${r.anthropic} Anthropic), ${r.priced_models} com preço`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Fonte inválida");
    } finally {
      setBusy("");
    }
  }

  async function handleSaveUrl() {
    setBusy("save");
    try {
      const cfg = await updateCatalogConfig(urlDraft.trim());
      setConfig(cfg);
      setUrlDraft(cfg.url);
      toast.success(cfg.url === cfg.default_url ? "Fonte padrão restaurada" : "URL da fonte salva");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha ao salvar a URL");
    } finally {
      setBusy("");
    }
  }

  async function handleRefreshNow() {
    setBusy("refresh");
    try {
      const r = await refreshModelCatalog();
      await Promise.all([load(), onCatalogChanged()]);
      toast.success(`Catálogo atualizado: ${r.models_total} modelos (${r.priced_models} com preço)`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha ao atualizar o catálogo");
    } finally {
      setBusy("");
    }
  }

  const isDefaultUrl = config != null && urlDraft.trim() === config.default_url;

  return (
    <div>
      <label className={fieldLabelClass} htmlFor="catalog-source-url">Fonte do catálogo (JSON)</label>
      <Input
        id="catalog-source-url"
        className="font-mono text-[0.72rem]"
        value={urlDraft}
        onChange={(e: InputLikeEvent) => setUrlDraft(e.target.value)}
        placeholder={config?.default_url}
        autoComplete="off"
      />
      <span className={hintClass}>
        Parâmetros e preços agregados das páginas oficiais OpenAI/Anthropic (formato LiteLLM).{" "}
        {!isDefaultUrl && config && (
          <button type="button" className="border-0 bg-transparent p-0 text-accent shadow-none hover:underline" onClick={() => setUrlDraft(config.default_url)}>
            usar padrão
          </button>
        )}
      </span>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Button variant="secondary" size="sm" disabled={busy !== ""} onClick={() => void handleTestUrl()}>
          {busy === "test" ? <Loader2 className="animate-spin" /> : <BadgeCheck />} Testar fonte
        </Button>
        <Button variant="secondary" size="sm" disabled={busy !== "" || urlDraft.trim() === config?.url} onClick={() => void handleSaveUrl()}>
          Salvar URL
        </Button>
        <Button size="sm" disabled={busy !== ""} onClick={() => void handleRefreshNow()}>
          <RefreshCw className={busy === "refresh" ? "animate-spin" : ""} /> Atualizar agora
        </Button>
        <span className="font-mono text-[0.68rem] text-tertiary">último refresh: {formatRefreshedAt(detail?.refreshed_at)}</span>
      </div>

      <div className="mt-4">
        <label className={cn(fieldLabelClass, "mt-0")}>
          Modelos disponíveis ({detail?.models.length ?? 0}) — preços por 1M tokens
        </label>
        <TableWrap className="max-h-72 overflow-y-auto">
          <DataTable>
            <thead>
              <tr>
                <th className="left">Modelo</th>
                <th>Contexto</th>
                <th>Max out</th>
                <th>Reasoning</th>
                <th>$ entrada</th>
                <th>$ saída</th>
                <th className="left">Origem</th>
              </tr>
            </thead>
            <tbody>
              {(detail?.models ?? []).map((m) => (
                <tr key={`${m.provider}/${m.model}`}>
                  <td className="left">{m.provider}/{m.model}</td>
                  <td>{m.context_tokens ? `${Math.round(m.context_tokens / 1000)}k` : "—"}</td>
                  <td>{m.max_output_tokens ? `${Math.round(m.max_output_tokens / 1000)}k` : "—"}</td>
                  <td>{m.supports_reasoning_effort ? "✓" : "—"}</td>
                  <td>{fmt1m(m.input_cost_per_1m)}</td>
                  <td>{fmt1m(m.output_cost_per_1m)}</td>
                  <td className="left">{m.source === "builtin" ? "builtin" : "remoto"}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </TableWrap>
      </div>
    </div>
  );
}

/** Combobox de modelo com dropdown PRÓPRIO (não datalist): o nativo é sequestrado
 *  pelo gerenciador de senhas do Firefox quando o input fica adjacente a um campo
 *  password ("Manage Passwords" no lugar da lista). type="search" + lista nossa =
 *  imune à heurística e estilizada no design system.
 *  O valor ATIVO só muda ao escolher um modelo conhecido ou validar um custom —
 *  digitação parcial fica no draft (nunca persistir "gpt-9" pela metade). */
function ModelCombobox({
  id,
  value,
  onChange,
  models,
  customModels,
  onValidated,
  apiKeys,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  models: ModelOption[];
  customModels: string[];
  onValidated: (value: string) => void;
  apiKeys: { openai?: string; anthropic?: string };
}) {
  const [validation, setValidation] = useState<ValidationState>({ status: "idle" });
  const [draft, setDraft] = useState(value);
  const [listOpen, setListOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  useEffect(() => setDraft(value), [value]);
  const knownValues = new Set([...models.map((m) => `${m.provider}/${m.model}`), ...customModels]);
  const normalized = normalizeModelValue(draft);
  const isCustom = normalized.length > 0 && !knownValues.has(normalized);

  const allOptions = [
    ...models.map((m) => ({ value: `${m.provider}/${m.model}`, label: m.label })),
    ...customModels
      .filter((c) => !models.some((m) => `${m.provider}/${m.model}` === c))
      .map((c) => ({ value: c, label: `${c} (validado por você)` })),
  ];
  // Com o valor ativo intacto no campo, mostrar a lista inteira; filtrar só ao digitar
  const filter = draft.trim() === value.trim() ? "" : draft.trim().toLowerCase();
  const visibleOptions = filter
    ? allOptions.filter((o) => o.value.toLowerCase().includes(filter) || o.label.toLowerCase().includes(filter))
    : allOptions;

  function choose(optionValue: string) {
    setValidation({ status: "idle" });
    setDraft(optionValue);
    onChange(optionValue);
    setListOpen(false);
  }

  async function handleValidate() {
    const [provider, ...rest] = normalized.split("/");
    const model = rest.join("/");
    setValidation({ status: "validating" });
    try {
      const result = await validateModel(provider, model, apiKeys);
      if (result.valid) {
        setValidation({ status: "valid", detail: result.detail });
        setDraft(normalized);
        onChange(normalized);
        onValidated(normalized);
      } else {
        setValidation({ status: "invalid", detail: result.detail });
      }
    } catch (e) {
      setValidation({ status: "invalid", detail: e instanceof Error ? e.message : "Falha ao validar" });
    }
  }

  return (
    <div>
      <div className="flex items-center gap-1.5">
        <div className="relative flex-1">
          <input
            id={id}
            type="search"
            name={`atlasfile-model-${id}`}
            role="combobox"
            aria-expanded={listOpen}
            aria-controls={`${id}-listbox`}
            className={cn(
              nativeSelectClass,
              "w-full font-mono text-[0.8rem] [&::-webkit-search-cancel-button]:hidden [&::-webkit-search-decoration]:hidden"
            )}
            value={draft}
            placeholder="provider/modelo — digite para modelos novos"
            onFocus={() => {
              setListOpen(true);
              setHighlighted(0);
            }}
            onBlur={() => setListOpen(false)}
            onChange={(e: InputLikeEvent) => {
              setValidation({ status: "idle" });
              setDraft(e.target.value);
              setListOpen(true);
              setHighlighted(0);
              const candidate = normalizeModelValue(e.target.value);
              if (knownValues.has(candidate)) onChange(candidate);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setListOpen(true);
                setHighlighted((h) => Math.min(h + 1, visibleOptions.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setHighlighted((h) => Math.max(h - 1, 0));
              } else if (e.key === "Enter") {
                if (listOpen && visibleOptions[highlighted]) {
                  e.preventDefault();
                  choose(visibleOptions[highlighted].value);
                }
              } else if (e.key === "Escape") {
                setListOpen(false);
              }
            }}
            autoComplete="off"
            spellCheck={false}
          />
          {listOpen && visibleOptions.length > 0 && (
            <ul
              id={`${id}-listbox`}
              role="listbox"
              className="absolute left-0 right-0 top-[calc(100%+4px)] z-30 m-0 max-h-60 list-none overflow-y-auto rounded-md border border-border bg-panel p-1 shadow-[0_10px_28px_rgba(0,0,0,0.4)]"
            >
              {visibleOptions.map((option, index) => (
                <li
                  key={option.value}
                  role="option"
                  aria-selected={option.value === value}
                  className={cn(
                    "cursor-pointer rounded px-2 py-1.5 text-[0.8rem]",
                    index === highlighted ? "bg-accent-soft text-accent" : "text-foreground hover:bg-panel-strong",
                    option.value === value && "font-semibold"
                  )}
                  onMouseEnter={() => setHighlighted(index)}
                  onMouseDown={(e) => {
                    // mousedown: escolher antes do blur fechar a lista
                    e.preventDefault();
                    choose(option.value);
                  }}
                >
                  <span className="font-mono">{option.value}</span>
                  <span className="ml-2 text-[0.7rem] text-tertiary">{option.label}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        {isCustom && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handleValidate()}
            disabled={validation.status === "validating"}
            title="Confirmar na API do provedor que o modelo existe"
          >
            {validation.status === "validating" ? <Loader2 className="animate-spin" /> : <BadgeCheck />}
            Validar
          </Button>
        )}
      </div>
      {isCustom && validation.status === "idle" && (
        <span className={hintClass}>Modelo fora do catálogo — valide antes de usar.</span>
      )}
      {validation.status === "valid" && (
        <span className={cn(hintClass, "text-success")}>{validation.detail}</span>
      )}
      {validation.status === "invalid" && (
        <span className={cn(hintClass, "text-destructive")}>{validation.detail}</span>
      )}
    </div>
  );
}

export function AssistantSettingsModal({
  open,
  selectedModelTriage,
  selectedModel,
  models,
  openaiApiKey,
  anthropicApiKey,
  onChangeModelTriage,
  onChangeModel,
  onChangeOpenAiKey,
  onChangeAnthropicKey,
  autoTitleLLM,
  onChangeAutoTitleLLM,
  onClose
}: Props) {
  useEscapeKey(open ? onClose : null);

  const { customModels, addCustomModel, reloadModels } = useSettings();
  const { selectedProject, selectedProjectLabel } = useProject();
  const isSingleProject = selectedProject !== ALL_PROJECTS && !!selectedProject;
  const [activeTab, setActiveTab] = useState<"assistente" | "catalogo">("assistente");
  const [triageSaveStatus, setTriageSaveStatus] = useState("");
  const [channelCfg, setChannelCfg] = useState<ChannelConfig>(DEFAULT_TG_CONFIG);
  const [channelStatus, setChannelStatus] = useState<ChannelStatusResponse | null>(null);
  const [expandedChannel, setExpandedChannel] = useState<string | null>(null);
  const [showToken, setShowToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const persistConfig = useCallback((cfg: ChannelConfig) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSaving(true);
      try {
        const saved = await updateChannelConfig(cfg);
        setChannelCfg(saved);
        const st = await fetchChannelStatus();
        setChannelStatus(st);
      } catch {
        /* keep local state */
      } finally {
        setSaving(false);
      }
    }, 600);
  }, []);

  useEffect(() => {
    if (!open) return;
    const savedToken = loadTgToken();
    fetchChannelConfig()
      .then((cfg) => {
        if (!cfg.telegram.bot_token && savedToken) {
          const restored: ChannelConfig = {
            ...cfg,
            channels_enabled: true,
            telegram: { enabled: true, bot_token: savedToken, mirror_responses: cfg.telegram.mirror_responses },
          };
          setChannelCfg(restored);
          persistConfig(restored);
        } else {
          setChannelCfg(cfg);
        }
      })
      .catch(() => {
        if (savedToken) {
          const restored: ChannelConfig = {
            channels_enabled: true,
            telegram: { enabled: true, bot_token: savedToken, mirror_responses: false },
          };
          setChannelCfg(restored);
        }
      });
    fetchChannelStatus().then(setChannelStatus).catch(() => {});
  }, [open, persistConfig]);

  const updateTelegram = useCallback(
    (patch: Partial<ChannelConfig["telegram"]>) => {
      const merged = { ...channelCfg.telegram, ...patch };
      const anyEnabled = merged.enabled && !!merged.bot_token;
      const next: ChannelConfig = {
        ...channelCfg,
        channels_enabled: anyEnabled || channelCfg.channels_enabled,
        telegram: merged,
      };
      saveTgToken(merged.bot_token);
      setChannelCfg(next);
      persistConfig(next);
    },
    [channelCfg, persistConfig]
  );

  /** Grava provider/model da triagem direto no perfil do projeto selecionado —
   *  sem isso a escolha só valeria quando o card do Classificador estivesse montado. */
  async function persistTriageModelToProject(value: string) {
    onChangeModelTriage(value);
    if (!isSingleProject) return;
    const [provider, ...rest] = value.split("/");
    const model = rest.join("/");
    if (!provider || !model) return;
    setTriageSaveStatus("salvando...");
    try {
      const current = await fetchProjectProfile(selectedProject);
      const basePolicy = current.profile.classification.llm_policy ?? {
        enabled: false,
        provider: "openai" as const,
        model,
        mode: "tag_only" as const,
        allow_override_fields: ["document_type", "tags", "confidence", "topics"],
        override_guardrails: {
          business_domain_override_only_if_rule_confidence_below: 0.65,
          require_explanation: true,
          max_business_domain_changes: 1,
        },
      };
      const updated: ProjectProfileV2 = {
        ...current.profile,
        classification: {
          ...current.profile.classification,
          llm_policy: {
            ...basePolicy,
            provider: (provider === "anthropic" ? "anthropic" : "openai"),
            model,
          },
        },
      };
      await updateProjectProfile(selectedProject, updated, current.version);
      setTriageSaveStatus(`salvo no projeto ${selectedProjectLabel}`);
    } catch {
      setTriageSaveStatus("falha ao salvar no projeto");
    }
  }

  if (!open) return null;

  const chatProvider = selectedModel ? normalizeModelValue(selectedModel).split("/")[0]?.toLowerCase() : null;
  const triageProvider = selectedModelTriage ? normalizeModelValue(selectedModelTriage).split("/")[0]?.toLowerCase() : null;
  const needOpenAI = chatProvider === "openai" || triageProvider === "openai";
  const needAnthropic = chatProvider === "anthropic" || triageProvider === "anthropic";

  const tgStatus = channelStatus?.channels.find((c) => c.channel_id === "telegram");

  return (
    <ModalShell label="Configuração do Assistente" title="Configuração do Assistente" className="max-h-[85vh] overflow-y-auto">
      <div className="mb-3 flex gap-1.5">
        {([["assistente", "Assistente"], ["catalogo", "Catálogo de modelos"]] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={cn(
              "rounded-full border px-3 py-1 text-[0.8rem] shadow-none transition-colors",
              activeTab === key
                ? "border-accent/40 bg-accent-soft text-accent"
                : "border-border bg-transparent text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === "catalogo" && <CatalogTab onCatalogChanged={reloadModels} />}

      {activeTab === "assistente" && (
      <>
      <p className="text-xs text-muted-foreground">
        Chaves são enviadas só na requisição e não ficam no servidor. Modelos novos podem ser digitados e validados na
        API do provedor (aba Catálogo mostra parâmetros e preços).
      </p>

      <label className={fieldLabelClass} htmlFor="settings-model-chat">Modelo chat</label>
      <ModelCombobox
        id="settings-model-chat"
        value={selectedModel}
        onChange={onChangeModel}
        models={models}
        customModels={customModels}
        onValidated={addCustomModel}
        apiKeys={{ openai: openaiApiKey || undefined, anthropic: anthropicApiKey || undefined }}
      />

      {isSingleProject ? (
        <>
          <label className={fieldLabelClass} htmlFor="settings-model-triage">
            Modelo triagem — projeto {selectedProjectLabel}
          </label>
          <ModelCombobox
            id="settings-model-triage"
            value={selectedModelTriage}
            onChange={(value) => void persistTriageModelToProject(value)}
            models={models}
            customModels={customModels}
            onValidated={addCustomModel}
            apiKeys={{ openai: openaiApiKey || undefined, anthropic: anthropicApiKey || undefined }}
          />
          <span className={cn(hintClass, triageSaveStatus.startsWith("falha") && "text-destructive")}>
            {triageSaveStatus || "A política LLM de triagem é por projeto — gravada no perfil ao selecionar."}
          </span>
        </>
      ) : (
        <>
          <label className={fieldLabelClass}>Modelo triagem</label>
          <span className={hintClass}>
            A política LLM de triagem é por projeto. Selecione um projeto na barra lateral para configurá-la.
          </span>
        </>
      )}

      {needOpenAI && (
        <>
          <label className={fieldLabelClass} htmlFor="settings-openai-key">OpenAI API Key</label>
          <Input
            id="settings-openai-key"
            type="password"
            className="font-mono"
            value={openaiApiKey}
            onChange={(e: InputLikeEvent) => onChangeOpenAiKey(e.target.value)}
            placeholder="sk-..."
            autoComplete="off"
          />
        </>
      )}
      {needAnthropic && (
        <>
          <label className={fieldLabelClass} htmlFor="settings-anthropic-key">Anthropic API Key</label>
          <Input
            id="settings-anthropic-key"
            type="password"
            className="font-mono"
            value={anthropicApiKey}
            onChange={(e: InputLikeEvent) => onChangeAnthropicKey(e.target.value)}
            placeholder="sk-ant-..."
            autoComplete="off"
          />
        </>
      )}

      <label className="mt-4 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-3.5 accent-[var(--accent)]"
          checked={autoTitleLLM}
          onChange={(e) => onChangeAutoTitleLLM(e.target.checked)}
        />
        Gerar título da sessão via LLM (em background)
      </label>
      <span className={hintClass}>Se desativado, o título será a primeira mensagem da conversa.</span>

      {/* ── Channels ── */}
      <hr className="my-4 border-0 border-t border-border" />
      <h4 className="font-display text-sm font-bold text-foreground-strong">Canais de comunicação</h4>
      <p className="mb-3 mt-0.5 text-xs text-muted-foreground">
        Conecte o assistente a canais de mensagem externos. Canais são opcionais e não afetam o chat web.
      </p>

      {/* Telegram */}
      <div className={cn(channelCardClass, "mb-2")}>
        <button
          type="button"
          className="flex w-full items-center justify-between border-0 bg-transparent p-0 text-left shadow-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => setExpandedChannel(expandedChannel === "telegram" ? null : "telegram")}
          aria-expanded={expandedChannel === "telegram"}
        >
          <strong className="flex items-center gap-1 font-display text-sm text-foreground-strong">
            <ChevronRight
              size={14}
              aria-hidden
              className={cn("text-tertiary transition-transform", expandedChannel === "telegram" && "rotate-90")}
            />
            Telegram
          </strong>
          <span
            className={cn(
              "flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 font-mono text-[0.68rem]",
              tgStatus?.connected ? "text-success" : tgStatus?.error ? "text-destructive" : "text-tertiary"
            )}
          >
            <span
              aria-hidden
              className={cn(
                "size-1.5 rounded-full",
                tgStatus?.connected ? "bg-success" : tgStatus?.error ? "bg-destructive" : "bg-tertiary"
              )}
            />
            {tgStatus?.connected ? "Conectado" : tgStatus?.error ? "Erro" : channelCfg.telegram.bot_token ? "Desconectado" : "Sem token"}
          </span>
        </button>
        {expandedChannel === "telegram" && (
          <div className="mt-3">
            <label className={cn(fieldLabelClass, "mt-0 flex items-center gap-1.5")} htmlFor="ch-tg-token">
              Bot Token
              <a
                href="https://t.me/BotFather"
                target="_blank"
                rel="noopener noreferrer"
                title="Criar bot via @BotFather"
                className="inline-flex text-accent"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink size={13} />
              </a>
            </label>
            <div className="flex items-center gap-1.5">
              <Input
                id="ch-tg-token"
                type={showToken ? "text" : "password"}
                className="flex-1 font-mono"
                value={channelCfg.telegram.bot_token}
                onChange={(e: InputLikeEvent) => updateTelegram({ bot_token: e.target.value, enabled: true })}
                placeholder="123456:ABC-DEF..."
                autoComplete="off"
              />
              <Button
                variant="secondary"
                size="icon"
                onClick={() => setShowToken(!showToken)}
                title={showToken ? "Ocultar token" : "Mostrar token"}
                aria-label={showToken ? "Ocultar token" : "Mostrar token"}
              >
                {showToken ? <EyeOff /> : <Eye />}
              </Button>
            </div>
            <span className={hintClass}>
              Crie um bot via{" "}
              <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                @BotFather
              </a>
              , copie o token e cole acima.
            </span>
            <label className="mt-3 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-3.5 accent-[var(--accent)]"
                checked={channelCfg.telegram.mirror_responses}
                onChange={(e) => updateTelegram({ mirror_responses: e.target.checked })}
              />
              Espelhar respostas para o Telegram
            </label>
            <span className={hintClass}>
              Quando ativado, respostas enviadas pelo chat web em sessões originadas no Telegram também são encaminhadas
              ao Telegram.
            </span>
            {tgStatus?.error && <p className="mt-2 text-[0.8rem] text-destructive">Erro: {tgStatus.error}</p>}
            {saving && <p className={hintClass}>Salvando...</p>}
          </div>
        )}
      </div>

      {/* Futuras integrações */}
      <div className={cn(channelCardClass, "mb-2 opacity-50")}>
        <div className="flex items-center justify-between">
          <strong className="font-display text-sm text-foreground-strong">Discord</strong>
          <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[0.68rem] text-tertiary">Em breve</span>
        </div>
      </div>
      <div className={cn(channelCardClass, "opacity-50")}>
        <div className="flex items-center justify-between">
          <strong className="font-display text-sm text-foreground-strong">Slack</strong>
          <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[0.68rem] text-tertiary">Em breve</span>
        </div>
      </div>

      </>
      )}

      <ModalActions>
        <Button onClick={onClose}>Fechar</Button>
      </ModalActions>
    </ModalShell>
  );
}
