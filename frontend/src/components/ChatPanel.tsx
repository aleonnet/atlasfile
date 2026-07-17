/**
 * Chat panel no estilo OpenClaw: avatar do agente, nome, hora por mensagem,
 * três pontos saltitantes quando está pensando, botão Brain para thinking, suporte a colar imagens.
 * Conteúdo do assistente é renderizado como Markdown (GFM), como no OpenClaw (marked + DOMPurify).
 * Ref.: openclaw-main/ui/src/ui/views/chat.ts + grouped-render.ts + markdown.ts
 */
import React, { useRef, useEffect, useState } from "react";
import { Brain, Clock, FileSearch, FileText, Layers, Loader2, Pencil, Plus, Send, Settings, Sparkles, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { fetchSuggestions, getFileDownloadUrl } from "../api";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";
import { Input, Textarea } from "./ui/input";
import { toast } from "./ui/sonner";
import { ChartBlock } from "./ChartBlock";
import { CompanionOrb } from "./CompanionOrb";
import type { CompanionState } from "./CompanionOrb";
import { useCompanionState } from "../hooks/useCompanionState";

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

/** Tipografia do Markdown do assistente via seletores arbitrários (sem CSS de componente). */
const MARKDOWN_PROSE_CLASS = cn(
  "[&_p]:mb-2 [&_p:last-child]:mb-0",
  "[&_ul]:my-1.5 [&_ul]:pl-5 [&_ol]:my-1.5 [&_ol]:pl-5 [&_li]:my-0.5",
  "[&_ul]:list-disc [&_ol]:list-decimal",
  "[&_code]:rounded [&_code]:bg-black/20 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.85em]",
  "[&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-black/20 [&_pre]:p-3",
  "[&_pre_code]:bg-transparent [&_pre_code]:p-0",
  "[&_strong]:font-semibold",
  "[&_a]:text-accent [&_a]:underline [&_a]:underline-offset-2 hover:[&_a]:text-accent-light",
  "[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-accent/50 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground",
  "[&_h1]:mb-1.5 [&_h1]:mt-3 [&_h1]:font-display [&_h1]:text-[1.15em] [&_h1]:font-semibold",
  "[&_h2]:mb-1.5 [&_h2]:mt-3 [&_h2]:font-display [&_h2]:text-[1.08em] [&_h2]:font-semibold",
  "[&_h3]:mb-1 [&_h3]:mt-2.5 [&_h3]:font-display [&_h3]:text-[1em] [&_h3]:font-semibold",
  "[&_img]:h-auto [&_img]:max-w-full [&_img]:rounded",
  "[&_table]:my-2 [&_table]:w-full [&_table]:border-collapse [&_th]:border-b [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_td]:border-b [&_td]:border-border-subtle [&_td]:px-2 [&_td]:py-1"
);

const toolbarIconBtnClass = cn(
  "inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-transparent p-0",
  "text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
  "disabled:pointer-events-none disabled:opacity-40"
);

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

/** Starter prompts do empty state — cada um ancorado numa tool real do MCP. */
const STARTER_PROMPTS: { label: string; prompt: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { label: "O que chegou de novo?", prompt: "Quais documentos foram adicionados recentemente ao projeto?", icon: Sparkles },
  { label: "Panorama por área", prompt: "Me dê um panorama do acervo: quantos documentos por área de negócio?", icon: Layers },
  { label: "Buscar propostas", prompt: "Encontre propostas comerciais no acervo e liste as principais.", icon: FileSearch },
];

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
    <section
      className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,0.2)]"
      aria-busy={savingSession}
    >
      {savingSession && (
        <div
          className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-black/50 text-sm text-foreground"
          role="status"
          aria-live="polite"
        >
          <Loader2 size={32} className="shrink-0 animate-spin" aria-hidden />
          <span>Salvando sessão…</span>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex min-w-0 items-center gap-2 border-b border-border px-4 py-2.5 max-lg:flex-wrap">
        <label htmlFor="chat-panel-model" className="font-mono text-[0.7rem] uppercase tracking-wide text-tertiary">
          Modelo
        </label>
        <select
          id="chat-panel-model"
          value={selectedModel}
          onChange={(e) => onModelChange(e.target.value)}
          disabled={models.length === 0}
          className={cn(
            "h-8 min-w-0 max-w-full rounded-md border border-border bg-panel px-2.5 text-sm text-foreground shadow-none",
            "transition-[border-color,box-shadow] hover:border-border-strong",
            "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft"
          )}
        >
          {models.map((m) => (
            <option key={m.label} value={`${m.provider}/${m.model}`}>
              {m.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={toolbarIconBtnClass}
          onClick={onOpenSettings}
          title="Configuração (modelo e API Key)"
          aria-label="Configuração (modelo e API Key)"
        >
          <Settings size={16} strokeWidth={2} aria-hidden />
        </button>
        <span aria-hidden className="mx-1 h-5 w-px shrink-0 bg-border" />
        <button
          type="button"
          className={cn(
            toolbarIconBtnClass,
            showThinking && reasoningSupported && "border-accent bg-accent-soft text-accent hover:border-accent hover:text-accent"
          )}
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
          className={toolbarIconBtnClass}
          onClick={onNewSession}
          title="Nova sessão"
          aria-label="Nova sessão"
        >
          <Plus size={18} strokeWidth={2} aria-hidden />
        </button>
        <div className="relative inline-flex shrink-0" ref={timerAnchorRef}>
          <button
            type="button"
            className={toolbarIconBtnClass}
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
                className="fixed inset-0 z-[99] cursor-default border-0 bg-transparent p-0"
                aria-label="Fechar histórico de sessões"
                onClick={onCloseHistory}
              />
              <div
                className={cn(
                  "absolute right-0 top-full z-[100] mt-1.5 flex max-h-[70vh] min-h-[380px] w-80 max-w-[420px] flex-col overflow-hidden",
                  "rounded-lg border border-border bg-elevated shadow-[0_8px_24px_rgba(0,0,0,0.4)]",
                  "animate-[atlas-pop-in_150ms_var(--ease-out)]"
                )}
                role="dialog"
                aria-label="Histórico de sessões"
                aria-modal="true"
              >
                <div className="shrink-0 border-b border-border p-2.5">
                  <Input
                    type="text"
                    placeholder="Buscar…"
                    value={historySearch}
                    onChange={(e) => setHistorySearch(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && onCloseHistory?.()}
                    aria-label="Filtrar sessões por título"
                  />
                </div>
                <div className="min-h-60 flex-1 overflow-y-auto py-2">
                  {sessionsLoading ? (
                    <div className="p-4 text-center text-sm text-muted-foreground">Carregando…</div>
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
                      return <div className="p-4 text-center text-sm text-muted-foreground">Nenhuma sessão encontrada.</div>;
                    }
                    return groups.map((g) => (
                      <div key={g.label} className="mb-3">
                        <div className="px-3 pb-1.5 pt-1 font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">{g.label}</div>
                        {g.items.map((s) => (
                          <div
                            key={s.id}
                            className={cn(
                              "flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-sm text-foreground",
                              "transition-colors hover:bg-accent-soft",
                              s.id === activeSessionId && "bg-accent-soft/60"
                            )}
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
                              <Input
                                type="text"
                                className="h-7 flex-1"
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
                                <span className="min-w-0 flex-1 truncate">
                                  {s.title || "Sem título"}
                                </span>
                                <div
                                  className="flex shrink-0 items-center gap-1 opacity-60 transition-opacity group-hover:opacity-100"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <button
                                    type="button"
                                    title="Editar título"
                                    aria-label="Editar título"
                                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent-soft hover:text-foreground"
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
                                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/15 hover:text-destructive"
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
            className={cn(toolbarIconBtnClass, "relative")}
            onClick={onToggleTelegram}
            title={telegramConnected ? "Telegram conectado — clique para desconectar" : "Telegram desconectado — clique para conectar"}
            aria-label={telegramConnected ? "Desconectar Telegram" : "Conectar Telegram"}
          >
            <Send size={16} strokeWidth={2} aria-hidden />
            <span
              aria-hidden
              className={cn(
                "absolute right-0.5 top-0.5 size-[7px] rounded-full border-[1.5px] border-background",
                telegramConnected ? "bg-accent" : "bg-muted"
              )}
            />
          </button>
        )}
      </div>

      {error && (
        <div className="mx-4 mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Thread */}
      <div className="min-h-[120px] flex-1 overflow-y-auto overflow-x-hidden px-5 py-3" ref={threadRef} role="log">
        {messages.length === 0 && !sending && (
          <div className="flex h-full flex-col items-center justify-center gap-5 py-10 text-center">
            <CompanionOrb state="idle" size={56} />
            <div>
              <p className="m-0 font-display text-lg font-bold text-foreground-strong">Como posso ajudar?</p>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Pergunto ao acervo do projeto e cito as fontes. Use Config para modelo e API Key.
              </p>
            </div>
            <div className="flex max-w-lg flex-wrap justify-center gap-2">
              {STARTER_PROMPTS.map((s) => (
                <button
                  key={s.label}
                  type="button"
                  disabled={disabled}
                  onClick={() => onSend(s.prompt)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border border-border bg-panel px-3 py-1.5 text-xs text-muted-foreground",
                    "transition-[border-color,color,box-shadow] duration-150",
                    "hover:border-accent/40 hover:text-foreground hover:shadow-[0_0_14px_var(--accent-soft)]",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    "disabled:pointer-events-none disabled:opacity-50"
                  )}
                >
                  <s.icon className="size-3.5 text-accent" aria-hidden />
                  {s.label}
                </button>
              ))}
            </div>
          </div>
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

      {/* Compose */}
      <div className="shrink-0 border-t border-border p-4">
        {attachments.length > 0 && (
          <div className="mb-2 inline-flex flex-wrap gap-2 rounded-lg border border-border bg-panel p-2">
            {attachments.map((att) => (
              <div key={att.id} className="relative size-20 overflow-hidden rounded-md border border-border bg-background">
                <img src={att.dataUrl} alt="Anexo" className="size-full object-contain" />
                <button
                  type="button"
                  className={cn(
                    "absolute right-1 top-1 flex size-[22px] items-center justify-center rounded-full border-0 p-0",
                    "bg-black/70 text-base leading-none text-white opacity-80 transition-colors hover:bg-destructive"
                  )}
                  aria-label="Remover anexo"
                  onClick={() => setAttachments((prev) => prev.filter((a) => a.id !== att.id))}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="relative">
          {/* Aura Apple-Intelligence enquanto o assistente pensa */}
          {sending && (
            <span aria-hidden className="atlas-aura pointer-events-none absolute -inset-[3px] rounded-[15px]" />
          )}
          <div
            className={cn(
              "relative flex flex-col rounded-xl border border-border bg-background",
              "transition-[border-color,box-shadow] duration-150",
              "focus-within:border-accent focus-within:ring-2 focus-within:ring-accent-soft"
            )}
          >
            <label className="min-w-0">
              <span className="sr-only">Mensagem</span>
              <Textarea
                ref={textareaRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
                placeholder={placeholder}
                disabled={disabled}
                rows={2}
                className="max-h-36 min-h-[48px] w-full resize-none rounded-none border-0 bg-transparent px-4 pb-0 pt-3 hover:border-0 focus:border-0 focus:ring-0"
              />
            </label>
            <div className="flex items-center gap-2 px-2.5 pb-2.5 pt-1.5">
              <ContextGauge ratio={contextPressureRatio} onNewSession={onNewSession} />
              <span className="flex-1" />
              <Button variant="ghost" size="sm" disabled={disabled || sending} onClick={onNewSession}>
                <Plus /> Nova sessão
              </Button>
              {canAbort && sending ? (
                <Button variant="destructive" size="sm" onClick={onAbort}>
                  <Loader2 className="animate-spin" /> Parar
                </Button>
              ) : (
                <Button
                  size="sm"
                  disabled={disabled || sending || (!draft.trim() && !hasAttachments)}
                  onClick={handleSend}
                >
                  <Send /> Enviar <kbd className="rounded border border-white/25 px-1 font-mono text-[0.65rem]">↵</kbd>
                </Button>
              )}
            </div>
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
      <div className="mb-1 grid size-10 shrink-0 place-items-center self-end rounded-lg bg-accent-soft text-sm font-semibold text-accent">
        U
      </div>
    ) : agentAvatarUrl && /^(https?:|\/|data:image)/i.test(agentAvatarUrl) ? (
      <img
        src={agentAvatarUrl}
        alt={agentName}
        className="mb-1 block size-10 shrink-0 self-end rounded-lg object-cover object-center"
      />
    ) : (
      <CompanionOrb state="idle" size={40} />
    );


  const userContentEl = isUser && hasImageParts && contentParts ? (
    <div className="flex flex-wrap items-start gap-2">
      {contentParts.map((p, i) =>
        p.type === "text" ? (
          p.text ? <span key={i}>{p.text}</span> : null
        ) : (
          <button
            key={i}
            type="button"
            className="block cursor-pointer overflow-hidden rounded-md border-0 bg-transparent p-0 hover:opacity-90"
            onClick={() => setImageModalUrl(p.image_url.url)}
            aria-label="Ver imagem em tamanho maior"
          >
            <img
              src={p.image_url.url}
              alt="Anexo"
              className="block h-auto max-h-28 w-auto max-w-52 rounded-md border border-border"
            />
          </button>
        )
      )}
    </div>
  ) : (
    content
  );

  const citations = !isUser && typeof content === "string" ? extractCitations(content) : [];

  return (
    <div className={cn("mb-4 mr-4 flex items-start gap-3", isUser && "flex-row-reverse justify-start")}>
      {avatarEl}
      <div className={cn("flex max-w-[min(900px,calc(100%-60px))] flex-col gap-0.5", isUser && "items-end")}>
        <div
          className={cn(
            "relative inline-block max-w-full break-words rounded-lg px-3.5 py-2.5",
            "animate-[atlas-slide-in_200ms_var(--ease-out)]",
            isUser
              ? "border border-accent/20 bg-accent-soft"
              : "border border-border-subtle bg-panel-strong"
          )}
        >
          <div className={cn("break-words", isUser ? "whitespace-pre-wrap" : MARKDOWN_PROSE_CLASS)}>
            {isUser ? (
              userContentEl
            ) : (
              <ReactMarkdown components={MARKDOWN_COMPONENTS}>{content}</ReactMarkdown>
            )}
          </div>
        </div>
        {citations.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {citations.map((filename) => (
              <CitationChip key={filename} filename={filename} />
            ))}
          </div>
        )}
        {imageModalUrl !== null && (
          <div
            className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/75 p-5"
            role="dialog"
            aria-modal="true"
            aria-label="Imagem em tamanho maior"
            onClick={() => setImageModalUrl(null)}
          >
            <div
              className="relative max-h-[90vh] max-w-[90vw] rounded-lg bg-elevated p-2 shadow-[0_8px_32px_rgba(0,0,0,0.5)]"
              onClick={(e) => e.stopPropagation()}
            >
              <img src={imageModalUrl} alt="Imagem anexada" className="block h-auto max-h-[85vh] w-auto max-w-[85vw] rounded-md" />
              <button
                type="button"
                className={cn(
                  "absolute right-1 top-1 flex size-8 items-center justify-center rounded-md border-0 p-0",
                  "bg-background text-2xl leading-none text-foreground transition-colors hover:bg-panel-strong"
                )}
                onClick={() => setImageModalUrl(null)}
                aria-label="Fechar"
              >
                ×
              </button>
            </div>
          </div>
        )}
        {isLastAssistant && lastToolCalls && lastToolCalls.length > 0 && (
          <div className="mt-2 rounded-md border border-border border-l-[3px] border-l-accent bg-panel px-3 py-2">
            <div className="mb-1.5 font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">Ferramentas usadas</div>
            <ul className="m-0 list-none p-0 font-mono text-[0.7rem] text-tertiary">
              {lastToolCalls.map((tc, i) => (
                <li key={i}>
                  <strong>{tc.name}</strong>
                  {tc.result_preview ? `: ${tc.result_preview.slice(0, 80)}…` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className={cn("mt-1.5 flex items-baseline gap-2", isUser && "justify-end")}>
          <span className="text-xs font-medium text-muted-foreground">{who}</span>
          {timeStr && <span className="text-[0.7rem] text-tertiary">{timeStr}</span>}
        </div>
      </div>
    </div>
  );
}

const DOC_EXTENSIONS = "pdf|docx?|xlsx?|xlsm|pptx?|msg|eml|csv|txt|md";
// 1º padrão: nome entre aspas/backticks (permite espaços); 2º: token sem espaços
const QUOTED_DOC_RE = new RegExp(`[\`"“']([^\`"“”'\\n]{3,120}?\\.(?:${DOC_EXTENSIONS}))[\`"”']`, "gi");
const BARE_DOC_RE = new RegExp(`(?:^|[\\s(])([^\\s\`"'()\\[\\]{},;]{3,120}?\\.(?:${DOC_EXTENSIONS}))(?=[\\s).,;:]|$)`, "gim");

/** Nomes de documentos citados pelo assistente (para os chips de citação). */
export function extractCitations(text: string): string[] {
  const seen = new Map<string, string>();
  for (const re of [QUOTED_DOC_RE, BARE_DOC_RE]) {
    re.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = re.exec(text)) !== null && seen.size < 6) {
      const name = match[1].trim();
      const key = name.toLowerCase();
      if (!seen.has(key)) seen.set(key, name);
    }
  }
  return [...seen.values()];
}

/** Citação clicável: resolve o doc via suggest e abre na location (direção de arte: a citação "acende"). */
function CitationChip({ filename }: { filename: string }) {
  const [resolving, setResolving] = useState(false);

  async function handleOpen() {
    if (resolving) return;
    setResolving(true);
    try {
      const res = await fetchSuggestions(filename);
      const item =
        res.items.find((s) => s.original_filename.toLowerCase() === filename.toLowerCase()) ?? res.items[0];
      if (!item) {
        toast.error(`Documento citado não encontrado no índice: ${filename}`);
        return;
      }
      window.open(getFileDownloadUrl(item.path), "_blank", "noreferrer");
    } catch {
      toast.error("Falha ao localizar o documento citado");
    } finally {
      setResolving(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleOpen}
      disabled={resolving}
      title={`Abrir ${filename}`}
      className={
        "inline-flex max-w-72 items-center gap-1.5 rounded-full border border-accent-soft bg-accent-soft/40 " +
        "px-2.5 py-1 font-mono text-[0.7rem] text-accent shadow-none transition-[box-shadow,border-color] " +
        "hover:border-accent/50 hover:shadow-[0_0_14px_var(--accent-soft)] disabled:opacity-60 " +
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      }
    >
      {resolving ? <Loader2 size={11} className="animate-spin" aria-hidden /> : <FileText size={11} aria-hidden />}
      <span className="truncate">{filename}</span>
    </button>
  );
}

/**
 * Órbita de contexto — na linguagem do orb da marca: uma lua percorre a órbita
 * tracejada conforme o contexto da sessão enche, deixando um rastro em
 * gradiente. O núcleo respira e esquenta (accent → âmbar → vermelho); aos 90%
 * o sistema pulsa e o clique "colapsa" para uma nova sessão. O % aparece ao
 * lado no hover.
 */
function ContextGauge({ ratio, onNewSession }: { ratio: number; onNewSession: () => void }) {
  const r = Math.max(0, Math.min(ratio, 1));
  const pct = Math.round(r * 100);
  const radius = 12;
  const circumference = 2 * Math.PI * radius;
  const critical = r >= 0.9;
  const warning = r >= 0.75;
  const coreColor = critical ? "var(--danger)" : warning ? "var(--chart-3)" : "var(--accent)";

  const tooltip = critical
    ? `Contexto: ${pct}% utilizado — clique para iniciar uma nova sessão.`
    : `Contexto da sessão: ${pct}% utilizado`;

  return (
    <button
      type="button"
      className={cn(
        "group/gauge flex shrink-0 items-center gap-1.5 rounded-full border-0 bg-transparent p-0",
        critical ? "cursor-pointer" : "cursor-default"
      )}
      title={tooltip}
      aria-label={tooltip}
      onClick={critical ? onNewSession : undefined}
    >
      <span className={cn("relative block size-8", critical && "motion-safe:animate-pulse")}>
        <svg width="32" height="32" viewBox="0 0 32 32" className="absolute inset-0">
          <defs>
            <linearGradient id="atlas-orbit-trail" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="var(--accent)" />
              <stop offset="100%" stopColor="var(--accent-purple)" />
            </linearGradient>
          </defs>
          {/* Órbita tracejada (diagrama astronômico) */}
          <circle cx="16" cy="16" r={radius} fill="none" stroke="var(--border-strong)" strokeWidth="1" strokeDasharray="1.5 3.2" />
          {/* Rastro da lua: arco em gradiente do início até a posição atual */}
          <circle
            cx="16" cy="16" r={radius}
            fill="none"
            stroke={warning ? "var(--danger)" : "url(#atlas-orbit-trail)"}
            strokeWidth="2"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - r)}
            strokeLinecap="round"
            transform="rotate(-90 16 16)"
            opacity={r > 0 ? 1 : 0}
            style={{ transition: "stroke-dashoffset 0.8s var(--ease-out), stroke 0.3s ease, opacity 0.3s ease" }}
          />
          {/* Núcleo que respira e esquenta com a pressão */}
          <circle
            cx="16" cy="16" r={3 + r * 1.5}
            fill={coreColor}
            className="motion-safe:animate-[atlas-orbit-breathe_2.6s_ease-in-out_infinite]"
            style={{ transformOrigin: "16px 16px", transition: "fill 0.3s ease, r 0.6s var(--ease-out)" }}
          />
          {/* Lua orbitando: ângulo = uso do contexto */}
          <g
            style={{ transform: `rotate(${r * 360}deg)`, transformOrigin: "16px 16px", transition: "transform 0.8s var(--ease-out)" }}
          >
            <circle cx="16" cy="4" r="2.2" fill={coreColor} style={{ transition: "fill 0.3s ease" }} />
            <circle cx="16" cy="4" r="3.6" fill={coreColor} opacity="0.25" />
          </g>
        </svg>
      </span>
      <span
        className={cn(
          "font-mono text-[0.65rem] tabular-nums opacity-0 transition-opacity duration-200 group-hover/gauge:opacity-100",
          warning ? "text-destructive" : "text-muted-foreground",
          critical && "opacity-100"
        )}
      >
        {pct}%
      </span>
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
    <div className="mb-4 mr-4 flex items-center gap-3">
      <CompanionOrb state={companionState} size={40} />
      <div className="flex flex-col gap-0.5">
        <div className="inline-flex items-center py-2" role="status" aria-label="Pensando">
          <span className="atlas-thinking-text font-mono text-xs tracking-wide">Pensando...</span>
        </div>
      </div>
    </div>
  );
}
