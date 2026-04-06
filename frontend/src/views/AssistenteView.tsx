import { useState } from "react";
import { ChatPanel } from "../components/ChatPanel";
import type { ChatAttachment } from "../components/ChatPanel";
import { UsageView } from "../features/usage/UsageView";
import type { ChatMessage as ChatMessageType, ChatSession, ModelOption, UsageTotals } from "../types";

const ALL_PROJECTS = "__all__";

type Props = {
  selectedProject: string;
  chatMessages: ChatMessageType[];
  chatSending: boolean;
  chatError: string | null;
  lastToolCalls: { name: string; result_preview?: string }[];
  contextPressureRatio: number;
  selectedModel: string;
  models: ModelOption[];
  onModelChange: (model: string) => void;
  onOpenSettings: () => void;
  onSend: (text: string, attachments?: ChatAttachment[]) => void;
  onAbort: () => void;
  onNewSession: () => void;
  showThinking: boolean;
  onShowThinkingChange: (value: boolean) => void;
  sessions: ChatSession[];
  sessionsLoading: boolean;
  activeSessionId: string | null;
  historyModalOpen: boolean;
  onOpenHistory: () => void;
  onCloseHistory: () => void;
  onSelectSession: (sessionId: string) => void;
  onEditSession: (sessionId: string, newTitle: string) => void;
  onDeleteSession: (sessionId: string) => void;
  savingSession: boolean;
  telegramConnected: boolean;
  onToggleTelegram: () => void;
};

export function AssistenteView({
  selectedProject,
  chatMessages,
  chatSending,
  chatError,
  lastToolCalls,
  contextPressureRatio,
  selectedModel,
  models,
  onModelChange,
  onOpenSettings,
  onSend,
  onAbort,
  onNewSession,
  showThinking,
  onShowThinkingChange,
  sessions,
  sessionsLoading,
  activeSessionId,
  historyModalOpen,
  onOpenHistory,
  onCloseHistory,
  onSelectSession,
  onEditSession,
  onDeleteSession,
  savingSession,
  telegramConnected,
  onToggleTelegram,
}: Props) {
  const [assistenteTab, setAssistenteTab] = useState<"chat" | "usage">("chat");

  return (
    <section className="assistente-card">
      <nav className="assistente-tabs" role="tablist">
        <div className="assistente-tabs-pill">
          <button
            type="button"
            role="tab"
            aria-selected={assistenteTab === "chat"}
            className={`assistente-tab${assistenteTab === "chat" ? " assistente-tab--active" : ""}`}
            onClick={() => setAssistenteTab("chat")}
          >
            Chat
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={assistenteTab === "usage"}
            className={`assistente-tab${assistenteTab === "usage" ? " assistente-tab--active" : ""}`}
            onClick={() => setAssistenteTab("usage")}
          >
            Uso e custo
          </button>
        </div>
      </nav>
      <div className="assistente-content">
        {assistenteTab === "chat" ? (
          <ChatPanel
            agentName="Assistente"
            agentAvatarUrl={null}
            messages={chatMessages
              .filter((m): m is ChatMessageType & { role: "user" | "assistant" } => m.role === "user" || m.role === "assistant")
              .map((m) => ({
                role: m.role,
                content: typeof m.content === "string" ? m.content : m.content.map((p) => (p.type === "text" ? p.text : "[imagem]")).join(" "),
                timestamp: m.timestamp,
                ...(m.role === "user" && Array.isArray(m.content) && { contentParts: m.content }),
                ...(m.model ? { model: m.model } : {}),
              }))}
            lastToolCalls={lastToolCalls}
            sending={chatSending}
            error={chatError}
            canAbort={chatSending}
            selectedModel={selectedModel}
            models={models}
            onModelChange={onModelChange}
            onOpenSettings={onOpenSettings}
            onSend={onSend}
            onAbort={onAbort}
            onNewSession={onNewSession}
            showThinking={showThinking}
            onShowThinkingChange={onShowThinkingChange}
            disabled={models.length === 0 || !selectedModel}
            sessions={sessions}
            sessionsLoading={sessionsLoading}
            activeSessionId={activeSessionId}
            historyModalOpen={historyModalOpen}
            onOpenHistory={onOpenHistory}
            onCloseHistory={onCloseHistory}
            onSelectSession={onSelectSession}
            onEditSession={onEditSession}
            onDeleteSession={onDeleteSession}
            savingSession={savingSession}
            telegramConnected={telegramConnected}
            onToggleTelegram={onToggleTelegram}
            contextPressureRatio={contextPressureRatio}
          />
        ) : (
          <UsageView projectId={selectedProject === ALL_PROJECTS ? null : selectedProject} />
        )}
      </div>
    </section>
  );
}
