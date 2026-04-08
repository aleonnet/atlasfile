import { FolderCog, LayoutDashboard, MessageCircle, Monitor, Moon, Search, Sun } from "lucide-react";
import { CompanionOrb } from "../components/CompanionOrb";
import type { CompanionState } from "../components/CompanionOrb";
import type { Project } from "../types";

type ThemeMode = "system" | "light" | "dark";
type ViewKind = "painel" | "assistente" | "config";

type Props = {
  healthOk: boolean | null;
  projects: Project[];
  selectedProject: string;
  onSelectProject: (value: string) => void;
  view: ViewKind;
  onChangeView: (view: ViewKind) => void;
  theme: ThemeMode;
  onChangeTheme: (theme: ThemeMode) => void;
  onOpenSearch: () => void;
  onNewProject?: () => void;
};

const ALL_PROJECTS = "__all__";

export function Topbar({
  healthOk,
  projects,
  selectedProject,
  onSelectProject,
  view,
  onChangeView,
  theme,
  onChangeTheme,
  onOpenSearch,
  onNewProject,
}: Props) {
  const orbState: CompanionState = healthOk === true ? "alive" : healthOk === false ? "error" : "idle";

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="topbar-left">
          <div className="brand" title={healthOk === true ? "API OK" : healthOk === false ? "API offline" : "A verificar..."}>
            <CompanionOrb state={orbState} size={48} />
            <h1>AtlasFile</h1>
          </div>
          <select
            className="project-select"
            value={selectedProject}
            onChange={(e) => {
              const v = e.target.value;
              if (v === "__new__") {
                e.target.value = selectedProject;
                onNewProject?.();
              } else {
                void onSelectProject(v);
              }
            }}
          >
            <option value={ALL_PROJECTS}>Geral (todos os projetos)</option>
            {projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.project_label}
                {project.initialized ? "" : " (nao inicializado)"}
              </option>
            ))}
            {onNewProject && <option value="__new__">+ Novo projeto</option>}
          </select>
        </div>
        <nav className="topbar-nav" aria-label="Visão">
          <button
            type="button"
            className={view === "painel" ? "active" : ""}
            onClick={() => onChangeView("painel")}
            aria-current={view === "painel" ? "page" : undefined}
            title="Painel"
          >
            <LayoutDashboard size={18} strokeWidth={2} aria-hidden />
            <span className="view-tab-label">Painel</span>
          </button>
          <button
            type="button"
            className={view === "assistente" ? "active" : ""}
            onClick={() => onChangeView("assistente")}
            aria-current={view === "assistente" ? "page" : undefined}
            title="Assistente"
          >
            <MessageCircle size={18} strokeWidth={2} aria-hidden />
            <span className="view-tab-label">Assistente</span>
          </button>
          <button
            type="button"
            className={view === "config" ? "active" : ""}
            onClick={() => onChangeView("config")}
            aria-current={view === "config" ? "page" : undefined}
            title="Configuração"
          >
            <FolderCog size={18} strokeWidth={2} aria-hidden />
            <span className="view-tab-label">Configuração</span>
          </button>
        </nav>
        <div className="topbar-center">
          <div className="header-search-card">
            <button className="header-search-btn" onClick={onOpenSearch} title="Abrir busca (Cmd/Ctrl + K)">
              <Search size={16} />
              <span className="header-search-text">Search...</span>
              <span className="kbd">⌘K</span>
            </button>
          </div>
        </div>
        <div className="topbar-status">
          <button className="topbar-search-icon" onClick={onOpenSearch} title="Buscar" aria-label="Buscar">
            <Search size={18} />
          </button>
          <div className="theme-toggle" role="group" aria-label="Tema">
            <button
              type="button"
              className={`theme-toggle__button ${theme === "system" ? "active" : ""}`}
              onClick={() => onChangeTheme("system")}
              aria-pressed={theme === "system"}
              aria-label="Tema sistema"
              title="Sistema"
            >
              <Monitor size={18} />
            </button>
            <button
              type="button"
              className={`theme-toggle__button ${theme === "light" ? "active" : ""}`}
              onClick={() => onChangeTheme("light")}
              aria-pressed={theme === "light"}
              aria-label="Tema claro"
              title="Claro"
            >
              <Sun size={18} />
            </button>
            <button
              type="button"
              className={`theme-toggle__button ${theme === "dark" ? "active" : ""}`}
              onClick={() => onChangeTheme("dark")}
              aria-pressed={theme === "dark"}
              aria-label="Tema escuro"
              title="Escuro"
            >
              <Moon size={18} />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
