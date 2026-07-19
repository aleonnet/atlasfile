import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test/utils";
import { useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NavigationProvider } from "../contexts/NavigationContext";
import { ProjectProvider, useProject } from "../contexts/ProjectContext";
import { SettingsProvider } from "../contexts/SettingsContext";
import { CommandPalette } from "./CommandPalette";
import { Sidebar } from "./Sidebar";

vi.mock("../api", () => ({
  fetchProjects: vi.fn(() =>
    Promise.resolve([
      { project_id: "p1", project_label: "Projeto 1", root: "/p1", initialized: true },
      { project_id: "p2", project_label: "Projeto 2", root: "/p2", initialized: true },
    ])
  ),
  fetchModels: vi.fn(() => Promise.resolve([])),
  getFileDownloadUrl: vi.fn((path: string) => `http://api/files?path=${path}`),
}));

function LoadProjects({ children }: { children: React.ReactNode }) {
  const { refreshProjects } = useProject();
  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);
  return <>{children}</>;
}

function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SettingsProvider>
      <ProjectProvider>
        <NavigationProvider>
          <LoadProjects>{children}</LoadProjects>
        </NavigationProvider>
      </ProjectProvider>
    </SettingsProvider>
  );
}

describe("Sidebar", () => {
  beforeEach(() => {
    localStorage.removeItem("atlasfile-sidebar-collapsed");
    window.location.hash = "";
  });

  it("renderiza navegação e alterna a view ativa", () => {
    renderWithProviders(
      <Providers>
        <Sidebar healthOk={true} onSelectProject={vi.fn()} onNewProject={vi.fn()} onOpenSearch={vi.fn()} />
      </Providers>
    );
    const painel = screen.getByRole("button", { name: "Painel" });
    expect(painel).toHaveAttribute("aria-current", "page");

    fireEvent.click(screen.getByRole("button", { name: "Assistente" }));
    expect(screen.getByRole("button", { name: "Assistente" })).toHaveAttribute("aria-current", "page");
    expect(window.location.hash).toBe("#/assistente");
  });

  it("colapsa, persiste e expande", () => {
    renderWithProviders(
      <Providers>
        <Sidebar healthOk={true} onSelectProject={vi.fn()} onNewProject={vi.fn()} onOpenSearch={vi.fn()} />
      </Providers>
    );
    fireEvent.click(screen.getByRole("button", { name: "Recolher sidebar" }));
    expect(localStorage.getItem("atlasfile-sidebar-collapsed")).toBe("true");
    // Colapsada: o wordmark some, os ícones ficam
    expect(screen.queryByText("AtlasFile")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Expandir sidebar" }));
    expect(localStorage.getItem("atlasfile-sidebar-collapsed")).toBe("false");
    expect(screen.getByText("AtlasFile")).toBeInTheDocument();
  });

  it("project switcher lista projetos e seleciona", async () => {
    const onSelectProject = vi.fn();
    renderWithProviders(
      <Providers>
        <Sidebar healthOk={true} onSelectProject={onSelectProject} onNewProject={vi.fn()} onOpenSearch={vi.fn()} />
      </Providers>
    );
    await waitFor(() => expect(screen.getByText(/2 projeto\(s\)/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/Projeto: /));
    const option = await screen.findByRole("button", { name: /Projeto 2/ });
    fireEvent.click(option);
    expect(onSelectProject).toHaveBeenCalledWith("p2");
  });
});

describe("CommandPalette", () => {
  it("mostra grupos de comandos e filtra por texto", async () => {
    const onQueryChange = vi.fn();
    renderWithProviders(
      <Providers>
        <CommandPalette
          open
          onOpenChange={vi.fn()}
          query=""
          onQueryChange={onQueryChange}
          hits={[]}
          loading={false}
          onSubmitSearch={vi.fn()}
          onSelectProject={vi.fn()}
          onNewProject={vi.fn()}
        />
      </Providers>
    );
    expect(screen.getByPlaceholderText("Search...")).toBeInTheDocument();
    expect(screen.getByText("Navegação")).toBeInTheDocument();
    expect(screen.getByText("Tema")).toBeInTheDocument();
    expect(screen.getByText("Novo projeto")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search..."), { target: { value: "assist" } });
    expect(onQueryChange).toHaveBeenCalledWith("assist");
  });

  it("com query, mostra documentos e ação de listar todos", () => {
    const onSubmitSearch = vi.fn();
    renderWithProviders(
      <Providers>
        <CommandPalette
          open
          onOpenChange={vi.fn()}
          query="contrato"
          onQueryChange={vi.fn()}
          hits={[
            {
              doc_id: "d1",
              project_id: "p1",
              original_filename: "Contrato_X.pdf",
              canonical_filename: "contrato_x.pdf",
              path: "/p1/02_AREAS/juridico/contrato/Contrato_X.pdf",
              score: 1,
              highlights: [],
              match_locations: [],
              evidences: [{ location: "page:3", snippet: "Trecho com <em>contrato</em>", match_count: 1 }],
              total_evidences: 1,
              omitted_evidences: 0,
            },
          ]}
          loading={false}
          onSubmitSearch={onSubmitSearch}
          onSelectProject={vi.fn()}
          onNewProject={vi.fn()}
        />
      </Providers>
    );
    expect(screen.getByText("Contrato_X.pdf")).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Listar todos os resultados/));
    expect(onSubmitSearch).toHaveBeenCalledWith("contrato");
  });
});
