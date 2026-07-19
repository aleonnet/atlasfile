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
  Sparkles,
  Sun,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { getFileDownloadUrl } from "../api";
import i18n from "../i18n";
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
  { view: "painel", label: i18n.t("painel:shell.navPainel"), icon: <LayoutDashboard /> },
  { view: "assistente", label: i18n.t("painel:shell.navAssistente"), icon: <MessageCircle /> },
  { view: "classificador", label: i18n.t("painel:shell.navClassificador"), icon: <Sparkles /> },
  { view: "config", label: i18n.t("painel:shell.navConfig"), icon: <FolderCog /> },
];

const THEME_ITEMS: Array<{ mode: ThemeMode; label: string; icon: React.ReactNode }> = [
  { mode: "system", label: i18n.t("painel:shell.themeItemSystem"), icon: <Monitor /> },
  { mode: "light", label: i18n.t("painel:shell.themeItemLight"), icon: <Sun /> },
  { mode: "dark", label: i18n.t("painel:shell.themeItemDark"), icon: <Moon /> },
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
  const { t } = useTranslation();
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
        <DialogTitle className="sr-only">{t("painel:shell.paletteTitle")}</DialogTitle>
        <Command
          shouldFilter={false}
          loop
          className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[0.68rem] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-tertiary"
        >
          <CommandInput placeholder={t("painel:shell.searchPlaceholder")} value={query} onValueChange={onQueryChange} autoFocus />
          <CommandList>
          {searching && (
            <CommandGroup heading={loading ? t("painel:shell.searchingDocs") : t("painel:shell.documents")}>
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
                    {t("painel:shell.listAllResults")} <strong className="text-accent">“{q}”</strong>
                  </span>
                  <CommandShortcut>↵</CommandShortcut>
                </CommandItem>
              )}
            </CommandGroup>
          )}

          {navMatches.length > 0 && (
            <CommandGroup heading={t("painel:shell.navigationGroup")}>
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
                  {view === item.view && <CommandShortcut>{t("painel:shell.current")}</CommandShortcut>}
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {projectMatches.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading={t("painel:shell.projectsGroup")}>
                {!searching && (
                  <CommandItem
                    value="project-all"
                    onSelect={() => {
                      onSelectProject(ALL_PROJECTS);
                      close();
                    }}
                  >
                    <Layers />
                    <span>{t("painel:shell.allProjects")}</span>
                    {selectedProject === ALL_PROJECTS && <CommandShortcut>{t("painel:shell.current")}</CommandShortcut>}
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
                    {selectedProject === project.project_id && <CommandShortcut>{t("painel:shell.current")}</CommandShortcut>}
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}

          {themeMatches.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading={t("painel:shell.themeGroup")}>
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

          {(!searching || matches(t("painel:shell.newProject"), q)) && (
            <>
              <CommandSeparator />
              <CommandGroup heading={t("painel:shell.actionsGroup")}>
                <CommandItem
                  value="new-project"
                  onSelect={() => {
                    onNewProject();
                    close();
                  }}
                >
                  <Plus />
                  <span>{t("painel:shell.newProject")}</span>
                </CommandItem>
              </CommandGroup>
            </>
          )}

          {searching && !loading && hits.length === 0 && navMatches.length === 0 && projectMatches.length === 0 && (
            <CommandEmpty>{t("painel:shell.noResultsFor", { query: q })}</CommandEmpty>
          )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
