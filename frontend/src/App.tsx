import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchChannelConfig,
  fetchChannelStatus,
  fetchHealth,
  fetchProjectProfile,
  fetchReconcileStatus,
  fetchSetupStatus,
  fetchStats,
  fetchTriage,
  getReconcileStatusStreamUrl,
  runReconcile,
  setUnauthorizedHandler,
  triageDecision,
  updateChannelConfig,
} from "./api";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { fieldLabelClass, ModalActions, ModalShell } from "./components/ui/modal-shell";
import { Toaster, toast } from "./components/ui/sonner";
import { emitDataRefresh, onDataRefresh } from "./lib/refreshBus";
import { NavigationProvider, useNavigation } from "./contexts/NavigationContext";
import { ALL_PROJECTS, ProjectProvider, useProject } from "./contexts/ProjectContext";
import { SettingsProvider, useSettings } from "./contexts/SettingsContext";
import { useChatSession } from "./hooks/useChatSession";
import { useSearch } from "./hooks/useSearch";
import { CommandPalette } from "./layouts/CommandPalette";
import { Sidebar } from "./layouts/Sidebar";
import { Topbar } from "./layouts/Topbar";
import { ConfigView } from "./views/ConfigView";
import { PainelView } from "./views/PainelView";
import { AssistantSettingsModal } from "./features/settings/AssistantSettingsModal";
import { CreateTaxonomyEntryModal } from "./features/templates/CreateTaxonomyEntryModal";
import { CorrectDecisionModal } from "./features/triage/CorrectDecisionModal";
import { TemplateSelectModal } from "./features/templates/TemplateSelectModal";
import { AssistenteView } from "./views/AssistenteView";
import { GlobalDropPortal } from "./features/ingest/GlobalDropPortal";
import { AuthGate } from "./features/onboarding/AuthGate";
import { OnboardingWizard } from "./features/onboarding/OnboardingWizard";
import type {
  ProjectArea,
  ProjectDocumentType,
  ReconcileStatus,
  StatsResponse,
  TriageItem,
} from "./types";

const ONBOARDING_DONE_KEY = "atlasfile-onboarding-done";
const TG_TOKEN_STORAGE_KEY = "atlasfile-telegram-bot-token";
const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/;

