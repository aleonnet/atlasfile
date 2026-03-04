/**
 * Chat panel no estilo OpenClaw: avatar do agente, nome, hora por mensagem,
 * três pontos saltitantes quando está pensando, botão Brain para thinking, suporte a colar imagens.
 * Conteúdo do assistente é renderizado como Markdown (GFM), como no OpenClaw (marked + DOMPurify).
 * Ref.: openclaw-main/ui/src/ui/views/chat.ts + grouped-render.ts + markdown.ts
 */
import React, { useRef, useEffect } from "react";
import { Brain } from "lucide-react";
import ReactMarkdown from "react-markdown";
import "./ChatPanel.css";

export interface ChatMessageWithMeta {
  role: "user" | "assistant";
  content: string;
  timestamp?: number;
}

export interface ChatAttachment {
  id: string;
  dataUrl: string;
  mimeType: string;
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
  models: { provider: string; model: string; label: string }[];
  onModelChange: (value: string) => void;
  onOpenSettings: () => void;
  onSend: (text: string, attachments?: ChatAttachment[]) => void;
  onAbort: () => void;
  onNewSession: () => void;
  /** Mostrar modo thinking (reasoning); modelos com essa capacidade */
  showThinking: boolean;
  onShowThinkingChange: (value: boolean) => void;
  disabled?: boolean;
}

function generateAttachmentId(): string {
  return `att-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
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
  disabled = false
}: ChatPanelProps) {
  const [draft, setDraft] = React.useState("");
  const [attachments, setAttachments] = React.useState<ChatAttachment[]>([]);
  const threadRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
    <section className="card chat chat-panel">
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
          className="btn btn-icon"
          onClick={onOpenSettings}
          title="Configuração (modelo e API Key)"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          Config
        </button>
        <span className="chat-controls__separator">|</span>
        <button
          type="button"
          className={`chat-controls__thinking-btn ${showThinking ? "chat-controls__thinking-btn--active" : ""}`}
          onClick={() => onShowThinkingChange(!showThinking)}
          title="Toggle assistant thinking/working output"
          aria-pressed={showThinking}
          aria-label="Toggle assistant thinking/working output"
        >
          <Brain size={18} strokeWidth={2} aria-hidden />
        </button>
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
            timestamp={msg.timestamp}
            agentName={agentName}
            agentAvatarUrl={msg.role === "assistant" ? agentAvatarUrl : undefined}
            isLastAssistant={msg.role === "assistant" && idx === messages.length - 1}
            lastToolCalls={msg.role === "assistant" && idx === messages.length - 1 ? lastToolCalls : undefined}
          />
        ))}
        {sending && (
          <ChatReadingIndicator agentName={agentName} agentAvatarUrl={agentAvatarUrl} />
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
  timestamp,
  agentName,
  agentAvatarUrl,
  isLastAssistant,
  lastToolCalls
}: {
  role: "user" | "assistant";
  content: string;
  timestamp?: number;
  agentName: string;
  agentAvatarUrl?: string | null;
  isLastAssistant: boolean;
  lastToolCalls?: { name: string; result_preview?: string }[];
}) {
  const timeStr = timestamp
    ? new Date(timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : "";
  const who = role === "user" ? "Você" : agentName;
  const initial = role === "user" ? "U" : (agentName.charAt(0) || "A").toUpperCase();
  const isUser = role === "user";

  const avatarEl =
    isUser ? (
      <div className="chat-avatar user">U</div>
    ) : agentAvatarUrl && /^(https?:|\/|data:image)/i.test(agentAvatarUrl) ? (
      <img src={agentAvatarUrl} alt={agentName} className="chat-avatar assistant" />
    ) : (
      <div className="chat-avatar assistant">{initial}</div>
    );

  const safeImgSrc = (src: string | undefined): boolean =>
    Boolean(src && /^(https?:|\/|data:image)/i.test(src));

  const markdownComponents = {
    a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
      <a href={href} target="_blank" rel="noreferrer noopener" {...props}>
        {children}
      </a>
    ),
    img: ({ src, alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) =>
      safeImgSrc(src) ? <img src={src} alt={alt ?? ""} {...props} /> : null
  };

  return (
    <div className={`chat-group ${isUser ? "user" : "assistant"}`}>
      {avatarEl}
      <div className="chat-group-messages">
        <div className="chat-bubble fade-in">
          <div className={`chat-text ${!isUser ? "chat-text--markdown" : ""}`}>
            {isUser ? (
              content
            ) : (
              <ReactMarkdown components={markdownComponents}>{content}</ReactMarkdown>
            )}
          </div>
        </div>
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

function ChatReadingIndicator({
  agentName,
  agentAvatarUrl
}: {
  agentName: string;
  agentAvatarUrl?: string | null;
}) {
  const initial = (agentName.charAt(0) || "A").toUpperCase();
  return (
    <div className="chat-group assistant">
      {agentAvatarUrl && /^(https?:|\/|data:image)/i.test(agentAvatarUrl) ? (
        <img src={agentAvatarUrl} alt={agentName} className="chat-avatar assistant" />
      ) : (
        <div className="chat-avatar assistant">{initial}</div>
      )}
      <div className="chat-group-messages">
        <div className="chat-bubble chat-reading-indicator" aria-hidden="true">
          <span className="chat-reading-indicator__dots">
            <span /><span /><span />
          </span>
        </div>
        <div className="chat-group-footer">
          <span className="chat-sender-name">{agentName}</span>
        </div>
      </div>
    </div>
  );
}
