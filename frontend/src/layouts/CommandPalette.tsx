import {
  FolderCog,
  FolderOpen,
  Layers,
  LayoutDashboard,
  MessageCircle,
  Monitor,
  Moon,
  Plus,
  Search,
  Sun,
} from "lucide-react";
import { getFileDownloadUrl } from "../api";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "../components/ui/command";
import { Dialog, DialogContent, DialogTitle } from "../components/ui/dialog";
import { ALL_PROJECTS, useProject } from "../contexts/ProjectContext";
import { useNavigation, type ViewKind } from "../contexts/NavigationContext";
import { useSettings, type ThemeMode } from "../contexts/SettingsContext";
import { buildEvidenceGroups, topLocations } from "../features/search/searchFormatters";
import type { SearchHit } from "../types";
import { projectColor, projectInitial } from "./projectVisual";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  query: string;
  onQueryChange: (value: string) => void;
  hits: SearchHit[];
  loading: boolean;
  onSubmitSearch: (query: string) => void;
  onSelectProject: (projectId: string) => void;
  onNewProject: () => void;
};

const NAV_ITEMS: Array<{ view: ViewKind; label: string; icon: React.ReactNode }> = [
  { view: "painel", label: "Painel", icon: <LayoutDashboard /> },
  { view: "assistente", label: "Assistente", icon: <MessageCircle /> },
  { view: "config", label: "Configuração", icon: <FolderCog /> },
];

const THEME_ITEMS: Array<{ mode: ThemeMode; label: string; icon: React.ReactNode }> = [
  { mode: "system", label: "Tema do sistema", icon: <Monitor /> },
  { mode: "light", label: "Tema claro", icon: <Sun /> },
  { mode: "dark", label: "Tema escuro", icon: <Moon /> },
];

function matches(label: string, query: string): boolean {
  return label.toLowerCase().includes(query.trim().toLowerCase());
}

