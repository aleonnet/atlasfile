import { File, FileSpreadsheet, FileText, Presentation, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChatSession,
  deleteChatSession,
  fetchChatSessions,
  fetchHealth,
  fetchModels,
  fetchProjectProfile,
  getChatSession,
  fetchProjects,
  fetchReconcileStatus,
  fetchSetupStatus,
  fetchStats,
  fetchTriage,
  getFileDownloadUrl,
  getReconcileStatusStreamUrl,
  initializeProject,
  runReconcile,
  searchDocuments,
  sendChatMessage,
  triageDecision,
  updateChatSession,
  fetchChannelConfig,
  fetchChannelStatus,
  updateChannelConfig,
  getSessionEventsUrl
} from "./api";
import type { ChatAttachment } from "./components/ChatPanel";
import { ToastProvider } from "./contexts/ToastContext";
import { SearchModal } from "./layouts/SearchModal";
import { Topbar } from "./layouts/Topbar";
import { ConfigView } from "./views/ConfigView";
import { PainelView } from "./views/PainelView";
import { AssistantSettingsModal } from "./features/settings/AssistantSettingsModal";
import { CorrectDecisionModal } from "./features/triage/CorrectDecisionModal";
import { TemplateSelectModal } from "./features/templates/TemplateSelectModal";
import { AssistenteView } from "./views/AssistenteView";
import { OnboardingWizard } from "./features/onboarding/OnboardingWizard";
import type {
  ChatContentPart,
  ChatMessage as ChatMessageType,
  ChatSession,
  ModelOption,
  Project,
  ProjectArea,
  ProjectDocumentType,
  ReconcileStatus,
  SearchFilters,
  SearchHit,
  StatsResponse,
  StoredChatMessage,
  TriageItem,
  UsageTotals
} from "./types";

const ALL_PROJECTS = "__all__";
const THEME_STORAGE_KEY = "atlasfile-theme";
const CHAT_MODEL_STORAGE_KEY = "atlasfile-chat-model";
const TRIAGE_MODEL_STORAGE_KEY = "atlasfile-triage-model";
const CHAT_SHOW_THINKING_KEY = "atlasfile-chat-show-thinking";
const OPENAI_API_KEY_STORAGE = "atlasfile-openai-api-key";
const ANTHROPIC_API_KEY_STORAGE = "atlasfile-anthropic-api-key";
const AUTO_TITLE_LLM_KEY = "atlasfile-auto-title-llm";
const ONBOARDING_DONE_KEY = "atlasfile-onboarding-done";
const TG_TOKEN_STORAGE_KEY = "atlasfile-telegram-bot-token";
type ThemeMode = "system" | "light" | "dark";
type ViewKind = "painel" | "assistente" | "config";
type InputLikeEvent = { target: { value: string } };
type KeyboardLikeEvent = { key: string };
type KeyboardEventLike = { key: string; shiftKey?: boolean; preventDefault?: () => void };

function getStoredTheme(): ThemeMode {
  try {
    const s = localStorage.getItem(THEME_STORAGE_KEY);
    if (s === "system" || s === "light" || s === "dark") return s;
  } catch {
    /* ignore */
  }
  return "system";
}

function resolveTheme(mode: ThemeMode): "light" | "dark" {
  if (mode === "light") return "light";
  if (mode === "dark") return "dark";
  if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)")?.matches) return "dark";
  return "light";
}

