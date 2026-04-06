/**
 * Chat panel no estilo OpenClaw: avatar do agente, nome, hora por mensagem,
 * três pontos saltitantes quando está pensando, botão Brain para thinking, suporte a colar imagens.
 * Conteúdo do assistente é renderizado como Markdown (GFM), como no OpenClaw (marked + DOMPurify).
 * Ref.: openclaw-main/ui/src/ui/views/chat.ts + grouped-render.ts + markdown.ts
 */
import React, { useRef, useEffect } from "react";
import { Brain, Clock, Loader2, Pencil, Plus, Send, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { ChartBlock } from "./ChartBlock";
import { CompanionOrb } from "./CompanionOrb";
import type { CompanionState } from "./CompanionOrb";
import { useCompanionState } from "../hooks/useCompanionState";
import "./ChatPanel.css";

const _safeImgSrc = (src: string | undefined): boolean =>
  Boolean(src && /^(https?:|\/|data:image)/i.test(src));

/** Stable reference — avoids ReactMarkdown full re-render on parent state changes. */
const MARKDOWN_COMPONENTS = {
  a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} target="_blank" rel="noreferrer noopener" {...props}>
      {children}
    </a>
  ),
  img: ({ src, alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) =>
    _safeImgSrc(src) ? <img src={src} alt={alt ?? ""} {...props} /> : null,
  code: ({ className, children, ...props }: React.HTMLAttributes<HTMLElement> & { inline?: boolean }) => {
    if (className === "language-chart" && typeof children === "string") {
      return <ChartBlock jsonString={children} />;
    }
    const childStr = Array.isArray(children) ? children.join("") : children;
    if (className === "language-chart" && typeof childStr === "string") {
      return <ChartBlock jsonString={childStr} />;
    }
    return <code className={className} {...props}>{children}</code>;
  },
};

/** Part for multimodal display (text or image in bubble). */
export type ChatContentPartDisplay =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

export interface ChatMessageWithMeta {
  role: "user" | "assistant";
  content: string;
  timestamp?: number;
  /** For user messages with images; enables rendering thumbnails and modal. */
  contentParts?: ChatContentPartDisplay[];
  /** Model that generated this response (e.g. "openai/gpt-4.1") */
  model?: string;
}

export interface ChatAttachment {
  id: string;
  dataUrl: string;
  mimeType: string;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  model: string;
  createdAt: number;
  updatedAt: number;
}

export interface ChatPanelProps {
  /** Nome do agente (ex.: "Orion", "Assistente") */
  agentName: string;
  /** URL do avatar do agente (opcional) */
  agentAvatarUrl?: string | null;
  messages: ChatMessageWithMeta[];
  /** Últimas ferramentas usadas (exibidas após última mensagem do assistente) */
  lastToolCalls?: { name: string; result_preview?: string }[];
  sending: boolean;
  error: string | null;
  canAbort: boolean;
  selectedModel: string;
  models: { provider: string; model: string; label: string; supports_reasoning_effort?: boolean }[];
  onModelChange: (value: string) => void;
  onOpenSettings: () => void;
  onSend: (text: string, attachments?: ChatAttachment[]) => void;
  onAbort: () => void;
  onNewSession: () => void;
  /** Mostrar modo thinking (reasoning); modelos com essa capacidade */
  showThinking: boolean;
  onShowThinkingChange: (value: boolean) => void;
  disabled?: boolean;
  sessions?: ChatSessionSummary[];
  sessionsLoading?: boolean;
  activeSessionId?: string | null;
  historyModalOpen?: boolean;
  onOpenHistory?: () => void;
  onCloseHistory?: () => void;
  onSelectSession?: (sessionId: string) => void;
  onEditSession?: (sessionId: string, newTitle: string) => void;
  onDeleteSession?: (sessionId: string) => void;
  /** Overlay com spinner durante salvamento da sessão (nova sessão) */
  savingSession?: boolean;
  /** Telegram channel connection state */
  telegramConnected?: boolean;
  onToggleTelegram?: () => void;
  /** Context pressure ratio (0.0 to 1.0) from the last LLM response */
  contextPressureRatio?: number;
}

