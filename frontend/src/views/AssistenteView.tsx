import { BarChart3, MessageCircle } from "lucide-react";
import { useState } from "react";
import { ChatPanel } from "../components/ChatPanel";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import { UsageView } from "../features/usage/UsageView";
import { useChatSession } from "../hooks/useChatSession";
import type { ChatMessage as ChatMessageType, ModelOption } from "../types";

const ALL_PROJECTS = "__all__";

type Props = {
  selectedProject: string;
  selectedModel: string;
  models: ModelOption[];
  onModelChange: (model: string) => void;
  onOpenSettings: () => void;
  showThinking: boolean;
  onShowThinkingChange: (value: boolean) => void;
  telegramConnected: boolean;
  onToggleTelegram: () => void;
};

export function AssistenteView({
  selectedProject,
  selectedModel,
  models,
  onModelChange,
  onOpenSettings,
  showThinking,
  onShowThinkingChange,
  telegramConnected,
  onToggleTelegram,
}: Props) {
  const [assistenteTab, setAssistenteTab] = useState("chat");
  // O chat vive AQUI (keep-alive da view preserva a sessão entre navegações) —
  // era elevado ao App só por causa do unmount, que não existe mais
  const chat = useChatSession();

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-4">
      <Tabs value={assistenteTab} onValueChange={setAssistenteTab} className="flex min-h-0 flex-1 flex-col">
        <TabsList aria-label="Assistente">
          <TabsTrigger value="chat"><MessageCircle aria-hidden /> Chat</TabsTrigger>
          <TabsTrigger value="usage"><BarChart3 aria-hidden /> Uso e custo</TabsTrigger>
        </TabsList>
        <div className="mt-4 flex min-h-0 flex-1 flex-col">
          {assistenteTab === "chat" ? (
            <ChatPanel
              agentName="Assistente"
              agentAvatarUrl={null}
              messages={chat.chatMessages
                .filter((m): m is ChatMessageType & { role: "user" | "assistant" } => m.role === "user" || m.role === "assistant")
                .map((m) => ({
                  role: m.role,
                  content: typeof m.content === "string" ? m.content : m.content.map((p) => (p.type === "text" ? p.text : "[imagem]")).join(" "),
                  timestamp: m.timestamp,
                  ...(m.role === "user" && Array.isArray(m.content) && { contentParts: m.content }),
                  ...(m.model ? { model: m.model } : {}),
                }))}
              lastToolCalls={chat.lastToolCalls}
              sending={chat.chatSending}
              error={chat.chatError}
              canAbort={chat.chatSending}
              selectedModel={selectedModel}
              models={models}
              onModelChange={onModelChange}
              onOpenSettings={onOpenSettings}
              onSend={chat.handleChatSend}
              onAbort={chat.handleChatAbort}
              onNewSession={chat.handleChatNewSession}
              showThinking={showThinking}
              onShowThinkingChange={onShowThinkingChange}
              disabled={models.length === 0 || !selectedModel}
              sessions={chat.sessions}
              sessionsLoading={chat.sessionsLoading}
              activeSessionId={chat.activeSessionId}
              historyModalOpen={chat.historyModalOpen}
              onOpenHistory={chat.openHistoryModal}
              onCloseHistory={() => chat.setHistoryModalOpen(false)}
              onSelectSession={chat.handleSelectSession}
              onEditSession={chat.handleEditSession}
              onDeleteSession={chat.handleDeleteSession}
              savingSession={chat.savingSession}
              telegramConnected={telegramConnected}
              onToggleTelegram={onToggleTelegram}
              contextPressureRatio={chat.contextPressureRatio}
            />
          ) : (
            <UsageView projectId={selectedProject === ALL_PROJECTS ? null : selectedProject} />
          )}
        </div>
      </Tabs>
    </section>
  );
}
