import { RefreshCw } from "lucide-react";
import { MiniOrb } from "../../components/ui/processing-aura";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { triggerScan } from "../../api";
import { Button } from "../../components/ui/button";
import i18n from "../../i18n";
import type { Project, ScanResult } from "../../types";
import { useIngestMonitor } from "./hooks/useIngestMonitor";

const ALL_PROJECTS = "__all__";

function formatPhaseLabel(phase?: string | null): string {
  if (!phase) return "";
  const key = `ingest:phase.${phase}`;
  return i18n.exists(key) ? i18n.t(key) : phase;
}

type Props = {
  selectedProject: string;
  projects: Project[];
  onStatus: (msg: string) => void;
  onScanComplete: () => void;
};

export function InboxScanCard({ selectedProject, projects, onStatus, onScanComplete }: Props) {
  const { t } = useTranslation();
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
    onStatus(t("ingest:scan.processingInbox"));
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
      onStatus(t("ingest:scan.result", {
        files: t("common:unit.file", { count: totals.processed }),
        failures: t("ingest:count.failure", { count: totals.failed })
      }));
    } catch {
      onStatus(t("ingest:scan.failed"));
    } finally {
      stopMonitor();
      refreshStatus();
      setLoading(false);
    }
  }

  return (
    <>
      <Button disabled={loading || !selectedProject} onClick={handleScan}>
        <RefreshCw className={loading ? "animate-spin" : ""} />
        {loading ? t("ingest:scan.processing") : t("ingest:scan.button")}
      </Button>

      {isRunning && (
        <div className="min-w-44 space-y-1">
          <p className="flex items-center gap-1.5 font-display text-xs font-semibold text-foreground-strong">
            <MiniOrb className="size-2.5" />
            {formatPhaseLabel(ingestStatus?.phase) || t("ingest:scan.starting")}
          </p>
          <div className="h-1 overflow-hidden rounded-full bg-panel-strong">
            <div
              className="h-full rounded-full bg-gradient-to-r from-accent to-accent-light shadow-[0_0_8px_var(--accent-soft)] transition-[width] duration-300"
              style={{
                width: (ingestStatus?.progress_total ?? 0) > 0
                  ? `${Math.min(100, (100 * (ingestStatus?.progress_current ?? 0)) / ingestStatus!.progress_total!)}%`
                  : "0%"
              }}
            />
          </div>
          <p className="font-mono text-[0.65rem] text-tertiary">
            {t("ingest:scan.progress", { current: ingestStatus?.progress_current ?? 0, count: ingestStatus?.progress_total ?? 0 })}
          </p>
          {ingestStatus?.progress_file && (
            <p className="truncate font-mono text-[0.65rem] text-tertiary">{ingestStatus.progress_file}</p>
          )}
        </div>
      )}

      {ingestStatus?.phase === "failed" && !loading && !ingestStatus?.running && (
        <div className="min-w-44 space-y-0.5 rounded-md border border-destructive/30 bg-destructive/10 px-2.5 py-1.5">
          <p className="font-display text-xs font-semibold text-destructive">{t("ingest:phase.failed")}</p>
          {ingestStatus.last_error && <p className="truncate font-mono text-[0.65rem] text-destructive/80">{ingestStatus.last_error}</p>}
        </div>
      )}
    </>
  );
}