function AppShell() {
  const { view, setView } = useNavigation();
  const {
    theme,
    setTheme,
    models,
    selectedModel,
    setSelectedModel,
    selectedModelTriage,
    setSelectedModelTriage,
    openaiApiKey,
    setOpenaiApiKey,
    anthropicApiKey,
    setAnthropicApiKey,
    showThinking,
    setShowThinking,
    autoTitleLLM,
    setAutoTitleLLM,
    settingsOpen,
    setSettingsOpen,
  } = useSettings();
  const {
    projects,
    selectedProject,
    setSelectedProject,
    selectedProjectLabel,
    projectLabelById,
    refreshProjects,
  } = useProject();

  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [status, setStatus] = useState("Pronto");

  // O footer .status morreu: mensagens de status viram um toast único que se
  // atualiza in-place (id fixo) — progresso contínuo não vira spam de toasts.
  useEffect(() => {
    if (!status || status === "Pronto") return;
    const isError = /falha|erro|negado|inválid/i.test(status);
    toast[isError ? "error" : "message"](status, { id: "app-status" });
  }, [status]);
  const [triageItems, setTriageItems] = useState<TriageItem[]>([]);
  const [reconcileStatus, setReconcileStatus] = useState<ReconcileStatus | null>(null);
  const [dashboardStats, setDashboardStats] = useState<StatsResponse | null>(null);
  const [initializingProjectId] = useState<string | null>(null);
  const [reconcilingNow, setReconcilingNow] = useState(false);
  const [correctModalItem, setCorrectModalItem] = useState<TriageItem | null>(null);
  const [correctBusinessDomainOptions, setCorrectBusinessDomainOptions] = useState<ProjectArea[]>([]);
  const [correctBusinessDomainValue, setCorrectBusinessDomainValue] = useState("");
  const [correctDocumentTypeOptions, setCorrectDocumentTypeOptions] = useState<ProjectDocumentType[]>([]);
  const [correctTaxonomyModalOpen, setCorrectTaxonomyModalOpen] = useState(false);
  const [correctDocumentTypeValue, setCorrectDocumentTypeValue] = useState("");
  const [correctSubmitting, setCorrectSubmitting] = useState(false);
  const [templateModalProject, setTemplateModalProject] = useState<{ ref: string; label: string } | null>(null);
  const [newProjectModalOpen, setNewProjectModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [telegramConnected, setTelegramConnected] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [appEnv, setAppEnv] = useState("production");
  const reconcileEsRef = useRef<EventSource | null>(null);

  const search = useSearch({ onStatus: setStatus });
  const chat = useChatSession();

  useEffect(() => {
    setUnauthorizedHandler((httpStatus, detail) => {
      if (httpStatus === 401) {
        // Sem key válida: o gate de autenticação assume a tela inteira —
        // capturar a key é a PRIMEIRA coisa, antes de onboarding ou dados.
        setAuthRequired(true);
        return;
      }
      setStatus(`Acesso negado: ${detail || "API key sem permissão para este projeto."}`);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    let mounted = true;
    // Debounce + retry adaptativo: 1 blip transitório (restart de container,
    // rede) não pode tremer o orb em "error" — exige 2 falhas seguidas; e em
    // erro re-verifica a cada 5s (não 30s) para recuperar rápido sem reload.
    let failures = 0;
    let timer: number | undefined;
    async function check() {
      let ok = false;
      try {
        ok = (await fetchHealth()).ok;
      } catch {
        ok = false;
      }
      if (!mounted) return;
      failures = ok ? 0 : failures + 1;
      if (ok) setHealthOk(true);
      else if (failures >= 2) setHealthOk(false);
      timer = window.setTimeout(check, failures > 0 ? 5000 : 30000);
    }
    void check();
    return () => {
      mounted = false;
      window.clearTimeout(timer);
    };
  }, []);

  // Auto-connect Telegram do localStorage no boot + poll de status
  useEffect(() => {
    let mounted = true;
    async function autoConnect() {
      const savedToken = (() => {
        try {
          return localStorage.getItem(TG_TOKEN_STORAGE_KEY) || "";
        } catch {
          return "";
        }
      })();
      if (!savedToken) return;
      try {
        const cfg = await fetchChannelConfig();
        if (!cfg.telegram.bot_token && savedToken) {
          await updateChannelConfig({
            channels_enabled: true,
            telegram: { enabled: true, bot_token: savedToken, mirror_responses: cfg.telegram.mirror_responses },
          });
        }
      } catch {
        /* backend ainda não pronto */
      }
      try {
        const st = await fetchChannelStatus();
        if (mounted) setTelegramConnected(st.channels.some((c) => c.channel_id === "telegram" && c.connected));
      } catch {
        /* ignore */
      }
    }
    autoConnect();
    const poll = setInterval(async () => {
      try {
        const st = await fetchChannelStatus();
        if (mounted) setTelegramConnected(st.channels.some((c) => c.channel_id === "telegram" && c.connected));
      } catch {
        /* ignore */
      }
    }, 15000);
    return () => {
      mounted = false;
      clearInterval(poll);
    };
  }, []);

  const handleToggleTelegram = async () => {
    const savedToken = (() => {
      try {
        return localStorage.getItem(TG_TOKEN_STORAGE_KEY) || "";
      } catch {
        return "";
      }
    })();
    if (telegramConnected) {
      try {
        const cfg = await fetchChannelConfig();
        await updateChannelConfig({
          channels_enabled: false,
          telegram: { enabled: false, bot_token: savedToken, mirror_responses: cfg.telegram.mirror_responses },
        });
        setTelegramConnected(false);
      } catch {
        /* ignore */
      }
    } else {
      if (!savedToken) {
        setSettingsOpen(true);
        return;
      }
      try {
        const cfg = await fetchChannelConfig();
        await updateChannelConfig({
          channels_enabled: true,
          telegram: { enabled: true, bot_token: savedToken, mirror_responses: cfg.telegram.mirror_responses },
        });
        const st = await fetchChannelStatus();
        setTelegramConnected(st.channels.some((c) => c.channel_id === "telegram" && c.connected));
      } catch {
        /* ignore */
      }
    }
  };

  useEffect(() => {
    fetchSetupStatus()
      .then((s) => {
        setAppEnv(s.app_env);
        const onboardingDone = localStorage.getItem(ONBOARDING_DONE_KEY) === "true";
        // Backend zerado = instalação nova: a flag do localStorage pode ser de
        // outra instância servida na mesma origem (localhost:5173) — ignorá-la.
        const backendEmpty = s.initialized_projects === 0;
        if (s.onboarding_suggested && (!onboardingDone || backendEmpty)) {
          setShowOnboarding(true);
        }
      })
      .catch(() => {});
  }, []);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProject, projects]);

  useEffect(() => {
    if (showOnboarding) return;
    let cancelled = false;
    (async () => {
      // Boot é best-effort: falha aqui (API subindo, backend zerado no wizard)
      // não vira toast — conectividade é sinalizada pelo orb de health
      const [, currentReconcile] = await Promise.all([
        refreshProjects().catch(() => undefined),
        fetchReconcileStatus().catch(() => null),
      ]);
      if (cancelled) return;
      if (currentReconcile) setReconcileStatus(currentReconcile);
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
        emitDataRefresh();
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showOnboarding]);

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
      emitDataRefresh();
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

  async function openCorrectModal(item: TriageItem) {
    setStatus(`Carregando catálogo de classificação de ${projectLabelById.get(item.project_id) || item.project_id}...`);
    try {
      const resp = await fetchProjectProfile(item.project_id);
      const classification = resp.profile.classification || {};
      const domainRows: Array<{ key: string; label?: string | null }> = classification.business_domains || [];
      const areas = domainRows.map((area) => ({
        key: area.key,
        label: area.label || area.key,
      }));
      if (!areas.length) {
        setStatus("Projeto sem domínios configurados para correção");
        return;
      }
      const suggestedDomain = item.suggested_business_domain || "";
      const suggestedDomainExists = !!suggestedDomain && areas.some((area) => area.key === suggestedDomain);
      const documentTypes = (classification.document_types || []).map((entry) => ({
        key: entry.key,
        label: entry.label || entry.key,
        folder: entry.folder,
      }));
      if (!documentTypes.length) {
        setStatus("Projeto sem tipos documentais configurados para correção");
        return;
      }
      const suggestedDocumentType = item.suggested_document_type || "";
      const suggestedDocumentTypeExists =
        !!suggestedDocumentType && documentTypes.some((entry) => entry.key === suggestedDocumentType);
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
      .then(() => {
        emitDataRefresh();
        setStatus(`Documento aprovado por correção e movido para ${businessDomainValue}/${documentTypeValue}`);
      })
      .catch(() => {
        setStatus("Falha ao registrar correção");
        void loadTriage();
      });
  }

  /** Fonte única de reatividade: TODA mutação emite no bus; o App assina o
   *  bus para triagem + stats (estado que vive aqui e nunca remonta), e os
   *  cards derivados (histórico, inbox, rejeitados, projetos) assinam cada um
   *  o seu — zero reloads de página, zero pontos esquecidos. */
  const handleDataChanged = useCallback(() => {
    emitDataRefresh();
  }, []);

  useEffect(
    () =>
      onDataRefresh(() => {
        void loadTriage();
        fetchStats().then(setDashboardStats).catch(() => {});
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedProject, projects]
  );

  async function handleDecision(item: TriageItem, action: "approve" | "correct" | "reject") {
    if (action === "correct") {
      await openCorrectModal(item);
      return;
    }
    try {
      await triageDecision(item.project_id, item.doc_id, action);
      emitDataRefresh();
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

  function handleNewProjectConfirm() {
    const name = newProjectName.trim();
    if (!name || !SLUG_RE.test(name)) return;
    setNewProjectModalOpen(false);
    setNewProjectName("");
    setTemplateModalProject({ ref: name, label: name });
  }

  if (authRequired) {
    return <AuthGate />;
  }

  if (showOnboarding) {
    return (
      <OnboardingWizard
        onComplete={handleOnboardingComplete}
        onCancel={() => {
          localStorage.setItem(ONBOARDING_DONE_KEY, "true");
          setShowOnboarding(false);
        }}
        openaiApiKey={openaiApiKey}
        anthropicApiKey={anthropicApiKey}
        onChangeOpenAiKey={setOpenaiApiKey}
        onChangeAnthropicKey={setAnthropicApiKey}
      />
    );
  }

  return (
    <div className="flex h-screen max-w-[100vw] overflow-hidden bg-background text-foreground">
      <Sidebar
        healthOk={healthOk}
        onSelectProject={(projectId) => void handleSelectProject(projectId)}
        onNewProject={() => {
          setNewProjectModalOpen(true);
          setNewProjectName("");
        }}
        onOpenSearch={() => search.setSearchModalOpen(true)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar>
          {appEnv === "dev" && (
            <Button variant="secondary" size="sm" onClick={handleReplayOnboarding} title="Replay Onboarding (dev only)">
              <RefreshCw /> Onboarding
            </Button>
          )}
        </Topbar>

        <main className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col gap-6 overflow-y-auto overflow-x-hidden px-7 pb-8 pt-6 [-webkit-overflow-scrolling:touch]">
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
            onScanComplete={handleDataChanged}
            fullQuery={search.fullQuery}
            fullResults={search.fullResults}
            fullPage={search.fullPage}
            fullTotalPages={search.fullTotalPages}
            fullTotal={search.fullTotal}
            fullLoading={search.fullLoading}
            fullSearchInput={search.fullSearchInput}
            searchFilters={search.searchFilters}
            searchStats={search.searchStats}
            onFullSearchInputChange={search.setFullSearchInput}
            onRunFullSearch={search.runFullSearch}
            onSearchFiltersChange={search.setSearchFilters}
            onClearSearch={search.clearSearch}
          />
        )}

        {view === "assistente" && (
          <AssistenteView
            selectedProject={selectedProject}
            chatMessages={chat.chatMessages}
            chatSending={chat.chatSending}
            chatError={chat.chatError}
            lastToolCalls={chat.lastToolCalls}
            contextPressureRatio={chat.contextPressureRatio}
            selectedModel={selectedModel}
            models={models}
            onModelChange={setSelectedModel}
            onOpenSettings={() => setSettingsOpen(true)}
            onSend={chat.handleChatSend}
            onAbort={chat.handleChatAbort}
            onNewSession={chat.handleChatNewSession}
            showThinking={showThinking}
            onShowThinkingChange={setShowThinking}
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
            onToggleTelegram={handleToggleTelegram}
          />
        )}

        {view === "config" && (
          <ConfigView
            selectedProject={selectedProject}
            selectedProjectLabel={selectedProjectLabel}
            triageItems={triageItems}
            onStatus={setStatus}
            openaiApiKey={openaiApiKey}
            anthropicApiKey={anthropicApiKey}
            onOpenSettings={() => setSettingsOpen(true)}
            selectedModelTriage={selectedModelTriage}
            onChangeModelTriage={setSelectedModelTriage}
          />
        )}

        </main>
      </div>

      {templateModalProject && (
        <TemplateSelectModal
          open={!!templateModalProject}
          projectRef={templateModalProject.ref}
          projectLabel={templateModalProject.label}
          onClose={() => setTemplateModalProject(null)}
          onInitialized={() => void handleTemplateInitialized()}
          onCreateTemplate={() => {
            setTemplateModalProject(null);
            setView("config");
          }}
        />
      )}

      <GlobalDropPortal onScanComplete={handleDataChanged} />

      <CommandPalette
        open={search.searchModalOpen}
        onOpenChange={search.setSearchModalOpen}
        query={search.query}
        onQueryChange={search.setQuery}
        hits={search.modalHits}
        loading={search.modalLoading}
        onSubmitSearch={(q) => {
          search.setFullSearchInput(q);
          void search.runFullSearch(1, q);
          setView("painel");
        }}
        onSelectProject={(projectId) => void handleSelectProject(projectId)}
        onNewProject={() => {
          setNewProjectModalOpen(true);
          setNewProjectName("");
        }}
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
        onCreateTaxonomyEntry={() => setCorrectTaxonomyModalOpen(true)}
      />

      <CreateTaxonomyEntryModal
        open={correctTaxonomyModalOpen}
        onClose={() => setCorrectTaxonomyModalOpen(false)}
        onCreated={(kind, key) => {
          // Recarrega o catálogo do projeto do item em correção e pré-seleciona o criado
          const item = correctModalItem;
          if (!item) return;
          fetchProjectProfile(item.project_id)
            .then((resp) => {
              const classification = resp.profile.classification || {};
              setCorrectBusinessDomainOptions(
                (classification.business_domains || []).map((a) => ({ key: a.key, label: a.label || a.key }))
              );
              setCorrectDocumentTypeOptions(
                (classification.document_types || []).map((t) => ({ key: t.key, label: t.label || t.key }))
              );
              if (kind === "business_domain") setCorrectBusinessDomainValue(key);
              else setCorrectDocumentTypeValue(key);
            })
            .catch(() => setStatus("Falha ao recarregar catálogo após criação"));
        }}
      />

      {newProjectModalOpen && (
        <ModalShell label="Novo projeto" title="Novo projeto" size="sm">
          <label className={fieldLabelClass} htmlFor="new-project-name">Nome do projeto (slug)</label>
          <Input
            id="new-project-name"
            type="text"
            className="font-mono"
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
            placeholder="meu_projeto"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") handleNewProjectConfirm();
            }}
          />
          <p className="mt-1.5 text-[0.72rem] text-tertiary">Apenas letras minúsculas, números, _ e - (sem espaços ou acentos)</p>
          {newProjectName && !SLUG_RE.test(newProjectName) && (
            <p className="mt-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-1.5 text-[0.8rem] text-destructive">
              Nome inválido
            </p>
          )}
          <ModalActions>
            <Button variant="secondary" onClick={() => setNewProjectModalOpen(false)}>
              Cancelar
            </Button>
            <Button disabled={!newProjectName || !SLUG_RE.test(newProjectName)} onClick={handleNewProjectConfirm}>
              Continuar
            </Button>
          </ModalActions>
        </ModalShell>
      )}
    </div>
  );
}

function App() {
  return (
    <SettingsProvider>
        <ProjectProvider>
          <NavigationProvider>
            <AppShell />
            <Toaster />
        </NavigationProvider>
      </ProjectProvider>
    </SettingsProvider>
  );
}

export default App;
