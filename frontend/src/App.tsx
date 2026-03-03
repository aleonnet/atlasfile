import { File, FileSpreadsheet, FileText, Monitor, Moon, Presentation, RefreshCw, Search, Sun } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchHealth,
  fetchProjectAreas,
  fetchProjects,
  fetchReconcileStatus,
  fetchTriage,
  getFileDownloadUrl,
  getReconcileStatusStreamUrl,
  initializeProject,
  runReconcile,
  searchDocuments,
  triageDecision,
  triggerScan
} from "./api";
import type { Project, ProjectArea, ReconcileStatus, SearchEvidence, SearchHit, TriageItem } from "./types";

const ALL_PROJECTS = "__all__";
const THEME_STORAGE_KEY = "atlasfile-theme";
type ThemeMode = "system" | "light" | "dark";
type InputLikeEvent = { target: { value: string } };
type KeyboardLikeEvent = { key: string };

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
  const [triageItems, setTriageItems] = useState<TriageItem[]>([]);
  const [reconcileStatus, setReconcileStatus] = useState<ReconcileStatus | null>(null);
  const [status, setStatus] = useState("Pronto");
  const [loading, setLoading] = useState(false);
  const [initializingProjectId, setInitializingProjectId] = useState<string | null>(null);
  const [reconcilingNow, setReconcilingNow] = useState(false);
  const [correctModalItem, setCorrectModalItem] = useState<TriageItem | null>(null);
  const [correctAreaOptions, setCorrectAreaOptions] = useState<ProjectArea[]>([]);
  const [correctAreaValue, setCorrectAreaValue] = useState("");
  const [correctSubmitting, setCorrectSubmitting] = useState(false);
  const reconcileEsRef = useRef<EventSource | null>(null);

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

  async function refreshProjects() {
    const data = await fetchProjects();
    setProjects(data);
    if (selectedProject !== ALL_PROJECTS && !data.some((p) => p.project_id === selectedProject)) {
      setSelectedProject(ALL_PROJECTS);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [projectList, currentReconcile] = await Promise.all([fetchProjects(), fetchReconcileStatus()]);
      if (cancelled) return;
      setProjects(projectList);
      setReconcileStatus(currentReconcile);

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
        const skipMsg = Number(latest.summary?.skipped_docs) > 0 ? `, ${latest.summary.skipped_docs} skip (inalterados)` : "";
        const failMsg = Number(latest.summary?.failed_docs) > 0 ? `, ${latest.summary.failed_docs} falha(s)` : "";
        setStatus(
          `Reconciliacao concluida: ${latest.summary?.adjustments_applied ?? 0} ajuste(s), ${latest.summary?.indexed_docs ?? 0} doc(s) indexado(s)${skipMsg}${failMsg}`
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
    })().catch(() => setStatus("Falha ao carregar projetos"));
    return () => {
      cancelled = true;
      reconcileEsRef.current?.close();
      reconcileEsRef.current = null;
    };
  }, []);

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
    setFullPage(1);
    setFullTotalPages(1);
    setFullTotal(0);
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

  function formatLocationLabel(loc: string): string {
    const normalized = (loc || "").trim().toLowerCase();
    const docxMatch = normalized.match(/^docx_page(_est)?:([0-9]+):paragraph:([0-9]+)(?::part:([0-9]+))?$/);
    if (docxMatch) {
      const estimated = docxMatch[1] === "_est";
      const page = docxMatch[2];
      const paragraph = docxMatch[3];
      const part = docxMatch[4] ? ` (parte ${docxMatch[4]})` : "";
      if (estimated) return `Pagina ~${page} / ${paragraph}o paragrafo${part} (estimada)`;
      return `Pagina ${page} / ${paragraph}o paragrafo${part}`;
    }
    if (normalized.startsWith("sheet ")) {
      const m = normalized.match(/^sheet\s+(.+?)\s+row\s+(\d+)\s+col\s+([a-z]+)(?:\s+part\s+(\d+))?$/i);
      if (m) {
        const sheetName = m[1].charAt(0).toUpperCase() + m[1].slice(1);
        const part = m[4] ? ` (parte ${m[4]})` : "";
        return `${sheetName}, linha ${m[2]}, Coluna ${m[3].toUpperCase()}${part}`;
      }
      return normalized.replace(/^sheet\s+/i, "Planilha ");
    }
    if (normalized.startsWith("slide ")) return normalized.replace(/^slide\s+/i, "Slide ");
    if (normalized.startsWith("page ")) return normalized.replace(/^page\s+/i, "Pagina ");
    if (normalized.startsWith("section ")) return normalized.replace(/^section\s+/i, "Secao ");
    if (normalized === "content_chunk") return "Trecho de conteudo";
    if (normalized === "content") return "Conteudo";
    if (normalized === "title") return "Titulo";
    if (normalized === "original_filename") return "Nome original";
    if (normalized === "canonical_filename") return "Nome canonico";
    return loc;
  }

  function pageKeyFromLocation(loc: string): string | null {
    const m = (loc || "").trim().toLowerCase().match(/^page:(\d+)(?::\d+)?$/);
    if (!m) return null;
    return `page:${m[1]}`;
  }

  function countSnippetMatches(snippet: string): number {
    const matches = (snippet || "").match(/<em>/gi);
    return matches?.length ?? 0;
  }

  function evidenceMatchCount(ev: SearchEvidence): number {
    return Math.max(1, Number(ev.match_count) || countSnippetMatches(ev.snippet));
  }

  function buildPageOccurrenceCounts(evidences: SearchEvidence[]): Map<string, number> {
    const counts = new Map<string, number>();
    for (const ev of evidences || []) {
      const key = pageKeyFromLocation(ev.location);
      if (!key) continue;
      const inc = evidenceMatchCount(ev);
      counts.set(key, (counts.get(key) ?? 0) + inc);
    }
    return counts;
  }

  function formatEvidenceLocation(loc: string, pageCounts: Map<string, number>): string {
    const key = pageKeyFromLocation(loc);
    if (key) {
      const total = pageCounts.get(key) ?? 0;
      if (total > 0) return `${key} (${total} ocorrência${total === 1 ? "" : "s"})`;
      return key;
    }
    return formatLocationLabel(loc);
  }

  type EvidenceGroup = {
    key: string;
    label: string;
    count: number;
    snippets: string[];
  };

  function buildEvidenceGroups(evidences: SearchEvidence[]): EvidenceGroup[] {
    const pageCounts = buildPageOccurrenceCounts(evidences);
    const groups = new Map<string, EvidenceGroup>();
    for (const ev of evidences || []) {
      const pageKey = pageKeyFromLocation(ev.location);
      const key = pageKey ?? ev.location;
      const label = formatEvidenceLocation(ev.location, pageCounts);
      const groupCount = pageKey ? pageCounts.get(pageKey) ?? evidenceMatchCount(ev) : evidenceMatchCount(ev);
      const existing = groups.get(key);
      if (!existing) {
        groups.set(key, { key, label, count: groupCount, snippets: [ev.snippet] });
        continue;
      }
      if (!existing.snippets.includes(ev.snippet) && existing.snippets.length < 2) {
        existing.snippets.push(ev.snippet);
      }
    }
    return Array.from(groups.values());
  }

  function topLocations(locations: string[], max = 3): string[] {
    if (!locations?.length) return [];
    return locations.slice(0, max).map(formatLocationLabel);
  }

  function formatTimestamp(value: string | null | undefined): string {
    if (!value) return "-";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString("pt-BR");
  }

  async function handleSelectProject(nextProject: string) {
    setSelectedProject(nextProject);
    if (nextProject === ALL_PROJECTS) return;

    const target = projects.find((project) => project.project_id === nextProject);
    if (!target || target.initialized) return;

    setInitializingProjectId(nextProject);
    setStatus(`Inicializando projeto ${target.project_label} sem alterar conteudo existente...`);
    try {
      await initializeProject(nextProject);
      await refreshProjects();
      setStatus(`Projeto ${target.project_label} inicializado com seguranca`);
    } catch {
      setStatus(`Falha ao inicializar projeto ${target.project_label}`);
    } finally {
      setInitializingProjectId(null);
    }
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
      const skipMsg = Number(latest.summary?.skipped_docs) > 0 ? `, ${latest.summary.skipped_docs} skip (inalterados)` : "";
        const failMsg = Number(latest.summary?.failed_docs) > 0 ? `, ${latest.summary.failed_docs} falha(s)` : "";
        setStatus(
          `Reconciliacao concluida (${scopeLabel}): ${latest.summary?.adjustments_applied ?? 0} ajuste(s), ${latest.summary?.indexed_docs ?? 0} doc(s) indexado(s)${skipMsg}${failMsg}`
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

  async function handleScan() {
    if (!selectedProject) return;
    setLoading(true);
    setStatus("Processando inbox...");
    try {
      if (selectedProject === ALL_PROJECTS) {
        for (const project of projects) {
          await triggerScan(project.project_id);
        }
      } else {
        await triggerScan(selectedProject);
      }
      await loadTriage();
      setStatus("Inbox processado");
    } catch {
      setStatus("Falha ao processar inbox");
    } finally {
      setLoading(false);
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

  async function runFullSearch(page = 1) {
    const q = query.trim();
    if (q.length < 2) return;
    setFullLoading(true);
    try {
      const data = await searchDocuments(q, selectedProject === ALL_PROJECTS ? undefined : selectedProject, page, 20);
      setFullQuery(q);
      setFullResults(data.hits);
      setFullPage(data.page);
      setFullTotal(data.total);
      setFullTotalPages(data.total_pages);
      setStatus(`${data.total} resultado(s)`);
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
    setStatus(`Carregando areas de ${projectLabelById.get(item.project_id) || item.project_id}...`);
    try {
      const areas = await fetchProjectAreas(item.project_id);
      if (!areas.length) {
        setStatus("Projeto sem areas configuradas para correcao");
        return;
      }
      setCorrectAreaOptions(areas);
      const preferred = item.suggested_area && areas.some((area) => area.key === item.suggested_area) ? item.suggested_area : "";
      setCorrectAreaValue(preferred || areas[0].key);
      setCorrectModalItem(item);
      setStatus("Selecione a area de destino para aprovar com correcao");
    } catch {
      setStatus("Falha ao carregar areas para correcao");
    }
  }

  function submitCorrectDecision() {
    if (!correctModalItem || !correctAreaValue) return;
    const item = correctModalItem;
    const areaValue = correctAreaValue;
    setCorrectModalItem(null);
    setCorrectSubmitting(false);
    setTriageItems((prev) => prev.filter((i) => i.doc_id !== item.doc_id));
    setStatus("Registrando correcao em segundo plano...");
    triageDecision(item.project_id, item.doc_id, "correct", areaValue)
      .then(() => loadTriage())
      .then(() => {
        setStatus(`Documento aprovado por correcao e movido para ${areaValue}`);
      })
      .catch(() => {
        setStatus("Falha ao registrar correcao");
        void loadTriage();
      });
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

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-left">
          <div className="brand">
            <span className="brand-dot" />
            <h1>AtlasFile</h1>
          </div>
          <select className="project-select" value={selectedProject} onChange={(e: InputLikeEvent) => void handleSelectProject(e.target.value)}>
            <option value={ALL_PROJECTS}>Geral (todos os projetos)</option>
            {projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.project_label}
                {project.initialized ? "" : " (nao inicializado)"}
              </option>
            ))}
          </select>
        </div>
        <div className="topbar-center">
          <div className="header-search-card">
            <button className="header-search-btn" onClick={() => setSearchModalOpen(true)} title="Abrir busca (Cmd/Ctrl + K)">
              <Search size={16} />
              <span className="header-search-text">Search...</span>
              <span className="kbd">⌘K</span>
            </button>
          </div>
        </div>
        <div className="topbar-status">
          <button className="topbar-search-icon" onClick={() => setSearchModalOpen(true)} title="Buscar" aria-label="Buscar">
            <Search size={18} />
          </button>
          <div className="pill health-pill" title={healthOk === true ? "API OK" : healthOk === false ? "API offline" : "A verificar..."}>
            <span className={`status-dot ${healthOk === true ? "ok" : ""}`} />
            <span>{healthOk === true ? "Health OK" : healthOk === false ? "Health Offline" : "Health …"}</span>
          </div>
          <div className="theme-toggle" role="group" aria-label="Tema">
            <button
              type="button"
              className={`theme-toggle__button ${theme === "system" ? "active" : ""}`}
              onClick={() => setTheme("system")}
              aria-pressed={theme === "system"}
              aria-label="Tema sistema"
              title="Sistema"
            >
              <Monitor size={18} />
            </button>
            <button
              type="button"
              className={`theme-toggle__button ${theme === "light" ? "active" : ""}`}
              onClick={() => setTheme("light")}
              aria-pressed={theme === "light"}
              aria-label="Tema claro"
              title="Claro"
            >
              <Sun size={18} />
            </button>
            <button
              type="button"
              className={`theme-toggle__button ${theme === "dark" ? "active" : ""}`}
              onClick={() => setTheme("dark")}
              aria-pressed={theme === "dark"}
              aria-label="Tema escuro"
              title="Escuro"
            >
              <Moon size={18} />
            </button>
          </div>
        </div>
      </header>

      <main className="content">
      <section className="panel panel-control card">
        <div className="panel-head card-header">
          <h2>Controle operacional</h2>
          <button className="btn primary" disabled={reconcilingNow} onClick={handleReconcileNow}>
            <RefreshCw size={14} className={reconcilingNow ? "spin" : ""} />
            {reconcilingNow ? "Reconciliando INDEX" : "Reconciliar INDEX"}
          </button>
        </div>
        {reconcileStatus?.running ? (
          <div className="reconcile-progress">
            <div className="progress-bar-wrap">
              <div
                className="progress-bar-fill"
                style={{
                  width: `${
                    (reconcileStatus.progress_total ?? 0) > 0
                      ? Math.min(
                          100,
                          (100 *
                            (Math.max(0, (reconcileStatus.progress_current ?? 1) - 1) +
                              (reconcileStatus.progress_file_pct ?? 0) / 100)) /
                            reconcileStatus.progress_total!
                        )
                      : 0
                  }%`,
                }}
              />
            </div>
            <p className="progress-stats">
              {reconcileStatus.progress_current ?? 0} / {reconcileStatus.progress_total ?? 0} docs
              {(reconcileStatus.progress_skipped ?? 0) > 0 && (
                <span className="progress-skip"> (skip: {reconcileStatus.progress_skipped})</span>
              )}
            </p>
            <p className="progress-file">
              Projeto: <strong>{reconcileStatus.progress_project ?? "—"}</strong>
            </p>
            <p className="progress-file sub">
              Arquivo: <span title={reconcileStatus.progress_file ?? ""}>{reconcileStatus.progress_file ? (reconcileStatus.progress_file.length > 60 ? reconcileStatus.progress_file.slice(0, 57) + "..." : reconcileStatus.progress_file) : "—"}</span>
            </p>
          </div>
        ) : (
          <div className="kpi-grid">
            <div className="kpi">
              <span>Ultima reconciliacao</span>
              <strong>{formatTimestamp(reconcileStatus?.last_run_finished_at)}</strong>
            </div>
            <div className="kpi">
              <span>Ajustes aplicados</span>
              <strong>{reconcileStatus?.summary.adjustments_applied ?? 0}</strong>
            </div>
            <div className="kpi">
              <span>Linhas reescritas</span>
              <strong>{reconcileStatus?.summary.rows_written ?? 0}</strong>
            </div>
            <div className="kpi">
              <span>Documentos reindexados</span>
              <strong>{reconcileStatus?.summary.indexed_docs ?? 0}</strong>
            </div>
            {typeof reconcileStatus?.summary.skipped_docs === "number" && (
              <div className="kpi">
                <span>Skip (inalterados)</span>
                <strong>{reconcileStatus.summary.skipped_docs}</strong>
              </div>
            )}
            {typeof reconcileStatus?.summary.failed_docs === "number" && reconcileStatus.summary.failed_docs > 0 && (
              <div className="kpi">
                <span>Falhas (indexacao)</span>
                <strong>{reconcileStatus.summary.failed_docs}</strong>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="panel card">
        <div className="panel-head card-header">
          <h2>Ingestao e triagem</h2>
          <button className="btn primary" disabled={loading || !selectedProject || initializingProjectId === selectedProject} onClick={handleScan}>
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            {loading ? "Processando..." : "Processar INBOX"}
          </button>
        </div>
        <div className="card-intro">
          <p>Projeto selecionado: {selectedProjectLabel || "-"}</p>
          <p>Itens pendentes: {triageItems.length}</p>
        </div>
        <ul className="list">
          {triageItems.map((item) => (
            <li key={item.doc_id} className="list-item">
              <strong className="list-title">{item.filename}</strong>
              <div className="sub list-meta">
                projeto: {projectLabelById.get(item.project_id) || item.project_id} | sugestao:{" "}
                {item.suggested_area || "sem sugestao"} | confianca: {item.confidence_score.toFixed(2)}
              </div>
              <div className="row">
                <button className="btn" disabled={!item.suggested_area} title={!item.suggested_area ? "Sem sugestao de area" : ""} onClick={() => handleDecision(item, "approve")}>
                  Aprovar
                </button>
                <button className="btn" onClick={() => handleDecision(item, "correct")}>Corrigir</button>
                <button className="btn danger" onClick={() => handleDecision(item, "reject")}>
                  Rejeitar
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {fullQuery && (
        <section className="panel card">
          <div className="panel-head panel-head-with-actions">
            <h2>
              <Search size={16} /> Resultados completos
            </h2>
            <div className="panel-head-right">
              <span className="sub">
                consulta: "{fullQuery}" | {fullTotal} resultado(s)
              </span>
              <button type="button" className="btn search-clear-btn" onClick={clearSearch} title="Limpar busca">
                Limpar busca
              </button>
            </div>
          </div>
          <ul className="list search-list">
            {fullResults.map((hit) => (
              <li key={`full-${hit.doc_id}`} className="list-item search-item">
                <div className="search-item-content">
                  <div className="sub breadcrumb-line">{renderBreadcrumb(hit.project_id, hit.path)}</div>
                  <div className="title-row">
                    <span className="doc-icon-inline">{getDocIcon(hit.content_type, hit.original_filename)}</span>
                    <a className="result-link result-title" href={getFileDownloadUrl(hit.path)} target="_blank" rel="noreferrer">
                      {highlightTerm(hit.original_filename, fullQuery)}
                    </a>
                  </div>
                  {hit.evidences && hit.evidences.length > 0 ? (
                    <>
                      {buildEvidenceGroups(hit.evidences ?? []).map((group, i: number) => (
                        <div key={`evg-${hit.doc_id}-${group.key}-${i}`} className="evidence">
                          <span className="evidence-location sub">{group.label}</span>
                          {group.snippets.map((snippet, j) => (
                            <div
                              key={`evg-${hit.doc_id}-${group.key}-${j}`}
                              className="snippet"
                              dangerouslySetInnerHTML={{ __html: snippet }}
                            />
                          ))}
                        </div>
                      ))}
                      {Number(hit.omitted_evidences) > 0 && (
                        <div className="sub">+ {hit.omitted_evidences} outro(s) trecho(s)</div>
                      )}
                    </>
                  ) : (
                    <>
                      {extractSnippets(hit.highlights).map((snippet, idx) => (
                        <div key={`full-${hit.doc_id}-snippet-${idx}`} className="snippet" dangerouslySetInnerHTML={{ __html: snippet }} />
                      ))}
                      {topLocations(hit.match_locations).length > 0 && (
                        <div className="sub">Local: {topLocations(hit.match_locations).join(" | ")}</div>
                      )}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <div className="search-modal-footer">
            <span className="sub">
              pagina {fullPage}/{fullTotalPages}
            </span>
            <div className="row">
              <button className="btn" disabled={fullLoading || fullPage <= 1} onClick={() => void runFullSearch(fullPage - 1)}>
                Anterior
              </button>
              <button className="btn" disabled={fullLoading || fullPage >= fullTotalPages} onClick={() => void runFullSearch(fullPage + 1)}>
                Proxima
              </button>
            </div>
          </div>
        </section>
      )}

      <footer className="status">{status}</footer>
      </main>

      {searchModalOpen && (
        <div className="search-modal-overlay" role="dialog" aria-modal="true" aria-label="Busca global">
          <div className="search-modal">
            <div className="search-modal-input-wrap">
              <Search size={18} className="search-modal-input-icon" />
              <input
                value={query}
                onChange={(e: InputLikeEvent) => setQuery(e.target.value)}
                onKeyDown={(e: KeyboardLikeEvent) => {
                  if (e.key === "Escape") {
                    if (query.trim()) clearSearch();
                    else setSearchModalOpen(false);
                  }
                  if (e.key === "Enter") {
                    void runFullSearch(1);
                    setSearchModalOpen(false);
                  }
                }}
                placeholder="Search..."
                autoFocus
              />
              {query.trim().length > 0 ? (
                <button type="button" className="search-modal-kbd esc-btn" onClick={clearSearch} title="Limpar (ESC)">
                  ESC
                </button>
              ) : (
                <span className="search-modal-kbd" aria-hidden>⌘K</span>
              )}
            </div>

            {query.trim().length > 0 && (
              <div className="search-results-scroll">
                <ul className="list search-list">
                  {modalHits.map((hit) => (
                    <li key={`top-${hit.doc_id}`} className="list-item search-item">
                      <div className="search-item-content">
                        <div className="sub breadcrumb-line">{renderBreadcrumb(hit.project_id, hit.path)}</div>
                        <div className="title-row">
                          <span className="doc-icon-inline">{getDocIcon(hit.content_type, hit.original_filename)}</span>
                          <a className="result-link result-title" href={getFileDownloadUrl(hit.path)} target="_blank" rel="noreferrer">
                            {highlightTerm(hit.original_filename, query)}
                          </a>
                        </div>
                        {hit.evidences && hit.evidences.length > 0 ? (
                          <div className="snippet" dangerouslySetInnerHTML={{ __html: hit.evidences[0].snippet }} />
                        ) : (
                          extractSnippets(hit.highlights).map((snippet, idx) => (
                            <div key={`top-${hit.doc_id}-snippet-${idx}`} className="snippet" dangerouslySetInnerHTML={{ __html: snippet }} />
                          ))
                        )}
                        {(() => {
                          const totalEv = hit.total_evidences ?? 0;
                          const groups = buildEvidenceGroups(hit.evidences ?? []);
                          const locs =
                            (hit.evidences?.length ?? 0) > 0
                              ? groups.slice(0, 2).map((g) => g.label)
                              : topLocations(hit.match_locations, 2);
                          const extra =
                            totalEv > 2 ? ` e outras ${totalEv - 2} ocorrência${totalEv - 2 === 1 ? "" : "s"}` : "";
                          return locs.length > 0 ? (
                            <div className="sub">
                              Local: {locs.join(" | ")}
                              {extra}
                            </div>
                          ) : null;
                        })()}
                      </div>
                    </li>
                  ))}
                </ul>
                {modalHits.length === 0 && query.trim().length >= 2 && !modalLoading && (
                  <p className="sub empty-search">Nenhum resultado para os termos digitados.</p>
                )}
              </div>
            )}

            {query.trim().length > 0 && (
              <div className="search-modal-footer">
                <span className="sub">
                  Top {modalHits.length} resultado(s) em tempo real. Pressione Enter para listar todos.
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {correctModalItem && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Aprovar com correcao">
          <div className="modal">
            <h3>Aprovar com correcao</h3>
            <p>
              Arquivo: <strong>{correctModalItem.filename}</strong>
            </p>
            <label htmlFor="area-select">Area destino</label>
            <select
              id="area-select"
              value={correctAreaValue}
              onChange={(e: InputLikeEvent) => setCorrectAreaValue(e.target.value)}
              disabled={correctSubmitting}
            >
              {correctAreaOptions.map((area) => (
                <option key={area.key} value={area.key}>
                  {area.label} ({area.key})
                </option>
              ))}
            </select>
            <div className="modal-actions">
              <button className="btn" disabled={correctSubmitting} onClick={() => setCorrectModalItem(null)}>
                Cancelar
              </button>
              <button className="btn primary" disabled={correctSubmitting || !correctAreaValue} onClick={submitCorrectDecision}>
                {correctSubmitting ? "Aprovando..." : "Aprovar e mover"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