function cleanSnippetHtml(snippet: string): string {
  return snippet
    .replace(/\[[^\]]+\]\s*/g, "")
    .replace(/\n+/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function hitSnippet(hit: SearchHit): string {
  const evidence = hit.evidences?.[0]?.snippet;
  if (evidence) return cleanSnippetHtml(evidence);
  const highlighted = hit.highlights.find((h) => h.includes("<em>")) || hit.highlights[0];
  return highlighted ? cleanSnippetHtml(highlighted) : "";
}

function hitLocation(hit: SearchHit): string {
  const groups = buildEvidenceGroups(hit.evidences ?? []);
  if (groups.length > 0) return groups[0].label;
  const locations = topLocations(hit.match_locations, 1);
  return locations[0] ?? "";
}

/** Command palette (⌘K): navegar, trocar projeto, tema, novo projeto e busca de documentos. */
export function CommandPalette({
  open,
  onOpenChange,
  query,
  onQueryChange,
  hits,
  loading,
  onSubmitSearch,
  onSelectProject,
  onNewProject,
}: Props) {
  const { view, setView } = useNavigation();
  const { setTheme } = useSettings();
  const { projects, selectedProject, projectLabelById } = useProject();

  const q = query.trim();
  const searching = q.length >= 2;

  const close = () => onOpenChange(false);

  const navMatches = NAV_ITEMS.filter((item) => !searching || matches(item.label, q));
  const projectMatches = projects.filter((p) => !searching || matches(p.project_label, q)).slice(0, 8);
  const themeMatches = THEME_ITEMS.filter((item) => !searching || matches(item.label, q));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl overflow-hidden border-accent-soft p-0 [&>button]:hidden">
        <DialogTitle className="sr-only">Busca e comandos</DialogTitle>
        <Command
          shouldFilter={false}
          loop
          className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[0.68rem] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-tertiary"
        >
          <CommandInput placeholder="Search..." value={query} onValueChange={onQueryChange} autoFocus />
          <CommandList>
          {searching && (
            <CommandGroup heading={loading ? "Buscando documentos..." : "Documentos"}>
              {hits.map((hit) => (
                <CommandItem
                  key={`doc-${hit.doc_id}`}
                  value={`doc-${hit.doc_id}`}
                  onSelect={() => {
                    window.open(getFileDownloadUrl(hit.path), "_blank", "noreferrer");
                    close();
                  }}
                  className="!items-start gap-3 py-2.5"
                >
                  <FolderOpen className="mt-0.5 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-display text-sm font-medium text-foreground-strong">
                      {hit.original_filename}
                    </div>
                    {hitSnippet(hit) && (
                      <div
                        className="mt-0.5 line-clamp-2 text-xs text-muted-foreground [&_em]:not-italic [&_em]:font-bold [&_em]:text-accent"
                        dangerouslySetInnerHTML={{ __html: hitSnippet(hit) }}
                      />
                    )}
                    <div className="mt-0.5 truncate font-mono text-[0.68rem] text-tertiary">
                      {projectLabelById.get(hit.project_id) || hit.project_id}
                      {hitLocation(hit) ? ` · ${hitLocation(hit)}` : ""}
                    </div>
                  </div>
                </CommandItem>
              ))}
              {!loading && (
                <CommandItem
                  value="search-all"
                  onSelect={() => {
                    onSubmitSearch(q);
                    close();
                  }}
                >
                  <Search />
                  <span>
                    Listar todos os resultados para <strong className="text-accent">“{q}”</strong>
                  </span>
                  <CommandShortcut>↵</CommandShortcut>
                </CommandItem>
              )}
            </CommandGroup>
          )}

          {navMatches.length > 0 && (
            <CommandGroup heading="Navegação">
              {navMatches.map((item) => (
                <CommandItem
                  key={`nav-${item.view}`}
                  value={`nav-${item.view}`}
                  onSelect={() => {
                    setView(item.view);
                    close();
                  }}
                >
                  {item.icon}
                  <span>{item.label}</span>
                  {view === item.view && <CommandShortcut>atual</CommandShortcut>}
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {projectMatches.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Projetos">
                {!searching && (
                  <CommandItem
                    value="project-all"
                    onSelect={() => {
                      onSelectProject(ALL_PROJECTS);
                      close();
                    }}
                  >
                    <Layers />
                    <span>Geral (todos os projetos)</span>
                    {selectedProject === ALL_PROJECTS && <CommandShortcut>atual</CommandShortcut>}
                  </CommandItem>
                )}
                {projectMatches.map((project) => (
                  <CommandItem
                    key={`proj-${project.project_id}`}
                    value={`proj-${project.project_id}`}
                    onSelect={() => {
                      onSelectProject(project.project_id);
                      close();
                    }}
                  >
                    <span
                      aria-hidden
                      className="flex size-4 items-center justify-center rounded font-display text-[0.6rem] font-bold text-white"
                      style={{ background: projectColor(project.project_id) }}
                    >
                      {projectInitial(project.project_label)}
                    </span>
                    <span className="truncate">{project.project_label}</span>
                    {selectedProject === project.project_id && <CommandShortcut>atual</CommandShortcut>}
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}

          {themeMatches.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Tema">
                {themeMatches.map((item) => (
                  <CommandItem
                    key={`theme-${item.mode}`}
                    value={`theme-${item.mode}`}
                    onSelect={() => {
                      setTheme(item.mode);
                      close();
                    }}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}

          {(!searching || matches("novo projeto", q)) && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Ações">
                <CommandItem
                  value="new-project"
                  onSelect={() => {
                    onNewProject();
                    close();
                  }}
                >
                  <Plus />
                  <span>Novo projeto</span>
                </CommandItem>
              </CommandGroup>
            </>
          )}

          {searching && !loading && hits.length === 0 && navMatches.length === 0 && projectMatches.length === 0 && (
            <CommandEmpty>Nenhum resultado para “{q}”.</CommandEmpty>
          )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