function generateAttachmentId(): string {
  return `att-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

const SESSION_GROUP_BUCKETS: { minDays: number; maxDays: number; label: string }[] = [
  { minDays: 0, maxDays: 1, label: "Hoje" },
  { minDays: 1, maxDays: 2, label: "1 dia" },
  { minDays: 2, maxDays: 3, label: "2 dias" },
  { minDays: 3, maxDays: 4, label: "3 dias" },
  { minDays: 4, maxDays: 5, label: "4 dias" },
  { minDays: 5, maxDays: 6, label: "5 dias" },
  { minDays: 6, maxDays: 7, label: "6 dias" },
  { minDays: 7, maxDays: 14, label: "1 semana" },
  { minDays: 14, maxDays: 21, label: "2 semanas" },
  { minDays: 21, maxDays: 30, label: "3 semanas" },
  { minDays: 30, maxDays: 90, label: "1 mês" },
  { minDays: 90, maxDays: Infinity, label: "3 meses" }
];

function getSessionGroupLabel(updatedAt: number): string {
  const ts = Number(updatedAt);
  if (!Number.isFinite(ts) || ts <= 0) return "Anterior";
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const updated = new Date(ts);
  if (Number.isNaN(updated.getTime())) return "Anterior";
  const updatedDayStart = new Date(updated.getFullYear(), updated.getMonth(), updated.getDate()).getTime();
  const calendarDaysAgo = Math.floor((todayStart - updatedDayStart) / (24 * 60 * 60 * 1000));
  const bucket = SESSION_GROUP_BUCKETS.find(
    (b) => calendarDaysAgo >= b.minDays && calendarDaysAgo < b.maxDays
  );
  return bucket ? bucket.label : "Anterior";
}

export function ChatPanel({
  agentName,
  agentAvatarUrl,
  messages,
  lastToolCalls = [],
  sending,
  error,
  canAbort,
  selectedModel,
  models,
  onModelChange,
  onOpenSettings,
  onSend,
  onAbort,
  onNewSession,
  showThinking,
  onShowThinkingChange,
  disabled = false,
  sessions = [],
  sessionsLoading = false,
  activeSessionId = null,
  historyModalOpen = false,
  onOpenHistory,
  onCloseHistory,
  onSelectSession,
  onEditSession,
  onDeleteSession,
  savingSession = false,
  telegramConnected = false,
  onToggleTelegram,
  contextPressureRatio = 0,
}: ChatPanelProps) {
  const reasoningSupported =
    selectedModel && (models.find((m) => `${m.provider}/${m.model}` === selectedModel)?.supports_reasoning_effort ?? false);
  const companionState = useCompanionState(sending, error);
  const [draft, setDraft] = React.useState("");
  const [attachments, setAttachments] = React.useState<ChatAttachment[]>([]);
  const [historySearch, setHistorySearch] = React.useState("");
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editingTitle, setEditingTitle] = React.useState("");
  const threadRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const timerAnchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const handleSend = () => {
    const text = draft.trim();
    if (!text && attachments.length === 0) return;
    if (disabled || sending) return;
    onSend(text, attachments.length > 0 ? attachments : undefined);
    setDraft("");
    setAttachments([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter") return;
    if (e.nativeEvent.isComposing) return;
    if (e.shiftKey) return;
    e.preventDefault();
    handleSend();
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const imageItems: DataTransferItem[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type.startsWith("image/")) imageItems.push(item);
    }
    if (imageItems.length === 0) return;
    e.preventDefault();
    imageItems.forEach((item) => {
      const file = item.getAsFile();
      if (!file) return;
      const reader = new FileReader();
      reader.addEventListener("load", () => {
        const dataUrl = reader.result as string;
        setAttachments((prev) => [
          ...prev,
          { id: generateAttachmentId(), dataUrl, mimeType: file.type }
        ]);
      });
      reader.readAsDataURL(file);
    });
  };

  const hasAttachments = attachments.length > 0;
  const placeholder = hasAttachments
    ? "Adicione uma mensagem ou cole mais imagens..."
    : "Mensagem (↵ enviar, Shift+↵ quebra de linha, cole imagens)";

  return (
    <section className="card chat chat-panel" aria-busy={savingSession}>
      {savingSession && (
        <div className="chat-panel-saving-overlay" role="status" aria-live="polite">
          <Loader2 size={32} className="chat-panel-saving-spinner spin" aria-hidden />
          <span>Salvando sessão…</span>
        </div>
      )}
      <div className="chat-toolbar chat-panel-toolbar">
        <label htmlFor="chat-panel-model">Modelo</label>
        <select
          id="chat-panel-model"
          value={selectedModel}
          onChange={(e) => onModelChange(e.target.value)}
          disabled={models.length === 0}
        >
          {models.map((m) => (
            <option key={m.label} value={`${m.provider}/${m.model}`}>
              {m.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="chat-controls__icon-btn"
          onClick={onOpenSettings}
          title="Configuração (modelo e API Key)"
          aria-label="Configuração (modelo e API Key)"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
        <span className="chat-controls__separator">|</span>
        <button
          type="button"
          className={`chat-controls__thinking-btn ${showThinking && reasoningSupported ? "chat-controls__thinking-btn--active" : ""}`}
          onClick={() => reasoningSupported && onShowThinkingChange(!showThinking)}
          title={reasoningSupported ? "Toggle assistant thinking/working output" : "Este modelo não suporta reasoning/thinking"}
          aria-pressed={showThinking}
          aria-label="Toggle assistant thinking/working output"
          disabled={!reasoningSupported}
        >
          <Brain size={18} strokeWidth={2} aria-hidden />
        </button>
        <button
          type="button"
          className="chat-controls__icon-btn"
          onClick={onNewSession}
          title="Nova sessão"
          aria-label="Nova sessão"
        >
          <Plus size={18} strokeWidth={2} aria-hidden />
        </button>
        <div className="chat-history-anchor" ref={timerAnchorRef}>
          <button
            type="button"
            className="chat-controls__icon-btn"
            onClick={onOpenHistory}
            title="Histórico de sessões"
            aria-label="Histórico de sessões"
            aria-expanded={historyModalOpen}
          >
            <Clock size={18} strokeWidth={2} aria-hidden />
          </button>
          {historyModalOpen && (
            <>
              <button
                type="button"
                className="chat-history-modal-backdrop"
                aria-label="Fechar histórico de sessões"
                onClick={onCloseHistory}
              />
              <div
                className="chat-history-modal"
                role="dialog"
                aria-label="Histórico de sessões"
                aria-modal="true"
              >
              <div className="chat-history-modal__search">
                <input
                  type="text"
                  placeholder="Search…"
                  value={historySearch}
                  onChange={(e) => setHistorySearch(e.target.value)}
                  onKeyDown={(e) => e.key === "Escape" && onCloseHistory?.()}
                  aria-label="Filtrar sessões por título"
                />
              </div>
              <div className="chat-history-modal__list">
                {sessionsLoading ? (
                  <div className="chat-history-modal__loading">Carregando…</div>
                ) : (() => {
                  const q = historySearch.trim().toLowerCase();
                  const filtered = q
                    ? sessions.filter((s) => s.title.toLowerCase().includes(q))
                    : sessions;
                  const byGroup = new Map<string, ChatSessionSummary[]>();
                  filtered.forEach((s) => {
                    const label = getSessionGroupLabel(s.updatedAt);
                    if (!byGroup.has(label)) byGroup.set(label, []);
                    byGroup.get(label)!.push(s);
                  });
                  const order = SESSION_GROUP_BUCKETS.map((g) => g.label).concat("Anterior");
                  const groups = order.filter((l) => byGroup.has(l)).map((l) => ({ label: l, items: byGroup.get(l)! }));
                  if (groups.length === 0) {
                    return <div className="chat-history-modal__empty">Nenhuma sessão encontrada.</div>;
                  }
                  return groups.map((g) => (
                    <div key={g.label} className="chat-history-modal__group">
                      <div className="chat-history-modal__group-title">{g.label}</div>
                      {g.items.map((s) => (
                        <div
                          key={s.id}
                          className="chat-history-modal__item"
                          role="button"
                          tabIndex={0}
                          onClick={() => {
                            if (editingId === s.id) return;
                            onSelectSession?.(s.id);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              if (editingId === s.id) return;
                              onSelectSession?.(s.id);
                            }
                            if (e.key === "Escape") {
                              setEditingId(null);
                              onCloseHistory?.();
                            }
                          }}
                        >
                          {editingId === s.id ? (
                            <input
                              type="text"
                              className="chat-history-modal__item-title"
                              value={editingTitle}
                              onChange={(e) => setEditingTitle(e.target.value)}
                              onBlur={() => {
                                const t = editingTitle.trim();
                                if (t && onEditSession) onEditSession(s.id, t);
                                setEditingId(null);
                              }}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  const t = editingTitle.trim();
                                  if (t && onEditSession) onEditSession(s.id, t);
                                  setEditingId(null);
                                }
                                e.stopPropagation();
                              }}
                              onClick={(e) => e.stopPropagation()}
                              autoFocus
                              aria-label="Editar título"
                            />
                          ) : (
                            <>
                              <span className="chat-history-modal__item-title">
                                {s.title || "Sem título"}
                              </span>
                              <div className="chat-history-modal__item-actions" onClick={(e) => e.stopPropagation()}>
                                <button
                                  type="button"
                                  title="Editar título"
                                  aria-label="Editar título"
                                  onClick={() => {
                                    setEditingId(s.id);
                                    setEditingTitle(s.title);
                                  }}
                                >
                                  <Pencil size={14} aria-hidden />
                                </button>
                                <button
                                  type="button"
                                  title="Excluir sessão"
                                  aria-label="Excluir sessão"
                                  onClick={() => onDeleteSession?.(s.id)}
                                >
                                  <Trash2 size={14} aria-hidden />
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      ))}
                    </div>
                  ));
                })()}
              </div>
            </div>
            </>
          )}
        </div>
        {onToggleTelegram && (
          <button
            type="button"
            className="chat-controls__icon-btn"
            onClick={onToggleTelegram}
            title={telegramConnected ? "Telegram conectado — clique para desconectar" : "Telegram desconectado — clique para conectar"}
            aria-label={telegramConnected ? "Desconectar Telegram" : "Conectar Telegram"}
            style={{ position: "relative" }}
          >
            <Send size={16} strokeWidth={2} aria-hidden />
            <span
              style={{
                position: "absolute",
                top: 2,
                right: 2,
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: telegramConnected ? "var(--accent)" : "var(--muted, #aaa)",
                border: "1.5px solid var(--bg)",
              }}
            />
          </button>
        )}
      </div>

      {error && <div className="callout danger chat-panel-error">{error}</div>}

      <div className="chat-thread chat-panel-thread" ref={threadRef} role="log">
        {messages.length === 0 && !sending && (
          <p className="chat-panel-empty">Envie uma mensagem para o assistente. Use Config para modelo e API Key.</p>
        )}
        {messages.map((msg, idx) => (
          <ChatMessageBubble
            key={`${msg.role}-${msg.timestamp ?? idx}-${idx}`}
            role={msg.role}
            content={msg.content}
            contentParts={msg.contentParts}
            timestamp={msg.timestamp}
            agentName={agentName}
            agentAvatarUrl={msg.role === "assistant" ? agentAvatarUrl : undefined}
            isLastAssistant={msg.role === "assistant" && idx === messages.length - 1}
            lastToolCalls={msg.role === "assistant" && idx === messages.length - 1 ? lastToolCalls : undefined}
            model={msg.model}
          />
        ))}
        {sending && (
          <ChatReadingIndicator agentName={agentName} companionState={companionState} />
        )}
      </div>

      <div className="chat-compose chat-panel-compose">
        {attachments.length > 0 && (
          <div className="chat-attachments">
            {attachments.map((att) => (
              <div key={att.id} className="chat-attachment">
                <img src={att.dataUrl} alt="Anexo" className="chat-attachment__img" />
                <button
                  type="button"
                  className="chat-attachment__remove"
                  aria-label="Remover anexo"
                  onClick={() => setAttachments((prev) => prev.filter((a) => a.id !== att.id))}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="chat-compose__row">
          <label className="field chat-compose__field">
            <span className="visually-hidden">Mensagem</span>
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={placeholder}
              disabled={disabled}
              rows={2}
            />
          </label>
          <div className="chat-compose__actions">
            <ContextRing ratio={contextPressureRatio} onNewSession={onNewSession} />
            <button
              type="button"
              className="btn"
              disabled={disabled}
              onClick={canAbort && sending ? onAbort : onNewSession}
            >
              {canAbort && sending ? "Parar" : "Nova sessão"}
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={disabled || sending || (!draft.trim() && !hasAttachments)}
              onClick={handleSend}
            >
              {sending ? "Enviando…" : "Enviar"} <kbd className="btn-kbd">↵</kbd>
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function ChatMessageBubble({
  role,
  content,
  contentParts,
  timestamp,
  agentName,
  agentAvatarUrl,
  isLastAssistant,
  lastToolCalls,
  model
}: {
  role: "user" | "assistant";
  content: string;
  contentParts?: ChatContentPartDisplay[];
  timestamp?: number;
  agentName: string;
  agentAvatarUrl?: string | null;
  isLastAssistant: boolean;
  lastToolCalls?: { name: string; result_preview?: string }[];
  model?: string;
}) {
  const [imageModalUrl, setImageModalUrl] = React.useState<string | null>(null);
  useEffect(() => {
    if (!imageModalUrl) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setImageModalUrl(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [imageModalUrl]);
  const timeStr = timestamp
    ? new Date(timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : "";
  const modelShort = model ? model.replace(/^[^/]+\//, "") : "";
  const who = role === "user" ? "Você" : (modelShort ? `${agentName} (${modelShort})` : agentName);
  const isUser = role === "user";
  const hasImageParts = isUser && contentParts?.some((p) => p.type === "image_url");

  const avatarEl =
    isUser ? (
      <div className="chat-avatar user">U</div>
    ) : agentAvatarUrl && /^(https?:|\/|data:image)/i.test(agentAvatarUrl) ? (
      <img src={agentAvatarUrl} alt={agentName} className="chat-avatar assistant" />
    ) : (
      <CompanionOrb state="idle" size={40} />
    );


  const userContentEl = isUser && hasImageParts && contentParts ? (
    <div className="chat-bubble-user-content">
      {contentParts.map((p, i) =>
        p.type === "text" ? (
          p.text ? <span key={i}>{p.text}</span> : null
        ) : (
          <button
            key={i}
            type="button"
            className="chat-bubble-inline-img"
            onClick={() => setImageModalUrl(p.image_url.url)}
            aria-label="Ver imagem em tamanho maior"
          >
            <img src={p.image_url.url} alt="Anexo" className="chat-bubble-inline-img__thumb" />
          </button>
        )
      )}
    </div>
  ) : (
    content
  );

  return (
    <div className={`chat-group ${isUser ? "user" : "assistant"}`}>
      {avatarEl}
      <div className="chat-group-messages">
        <div className="chat-bubble fade-in">
          <div className={`chat-text ${!isUser ? "chat-text--markdown" : ""}`}>
            {isUser ? (
              userContentEl
            ) : (
              <ReactMarkdown components={MARKDOWN_COMPONENTS}>{content}</ReactMarkdown>
            )}
          </div>
        </div>
        {imageModalUrl !== null && (
          <div
            className="chat-image-modal-overlay"
            role="dialog"
            aria-modal="true"
            aria-label="Imagem em tamanho maior"
            onClick={() => setImageModalUrl(null)}
          >
            <div className="chat-image-modal" onClick={(e) => e.stopPropagation()}>
              <img src={imageModalUrl} alt="Imagem anexada" className="chat-image-modal__img" />
              <button
                type="button"
                className="chat-image-modal__close"
                onClick={() => setImageModalUrl(null)}
                aria-label="Fechar"
              >
                ×
              </button>
            </div>
          </div>
        )}
        {isLastAssistant && lastToolCalls && lastToolCalls.length > 0 && (
          <div className="tool-call-block">
            <div className="tool-call-header">Ferramentas usadas</div>
            <ul className="sub">
              {lastToolCalls.map((tc, i) => (
                <li key={i}>
                  <strong>{tc.name}</strong>
                  {tc.result_preview ? `: ${tc.result_preview.slice(0, 80)}…` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="chat-group-footer">
          <span className="chat-sender-name">{who}</span>
          {timeStr && <span className="chat-group-timestamp">{timeStr}</span>}
        </div>
      </div>
    </div>
  );
}

function ContextRing({ ratio, onNewSession }: { ratio: number; onNewSession: () => void }) {
  const r = Math.max(0, Math.min(ratio, 1));
  const pct = Math.round(r * 100);
  const radius = 10;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - r);
  let strokeColor = "var(--muted, #aaa)";
  if (r >= 0.75) strokeColor = "var(--danger, #e74c3c)";
  else if (r >= 0.5) strokeColor = "var(--warning, #f39c12)";

  const tooltip = r >= 0.9
    ? `Contexto: ${pct}% utilizado. Considere iniciar uma nova sessão.`
    : `Contexto: ${pct}% utilizado`;

  return (
    <button
      type="button"
      className="context-ring-btn"
      title={tooltip}
      aria-label={tooltip}
      onClick={r >= 0.9 ? onNewSession : undefined}
      style={{ cursor: r >= 0.9 ? "pointer" : "default" }}
    >
      <svg width="26" height="26" viewBox="0 0 26 26" className="context-ring-svg">
        <circle
          cx="13" cy="13" r={radius}
          fill="none"
          stroke="var(--border, #ddd)"
          strokeWidth="2.5"
        />
        <circle
          cx="13" cy="13" r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2.5"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform="rotate(-90 13 13)"
          style={{ transition: "stroke-dashoffset 0.4s ease, stroke 0.3s ease" }}
        />
      </svg>
      <span className="context-ring-label">{pct}%</span>
    </button>
  );
}

function ChatReadingIndicator({
  agentName,
  companionState
}: {
  agentName: string;
  companionState: CompanionState;
}) {
  return (
    <div className="chat-group assistant chat-group--thinking">
      <CompanionOrb state={companionState} size={40} />
      <div className="chat-group-messages">
        <div className="chat-thinking-indicator" role="status" aria-label="Pensando">
          <span className="chat-thinking-label">Pensando...</span>
        </div>
      </div>
    </div>
  );
}
