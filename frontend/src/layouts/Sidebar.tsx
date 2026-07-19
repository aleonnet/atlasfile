import { STORAGE_KEYS } from "../lib/storage";
import {
  Sparkles,
  Check,
  ChevronsUpDown,
  FolderCog,
  Layers,
  LayoutDashboard,
  MessageCircle,
  Monitor,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  Sun,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { Orb, type OrbGLState } from "../components/OrbGL";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../components/ui/tooltip";
import { ALL_PROJECTS, useProject } from "../contexts/ProjectContext";
import { useNavigation, type ViewKind } from "../contexts/NavigationContext";
import { useSettings, type ThemeMode } from "../contexts/SettingsContext";
import { cn } from "../lib/utils";
import { projectColor, projectInitial } from "./projectVisual";

const SIDEBAR_COLLAPSED_KEY = STORAGE_KEYS.sidebarCollapsed;
const EXPANDED_WIDTH = 248;
const COLLAPSED_WIDTH = 64;

const NAV_ITEMS: Array<{ view: ViewKind; label: string; icon: React.ReactNode }> = [
  { view: "painel", label: "Painel", icon: <LayoutDashboard size={18} strokeWidth={2} aria-hidden /> },
  { view: "assistente", label: "Assistente", icon: <MessageCircle size={18} strokeWidth={2} aria-hidden /> },
  { view: "classificador", label: "Classificador", icon: <Sparkles size={18} strokeWidth={2} aria-hidden /> },
  { view: "config", label: "Configuração", icon: <FolderCog size={18} strokeWidth={2} aria-hidden /> },
];

const THEME_CYCLE: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };
const THEME_ICON: Record<ThemeMode, React.ReactNode> = {
  system: <Monitor size={16} aria-hidden />,
  light: <Sun size={16} aria-hidden />,
  dark: <Moon size={16} aria-hidden />,
};
const THEME_LABEL: Record<ThemeMode, string> = { system: "Tema: sistema", light: "Tema: claro", dark: "Tema: escuro" };

type Props = {
  healthOk: boolean | null;
  onSelectProject: (projectId: string) => void;
  onNewProject: () => void;
  onOpenSearch: () => void;
};

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  } catch {
    return false;
  }
}

