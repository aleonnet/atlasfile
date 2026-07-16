import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { fetchProjects } from "../api";
import type { Project } from "../types";

export const ALL_PROJECTS = "__all__";

type ProjectContextValue = {
  projects: Project[];
  setProjects: React.Dispatch<React.SetStateAction<Project[]>>;
  selectedProject: string;
  setSelectedProject: React.Dispatch<React.SetStateAction<string>>;
  /** undefined quando "todos os projetos" — pronto para passar à API. */
  selectedProjectScope: string | undefined;
  selectedProjectLabel: string;
  projectLabelById: Map<string, string>;
  refreshProjects: () => Promise<void>;
};

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>(ALL_PROJECTS);

  const refreshProjects = useCallback(async () => {
    const data = await fetchProjects();
    setProjects(data);
    setSelectedProject((current) =>
      current !== ALL_PROJECTS && !data.some((p) => p.project_id === current) ? ALL_PROJECTS : current
    );
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

  const value = useMemo<ProjectContextValue>(
    () => ({
      projects,
      setProjects,
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
