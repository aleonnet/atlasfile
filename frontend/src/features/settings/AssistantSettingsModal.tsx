import { useCallback, useEffect, useRef, useState } from "react";
import { Eye, EyeOff, ExternalLink } from "lucide-react";
import { fetchChannelConfig, fetchChannelStatus, updateChannelConfig } from "../../api";
import { useEscapeKey } from "../../hooks/useEscapeKey";
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
            telegram: { enabled: true, bot_token: savedToken },
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
            telegram: { enabled: true, bot_token: savedToken },
          };
          setChannelCfg(restored);
        }
      });
    fetchChannelStatus().then(setChannelStatus).catch(() => {});
  }, [open, persistConfig]);

  const updateCfg = useCallback(
    (patch: Partial<ChannelConfig>) => {
      const next = { ...channelCfg, ...patch };
      setChannelCfg(next);
      persistConfig(next);
    },
    [channelCfg, persistConfig]
  );

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
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Configuração do Assistente" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxHeight: "85vh", overflowY: "auto" }}>
        <h3>Configuração do Assistente</h3>
        <p className="sub">
          Modelo de triagem (classificação no ingest) e modelo de chat podem ser diferentes. Chaves são enviadas só na requisição e não ficam no servidor.
        </p>
        <div className="field">
          <label htmlFor="settings-model-triage">Modelo triagem</label>
          <select
            id="settings-model-triage"
            value={selectedModelTriage}
            onChange={(e: InputLikeEvent) => onChangeModelTriage(e.target.value)}
          >
            {models.map((m) => (
              <option key={`triage-${m.label}`} value={`${m.provider}/${m.model}`}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="settings-model-chat">Modelo chat</label>
          <select
            id="settings-model-chat"
            value={selectedModel}
            onChange={(e: InputLikeEvent) => onChangeModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={`chat-${m.label}`} value={`${m.provider}/${m.model}`}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        {needOpenAI && (
          <div className="field">
            <label htmlFor="settings-openai-key">OpenAI API Key</label>
            <input
              id="settings-openai-key"
              type="password"
              value={openaiApiKey}
              onChange={(e: InputLikeEvent) => onChangeOpenAiKey(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
            />
          </div>
        )}
        {needAnthropic && (
          <div className="field">
            <label htmlFor="settings-anthropic-key">Anthropic API Key</label>
            <input
              id="settings-anthropic-key"
              type="password"
              value={anthropicApiKey}
              onChange={(e: InputLikeEvent) => onChangeAnthropicKey(e.target.value)}
              placeholder="sk-ant-..."
              autoComplete="off"
            />
          </div>
        )}
        <label className="checkbox-inline" style={{ marginTop: "0.5rem" }}>
          <input
            type="checkbox"
            checked={autoTitleLLM}
            onChange={(e) => onChangeAutoTitleLLM(e.target.checked)}
          />
          Gerar título da sessão via LLM (em background)
        </label>
        <span className="sub" style={{ fontSize: "0.8rem", marginTop: 2 }}>
          Se desativado, o título será a primeira mensagem da conversa.
        </span>

        {/* ── Channels ── */}
        <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "16px 0" }} />
        <h4 style={{ margin: "0 0 4px" }}>Canais de comunicação</h4>
        <p className="sub" style={{ marginBottom: 12 }}>
          Conecte o assistente a canais de mensagem externos. Canais são opcionais e não afetam o chat web.
        </p>

        {/* Telegram card */}
        <div className="card" style={{ marginBottom: 8 }}>
          <div
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
            onClick={() => setExpandedChannel(expandedChannel === "telegram" ? null : "telegram")}
          >
            <strong style={{ fontSize: "0.95rem" }}>
              {expandedChannel === "telegram" ? "▼" : "▶"} Telegram
            </strong>
            <span className="pill" style={{
              color: tgStatus?.connected ? "var(--accent)" : tgStatus?.error ? "var(--danger, red)" : undefined,
              opacity: tgStatus?.connected || tgStatus?.error ? 1 : 0.6,
            }}>
              {tgStatus?.connected ? "● Conectado" : tgStatus?.error ? "● Erro" : channelCfg.telegram.bot_token ? "○ Desconectado" : "○ Sem token"}
            </span>
          </div>
          {expandedChannel === "telegram" && (
            <div style={{ marginTop: 10 }}>
              <div className="field" style={{ marginBottom: 6 }}>
                <label htmlFor="ch-tg-token" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  Bot Token
                  <a
                    href="https://t.me/BotFather"
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Criar bot via @BotFather"
                    style={{ display: "inline-flex", color: "var(--accent)" }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink size={14} />
                  </a>
                </label>
                <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <input
                    id="ch-tg-token"
                    type={showToken ? "text" : "password"}
                    value={channelCfg.telegram.bot_token}
                    onChange={(e: InputLikeEvent) => updateTelegram({ bot_token: e.target.value, enabled: true })}
                    placeholder="123456:ABC-DEF..."
                    autoComplete="off"
                    style={{ flex: 1 }}
                  />
                  <button
                    type="button"
                    className="btn"
                    style={{ padding: "5px 6px", lineHeight: 1, display: "inline-flex" }}
                    onClick={() => setShowToken(!showToken)}
                    title={showToken ? "Ocultar token" : "Mostrar token"}
                  >
                    {showToken ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
              <span className="sub" style={{ fontSize: "0.8rem" }}>
                Crie um bot via{" "}
                <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>
                  @BotFather
                </a>
                , copie o token e cole acima.
              </span>
              <label className="checkbox-inline" style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 6 }}>
                <input
                  type="checkbox"
                  checked={channelCfg.telegram.mirror_responses}
                  onChange={(e) => updateTelegram({ mirror_responses: e.target.checked })}
                />
                Espelhar respostas para o Telegram
              </label>
              <span className="sub" style={{ fontSize: "0.78rem", marginTop: 2 }}>
                Quando ativado, respostas enviadas pelo chat web em sessões originadas no Telegram também são encaminhadas ao Telegram.
              </span>
              {tgStatus?.error && (
                <p style={{ color: "var(--danger, red)", fontSize: "0.85rem", marginTop: 6 }}>
                  Erro: {tgStatus.error}
                </p>
              )}
              {saving && (
                <p className="sub" style={{ fontSize: "0.8rem", marginTop: 4 }}>Salvando...</p>
              )}
            </div>
          )}
        </div>

        {/* Future channels (placeholder) */}
        <div className="card" style={{ marginBottom: 8, opacity: 0.5 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <strong style={{ fontSize: "0.95rem" }}>▶ Discord</strong>
            <span className="pill">Em breve</span>
          </div>
        </div>
        <div className="card" style={{ marginBottom: 8, opacity: 0.5 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <strong style={{ fontSize: "0.95rem" }}>▶ Slack</strong>
            <span className="pill">Em breve</span>
          </div>
        </div>

        <div className="modal-actions">
          <button type="button" className="btn primary" onClick={onClose}>
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}