function ProjectSwitcher({
  collapsed,
  onSelectProject,
  onNewProject,
}: {
  collapsed: boolean;
  onSelectProject: (projectId: string) => void;
  onNewProject: () => void;
}) {
  const { projects, selectedProject, selectedProjectLabel } = useProject();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    const term = filter.trim().toLowerCase();
    if (!term) return projects;
    return projects.filter((p) => p.project_label.toLowerCase().includes(term));
  }, [projects, filter]);

  const isAll = selectedProject === ALL_PROJECTS;

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setFilter("");
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Projeto: ${selectedProjectLabel}`}
          title={collapsed ? selectedProjectLabel : undefined}
          className={cn(
            "group flex w-full items-center gap-2.5 rounded-lg border border-border bg-panel-strong text-left shadow-none",
            "transition-[border-color,box-shadow] duration-150 hover:border-border-strong",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            collapsed ? "justify-center p-2" : "px-2.5 py-2"
          )}
        >
          <span
            aria-hidden
            className="flex size-7 shrink-0 items-center justify-center rounded-md font-display text-xs font-bold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.2)]"
            style={{ background: isAll ? "linear-gradient(135deg, var(--accent), var(--accent-purple))" : projectColor(selectedProject) }}
          >
            {isAll ? <Layers size={14} /> : projectInitial(selectedProjectLabel)}
          </span>
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-display text-sm font-semibold text-foreground-strong">
                  {selectedProjectLabel}
                </span>
                <span className="block font-mono text-[0.65rem] text-tertiary">
                  {isAll ? `${projects.length} projeto(s)` : "projeto ativo"}
                </span>
              </span>
              <ChevronsUpDown size={14} className="shrink-0 text-tertiary transition-colors group-hover:text-muted-foreground" aria-hidden />
            </>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={8} className="w-64 p-1.5">
        <div className="flex items-center gap-2 border-b border-border px-2 pb-1.5">
          <Search size={13} className="text-tertiary" aria-hidden />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filtrar projetos..."
            className="h-7 w-full rounded-none border-0 bg-transparent p-0 text-xs text-foreground shadow-none outline-none placeholder:text-tertiary focus:shadow-none"
            autoFocus
          />
        </div>
        <div className="max-h-64 overflow-y-auto py-1">
          <button
            type="button"
            className={cn(
              "flex w-full items-center gap-2 rounded-md border-0 bg-transparent px-2 py-1.5 text-left text-sm shadow-none",
              "hover:bg-accent-soft hover:text-accent focus-visible:outline-none focus-visible:bg-accent-soft"
            )}
            onClick={() => {
              onSelectProject(ALL_PROJECTS);
              setOpen(false);
            }}
          >
            <Layers size={14} className="text-muted-foreground" aria-hidden />
            <span className="flex-1 truncate">Geral (todos os projetos)</span>
            {isAll && <Check size={14} className="text-accent" aria-hidden />}
          </button>
          {filtered.map((project) => (
            <button
              key={project.project_id}
              type="button"
              className={cn(
                "flex w-full items-center gap-2 rounded-md border-0 bg-transparent px-2 py-1.5 text-left text-sm shadow-none",
                "hover:bg-accent-soft hover:text-accent focus-visible:outline-none focus-visible:bg-accent-soft"
              )}
              onClick={() => {
                onSelectProject(project.project_id);
                setOpen(false);
              }}
            >
              <span
                aria-hidden
                className="flex size-5 items-center justify-center rounded font-display text-[0.65rem] font-bold text-white"
                style={{ background: projectColor(project.project_id) }}
              >
                {projectInitial(project.project_label)}
              </span>
              <span className="flex-1 truncate">
                {project.project_label}
                {!project.initialized && <span className="ml-1 font-mono text-[0.62rem] text-tertiary">(não inicializado)</span>}
              </span>
              {selectedProject === project.project_id && <Check size={14} className="text-accent" aria-hidden />}
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="px-2 py-3 text-center text-xs text-tertiary">Nenhum projeto encontrado.</p>
          )}
        </div>
        <div className="border-t border-border pt-1">
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-md border-0 bg-transparent px-2 py-1.5 text-left text-sm text-accent shadow-none hover:bg-accent-soft focus-visible:outline-none focus-visible:bg-accent-soft"
            onClick={() => {
              setOpen(false);
              onNewProject();
            }}
          >
            <Plus size={14} aria-hidden />
            Novo projeto
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** Sidebar colapsável: navegação, project switcher rico e status — a coluna viva do shell. */
export function Sidebar({ healthOk, onSelectProject, onNewProject, onOpenSearch }: Props) {
  const { view, setView } = useNavigation();
  const { theme, setTheme } = useSettings();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const reducedMotion = useReducedMotion();

  // Ingestão ativa (upload/scan do portal global) leva o orb a "ingesting"
  const [ingestActive, setIngestActive] = useState(false);
  useEffect(() => {
    const handler = (e: Event) => setIngestActive(Boolean((e as CustomEvent).detail));
    window.addEventListener("atlas:ingest-active", handler);
    return () => window.removeEventListener("atlas:ingest-active", handler);
  }, []);

  const orbState: OrbGLState =
    healthOk === false ? "error" : ingestActive ? "ingesting" : healthOk === true ? "alive" : "idle";

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  return (
    <TooltipProvider delayDuration={300}>
      <motion.aside
        aria-label="Navegação principal"
        initial={false}
        animate={{ width: collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH }}
        transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 320, damping: 34 }}
        className="relative z-30 flex h-full shrink-0 flex-col overflow-hidden border-r border-border bg-panel"
      >
        {/* Luz do orb: micro-gradiente radial no topo (direção de arte: elevação = luz).
            Só no estado expandido — colapsada, 64px espremem o radial num "meio círculo". */}
        {!collapsed && (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 h-36 opacity-70"
            style={{ background: "radial-gradient(240px 120px at 30px 22px, var(--accent-soft), transparent 70%)" }}
          />
        )}

        <div className={cn("relative flex items-center gap-2.5 pt-4", collapsed ? "justify-center px-0" : "px-4")}>
          <Orb state={orbState} size={collapsed ? 28 : 40} />
          {!collapsed && (
            <h1 className="font-display text-lg font-bold tracking-tight text-foreground-strong">AtlasFile</h1>
          )}
        </div>

        <div className={cn("relative mt-4", collapsed ? "px-2" : "px-3")}>
          <ProjectSwitcher collapsed={collapsed} onSelectProject={onSelectProject} onNewProject={onNewProject} />
        </div>

        <div className={cn("relative mt-3", collapsed ? "px-2" : "px-3")}>
          <button
            type="button"
            onClick={onOpenSearch}
            title="Buscar (⌘K)"
            aria-label="Buscar (Cmd/Ctrl + K)"
            className={cn(
              "flex w-full items-center gap-2 rounded-md border border-border bg-background/40 text-tertiary shadow-none",
              "transition-colors hover:border-border-strong hover:text-muted-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              collapsed ? "justify-center p-2" : "px-2.5 py-1.5"
            )}
          >
            <Search size={14} aria-hidden />
            {!collapsed && (
              <>
                <span className="flex-1 text-left text-xs">Search...</span>
                <kbd className="rounded border border-border bg-panel-strong px-1 font-mono text-[0.62rem]">⌘K</kbd>
              </>
            )}
          </button>
        </div>

        <nav aria-label="Visão" className={cn("relative mt-5 flex flex-col gap-0.5", collapsed ? "px-2" : "px-3")}>
          {!collapsed && (
            <p className="px-2.5 pb-1 font-mono text-[0.62rem] uppercase tracking-widest text-tertiary">Workspace</p>
          )}
          {NAV_ITEMS.map((item) => {
            const active = view === item.view;
            const button = (
              <button
                key={item.view}
                type="button"
                onClick={() => setView(item.view)}
                aria-current={active ? "page" : undefined}
                title={collapsed ? item.label : undefined}
                className={cn(
                  "relative flex w-full items-center gap-2.5 rounded-md border-0 bg-transparent font-display text-sm font-medium shadow-none",
                  "transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  collapsed ? "justify-center p-2.5" : "px-2.5 py-2",
                  active ? "text-accent" : "text-muted-foreground hover:bg-panel-strong hover:text-foreground"
                )}
              >
                {active && (
                  <motion.span
                    layoutId="sidebar-active"
                    aria-hidden
                    transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 420, damping: 36 }}
                    className="absolute inset-0 rounded-md bg-accent-soft shadow-[inset_2px_0_0_var(--accent)]"
                  />
                )}
                <span className="relative">{item.icon}</span>
                {!collapsed && <span className="relative">{item.label}</span>}
              </button>
            );
            return collapsed ? (
              <Tooltip key={item.view}>
                <TooltipTrigger asChild>{button}</TooltipTrigger>
                <TooltipContent side="right">{item.label}</TooltipContent>
              </Tooltip>
            ) : (
              button
            );
          })}
        </nav>

        <div className="relative mt-auto flex flex-col gap-1 border-t border-border p-2.5">
          <div className={cn("flex items-center gap-1", collapsed ? "flex-col" : "justify-between px-1")}>
            <span
              className="flex items-center gap-1.5 font-mono text-[0.65rem] text-tertiary"
              title={healthOk === true ? "API OK" : healthOk === false ? "API offline" : "Verificando..."}
            >
              <span
                aria-hidden
                className={cn(
                  "size-1.5 rounded-full",
                  healthOk === true && "bg-success shadow-[0_0_6px_var(--ok)]",
                  healthOk === false && "bg-destructive shadow-[0_0_6px_var(--danger)]",
                  healthOk === null && "bg-tertiary"
                )}
              />
              {!collapsed && (healthOk === true ? "online" : healthOk === false ? "offline" : "...")}
            </span>
            <div className={cn("flex items-center gap-0.5", collapsed && "flex-col")}>
              <button
                type="button"
                onClick={() => setTheme(THEME_CYCLE[theme])}
                title={THEME_LABEL[theme]}
                aria-label={THEME_LABEL[theme]}
                className="rounded-md border-0 bg-transparent p-1.5 text-tertiary shadow-none transition-colors hover:bg-panel-strong hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {THEME_ICON[theme]}
              </button>
              <button
                type="button"
                onClick={toggleCollapsed}
                title={collapsed ? "Expandir sidebar" : "Recolher sidebar"}
                aria-label={collapsed ? "Expandir sidebar" : "Recolher sidebar"}
                aria-expanded={!collapsed}
                className="rounded-md border-0 bg-transparent p-1.5 text-tertiary shadow-none transition-colors hover:bg-panel-strong hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <AnimatePresence mode="wait" initial={false}>
                  <motion.span
                    key={collapsed ? "open" : "close"}
                    initial={reducedMotion ? false : { opacity: 0, rotate: -20 }}
                    animate={{ opacity: 1, rotate: 0 }}
                    exit={reducedMotion ? undefined : { opacity: 0, rotate: 20 }}
                    transition={{ duration: 0.12 }}
                    className="block"
                  >
                    {collapsed ? <PanelLeftOpen size={16} aria-hidden /> : <PanelLeftClose size={16} aria-hidden />}
                  </motion.span>
                </AnimatePresence>
              </button>
            </div>
          </div>
        </div>
      </motion.aside>
    </TooltipProvider>
  );
}
