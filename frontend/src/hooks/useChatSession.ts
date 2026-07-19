import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  createChatSession,
  deleteChatSession,
  fetchChatSessions,
  getChatSession,
  getSessionEventsUrl,
  sendChatMessage,
  updateChatSession,
} from "../api";
import type { ChatAttachment } from "../components/ChatPanel";
import { useProject } from "../contexts/ProjectContext";
import { useSettings } from "../contexts/SettingsContext";
import type {
  ChatContentPart,
  ChatMessage as ChatMessageType,
  ChatSession,
  StoredChatMessage,
  UsageTotals,
} from "../types";

function messagesToStored(messages: ChatMessageType[]): StoredChatMessage[] {
  return messages.map((m) => {
    const content =
      typeof m.content === "string"
        ? m.content
        : m.content.map((p) => (p.type === "text" ? p.text : "[imagem]")).join(" ");
    return { role: m.role, content, timestamp: m.timestamp, ...(m.model ? { model: m.model } : {}) };
  });
}

/** Estado e ações do assistente: mensagens, sessões persistidas, usage e SSE. */
export function useChatSession() {
  const { t } = useTranslation();
  const { selectedProjectScope } = useProject();
  const { selectedModel, setSelectedModel, openaiApiKey, anthropicApiKey, showThinking, autoTitleLLM } = useSettings();

  const [chatMessages, setChatMessages] = useState<ChatMessageType[]>([]);
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatAbortRef, setChatAbortRef] = useState<AbortController | null>(null);
  const [lastToolCalls, setLastToolCalls] = useState<{ name: string; result_preview?: string }[]>([]);
  const [contextPressureRatio, setContextPressureRatio] = useState(0);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [savingSession] = useState(false);
  const [sessionUsageTotals, setSessionUsageTotals] = useState<UsageTotals | null>(null);
  const [sessionUsageByModel, setSessionUsageByModel] = useState<Record<string, UsageTotals>>({});

  // SSE: atualizações da sessão vindas de outros canais (ex.: Telegram)
  useEffect(() => {
    if (!activeSessionId || chatSending) return;
    const url = getSessionEventsUrl(activeSessionId);
    const es = new EventSource(url);
    es.addEventListener("session_update", (e: MessageEvent) => {
      try {
        const session = JSON.parse(e.data) as ChatSession;
        if (session.messages && session.messages.length > 0) {
          const freshMsgs: ChatMessageType[] = session.messages.map((m) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
            timestamp: m.timestamp,
            model: m.model,
          }));
          setChatMessages(freshMsgs);
          if (session.usage_totals) setSessionUsageTotals(session.usage_totals);
          if (session.usage_by_model) setSessionUsageByModel(session.usage_by_model);
        }
      } catch {
        /* evento malformado */
      }
    });
    es.onerror = () => {
      es.close();
    };
    return () => es.close();
  }, [activeSessionId, chatSending]);

  function generateTitleInBackground(
    sessionId: string,
    msgs: ChatMessageType[],
    existingTotals: UsageTotals | null,
    existingByModel: Record<string, UsageTotals>
  ) {
    const textStart = msgs.slice(0, 6).map((m) => {
      const c =
        typeof m.content === "string"
          ? m.content
          : m.content.map((p) => (p.type === "text" ? p.text : "[imagem]")).join(" ");
      return { role: m.role, content: c };
    });
    const titleMessages = [
      { role: "system" as const, content: "Retorne apenas um título curto em uma linha, sem explicação." },
      ...textStart,
    ];
    const [provider, model] = selectedModel.split("/");
    sendChatMessage(titleMessages, {
      provider,
      model,
      openaiApiKey: provider === "openai" ? openaiApiKey || undefined : undefined,
      anthropicApiKey: provider === "anthropic" ? anthropicApiKey || undefined : undefined,
      enableThinking: false,
    })
      .then((res) => {
        const llmTitle = (res.content || "").trim().split("\n")[0].slice(0, 100);
        if (!llmTitle) return;
        const turn = res.usage;
        if (!turn) return updateChatSession(sessionId, { title: llmTitle });
        const pt = existingTotals ?? { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_cost_usd: 0 };
        const mergedTotals: UsageTotals = {
          input_tokens: pt.input_tokens + (turn.input_tokens ?? 0),
          output_tokens: pt.output_tokens + (turn.output_tokens ?? 0),
          total_tokens: pt.total_tokens + (turn.total_tokens ?? 0),
          estimated_cost_usd: pt.estimated_cost_usd + (turn.estimated_cost_usd ?? 0),
        };
        const pm = existingByModel[selectedModel] ?? {
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          estimated_cost_usd: 0,
        };
        const mergedByModel: Record<string, UsageTotals> = {
          ...existingByModel,
          [selectedModel]: {
            input_tokens: pm.input_tokens + (turn.input_tokens ?? 0),
            output_tokens: pm.output_tokens + (turn.output_tokens ?? 0),
            total_tokens: pm.total_tokens + (turn.total_tokens ?? 0),
            estimated_cost_usd: pm.estimated_cost_usd + (turn.estimated_cost_usd ?? 0),
          },
        };
        return updateChatSession(sessionId, {
          title: llmTitle,
          usage_totals: mergedTotals,
          usage_by_model: mergedByModel,
        });
      })
      .then(() => fetchChatSessions().then(setSessions))
      .catch(() => {});
  }

  async function handleChatSend(text: string, attachments?: ChatAttachment[]) {
    const trimmed = text.trim();
    const hasAttachments = attachments && attachments.length > 0;
    if (!trimmed && !hasAttachments) return;
    if (chatSending || !selectedModel) return;
    const userContent: string | ChatContentPart[] = hasAttachments
      ? [
          { type: "text", text: trimmed || "(imagem anexada)" },
          ...attachments!.map((a) => ({ type: "image_url" as const, image_url: { url: a.dataUrl } })),
        ]
      : trimmed;
    const userMsg: ChatMessageType = { role: "user", content: userContent, timestamp: Date.now() };
    setChatMessages((prev) => [...prev, userMsg]);
    setChatError(null);
    setLastToolCalls([]);
    const controller = new AbortController();
    setChatAbortRef(controller);
    setChatSending(true);
    try {
      // Recarrega a sessão do backend para absorver mensagens de outros canais
      let baseMsgs = chatMessages;
      if (activeSessionId) {
        try {
          const fresh = await getChatSession(activeSessionId);
          if (fresh.messages && fresh.messages.length > 0) {
            const freshChat: ChatMessageType[] = fresh.messages.map((m) => ({
              role: m.role as "user" | "assistant",
              content: m.content,
              timestamp: m.timestamp,
              model: m.model,
            }));
            baseMsgs = freshChat;
            // Mantém o echo otimista da mensagem recém-enviada ao absorver o refresh
            setChatMessages([...freshChat, userMsg]);
          }
        } catch {
          /* usa estado local */
        }
      }
      const newUserContent: string | ChatContentPart[] = hasAttachments
        ? [
            { type: "text", text: trimmed || "(imagem anexada)" },
            ...attachments!.map((a) => ({ type: "image_url" as const, image_url: { url: a.dataUrl } })),
          ]
        : trimmed;
      const messagesForApi: ChatMessageType[] = [
        ...baseMsgs.map((m) => ({ role: m.role, content: m.content })),
        { role: "user", content: newUserContent },
      ];
      const [provider, model] = selectedModel.split("/");
      const res = await sendChatMessage(messagesForApi, {
        projectId: selectedProjectScope,
        provider,
        model,
        openaiApiKey: provider === "openai" ? openaiApiKey || undefined : undefined,
        anthropicApiKey: provider === "anthropic" ? anthropicApiKey || undefined : undefined,
        enableThinking: showThinking,
        signal: controller.signal,
      });
      const assistantMsg: ChatMessageType = {
        role: "assistant",
        content: res.content,
        timestamp: Date.now(),
        model: selectedModel,
      };
      const finalMessages: ChatMessageType[] = [...baseMsgs, userMsg, assistantMsg];
      setChatMessages(finalMessages);

      const turn = res.usage;
      let mergedTotals = sessionUsageTotals;
      let newByModel = sessionUsageByModel;
      if (turn) {
        const pt = sessionUsageTotals ?? {
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          estimated_cost_usd: 0,
          api_call_count: 0,
        };
        mergedTotals = {
          input_tokens: pt.input_tokens + (turn.input_tokens ?? 0),
          output_tokens: pt.output_tokens + (turn.output_tokens ?? 0),
          total_tokens: pt.total_tokens + (turn.total_tokens ?? 0),
          estimated_cost_usd: pt.estimated_cost_usd + (turn.estimated_cost_usd ?? 0),
          api_call_count: (pt.api_call_count ?? 0) + (turn.api_call_count ?? 0),
          cache_read_input_tokens: (pt.cache_read_input_tokens ?? 0) + (turn.cache_read_input_tokens ?? 0) || undefined,
          cache_creation_input_tokens:
            (pt.cache_creation_input_tokens ?? 0) + (turn.cache_creation_input_tokens ?? 0) || undefined,
          cache_write_input_tokens:
            (pt.cache_write_input_tokens ?? 0) + (turn.cache_write_input_tokens ?? 0) || undefined,
        };
        setSessionUsageTotals(mergedTotals);
        const modelKey = selectedModel;
        const pm = sessionUsageByModel[modelKey] ?? {
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          estimated_cost_usd: 0,
          api_call_count: 0,
        };
        newByModel = {
          ...sessionUsageByModel,
          [modelKey]: {
            input_tokens: pm.input_tokens + (turn.input_tokens ?? 0),
            output_tokens: pm.output_tokens + (turn.output_tokens ?? 0),
            total_tokens: pm.total_tokens + (turn.total_tokens ?? 0),
            estimated_cost_usd: pm.estimated_cost_usd + (turn.estimated_cost_usd ?? 0),
            api_call_count: (pm.api_call_count ?? 0) + (turn.api_call_count ?? 0),
            cache_read_input_tokens:
              (pm.cache_read_input_tokens ?? 0) + (turn.cache_read_input_tokens ?? 0) || undefined,
            cache_creation_input_tokens:
              (pm.cache_creation_input_tokens ?? 0) + (turn.cache_creation_input_tokens ?? 0) || undefined,
            cache_write_input_tokens:
              (pm.cache_write_input_tokens ?? 0) + (turn.cache_write_input_tokens ?? 0) || undefined,
          },
        };
        setSessionUsageByModel(newByModel);
      }

      const projectId = selectedProjectScope ?? null;
      if (activeSessionId) {
        const newMsgs = messagesToStored([userMsg, assistantMsg]);
        updateChatSession(activeSessionId, {
          append_messages: newMsgs,
          ...(mergedTotals ? { usage_totals: mergedTotals, usage_by_model: newByModel } : {}),
          project_id: projectId,
          source_channel: "web",
        }).catch(() => {});
      } else {
        const firstText =
          typeof userMsg.content === "string"
            ? userMsg.content
            : userMsg.content.map((p) => (p.type === "text" ? p.text : "")).join(" ").trim();
        const title =
          firstText.slice(0, 80) ||
          `Conversa ${new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}`;
        const storedMsgs = messagesToStored(finalMessages);
        createChatSession({
          title,
          messages: storedMsgs,
          model: selectedModel,
          project_id: projectId,
          usage_totals: mergedTotals,
          usage_by_model: Object.keys(newByModel).length > 0 ? newByModel : null,
          channel: "web",
        })
          .then((created) => {
            setActiveSessionId(created.id);
            setSessions((prev) => [created, ...prev]);
            if (autoTitleLLM) {
              generateTitleInBackground(created.id, finalMessages, created.usage_totals ?? null, created.usage_by_model ?? {});
            }
          })
          .catch(() => setChatError(t("chat:session.saveFailed")));
      }
      if (res.context_pressure) {
        setContextPressureRatio(res.context_pressure.context_pressure_ratio);
      }
      setLastToolCalls(res.tool_calls_used ?? []);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      const err = e as Error;
      const msg =
        err.message && (err.message.includes("fetch") || err.message.includes("NetworkError"))
          ? t("chat:session.networkError")
          : err.message || t("chat:session.chatError");
      setChatError(msg);
      setChatSending(false);
      setChatAbortRef(null);
    } finally {
      setChatSending(false);
      setChatAbortRef(null);
    }
  }

  function handleChatNewSession() {
    setChatMessages([]);
    setChatError(null);
    setContextPressureRatio(0);
    setLastToolCalls([]);
    setActiveSessionId(null);
    setSessionUsageTotals(null);
    setSessionUsageByModel({});
  }

  function openHistoryModal() {
    setChatError(null);
    setHistoryModalOpen(true);
    setSessionsLoading(true);
    fetchChatSessions()
      .then((list) => {
        setSessions(list);
      })
      .catch(() => {
        setChatError(t("chat:session.historyLoadFailed"));
      })
      .finally(() => setSessionsLoading(false));
  }

  function handleSelectSession(sessionId: string) {
    getChatSession(sessionId)
      .then((session) => {
        const msgs: ChatMessageType[] = session.messages.map((m) => ({
          role: m.role as "user" | "assistant" | "system",
          content: m.content,
          timestamp: m.timestamp,
          ...(m.model ? { model: m.model } : {}),
        }));
        setChatMessages(msgs);
        if (session.model) setSelectedModel(session.model);
        setActiveSessionId(session.id);
        setSessionUsageTotals(session.usage_totals ?? null);
        setSessionUsageByModel(session.usage_by_model ?? {});
        setChatError(null);
        setHistoryModalOpen(false);
      })
      .catch(() => setChatError(t("chat:session.sessionLoadFailed")));
  }

  function handleEditSession(sessionId: string, newTitle: string) {
    updateChatSession(sessionId, { title: newTitle }).then(() => fetchChatSessions().then(setSessions));
  }

  function handleDeleteSession(sessionId: string) {
    deleteChatSession(sessionId).then(() => {
      fetchChatSessions().then(setSessions);
      if (activeSessionId === sessionId) {
        setChatMessages([]);
        setActiveSessionId(null);
        setSessionUsageTotals(null);
        setSessionUsageByModel({});
      }
      setHistoryModalOpen(false);
    });
  }

  function handleChatAbort() {
    chatAbortRef?.abort();
  }

  return {
    chatMessages,
    chatSending,
    chatError,
    lastToolCalls,
    contextPressureRatio,
    sessions,
    activeSessionId,
    historyModalOpen,
    setHistoryModalOpen,
    sessionsLoading,
    savingSession,
    handleChatSend,
    handleChatAbort,
    handleChatNewSession,
    openHistoryModal,
    handleSelectSession,
    handleEditSession,
    handleDeleteSession,
  };
}
