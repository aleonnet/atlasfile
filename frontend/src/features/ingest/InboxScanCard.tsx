import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { triggerScan } from "../../api";
import type { Project, ScanResult } from "../../types";
import { useIngestMonitor } from "./hooks/useIngestMonitor";

const ALL_PROJECTS = "__all__";

function formatPhaseLabel(phase?: string | null): string {
  if (!phase) return "";
  switch (phase) {
    case "starting":
      return "Iniciando";
    case "extracting":
      return "Extraindo conteúdos";
    case "processing":
      return "Processando arquivos";
    case "completed":
      return "Concluído";
    case "failed":
      return "Falhou";
    default:
      return phase;
  }
}

type Props = {
  selectedProject: string;
  projects: Project[];
  onStatus: (msg: string) => void;
  onScanComplete: () => void;
};

export function InboxScanCard({ selectedProject, projects, onStatus, onScanComplete }: Props) {
  const [loading, setLoading] = useState(false);
  const { ingestStatus, startMonitor, stopMonitor, setPending, refreshStatus } = useIngestMonitor();

  const isRunning = loading || ingestStatus?.running ||
    ingestStatus?.phase === "starting" ||
    ingestStatus?.phase === "extracting" ||
    ingestStatus?.phase === "processing";

  async function handleScan() {
    if (!selectedProject) return;
    setLoading(true);
    setPending(selectedProject === ALL_PROJECTS ? null : selectedProject);
    onStatus("Processando inbox...");
    try {
      const results: ScanResult[] = [];
      if (selectedProject === ALL_PROJECTS) {
        for (const project of projects) {
          const scanPromise = triggerScan(project.project_id);
          startMonitor(scanPromise);
          results.push(await scanPromise);
        }
      } else {
        const scanPromise = triggerScan(selectedProject);
        startMonitor(scanPromise);
        results.push(await scanPromise);
      }

      onScanComplete();

      const totals = results.reduce(
        (acc, r) => ({
          processed: acc.processed + r.processed_count,
          failed: acc.failed + r.failed_count
        }),
        { processed: 0, failed: 0 }
      );
      onStatus(`Inbox processado: ${totals.processed} arquivo${totals.processed !== 1 ? "s" : ""}, ${totals.failed} falha${totals.failed !== 1 ? "s" : ""}`);
    } catch {
      onStatus("Falha ao processar inbox");
    } finally {
      stopMonitor();
      refreshStatus();
      setLoading(false);
    }
  }

  return (
    <>
      <button
        className="btn primary"
        disabled={loading || !selectedProject}
        onClick={handleScan}
      >
        <RefreshCw size={14} className={loading ? "spin" : ""} />
        {loading ? "Processando..." : "Processar INBOX"}
      </button>

      {isRunning && (
        <div className="itc-op-progress">
          <p className="itc-op-phase">{formatPhaseLabel(ingestStatus?.phase) || "Iniciando..."}</p>
          <div className="itc-op-bar-wrap">
            <div
              className="itc-op-bar-fill"
              style={{
                width: (ingestStatus?.progress_total ?? 0) > 0
                  ? `${Math.min(100, (100 * (ingestStatus?.progress_current ?? 0)) / ingestStatus!.progress_total!)}%`
                  : "0%"
              }}
            />
          </div>
          <p className="itc-op-stats">
            {ingestStatus?.progress_current ?? 0} / {ingestStatus?.progress_total ?? 0} arquivo{(ingestStatus?.progress_total ?? 0) !== 1 ? "s" : ""}
          </p>
          {ingestStatus?.progress_file && (
            <p className="itc-op-file">{ingestStatus.progress_file}</p>
          )}
        </div>
      )}

      {ingestStatus?.phase === "failed" && !loading && !ingestStatus?.running && (
        <div className="itc-op-progress itc-op-error">
          <p className="itc-op-phase">Falhou</p>
          {ingestStatus.last_error && <p className="itc-op-file">{ingestStatus.last_error}</p>}
        </div>
      )}
    </>
  );
}
