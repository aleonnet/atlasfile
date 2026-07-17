import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NavigationProvider } from "../../contexts/NavigationContext";
import { ProjectProvider, useProject } from "../../contexts/ProjectContext";
import { SettingsProvider } from "../../contexts/SettingsContext";
import { GlobalDropPortal } from "./GlobalDropPortal";

const uploadFileWithProgress = vi.fn();
const triggerScan = vi.fn();

vi.mock("../../api", () => ({
  fetchProjects: vi.fn(() =>
    Promise.resolve([
      { project_id: "p1", project_label: "Projeto 1", root: "/p1", initialized: true },
      { project_id: "p2", project_label: "Projeto 2", root: "/p2", initialized: true },
    ])
  ),
  fetchModels: vi.fn(() => Promise.resolve([])),
  uploadFileWithProgress: (...args: unknown[]) => uploadFileWithProgress(...args),
  triggerScan: (...args: unknown[]) => triggerScan(...args),
}));

function SelectProject({ id, children }: { id: string; children: React.ReactNode }) {
  const { refreshProjects, setSelectedProject, selectedProject } = useProject();
  useEffect(() => {
    void refreshProjects().then(() => setSelectedProject(id));
  }, [refreshProjects, setSelectedProject, id]);
  return (
    <>
      <span data-testid="selected-probe">{selectedProject}</span>
      {children}
    </>
  );
}

async function waitForSelection(projectId: string) {
  await waitFor(() => expect(screen.getByTestId("selected-probe").textContent).toBe(projectId));
}

function renderPortal(projectId: string, onScanComplete = vi.fn()) {
  return render(
    <SettingsProvider>
      <ProjectProvider>
        <NavigationProvider>
          <SelectProject id={projectId}>
            <GlobalDropPortal onScanComplete={onScanComplete} />
          </SelectProject>
        </NavigationProvider>
      </ProjectProvider>
    </SettingsProvider>
  );
}

function dropFiles(files: File[]) {
  const dataTransfer = {
    types: ["Files"],
    files,
  };
  fireEvent.dragEnter(window, { dataTransfer });
  fireEvent.drop(window, { dataTransfer });
}

describe("GlobalDropPortal", () => {
  beforeEach(() => {
    uploadFileWithProgress.mockReset();
    triggerScan.mockReset();
  });

  it("mostra o overlay do portal durante o drag e some ao soltar", async () => {
    uploadFileWithProgress.mockResolvedValue({ uploaded: [] });
    triggerScan.mockResolvedValue({ processed_count: 1, failed_count: 0 });
    renderPortal("p1");
    await waitForSelection("p1");

    fireEvent.dragEnter(window, { dataTransfer: { types: ["Files"], files: [] } });
    expect(await screen.findByTestId("drop-overlay")).toBeInTheDocument();

    await act(async () => {
      fireEvent.drop(window, { dataTransfer: { types: ["Files"], files: [] } });
    });
    await waitFor(() => expect(screen.queryByTestId("drop-overlay")).not.toBeInTheDocument());
  });

  it("com projeto selecionado, sobe o arquivo, dispara o scan e notifica", async () => {
    uploadFileWithProgress.mockResolvedValue({ uploaded: [{ filename: "doc.pdf" }] });
    triggerScan.mockResolvedValue({ processed_count: 1, failed_count: 0 });
    const onScanComplete = vi.fn();
    renderPortal("p1", onScanComplete);
    await waitForSelection("p1");

    const file = new File([new Uint8Array(10)], "doc.pdf", { type: "application/pdf" });
    await act(async () => {
      dropFiles([file]);
    });

    expect(await screen.findByTestId("upload-queue")).toBeInTheDocument();
    expect(screen.getByText("doc.pdf")).toBeInTheDocument();
    await waitFor(() => expect(uploadFileWithProgress).toHaveBeenCalledTimes(1));
    expect(uploadFileWithProgress.mock.calls[0][0]).toBe("p1");
    await waitFor(() => expect(triggerScan).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onScanComplete).toHaveBeenCalled());

    // Regressão: o efeito re-roda enquanto a fila concluída aguarda o auto-fechamento —
    // o scan deve disparar exatamente 1 vez por lote (bug dos toasts em loop).
    await act(async () => {
      await new Promise((r) => setTimeout(r, 300));
    });
    expect(triggerScan).toHaveBeenCalledTimes(1);
  });

  it("erro de upload aparece no item e não dispara scan sem sucesso", async () => {
    uploadFileWithProgress.mockRejectedValue(new Error("Upload falhou (500)"));
    renderPortal("p1");
    await waitForSelection("p1");

    const file = new File([new Uint8Array(4)], "quebrado.pdf", { type: "application/pdf" });
    await act(async () => {
      dropFiles([file]);
    });

    expect(await screen.findByText("Upload falhou (500)")).toBeInTheDocument();
    expect(triggerScan).not.toHaveBeenCalled();
  });

  it("sem projeto selecionado, pede a escolha do projeto antes de subir", async () => {
    uploadFileWithProgress.mockResolvedValue({ uploaded: [] });
    triggerScan.mockResolvedValue({ processed_count: 0, failed_count: 0 });
    renderPortal("__all__");
    await waitForSelection("__all__");

    const file = new File([new Uint8Array(4)], "solto.pdf", { type: "application/pdf" });
    await act(async () => {
      dropFiles([file]);
    });

    expect(await screen.findByText("Para qual projeto?")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /Projeto 2/ }));
    await waitFor(() => expect(uploadFileWithProgress).toHaveBeenCalled());
    expect(uploadFileWithProgress.mock.calls[0][0]).toBe("p2");
  });
});
