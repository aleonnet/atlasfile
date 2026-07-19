import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchProjects } from "../api";
import i18n from "../i18n";
import { qk } from "../lib/queryKeys";
import { STORAGE_KEYS, storageGet, storageSet } from "../lib/storage";
import type { Project } from "../types";

export const ALL_PROJECTS = "__all__";

type ProjectContextValue = {
  projects: Project[];
  selectedProject: string;
  setSelectedProject: React.Dispatch<React.SetStateAction<string>>;
  /** undefined quando "todos os projetos" — pronto para passar à API. */
  selectedProjectScope: string | undefined;
  selectedProjectLabel: string;
  projectLabelById: Map<string, string>;
  refreshProjects: () => Promise<void>;
};

const ProjectContext = createContext<ProjectContextValue | null>(null);

function readStoredProject(): string {
  return storageGet(STORAGE_KEYS.selectedProject) || ALL_PROJECTS;
}

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const projectsQuery = useQuery({ queryKey: qk.projects(), queryFn: fetchProjects });
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);
  // Persistido: a seleção de projeto sobrevive ao reload da página; se o
  // projeto salvo não existir mais, refreshProjects volta para "todos"
  const [selectedProject, setSelectedProject] = useState<string>(readStoredProject);

  useEffect(() => {
    storageSet(STORAGE_KEYS.selectedProject, selectedProject);
  }, [selectedProject]);

  const refreshProjects = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: qk.projects() });
  }, [queryClient]);

  // Se o projeto persistido não existe mais (lista recarregada), volta a "todos"
  useEffect(() => {
    if (projectsQuery.data) {
      const data = projectsQuery.data;
      setSelectedProject((current) =>
        current !== ALL_PROJECTS && !data.some((p) => p.project_id === current) ? ALL_PROJECTS : current
      );
    }
  }, [projectsQuery.data]);

  const selectedProjectLabel = useMemo(
    () =>
      selectedProject === ALL_PROJECTS
        ? i18n.t("common:allProjects")
        : projects.find((p) => p.project_id === selectedProject)?.project_label ?? "",
    [projects, selectedProject]
  );

  const projectLabelById = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of projects) map.set(p.project_id, p.project_label);
    return map;
  }, [projects]);

  const value = useMemo<ProjectContextValue>(
    () => ({
      projects,
      selectedProject,
      setSelectedProject,
      selectedProjectScope: selectedProject === ALL_PROJECTS ? undefined : selectedProject,
      selectedProjectLabel,
      projectLabelById,
      refreshProjects,
    }),
    [projects, selectedProject, selectedProjectLabel, projectLabelById, refreshProjects]
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject(): ProjectContextValue {
  const context = useContext(ProjectContext);
  if (!context) throw new Error("useProject deve ser usado dentro de <ProjectProvider>");
  return context;
}
