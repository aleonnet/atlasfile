import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  fetchAliasSuggestions,
  fetchChannelConfig,
  fetchChannelStatus,
  fetchHealth,
  fetchProjectProfile,
  fetchSetupStatus,
  fetchStats,
  fetchTriage,
  setUnauthorizedHandler,
  triageDecision,
  updateChannelConfig,
} from "./api";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { fieldLabelClass, ModalActions, ModalShell } from "./components/ui/modal-shell";
import { Toaster, toast } from "./components/ui/sonner";
import { MiniOrb } from "./components/ui/processing-aura";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./lib/queryClient";
import { useQuery } from "@tanstack/react-query";
import { qk } from "./lib/queryKeys";
import { ApiError } from "./lib/apiError";
import { STORAGE_KEYS, storageGet } from "./lib/storage";
import { useReconcileMonitor } from "./hooks/useReconcileMonitor";
import {
  invalidateAfterReconcile,
  invalidateAfterScan,
  invalidateAfterTriageDecision,
} from "./lib/mutations";
import { NavigationProvider, useNavigation, type ViewKind } from "./contexts/NavigationContext";
import { ALL_PROJECTS, ProjectProvider, useProject } from "./contexts/ProjectContext";
import { SettingsProvider, useSettings } from "./contexts/SettingsContext";
import { formatDecisionAction, formatDecisionPhase, ProcessingProvider, useProcessing } from "./contexts/ProcessingContext";
import { useQuickSearch } from "./hooks/useQuickSearch";
import { CommandPalette } from "./layouts/CommandPalette";
import { Sidebar } from "./layouts/Sidebar";
import { Topbar } from "./layouts/Topbar";
import { ClassificadorView } from "./views/ClassificadorView";
import { ConfigView } from "./views/ConfigView";
import { PainelView } from "./views/PainelView";
import { AssistantSettingsModal } from "./features/settings/AssistantSettingsModal";
import { CreateTaxonomyEntryModal } from "./features/templates/CreateTaxonomyEntryModal";
import { CorrectDecisionModal } from "./features/triage/CorrectDecisionModal";
import { TemplateSelectModal } from "./features/templates/TemplateSelectModal";
import { AssistenteView } from "./views/AssistenteView";
import { GlobalDropPortal } from "./features/ingest/GlobalDropPortal";
import { RootRecoveryModal } from "./features/recovery/RootRecoveryModal";
import { AuthGate } from "./features/onboarding/AuthGate";
import { OnboardingWizard } from "./features/onboarding/OnboardingWizard";
import type {
  ProjectArea,
  ProjectDocumentType,
  ReconcileStatus,
  StatsResponse,
  StatusSeverity,
  TriageItem,
} from "./types";

const ONBOARDING_DONE_KEY = STORAGE_KEYS.onboardingDone;
const TG_TOKEN_STORAGE_KEY = STORAGE_KEYS.telegramBotToken;
const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/;