function App() {
  const [theme, setTheme] = useState<ThemeMode>(getStoredTheme);
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>(ALL_PROJECTS);
  const [query, setQuery] = useState("");
  const [modalHits, setModalHits] = useState<SearchHit[]>([]);
  const [searchModalOpen, setSearchModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [fullResults, setFullResults] = useState<SearchHit[]>([]);
  const [fullQuery, setFullQuery] = useState("");
  const [fullPage, setFullPage] = useState(1);
  const [fullTotalPages, setFullTotalPages] = useState(1);
  const [fullTotal, setFullTotal] = useState(0);
  const [fullLoading, setFullLoading] = useState(false);
  const [fullSearchInput, setFullSearchInput] = useState("");
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [searchStats, setSearchStats] = useState<StatsResponse | null>(null);
  const [triageItems, setTriageItems] = useState<TriageItem[]>([]);
  const [reconcileStatus, setReconcileStatus] = useState<ReconcileStatus | null>(null);
  const [dashboardStats, setDashboardStats] = useState<StatsResponse | null>(null);
  const [status, setStatus] = useState("Pronto");
  const [initializingProjectId, setInitializingProjectId] = useState<string | null>(null);
  const [reconcilingNow, setReconcilingNow] = useState(false);
  const [correctModalItem, setCorrectModalItem] = useState<TriageItem | null>(null);
  const [correctBusinessDomainOptions, setCorrectBusinessDomainOptions] = useState<ProjectArea[]>([]);
  const [correctBusinessDomainValue, setCorrectBusinessDomainValue] = useState("");
  const [correctDocumentTypeOptions, setCorrectDocumentTypeOptions] = useState<ProjectDocumentType[]>([]);
  const [correctDocumentTypeValue, setCorrectDocumentTypeValue] = useState("");
  const [correctSubmitting, setCorrectSubmitting] = useState(false);
  const reconcileEsRef = useRef<EventSource | null>(null);

  const [view, setView] = useState<ViewKind>("painel");
  const [templateModalProject, setTemplateModalProject] = useState<{ ref: string; label: string } | null>(null);
  const [newProjectModalOpen, setNewProjectModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessageType[]>([]);
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatAbortRef, setChatAbortRef] = useState<AbortController | null>(null);
  const [showThinking, setShowThinking] = useState<boolean>(() => {
    try {
      const s = localStorage.getItem(CHAT_SHOW_THINKING_KEY);
      return s === "true";
    } catch {
      return false;
    }
  });
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    try {
      const s = localStorage.getItem(CHAT_MODEL_STORAGE_KEY);
      return s || "";
    } catch {
      return "";
    }
  });
  const [selectedModelTriage, setSelectedModelTriage] = useState<string>(() => {
    try {
      const s = localStorage.getItem(TRIAGE_MODEL_STORAGE_KEY);
      return s || "";
    } catch {
      return "";
    }
  });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [openaiApiKey, setOpenaiApiKey] = useState<string>(() => {
    try {
      return localStorage.getItem(OPENAI_API_KEY_STORAGE) || "";
    } catch {
      return "";
    }
  });
  const [anthropicApiKey, setAnthropicApiKey] = useState<string>(() => {
    try {
      return localStorage.getItem(ANTHROPIC_API_KEY_STORAGE) || "";
    } catch {
      return "";
    }
  });
  const [lastToolCalls, setLastToolCalls] = useState<{ name: string; result_preview?: string }[]>([]);
  const [contextPressureRatio, setContextPressureRatio] = useState(0);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [savingSession, setSavingSession] = useState(false);
  const [autoTitleLLM, setAutoTitleLLM] = useState<boolean>(() => {
    try { return localStorage.getItem(AUTO_TITLE_LLM_KEY) === "true"; } catch { return false; }
  });
  const [telegramConnected, setTelegramConnected] = useState(false);
  const [sessionUsageTotals, setSessionUsageTotals] = useState<UsageTotals | null>(null);
  const [sessionUsageByModel, setSessionUsageByModel] = useState<Record<string, UsageTotals>>({});

  const [showOnboarding, setShowOnboarding] = useState(false);
  const [appEnv, setAppEnv] = useState("production");

  const resolvedTheme = useMemo(() => resolveTheme(theme), [theme]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", resolvedTheme);
  }, [resolvedTheme]);

  useEffect(() => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  useEffect(() => {
    if (selectedModel) {
      try {
        localStorage.setItem(CHAT_MODEL_STORAGE_KEY, selectedModel);
      } catch {
        /* ignore */
      }
    }
  }, [selectedModel]);

  useEffect(() => {
    if (selectedModelTriage !== undefined) {
      try {
        localStorage.setItem(TRIAGE_MODEL_STORAGE_KEY, selectedModelTriage);
      } catch {
        /* ignore */
      }
    }
  }, [selectedModelTriage]);

  useEffect(() => {
    try {
      localStorage.setItem(CHAT_SHOW_THINKING_KEY, String(showThinking));
    } catch {
      /* ignore */
    }
  }, [showThinking]);

  useEffect(() => {
    try {
      if (openaiApiKey) localStorage.setItem(OPENAI_API_KEY_STORAGE, openaiApiKey);
      else localStorage.removeItem(OPENAI_API_KEY_STORAGE);
    } catch {
      /* ignore */
    }
  }, [openaiApiKey]);

  useEffect(() => {
    try {
      if (anthropicApiKey) localStorage.setItem(ANTHROPIC_API_KEY_STORAGE, anthropicApiKey);
      else localStorage.removeItem(ANTHROPIC_API_KEY_STORAGE);
    } catch {
      /* ignore */
    }
  }, [anthropicApiKey]);

  useEffect(() => {
    try { localStorage.setItem(AUTO_TITLE_LLM_KEY, String(autoTitleLLM)); } catch { /* ignore */ }
  }, [autoTitleLLM]);

  useEffect(() => {
    if (models.length === 0) {
      fetchModels()
        .then((list) => {
          setModels(list);
          const values = list.map((m) => `${m.provider}/${m.model}`);
          const first = values[0];
          if (first) {
            setSelectedModel((s) => (!s || !values.includes(s) ? first : s));
            setSelectedModelTriage((s) => (!s || !values.includes(s) ? first : s));
          }
        })
        .catch(() => setModels([]));
    }
  }, [models.length]);

  useEffect(() => {
    let mounted = true;
    async function check() {
      try {
        const { ok } = await fetchHealth();
        if (mounted) setHealthOk(ok);
      } catch {
        if (mounted) setHealthOk(false);
      }
    }
    check();
    const t = setInterval(check, 30000);
    return () => {
      mounted = false;
      clearInterval(t);
    };
  }, []);

  // Auto-connect Telegram from localStorage on boot + poll status
  useEffect(() => {
    let mounted = true;
    async function autoConnect() {
      const savedToken = (() => { try { return localStorage.getItem(TG_TOKEN_STORAGE_KEY) || ""; } catch { return ""; } })();
      if (!savedToken) return;
      try {
        const cfg = await fetchChannelConfig();
        if (!cfg.telegram.bot_token && savedToken) {
          await updateChannelConfig({
            channels_enabled: true,
            telegram: { enabled: true, bot_token: savedToken, mirror_responses: cfg.telegram.mirror_responses }
          });
        }
      } catch { /* backend not ready yet */ }
      try {
        const st = await fetchChannelStatus();
        if (mounted) setTelegramConnected(st.channels.some((c) => c.channel_id === "telegram" && c.connected));
      } catch { /* ignore */ }
    }
    autoConnect();
    const poll = setInterval(async () => {
      try {
        const st = await fetchChannelStatus();
        if (mounted) setTelegramConnected(st.channels.some((c) => c.channel_id === "telegram" && c.connected));
      } catch { /* ignore */ }
    }, 15000);
    return () => { mounted = false; clearInterval(poll); };
  }, []);

  const handleToggleTelegram = async () => {
    const savedToken = (() => { try { return localStorage.getItem(TG_TOKEN_STORAGE_KEY) || ""; } catch { return ""; } })();
    if (telegramConnected) {
      try {
        const cfg = await fetchChannelConfig();
        await updateChannelConfig({
          channels_enabled: false,
          telegram: { enabled: false, bot_token: savedToken, mirror_responses: cfg.telegram.mirror_responses }
        });
        setTelegramConnected(false);
      } catch { /* ignore */ }
    } else {
      if (!savedToken) {
        setSettingsOpen(true);
        return;
      }
      try {
        const cfg = await fetchChannelConfig();
        await updateChannelConfig({
          channels_enabled: true,
          telegram: { enabled: true, bot_token: savedToken, mirror_responses: cfg.telegram.mirror_responses }
        });
        const st = await fetchChannelStatus();
        setTelegramConnected(st.channels.some((c) => c.channel_id === "telegram" && c.connected));
      } catch { /* ignore */ }
    }
  };

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      if (isCmdK) {
        e.preventDefault();
        setSearchModalOpen(true);
      }
      if (e.key === "Escape" && searchModalOpen && !query.trim()) {
        setSearchModalOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [searchModalOpen, query]);

  useEffect(() => {
    const content = document.querySelector(".content");
    if (!content) return;
    const onScroll = () => {
      const topbar = document.querySelector(".topbar");
      if (topbar) topbar.classList.toggle("is-opaque", content.scrollTop > 0);
    };
    content.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => content.removeEventListener("scroll", onScroll);
  }, []);

  async function refreshProjects() {
    const data = await fetchProjects();
    setProjects(data);
    if (selectedProject !== ALL_PROJECTS && !data.some((p) => p.project_id === selectedProject)) {
      setSelectedProject(ALL_PROJECTS);
    }
  }

  useEffect(() => {
    fetchSetupStatus()
      .then((s) => {
        setAppEnv(s.app_env);
        const onboardingDone = localStorage.getItem(ONBOARDING_DONE_KEY) === "true";
        if (s.onboarding_suggested && !onboardingDone) {
          setShowOnboarding(true);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (showOnboarding) return;
    let cancelled = false;
    (async () => {
      const [projectList, currentReconcile] = await Promise.all([
        fetchProjects(),
        fetchReconcileStatus(),
      ]);
      if (cancelled) return;
      setProjects(projectList);
      setReconcileStatus(currentReconcile);
      fetchStats().then(setDashboardStats).catch(() => {});

      if (!currentReconcile?.running) return;
      setReconcilingNow(true);
      setStatus("Reconciliacao ja em andamento; atualizando progresso...");
      const applyStatusMessage = (latest: ReconcileStatus) => {
        if (latest.running) {
          const proj = latest.progress_project ?? "—";
          const file = latest.progress_file ?? "—";
          setStatus(
            `Reconciliando: ${latest.progress_current ?? 0} / ${latest.progress_total ?? 0} docs | Projeto: ${proj} | Arquivo: ${file}${(latest.progress_skipped ?? 0) > 0 ? ` (skip: ${latest.progress_skipped})` : ""}`
          );
        }
      };
      const finishReconcileFromLoad = async (latest: ReconcileStatus) => {
        if (cancelled) return;
        await loadTriage();
        if (cancelled) return;
        fetchStats().then(setDashboardStats).catch(() => {});
        const skipMsg = Number(latest.summary?.skipped_docs) > 0 ? `, ${latest.summary.skipped_docs} skip (inalterados)` : "";
        const failMsg = Number(latest.summary?.failed_docs) > 0 ? `, ${latest.summary.failed_docs} falha(s)` : "";
        const orphanMsg = Number(latest.summary?.orphan_docs_deleted) > 0 ? `, ${latest.summary.orphan_docs_deleted} orfao(s) removido(s)` : "";
        setStatus(
          `Reconciliacao concluida: ${latest.summary?.adjustments_applied ?? 0} ajuste(s), ${latest.summary?.indexed_docs ?? 0} doc(s) indexado(s)${skipMsg}${failMsg}${orphanMsg}`
        );
        setReconcilingNow(false);
      };
      const streamUrl = getReconcileStatusStreamUrl();
      const es = new EventSource(streamUrl);
      reconcileEsRef.current = es;
      es.onmessage = async (e: MessageEvent) => {
        if (cancelled) return;
        const latest: ReconcileStatus = JSON.parse(e.data);
        setReconcileStatus(latest);
        applyStatusMessage(latest);
        if (!latest.running) {
          es.close();
          reconcileEsRef.current = null;
          await finishReconcileFromLoad(latest);
        }
      };
      es.onerror = async () => {
        es.close();
        reconcileEsRef.current = null;
        if (cancelled) return;
        const latest = await fetchReconcileStatus();
        setReconcileStatus(latest);
        if (!latest.running) {
          await finishReconcileFromLoad(latest);
          return;
        }
        let running: boolean = !!latest.running;
        while (running && !cancelled) {
          await new Promise((r) => setTimeout(r, 1500));
          const next = await fetchReconcileStatus();
          setReconcileStatus(next);
          applyStatusMessage(next);
          running = !!next.running;
        }
        if (!cancelled) await finishReconcileFromLoad(await fetchReconcileStatus());
      };
    })().catch((err) => setStatus(`Falha ao carregar dados: ${err instanceof Error ? err.message : "erro desconhecido"}`));
    return () => {
      cancelled = true;
      reconcileEsRef.current?.close();
      reconcileEsRef.current = null;
    };
  }, [showOnboarding]);

  const selectedProjectLabel = useMemo(
    () =>
      selectedProject === ALL_PROJECTS
        ? "Todos os projetos"
        : projects.find((p) => p.project_id === selectedProject)?.project_label ?? "",
    [projects, selectedProject]
  );

  const projectLabelById = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of projects) map.set(p.project_id, p.project_label);
    return map;
  }, [projects]);

  function extractFolder(path: string): string {
    const parts = path.split("/").filter(Boolean);
    const workIdx = parts.indexOf("_WORK");
    if (workIdx >= 0 && parts[workIdx + 1]) return parts[workIdx + 1];
    const triageIdx = parts.indexOf("_TRIAGE_REVIEW");
    if (triageIdx >= 0 && parts[triageIdx + 1]) return `_TRIAGE/${parts[triageIdx + 1]}`;
    return parts.length >= 2 ? parts[parts.length - 2] : "-";
  }

  function renderBreadcrumb(projectId: string, path: string): string {
    const projectLabel = projectLabelById.get(projectId) || projectId;
    return `${projectLabel} > ${extractFolder(path)}`;
  }

  function cleanSnippetHtml(snippet: string): string {
    return snippet
      .replace(/\[[^\]]+\]\s*/g, "")
      .replace(/\n+/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim();
  }

  function bestSnippet(highlights: string[]): string {
    if (!highlights.length) return "Sem trecho destacado para esta busca.";
    const withEmphasis = highlights.find((h) => h.includes("<em>")) || highlights[0];
    return cleanSnippetHtml(withEmphasis);
  }

  function highlightTerm(text: string, term: string) {
    const tokens = term
      .trim()
      .split(/\s+/)
      .map((t) => t.trim())
      .filter((t) => t.length >= 2);
    if (!tokens.length) return [text];
    const escaped = tokens
      .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .sort((a, b) => b.length - a.length)
      .join("|");
    const parts = text.split(new RegExp(`(${escaped})`, "ig"));
    return parts.map((part, idx) => {
      const isMatch = tokens.some((token) => token.toLowerCase() === part.toLowerCase());
      return isMatch ? <em key={`${text}-${idx}`}>{part}</em> : part;
    });
  }

  function clearSearch() {
    setQuery("");
    setModalHits([]);
    setFullResults([]);
    setFullQuery("");
    setFullSearchInput("");
    setFullPage(1);
    setFullTotalPages(1);
    setFullTotal(0);
    setSearchFilters({});
    setSearchStats(null);
    setStatus("Busca limpa");
  }

  function extractSnippets(highlights: string[]): string[] {
    return [bestSnippet(highlights)];
  }

  function getDocIcon(contentType?: string | null, filename?: string) {
    const ext = (filename?.split(".").pop() || "").toLowerCase();
    if (contentType === "xlsx" || ["xlsx", "xls", "xlsm", "csv"].includes(ext)) return <FileSpreadsheet size={16} />;
    if (contentType === "pptx" || ["ppt", "pptx"].includes(ext)) return <Presentation size={16} />;
    if (contentType === "docx" || contentType === "pdf" || ["doc", "docx", "pdf", "txt", "md"].includes(ext)) {
      return <FileText size={16} />;
    }
    return <File size={16} />;
  }

  async function handleSelectProject(nextProject: string) {
    if (nextProject === ALL_PROJECTS) {
      setSelectedProject(nextProject);
      return;
    }

    const target = projects.find((project) => project.project_id === nextProject);
    if (!target) return;

    if (target.initialized) {
      setSelectedProject(nextProject);
      return;
    }

    setTemplateModalProject({ ref: nextProject, label: target.project_label });
  }

  async function handleTemplateInitialized() {
    const ref = templateModalProject?.ref;
    setTemplateModalProject(null);
    await refreshProjects();
    if (ref) setSelectedProject(ref);
    setStatus("Projeto inicializado com sucesso");
  }

  async function handleReconcileNow() {
    const scopeLabel = selectedProject === ALL_PROJECTS ? "todos os projetos" : selectedProjectLabel || selectedProject;
    setReconcilingNow(true);
    setStatus(`Iniciando reconciliacao de ${scopeLabel}...`);

    const applyStatusMessage = (latest: ReconcileStatus) => {
      if (latest.running) {
        const proj = latest.progress_project ?? "—";
        const file = latest.progress_file ?? "—";
        setStatus(
          `Reconciliando: ${latest.progress_current ?? 0} / ${latest.progress_total ?? 0} docs | Projeto: ${proj} | Arquivo: ${file}${(latest.progress_skipped ?? 0) > 0 ? ` (skip: ${latest.progress_skipped})` : ""}`
        );
      }
    };

    const finishReconcile = async (latest: ReconcileStatus) => {
      await loadTriage();
      fetchStats().then(setDashboardStats).catch(() => {});
      const skipMsg = Number(latest.summary?.skipped_docs) > 0 ? `, ${latest.summary.skipped_docs} skip (inalterados)` : "";
        const failMsg = Number(latest.summary?.failed_docs) > 0 ? `, ${latest.summary.failed_docs} falha(s)` : "";
        const orphanMsg = Number(latest.summary?.orphan_docs_deleted) > 0 ? `, ${latest.summary.orphan_docs_deleted} orfao(s) removido(s)` : "";
        setStatus(
          `Reconciliacao concluida (${scopeLabel}): ${latest.summary?.adjustments_applied ?? 0} ajuste(s), ${latest.summary?.indexed_docs ?? 0} doc(s) indexado(s)${skipMsg}${failMsg}${orphanMsg}`
        );
      setReconcilingNow(false);
    };

    const subscribeToReconcileStream = () => {
      const streamUrl = getReconcileStatusStreamUrl();
      const es = new EventSource(streamUrl);
      es.onmessage = async (e: MessageEvent) => {
        const latest: ReconcileStatus = JSON.parse(e.data);
        setReconcileStatus(latest);
        applyStatusMessage(latest);
        if (!latest.running) {
          es.close();
          await finishReconcile(latest);
        }
      };
      es.onerror = async () => {
        es.close();
        const latest = await fetchReconcileStatus();
        setReconcileStatus(latest);
        if (!latest.running) {
          await finishReconcile(latest);
          return;
        }
        let running: boolean = !!latest.running;
        while (running) {
          await new Promise((r) => setTimeout(r, 1500));
          const next = await fetchReconcileStatus();
          setReconcileStatus(next);
          applyStatusMessage(next);
          running = !!next.running;
        }
        await finishReconcile(await fetchReconcileStatus());
      };
    };

    try {
      await runReconcile(selectedProject === ALL_PROJECTS ? undefined : selectedProject);
      subscribeToReconcileStream();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Falha ao reconciliar";
      if (msg.includes("ja em andamento")) {
        setStatus("Reconciliacao ja em andamento; acompanhando progresso...");
        subscribeToReconcileStream();
      } else {
        setStatus(msg);
        setReconcilingNow(false);
      }
    }
  }

  async function loadModalTopHits() {
    const q = query.trim();
    if (q.length < 2) {
      setModalHits([]);
      return;
    }
    setModalLoading(true);
    try {
      const data = await searchDocuments(q, selectedProject === ALL_PROJECTS ? undefined : selectedProject, 1, 6);
      setModalHits(data.hits);
    } catch {
      setModalHits([]);
    } finally {
      setModalLoading(false);
    }
  }

  async function runFullSearch(page = 1, overrideQuery?: string, overrideFilters?: SearchFilters) {
    const q = (overrideQuery ?? (fullSearchInput || query)).trim();
    if (q.length < 2) return;
    const filters = overrideFilters ?? searchFilters;
    const activeFilters: SearchFilters = {};
    if (filters.doc_kind) activeFilters.doc_kind = filters.doc_kind;
    if (filters.document_type) activeFilters.document_type = filters.document_type;
    if (filters.business_domain) activeFilters.business_domain = filters.business_domain;
    setFullLoading(true);
    try {
      const projectScope = selectedProject === ALL_PROJECTS ? undefined : selectedProject;
      const data = await searchDocuments(q, projectScope, page, 20, Object.keys(activeFilters).length > 0 ? activeFilters : undefined);
      setFullQuery(q);
      setFullSearchInput(q);
      setFullResults(data.hits);
      setFullPage(data.page);
      setFullTotal(data.total);
      setFullTotalPages(data.total_pages);
      setStatus(`${data.total} resultado(s)`);
      if (!searchStats) {
        fetchStats(projectScope).then(setSearchStats).catch(() => {});
      }
    } catch {
      setStatus("Falha na busca");
    } finally {
      setFullLoading(false);
    }
  }

  useEffect(() => {
    const q = query.trim();
    if (!searchModalOpen || q.length < 2) {
      setModalHits([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void loadModalTopHits();
    }, 220);
    return () => window.clearTimeout(timer);
  }, [query, selectedProject, searchModalOpen]);

  async function loadTriage() {
    if (!selectedProject) return;
    try {
      if (selectedProject === ALL_PROJECTS) {
        const batches = await Promise.all(projects.map((p) => fetchTriage(p.project_id)));
        setTriageItems(batches.flat());
      } else {
        const data = await fetchTriage(selectedProject);
        setTriageItems(data);
      }
    } catch {
      setStatus("Falha ao carregar triagem");
    }
  }

  useEffect(() => {
    void loadTriage();
  }, [selectedProject, projects]);

  async function openCorrectModal(item: TriageItem) {
    setStatus(`Carregando catálogo de classificação de ${projectLabelById.get(item.project_id) || item.project_id}...`);
    try {
      const resp = await fetchProjectProfile(item.project_id);
      const classification = resp.profile.classification || {};
      const domainRows: Array<{ key: string; label?: string | null }> = classification.business_domains || [];
      const areas = domainRows.map((area) => ({
        key: area.key,
        label: area.label || area.key
      }));
      if (!areas.length) {
        setStatus("Projeto sem domínios configurados para correção");
        return;
      }
      const suggestedDomain = item.suggested_business_domain || "";
      const suggestedDomainExists = !!suggestedDomain && areas.some((area) => area.key === suggestedDomain);
      const documentTypes = (classification.document_types || []).map((item) => ({
        key: item.key,
        label: item.label || item.key,
        folder: item.folder
      }));
      if (!documentTypes.length) {
        setStatus("Projeto sem tipos documentais configurados para correção");
        return;
      }
      const suggestedDocumentType = item.suggested_document_type || "";
      const suggestedDocumentTypeExists = !!suggestedDocumentType && documentTypes.some((entry) => entry.key === suggestedDocumentType);
      setCorrectBusinessDomainOptions(areas);
      setCorrectDocumentTypeOptions(documentTypes);
      setCorrectBusinessDomainValue(suggestedDomainExists ? suggestedDomain : areas[0].key);
      setCorrectDocumentTypeValue(suggestedDocumentTypeExists ? suggestedDocumentType : documentTypes[0].key);
      setCorrectModalItem(item);
      setStatus("Selecione domínio e tipo documental para aprovar com correção");
    } catch {
      setStatus("Falha ao carregar catálogo para correção");
    }
  }

  function submitCorrectDecision() {
    if (!correctModalItem || !correctBusinessDomainValue || !correctDocumentTypeValue) return;
    const item = correctModalItem;
    const businessDomainValue = correctBusinessDomainValue;
    const documentTypeValue = correctDocumentTypeValue;
    setCorrectModalItem(null);
    setCorrectSubmitting(false);
    setTriageItems((prev) => prev.filter((i) => i.doc_id !== item.doc_id));
    setStatus("Registrando correcao em segundo plano...");
    triageDecision(item.project_id, item.doc_id, "correct", businessDomainValue, documentTypeValue)
      .then(() => loadTriage())
      .then(() => {
        setStatus(`Documento aprovado por correção e movido para ${businessDomainValue}/${documentTypeValue}`);
      })
      .catch(() => {
        setStatus("Falha ao registrar correção");
        void loadTriage();
      });
  }

  // SSE: real-time session updates from other channels (e.g. Telegram)
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
      } catch { /* ignore malformed event */ }
    });
    es.onerror = () => {
      es.close();
    };
    return () => es.close();
  }, [activeSessionId, chatSending]);

  async function handleChatSend(text: string, attachments?: ChatAttachment[]) {
    const trimmed = text.trim();
    const hasAttachments = attachments && attachments.length > 0;
    if (!trimmed && !hasAttachments) return;
    if (chatSending || !selectedModel) return;
    const userContent: string | ChatContentPart[] = hasAttachments
      ? [
          { type: "text", text: trimmed || "(imagem anexada)" },
          ...attachments!.map((a) => ({ type: "image_url" as const, image_url: { url: a.dataUrl } }))
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
      // Refresh session from backend to pick up messages added by other channels
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
            setChatMessages(freshChat);
          }
        } catch {
          // fallback to local state
        }
      }
      const newUserContent: string | ChatContentPart[] = hasAttachments
        ? [
            { type: "text", text: trimmed || "(imagem anexada)" },
            ...attachments!.map((a) => ({ type: "image_url" as const, image_url: { url: a.dataUrl } }))
          ]
        : trimmed;
      const messagesForApi: ChatMessageType[] = [
        ...baseMsgs.map((m) => ({ role: m.role, content: m.content })),
        { role: "user", content: newUserContent }
      ];
      const projectScope = selectedProject === ALL_PROJECTS ? undefined : selectedProject;
      const [provider, model] = selectedModel.split("/");
      const res = await sendChatMessage(messagesForApi, {
        projectId: projectScope,
        provider,
        model,
        openaiApiKey: provider === "openai" ? (openaiApiKey || undefined) : undefined,
        anthropicApiKey: provider === "anthropic" ? (anthropicApiKey || undefined) : undefined,
        enableThinking: showThinking,
        signal: controller.signal
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
        const pt = sessionUsageTotals ?? { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_cost_usd: 0, api_call_count: 0 };
        mergedTotals = {
          input_tokens: pt.input_tokens + (turn.input_tokens ?? 0),
          output_tokens: pt.output_tokens + (turn.output_tokens ?? 0),
          total_tokens: pt.total_tokens + (turn.total_tokens ?? 0),
          estimated_cost_usd: pt.estimated_cost_usd + (turn.estimated_cost_usd ?? 0),
          api_call_count: (pt.api_call_count ?? 0) + (turn.api_call_count ?? 0),
          cache_read_input_tokens: (pt.cache_read_input_tokens ?? 0) + (turn.cache_read_input_tokens ?? 0) || undefined,
          cache_creation_input_tokens: (pt.cache_creation_input_tokens ?? 0) + (turn.cache_creation_input_tokens ?? 0) || undefined,
          cache_write_input_tokens: (pt.cache_write_input_tokens ?? 0) + (turn.cache_write_input_tokens ?? 0) || undefined,
        };
        setSessionUsageTotals(mergedTotals);
        const modelKey = selectedModel;
        const pm = sessionUsageByModel[modelKey] ?? { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_cost_usd: 0, api_call_count: 0 };
        newByModel = {
          ...sessionUsageByModel,
          [modelKey]: {
            input_tokens: pm.input_tokens + (turn.input_tokens ?? 0),
            output_tokens: pm.output_tokens + (turn.output_tokens ?? 0),
            total_tokens: pm.total_tokens + (turn.total_tokens ?? 0),
            estimated_cost_usd: pm.estimated_cost_usd + (turn.estimated_cost_usd ?? 0),
            api_call_count: (pm.api_call_count ?? 0) + (turn.api_call_count ?? 0),
            cache_read_input_tokens: (pm.cache_read_input_tokens ?? 0) + (turn.cache_read_input_tokens ?? 0) || undefined,
            cache_creation_input_tokens: (pm.cache_creation_input_tokens ?? 0) + (turn.cache_creation_input_tokens ?? 0) || undefined,
            cache_write_input_tokens: (pm.cache_write_input_tokens ?? 0) + (turn.cache_write_input_tokens ?? 0) || undefined,
          },
        };
        setSessionUsageByModel(newByModel);
      }

      const projectId = projectScope ?? null;
      if (activeSessionId) {
        const newMsgs = messagesToStored([userMsg, assistantMsg]);
        updateChatSession(activeSessionId, {
          append_messages: newMsgs,
          ...(mergedTotals ? { usage_totals: mergedTotals, usage_by_model: newByModel } : {}),
          project_id: projectId,
          source_channel: "web",
        }).catch(() => {});
      } else {
        const firstText = typeof userMsg.content === "string"
          ? userMsg.content
          : userMsg.content.map((p) => (p.type === "text" ? p.text : "")).join(" ").trim();
        const title = firstText.slice(0, 80) || `Conversa ${new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}`;
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
          .catch(() => setChatError("Falha ao salvar sessão automaticamente"));
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
          ? "Erro de rede. Verifique se a API está rodando (ex.: http://localhost:8000) e se o backend está acessível."
          : err.message || "Erro no chat";
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

  function handleRequestNewSession() {
    handleChatNewSession();
  }

  function generateTitleInBackground(
    sessionId: string,
    msgs: ChatMessageType[],
    existingTotals: UsageTotals | null,
    existingByModel: Record<string, UsageTotals>,
  ) {
    const textStart = msgs.slice(0, 6).map((m) => {
      const c = typeof m.content === "string" ? m.content : m.content.map((p) => (p.type === "text" ? p.text : "[imagem]")).join(" ");
      return { role: m.role, content: c };
    });
    const titleMessages = [
      { role: "system" as const, content: "Retorne apenas um título curto em uma linha, sem explicação." },
      ...textStart
    ];
    const [provider, model] = selectedModel.split("/");
    sendChatMessage(titleMessages, {
      provider,
      model,
      openaiApiKey: provider === "openai" ? (openaiApiKey || undefined) : undefined,
      anthropicApiKey: provider === "anthropic" ? (anthropicApiKey || undefined) : undefined,
      enableThinking: false
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
        const pm = existingByModel[selectedModel] ?? { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_cost_usd: 0 };
        const mergedByModel: Record<string, UsageTotals> = {
          ...existingByModel,
          [selectedModel]: {
            input_tokens: pm.input_tokens + (turn.input_tokens ?? 0),
            output_tokens: pm.output_tokens + (turn.output_tokens ?? 0),
            total_tokens: pm.total_tokens + (turn.total_tokens ?? 0),
            estimated_cost_usd: pm.estimated_cost_usd + (turn.estimated_cost_usd ?? 0),
          },
        };
        return updateChatSession(sessionId, { title: llmTitle, usage_totals: mergedTotals, usage_by_model: mergedByModel });
      })
      .then(() => fetchChatSessions().then(setSessions))
      .catch(() => {});
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
        setChatError("Falha ao carregar histórico de sessões");
      })
      .finally(() => setSessionsLoading(false));
  }

  function messagesToStored(messages: ChatMessageType[]): StoredChatMessage[] {
    return messages.map((m) => {
      const content =
        typeof m.content === "string"
          ? m.content
          : m.content
              .map((p) => (p.type === "text" ? p.text : "[imagem]"))
              .join(" ");
      return { role: m.role, content, timestamp: m.timestamp, ...(m.model ? { model: m.model } : {}) };
    });
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
      .catch(() => setChatError("Falha ao carregar sessão"));
  }

  function handleEditSession(sessionId: string, newTitle: string) {
    updateChatSession(sessionId, { title: newTitle }).then(() =>
      fetchChatSessions().then(setSessions)
    );
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

  async function handleDecision(item: TriageItem, action: "approve" | "correct" | "reject") {
    if (action === "correct") {
      await openCorrectModal(item);
      return;
    }
    try {
      await triageDecision(item.project_id, item.doc_id, action);
      await loadTriage();
      if (action === "reject") {
        setStatus("Documento rejeitado e movido para rejected com nome original");
      } else {
        setStatus(`Decisao registrada: ${action}`);
      }
    } catch {
      setStatus("Falha ao registrar decisao");
    }
  }

  function handleOnboardingComplete(createdProjectId?: string) {
    localStorage.setItem(ONBOARDING_DONE_KEY, "true");
    setShowOnboarding(false);
    refreshProjects().then(() => {
      if (createdProjectId) setSelectedProject(createdProjectId);
    });
  }

  function handleReplayOnboarding() {
    localStorage.removeItem(ONBOARDING_DONE_KEY);
    setShowOnboarding(true);
  }

  const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/;

  function handleNewProjectConfirm() {
    const name = newProjectName.trim();
    if (!name || !SLUG_RE.test(name)) return;
    setNewProjectModalOpen(false);
    setNewProjectName("");
    setTemplateModalProject({ ref: name, label: name });
  }

  if (showOnboarding) {
    return (
      <OnboardingWizard
        onComplete={handleOnboardingComplete}
        onCancel={() => { localStorage.setItem(ONBOARDING_DONE_KEY, "true"); setShowOnboarding(false); }}
        openaiApiKey={openaiApiKey}
        anthropicApiKey={anthropicApiKey}
        onChangeOpenAiKey={setOpenaiApiKey}
        onChangeAnthropicKey={setAnthropicApiKey}
      />
    );
  }

  return (
    <ToastProvider>
    <div className="shell">
      <Topbar
        healthOk={healthOk}
        projects={projects}
        selectedProject={selectedProject}
        onSelectProject={handleSelectProject}
        view={view}
        onChangeView={setView}
        theme={theme}
        onChangeTheme={setTheme}
        onOpenSearch={() => setSearchModalOpen(true)}
        onNewProject={() => { setNewProjectModalOpen(true); setNewProjectName(""); }}
      />

      {appEnv === "dev" && (
        <button type="button" className="dev-onboarding-btn" onClick={handleReplayOnboarding} title="Replay Onboarding (dev only)">
          <RefreshCw size={14} /> Onboarding
        </button>
      )}

      <main className="content">
      {view === "painel" && (
        <PainelView
          projects={projects}
          selectedProject={selectedProject}
          projectLabelById={projectLabelById}
          triageItems={triageItems}
          dashboardStats={dashboardStats}
          reconcileStatus={reconcileStatus}
          reconcilingNow={reconcilingNow}
          onReconcile={handleReconcileNow}
          onDecision={handleDecision}
          onStatus={setStatus}
          onScanComplete={() => { void loadTriage(); }}
          fullQuery={fullQuery}
          fullResults={fullResults}
          fullPage={fullPage}
          fullTotalPages={fullTotalPages}
          fullTotal={fullTotal}
          fullLoading={fullLoading}
          fullSearchInput={fullSearchInput}
          searchFilters={searchFilters}
          searchStats={searchStats}
          onFullSearchInputChange={setFullSearchInput}
          onRunFullSearch={runFullSearch}
          onSearchFiltersChange={setSearchFilters}
          onClearSearch={clearSearch}
        />
      )}

      {view === "assistente" && (
        <AssistenteView
          selectedProject={selectedProject}
          chatMessages={chatMessages}
          chatSending={chatSending}
          chatError={chatError}
          lastToolCalls={lastToolCalls}
          contextPressureRatio={contextPressureRatio}
          selectedModel={selectedModel}
          models={models}
          onModelChange={setSelectedModel}
          onOpenSettings={() => setSettingsOpen(true)}
          onSend={handleChatSend}
          onAbort={handleChatAbort}
          onNewSession={handleRequestNewSession}
          showThinking={showThinking}
          onShowThinkingChange={setShowThinking}
          sessions={sessions}
          sessionsLoading={sessionsLoading}
          activeSessionId={activeSessionId}
          historyModalOpen={historyModalOpen}
          onOpenHistory={openHistoryModal}
          onCloseHistory={() => setHistoryModalOpen(false)}
          onSelectSession={handleSelectSession}
          onEditSession={handleEditSession}
          onDeleteSession={handleDeleteSession}
          savingSession={savingSession}
          telegramConnected={telegramConnected}
          onToggleTelegram={handleToggleTelegram}
        />
      )}

      {view === "config" && (
        <ConfigView
          selectedProject={selectedProject}
          selectedProjectLabel={selectedProjectLabel}
          projects={projects}
          projectLabelById={projectLabelById}
          triageItems={triageItems}
          initializingProjectId={initializingProjectId}
          onLoadTriage={loadTriage}
          onStatus={setStatus}
          openaiApiKey={openaiApiKey}
          anthropicApiKey={anthropicApiKey}
          onOpenSettings={() => setSettingsOpen(true)}
          selectedModelTriage={selectedModelTriage}
          onChangeModelTriage={setSelectedModelTriage}
        />
      )}

      <footer className="status">{status}</footer>
      </main>

      {templateModalProject && (
        <TemplateSelectModal
          open={!!templateModalProject}
          projectRef={templateModalProject.ref}
          projectLabel={templateModalProject.label}
          onClose={() => setTemplateModalProject(null)}
          onInitialized={() => void handleTemplateInitialized()}
          onCreateTemplate={() => { setTemplateModalProject(null); setView("config"); }}
        />
      )}

      <SearchModal
        open={searchModalOpen}
        query={query}
        onQueryChange={setQuery}
        modalHits={modalHits}
        modalLoading={modalLoading}
        onClose={() => setSearchModalOpen(false)}
        onClearSearch={clearSearch}
        onSubmitSearch={(q) => {
          setFullSearchInput(q);
          void runFullSearch(1, q);
          setSearchModalOpen(false);
        }}
        renderBreadcrumb={renderBreadcrumb}
        highlightTerm={highlightTerm}
        extractSnippets={extractSnippets}
        getDocIcon={getDocIcon}
        getFileDownloadUrl={getFileDownloadUrl}
      />

      <AssistantSettingsModal
        open={settingsOpen}
        selectedModel={selectedModel}
        selectedModelTriage={selectedModelTriage}
        models={models}
        openaiApiKey={openaiApiKey}
        anthropicApiKey={anthropicApiKey}
        onChangeModel={setSelectedModel}
        onChangeModelTriage={setSelectedModelTriage}
        onChangeOpenAiKey={setOpenaiApiKey}
        onChangeAnthropicKey={setAnthropicApiKey}
        autoTitleLLM={autoTitleLLM}
        onChangeAutoTitleLLM={setAutoTitleLLM}
        onClose={() => setSettingsOpen(false)}
      />

      <CorrectDecisionModal
        item={correctModalItem}
        submitting={correctSubmitting}
        businessDomainValue={correctBusinessDomainValue}
        businessDomainOptions={correctBusinessDomainOptions}
        documentTypeValue={correctDocumentTypeValue}
        documentTypeOptions={correctDocumentTypeOptions}
        onChangeBusinessDomain={setCorrectBusinessDomainValue}
        onChangeDocumentType={setCorrectDocumentTypeValue}
        onCancel={() => {
          setCorrectModalItem(null);
          setCorrectBusinessDomainValue("");
          setCorrectDocumentTypeValue("");
        }}
        onSubmit={submitCorrectDecision}
      />

      {newProjectModalOpen && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Novo projeto">
          <div className="modal">
            <h3>Novo projeto</h3>
            <label htmlFor="new-project-name">Nome do projeto (slug)</label>
            <input
              id="new-project-name"
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
              placeholder="meu_projeto"
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter") handleNewProjectConfirm(); }}
            />
            <p className="sub">Apenas letras minúsculas, números, _ e - (sem espaços ou acentos)</p>
            {newProjectName && !SLUG_RE.test(newProjectName) && (
              <p className="modal-move-error">Nome inválido</p>
            )}
            <div className="modal-actions">
              <button className="btn" onClick={() => setNewProjectModalOpen(false)}>Cancelar</button>
              <button
                className="btn primary"
                disabled={!newProjectName || !SLUG_RE.test(newProjectName)}
                onClick={handleNewProjectConfirm}
              >
                Continuar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </ToastProvider>
  );
}

export default App;
