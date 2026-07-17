import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight, Eye, EyeOff, ExternalLink } from "lucide-react";
import { fetchChannelConfig, fetchChannelStatus, updateChannelConfig } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "../../components/ui/modal-shell";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { cn } from "../../lib/utils";
import type { ChannelConfig, ChannelStatusResponse, ModelOption } from "../../types";

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

  if (!open) return null;

  const chatProvider = selectedModel ? selectedModel.split("/")[0]?.toLowerCase() : null;
  const triageProvider = selectedModelTriage ? selectedModelTriage.split("/")[0]?.toLowerCase() : null;
  const needOpenAI = chatProvider === "openai" || triageProvider === "openai";
  const needAnthropic = chatProvider === "anthropic" || triageProvider === "anthropic";

  const tgStatus = channelStatus?.channels.find((c) => c.channel_id === "telegram");

  return (
    <ModalShell label="Configuração do Assistente" title="Configuração do Assistente" className="max-h-[85vh] overflow-y-auto">
      <p className="text-xs text-muted-foreground">
        Modelo de triagem (classificação no ingest) e modelo de chat podem ser diferentes. Chaves são enviadas só na
        requisição e não ficam no servidor.
      </p>

      <label className={fieldLabelClass} htmlFor="settings-model-triage">Modelo triagem</label>
      <select
        id="settings-model-triage"
        className={nativeSelectClass}
        value={selectedModelTriage}
        onChange={(e: InputLikeEvent) => onChangeModelTriage(e.target.value)}
      >
        {models.map((m) => (
          <option key={`triage-${m.label}`} value={`${m.provider}/${m.model}`}>
            {m.label}
          </option>
        ))}
      </select>

      <label className={fieldLabelClass} htmlFor="settings-model-chat">Modelo chat</label>
      <select
        id="settings-model-chat"
        className={nativeSelectClass}
        value={selectedModel}
        onChange={(e: InputLikeEvent) => onChangeModel(e.target.value)}
      >
        {models.map((m) => (
          <option key={`chat-${m.label}`} value={`${m.provider}/${m.model}`}>
            {m.label}
          </option>
        ))}
      </select>

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

      <ModalActions>
        <Button onClick={onClose}>Fechar</Button>
      </ModalActions>
    </ModalShell>
  );
}