function AppShell() {
  const { t } = useTranslation();
  const { view, setView, requestSearch } = useNavigation();
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
    moonshotApiKey,
    setMoonshotApiKey,
    reloadModels,
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

  const processing = useProcessing();
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  // Keep-alive de telas: monta na primeira visita e NUNCA desmonta (esconde
  // com CSS) — todo estado de tela (chat, abas, colapsáveis, rascunhos,
  // monitores ao vivo) sobrevive à navegação. Padrão tab-navigator/Activity.
  const [visitedViews, setVisitedViews] = useState<Set<ViewKind>>(() => new Set([view]));
  useEffect(() => {
    setVisitedViews((prev) => (prev.has(view) ? prev : new Set(prev).add(view)));
  }, [view]);
  const [status, setStatus] = useState<{ text: string; severity: StatusSeverity }>(() => ({
    text: t("painel:app.statusReady"),
    severity: "info",
  }));
  // Canal de status estrutural: cada emissor declara a severidade (default
  // "info") — zero sniffing de texto, funciona igual em qualquer idioma.
  const handleStatus = useCallback((msg: string, severity: StatusSeverity = "info") => {
    setStatus({ text: msg, severity });
  }, []);

  // O footer .status morreu: mensagens de status viram um toast único que se
  // atualiza in-place (id fixo) — progresso contínuo não vira spam de toasts.
  useEffect(() => {
    if (!status.text || status.text === t("painel:app.statusReady")) return;
    toast[status.severity === "error" ? "error" : "message"](status.text, { id: "app-status" });
  }, [status]);


  const [initializingProjectId] = useState<string | null>(null);

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
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [appEnv, setAppEnv] = useState("production");

  const quickSearch = useQuickSearch();

  useEffect(() => {
    setUnauthorizedHandler((httpStatus, detail) => {
      if (httpStatus === 401) {
        // Sem key válida: o gate de autenticação assume a tela inteira —
        // capturar a key é a PRIMEIRA coisa, antes de onboarding ou dados.
        setAuthRequired(true);
        return;
      }
      handleStatus(t("painel:app.accessDenied", { detail: detail || t("painel:app.accessDeniedDefault") }), "error");
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  // Health: query com poll adaptativo (30s ok / 5s em falha) e debounce de 2
  // falhas seguidas — 1 blip transitório não pode tremer o orb em "error"
  const healthQuery = useQuery({
    queryKey: qk.health(),
    queryFn: async () => {
      try {
        return (await fetchHealth()).ok;
      } catch {
        return false;
      }
    },
    refetchInterval: (query) => (query.state.data === false ? 5000 : 30000),
    refetchIntervalInBackground: false,
    retry: false,
  });
  const setupStatusQuery = useQuery({
    queryKey: qk.setupStatus(),
    queryFn: fetchSetupStatus,
    refetchInterval: 20_000,
    refetchIntervalInBackground: false,
    retry: false,
  });
  // Raiz esvaziada (mount fantasma) OU inacessível (mount quebrado): a deleção
  // da pasta host manifesta dos dois jeitos no VirtioFS — a cura é a mesma
  // (restart re-vincula o mount e o Docker recria a pasta)
  const rootState = setupStatusQuery.data?.projects_root_state;
  const projectsRootBroken = rootState === "emptied" || rootState === "unavailable";

  const healthFailuresRef = useRef(0);
  useEffect(() => {
    if (healthQuery.data === undefined) return;
    if (healthQuery.data) {
      healthFailuresRef.current = 0;
      setHealthOk(true);
    } else {
      healthFailuresRef.current += 1;
      if (healthFailuresRef.current >= 2) setHealthOk(false);
    }
  }, [healthQuery.data, healthQuery.dataUpdatedAt]);

  // Auto-connect Telegram do localStorage no boot (one-shot); status via query 15s
  useEffect(() => {
    async function autoConnect() {
      const savedToken = storageGet(TG_TOKEN_STORAGE_KEY) || "";
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
    }
    void autoConnect();
  }, []);
  const channelStatusQuery = useQuery({
    queryKey: qk.channelStatus(),
    queryFn: fetchChannelStatus,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    retry: false,
  });
  const telegramConnected =
    channelStatusQuery.data?.channels.some((c) => c.channel_id === "telegram" && c.connected) ?? false;

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
        void queryClient.invalidateQueries({ queryKey: qk.channelStatus() });
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
        void queryClient.invalidateQueries({ queryKey: qk.channelStatus() });
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

  // Fila de triagem e stats do painel: caches — mutações invalidam, aqui só lê
  const projectIds = projects.map((p) => p.project_id);
  const triageQuery = useQuery({
    queryKey: [...qk.triage.list(selectedProject || "none"), projectIds],
    queryFn: async () => {
      if (selectedProject === ALL_PROJECTS) {
        const batches = await Promise.all(projectIds.map((id) => fetchTriage(id)));
        return batches.flat();
      }
      return fetchTriage(selectedProject);
    },
    enabled: !!selectedProject && (selectedProject !== ALL_PROJECTS || projectIds.length > 0),
  });
  const triageItems: TriageItem[] = triageQuery.data ?? [];
  const statsQuery = useQuery({ queryKey: qk.stats(), queryFn: () => fetchStats() });
  const dashboardStats: StatsResponse | null = statsQuery.data ?? null;

  // Reconciliação: ponte SSE→Query única (boot retoma sozinho se estiver rodando)
  const reconcile = useReconcileMonitor({ onStatus: handleStatus });
  const reconcileStatus = reconcile.reconcileStatus;
  const reconcilingNow = reconcile.reconciling;

  // Boot: projects/stats/reconcile são queries — nada a orquestrar aqui; o
  // canal de reconcile retoma sozinho se houver operação em andamento.


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
    handleStatus(t("painel:app.projectInitialized"));
  }

  async function handleReconcileNow() {
    const scopeLabel = selectedProject === ALL_PROJECTS ? t("painel:app.allProjectsScope") : selectedProjectLabel || selectedProject;
    try {
      await reconcile.start(selectedProject === ALL_PROJECTS ? undefined : selectedProject, scopeLabel);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("painel:app.reconcileFailed");
      if (err instanceof ApiError && err.code === "RECONCILE_IN_PROGRESS") {
        handleStatus(t("painel:app.reconcileAlreadyRunning"));
        void reconcile.start; // canal já acompanha via snapshot ativo
      } else {
        handleStatus(msg, "error");
      }
    }
  }

  async function openCorrectModal(item: TriageItem) {
    handleStatus(t("painel:app.loadingCatalog", { project: projectLabelById.get(item.project_id) || item.project_id }));
    try {
      const resp = await fetchProjectProfile(item.project_id);
      const classification = resp.profile.classification || {};
      const domainRows: Array<{ key: string; label?: string | null }> = classification.business_domains || [];
      const areas = domainRows.map((area) => ({
        key: area.key,
        label: area.label || area.key,
      }));
      if (!areas.length) {
        handleStatus(t("painel:app.noDomainsForCorrection"), "error");
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
        handleStatus(t("painel:app.noTypesForCorrection"), "error");
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
      handleStatus(t("painel:app.selectDomainAndType"));
    } catch {
      handleStatus(t("painel:app.loadCatalogFailed"), "error");
    }
  }

  function submitCorrectDecision() {
    if (!correctModalItem || !correctBusinessDomainValue || !correctDocumentTypeValue) return;
    const item = correctModalItem;
    const businessDomainValue = correctBusinessDomainValue;
    const documentTypeValue = correctDocumentTypeValue;
    setCorrectModalItem(null);
    setCorrectSubmitting(false);
    // O card permanece na fila durante o processamento — é o palco da aura
    // focal (Processamento Focal); o bus o remove quando a decisão conclui
    processing.start({ docId: item.doc_id, projectId: item.project_id, filename: item.filename, action: "correct" });
    triageDecision(item.project_id, item.doc_id, "correct", businessDomainValue, documentTypeValue)
      .then(() => {
        invalidateAfterTriageDecision();
        void notifyNewAliasSuggestions(item.project_id);
        handleStatus(t("painel:app.correctedAndMoved", { businessDomain: businessDomainValue, documentType: documentTypeValue }));
      })
      .catch(() => {
        handleStatus(t("painel:app.correctionFailed"), "error");
        invalidateAfterTriageDecision();
      })
      .finally(() => processing.finish());
  }

  /** Pós-scan (portal ou botão): invalidations finas — os caches certos
   *  refetcham e todos os consumidores (cards, contexts) atualizam sozinhos. */
  const handleDataChanged = useCallback(() => {
    invalidateAfterScan();
  }, []);

  /** Toast quando a decisão de triagem faz surgirem termos NOVOS no minerador
   *  de aliases — o aprendizado nunca acontece em silêncio. O conjunto já
   *  notificado fica em memória por projeto (sem repetir a cada decisão). */
  const notifiedAliasTermsRef = useRef<Map<string, Set<string>>>(new Map());
  const notifyNewAliasSuggestions = useCallback(async (projectId: string) => {
    try {
      const data = await fetchAliasSuggestions(projectId);
      const seen = notifiedAliasTermsRef.current.get(projectId) ?? new Set<string>();
      const fresh = data.suggestions
        .flatMap((g) => g.terms.map((term) => `${g.kind}:${g.key}:${term.term}`))
        .filter((token) => !seen.has(token));
      if (fresh.length > 0) {
        fresh.forEach((token) => seen.add(token));
        notifiedAliasTermsRef.current.set(projectId, seen);
        toast.success(t("ingest:aliasSuggest.toastNew", { count: fresh.length }));
      }
    } catch {
      // análise informativa — falha aqui nunca interfere na decisão de triagem
    }
  }, [t]);

  async function handleDecision(item: TriageItem, action: "approve" | "correct" | "reject") {
    if (action === "correct") {
      await openCorrectModal(item);
      return;
    }
    processing.start({ docId: item.doc_id, projectId: item.project_id, filename: item.filename, action });
    try {
      await triageDecision(item.project_id, item.doc_id, action);
      invalidateAfterTriageDecision();
      if (action === "reject") {
        handleStatus(t("painel:app.rejectedAndMoved"));
      } else {
        // aprovação também alimenta o corpus do minerador (contraste)
        void notifyNewAliasSuggestions(item.project_id);
        handleStatus(t("painel:app.decisionRecorded", { action }));
      }
    } catch {
      handleStatus(t("painel:app.decisionFailed"), "error");
    } finally {
      processing.finish();
    }
  }

  function handleOnboardingComplete(createdProjectId?: string) {
    localStorage.setItem(ONBOARDING_DONE_KEY, "true");
    setShowOnboarding(false);
    refreshProjects().then(() => {
      if (createdProjectId) setSelectedProject(createdProjectId);
    });
    // O backend dispara um refresh do catálogo LLM no primeiro boot; ao cair no
    // app, recarrega a lista para o seletor já refletir o catálogo completo.
    void reloadModels();
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
        onOpenSearch={() => quickSearch.setOpen(true)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar>
          {appEnv === "dev" && (
            <Button variant="secondary" size="sm" onClick={handleReplayOnboarding} title={t("painel:app.replayOnboardingTitle")}>
              <RefreshCw /> {t("painel:app.onboarding")}
            </Button>
          )}
        </Topbar>

        <RootRecoveryModal
          open={projectsRootBroken}
          hostRoot={setupStatusQuery.data?.projects_host_root}
          onRevalidate={() => void setupStatusQuery.refetch()}
        />


        <main className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col gap-6 overflow-y-auto overflow-x-hidden px-7 pb-8 pt-6 [-webkit-overflow-scrolling:touch]">
        <div className={view === "painel" ? "contents" : "hidden"}>
          {visitedViews.has("painel") && (
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
            onStatus={handleStatus}
            onScanComplete={handleDataChanged}
          />
          )}
        </div>

        <div className={view === "assistente" ? "contents" : "hidden"}>
          {visitedViews.has("assistente") && (
          <AssistenteView
            selectedProject={selectedProject}
            selectedModel={selectedModel}
            models={models}
            onModelChange={setSelectedModel}
            onOpenSettings={() => setSettingsOpen(true)}
            showThinking={showThinking}
            onShowThinkingChange={setShowThinking}
            telegramConnected={telegramConnected}
            onToggleTelegram={handleToggleTelegram}
          />
          )}
        </div>

        <div className={view === "classificador" ? "contents" : "hidden"}>
          {visitedViews.has("classificador") && (
          <ClassificadorView
            selectedProject={selectedProject}
            selectedProjectLabel={selectedProjectLabel}
            triageItems={triageItems}
            onStatus={handleStatus}
            openaiApiKey={openaiApiKey}
            anthropicApiKey={anthropicApiKey}
            onOpenSettings={() => setSettingsOpen(true)}
            selectedModelTriage={selectedModelTriage}
            onChangeModelTriage={setSelectedModelTriage}
          />
          )}
        </div>

        <div className={view === "config" ? "contents" : "hidden"}>
          {visitedViews.has("config") && (
          <ConfigView selectedProject={selectedProject} onStatus={handleStatus} />
          )}
        </div>

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

      {processing.active && view !== "painel" && (
        <button
          type="button"
          onClick={() => setView("painel")}
          title={t("painel:app.backToPainel")}
          className="fixed bottom-5 right-5 z-50 flex items-center gap-2.5 rounded-full border border-border bg-panel py-2 pl-3 pr-4 font-mono text-[0.75rem] text-foreground shadow-[0_8px_24px_rgba(0,0,0,0.45)] transition-transform hover:scale-[1.03]"
        >
          <MiniOrb />
          <span className="max-w-56 truncate">
            {formatDecisionAction(processing.active.action)} {processing.active.filename}
          </span>
          <span className="atlas-thinking-text">{formatDecisionPhase(processing.phase)}…</span>
        </button>
      )}

      <GlobalDropPortal onScanComplete={handleDataChanged} />

      <CommandPalette
        open={quickSearch.open}
        onOpenChange={quickSearch.setOpen}
        query={quickSearch.query}
        onQueryChange={quickSearch.setQuery}
        hits={quickSearch.hits}
        loading={quickSearch.loading}
        onSubmitSearch={(q) => {
          // Handoff benchmark: navegação com intent — o Painel semeia e busca
          requestSearch(q);
          quickSearch.setOpen(false);
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
        moonshotApiKey={moonshotApiKey}
        onChangeModel={setSelectedModel}
        onChangeModelTriage={setSelectedModelTriage}
        onChangeOpenAiKey={setOpenaiApiKey}
        onChangeAnthropicKey={setAnthropicApiKey}
        onChangeMoonshotKey={setMoonshotApiKey}
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
            .catch(() => handleStatus(t("painel:app.reloadCatalogFailed"), "error"));
        }}
      />

      {newProjectModalOpen && (
        <ModalShell label={t("painel:app.newProjectTitle")} title={t("painel:app.newProjectTitle")} size="sm">
          <label className={fieldLabelClass} htmlFor="new-project-name">{t("painel:app.projectNameLabel")}</label>
          <Input
            id="new-project-name"
            type="text"
            className="font-mono"
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
            placeholder={t("painel:app.projectNamePlaceholder")}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") handleNewProjectConfirm();
            }}
          />
          <p className="mt-1.5 text-[0.72rem] text-tertiary">{t("painel:app.projectNameHint")}</p>
          {newProjectName && !SLUG_RE.test(newProjectName) && (
            <p className="mt-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-1.5 text-[0.8rem] text-destructive">
              {t("painel:app.invalidName")}
            </p>
          )}
          <ModalActions>
            <Button variant="secondary" onClick={() => setNewProjectModalOpen(false)}>
              {t("common:action.cancel")}
            </Button>
            <Button disabled={!newProjectName || !SLUG_RE.test(newProjectName)} onClick={handleNewProjectConfirm}>
              {t("painel:app.continue")}
            </Button>
          </ModalActions>
        </ModalShell>
      )}
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SettingsProvider>
        <ProjectProvider>
          <NavigationProvider>
            <ProcessingProvider>
              <AppShell />
              <Toaster />
            </ProcessingProvider>
          </NavigationProvider>
        </ProjectProvider>
      </SettingsProvider>
    </QueryClientProvider>
  );
}

export default App;
