/// <reference types="@testing-library/jest-dom/vitest" />
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { OnboardingWizard } from "./OnboardingWizard";

vi.mock("../../api", () => ({
  fetchSetupStatus: vi.fn(() =>
    Promise.resolve({
      app_env: "dev",
      projects_root: "/projects",
      total_project_dirs: 0,
      initialized_projects: 0,
      onboarding_suggested: true,
    })
  ),
  fetchProjects: vi.fn(() => Promise.resolve([])),
  listTemplates: vi.fn(() =>
    Promise.resolve([
      { slug: "default", name: "M&A / Carve-out", description: "Template padrao", areas_count: 8 },
      { slug: "due_diligence", name: "Due Diligence", description: "", areas_count: 5 },
    ])
  ),
  initializeProject: vi.fn(() => Promise.resolve({ status: "ok", already_initialized: false })),
}));

function defaultProps(overrides?: Partial<React.ComponentProps<typeof OnboardingWizard>>) {
  return {
    onComplete: vi.fn(),
    openaiApiKey: "",
    anthropicApiKey: "",
    onChangeOpenAiKey: vi.fn(),
    onChangeAnthropicKey: vi.fn(),
    ...overrides,
  };
}

describe("OnboardingWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders welcome step by default", async () => {
    render(<OnboardingWizard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Bem-vindo ao AtlasFile/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Comecar/)).toBeInTheDocument();
  });

  it("shows projects_root from setup status", async () => {
    render(<OnboardingWizard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText("/projects")).toBeInTheDocument();
    });
  });

  it("navigates to create project step", async () => {
    render(<OnboardingWizard {...defaultProps()} />);
    await waitFor(() => {
      expect(screen.getByText(/Comecar/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Comecar/));
    await waitFor(() => {
      expect(screen.getByText(/Crie seu primeiro projeto/)).toBeInTheDocument();
    });
  });

  it("back button returns to previous step", async () => {
    render(<OnboardingWizard {...defaultProps()} />);
    await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Comecar/));
    await waitFor(() => expect(screen.getByText(/Crie seu primeiro projeto/)).toBeInTheDocument());

    fireEvent.click(screen.getByText(/Voltar/));
    await waitFor(() => {
      expect(screen.getByText(/Bem-vindo ao AtlasFile/)).toBeInTheDocument();
    });
  });

  it("validates project name (empty)", async () => {
    render(<OnboardingWizard {...defaultProps()} />);
    await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Comecar/));
    await waitFor(() => expect(screen.getByText(/Criar e Continuar/)).toBeInTheDocument());

    fireEvent.click(screen.getByText(/Criar e Continuar/));
    await waitFor(() => {
      expect(screen.getByText(/Nome do projeto e obrigatorio/)).toBeInTheDocument();
    });
  });

  it("validates project name (invalid slug)", async () => {
    render(<OnboardingWizard {...defaultProps()} />);
    await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Comecar/));
    await waitFor(() => expect(screen.getByLabelText(/Nome do projeto/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Nome do projeto/), { target: { value: "Meu Projeto" } });
    fireEvent.click(screen.getByText(/Criar e Continuar/));
    await waitFor(() => {
      expect(screen.getByText(/letras minusculas/)).toBeInTheDocument();
    });
  });

  it("calls initializeProject on valid submit", async () => {
    const { initializeProject } = await import("../../api");
    render(<OnboardingWizard {...defaultProps()} />);
    await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Comecar/));
    await waitFor(() => expect(screen.getByLabelText(/Nome do projeto/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Nome do projeto/), { target: { value: "meu_projeto" } });
    fireEvent.click(screen.getByText(/Criar e Continuar/));
    await waitFor(() => {
      expect(initializeProject).toHaveBeenCalledWith("meu_projeto", "default");
    });
  });

  it("shows error when initializeProject fails", async () => {
    const { initializeProject } = await import("../../api");
    vi.mocked(initializeProject).mockRejectedValueOnce(new Error("API error"));

    render(<OnboardingWizard {...defaultProps()} />);
    await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Comecar/));
    await waitFor(() => expect(screen.getByLabelText(/Nome do projeto/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Nome do projeto/), { target: { value: "test_proj" } });
    fireEvent.click(screen.getByText(/Criar e Continuar/));
    await waitFor(() => {
      expect(screen.getByText(/API error/)).toBeInTheDocument();
    });
  });

  it("navigates to LLM step after project creation", async () => {
    render(<OnboardingWizard {...defaultProps()} />);
    await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Comecar/));
    await waitFor(() => expect(screen.getByLabelText(/Nome do projeto/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Nome do projeto/), { target: { value: "my_proj" } });
    fireEvent.click(screen.getByText(/Criar e Continuar/));
    await waitFor(() => {
      expect(screen.getByText(/Configure o assistente/)).toBeInTheDocument();
    });
  });

  it("skip LLM completes onboarding", async () => {
    const onComplete = vi.fn();
    render(<OnboardingWizard {...defaultProps({ onComplete })} />);
    await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Comecar/));
    await waitFor(() => expect(screen.getByLabelText(/Nome do projeto/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Nome do projeto/), { target: { value: "proj1" } });
    fireEvent.click(screen.getByText(/Criar e Continuar/));
    await waitFor(() => expect(screen.getByText(/Configure o assistente/)).toBeInTheDocument());

    fireEvent.click(screen.getByText(/Pular/));
    await waitFor(() => expect(screen.getByText(/Tudo pronto/)).toBeInTheDocument());

    fireEvent.click(screen.getByText(/Abrir Dashboard/));
    expect(onComplete).toHaveBeenCalledWith("proj1");
  });

  it("save LLM key and complete", async () => {
    const onChangeOpenAiKey = vi.fn();
    const onComplete = vi.fn();
    render(<OnboardingWizard {...defaultProps({ onComplete, onChangeOpenAiKey })} />);
    await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Comecar/));
    await waitFor(() => expect(screen.getByLabelText(/Nome do projeto/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Nome do projeto/), { target: { value: "proj2" } });
    fireEvent.click(screen.getByText(/Criar e Continuar/));
    await waitFor(() => expect(screen.getByText(/Configure o assistente/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/API Key/), { target: { value: "sk-test-123" } });
    fireEvent.click(screen.getByText(/Salvar e Concluir/));
    await waitFor(() => expect(screen.getByText(/Tudo pronto/)).toBeInTheDocument());

    expect(onChangeOpenAiKey).toHaveBeenCalledWith("sk-test-123");
  });

  describe("replay mode (existing projects)", () => {
    beforeEach(async () => {
      const api = await import("../../api");
      vi.mocked(api.fetchProjects).mockResolvedValue([
        { project_id: "existing_proj", project_label: "My Existing", root: "/projects/existing_proj", initialized: true },
      ]);
      vi.mocked(api.fetchSetupStatus).mockResolvedValue({
        app_env: "dev",
        projects_root: "/projects",
        total_project_dirs: 1,
        initialized_projects: 1,
        onboarding_suggested: false,
      });
    });

    it("shows existing projects on replay", async () => {
      render(<OnboardingWizard {...defaultProps()} />);
      await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
      fireEvent.click(screen.getByText(/Comecar/));
      await waitFor(() => {
        expect(screen.getByText(/Seus projetos/)).toBeInTheDocument();
        expect(screen.getByText(/My Existing/)).toBeInTheDocument();
      });
    });

    it("continue without creating project on replay", async () => {
      const { initializeProject } = await import("../../api");
      render(<OnboardingWizard {...defaultProps()} />);
      await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
      fireEvent.click(screen.getByText(/Comecar/));
      await waitFor(() => expect(screen.getByText(/Seus projetos/)).toBeInTheDocument());

      fireEvent.click(screen.getByText(/Continuar/));
      await waitFor(() => expect(screen.getByText(/Configure o assistente/)).toBeInTheDocument());
      expect(initializeProject).not.toHaveBeenCalled();
    });

    it("expands create form on replay", async () => {
      render(<OnboardingWizard {...defaultProps()} />);
      await waitFor(() => expect(screen.getByText(/Comecar/)).toBeInTheDocument());
      fireEvent.click(screen.getByText(/Comecar/));
      await waitFor(() => expect(screen.getByText(/Seus projetos/)).toBeInTheDocument());

      fireEvent.click(screen.getByText(/Criar novo projeto/));
      await waitFor(() => {
        expect(screen.getByLabelText(/Nome do projeto/)).toBeInTheDocument();
        expect(screen.getByText(/Criar e Continuar/)).toBeInTheDocument();
      });
    });
  });
});
