import { useEffect, useRef } from "react";
import { fetchReconcileStatus, getReconcileStatusStreamUrl, runReconcile } from "../api";
import i18n from "../i18n";
import { invalidateAfterReconcile } from "../lib/mutations";
import { qk } from "../lib/queryKeys";
import { useSseChannel } from "./useSseChannel";
import type { ReconcileStatus, StatusSeverity } from "../types";

function progressMessage(latest: ReconcileStatus): string {
  const skipped = latest.progress_skipped ?? 0;
  return i18n.t("painel:reconcile.progress", {
    current: latest.progress_current ?? 0,
    total: latest.progress_total ?? 0,
    project: latest.progress_project ?? "—",
    file: latest.progress_file ?? "—",
    skip: skipped > 0 ? i18n.t("painel:reconcile.progressSkip", { count: skipped }) : "",
  });
}

function summaryMessage(latest: ReconcileStatus, scopeLabel?: string): string {
  const skipped = Number(latest.summary?.skipped_docs) || 0;
  const failed = Number(latest.summary?.failed_docs) || 0;
  const orphans = Number(latest.summary?.orphan_docs_deleted) || 0;
  return i18n.t("painel:reconcile.summary", {
    scope: scopeLabel ? i18n.t("painel:reconcile.scopeSuffix", { scope: scopeLabel }) : "",
    adjustments: i18n.t("painel:reconcile.summaryAdjustments", { count: latest.summary?.adjustments_applied ?? 0 }),
    indexed: i18n.t("painel:reconcile.summaryIndexed", { count: latest.summary?.indexed_docs ?? 0 }),
    skip: skipped > 0 ? i18n.t("painel:reconcile.summarySkip", { count: skipped }) : "",
    fail: failed > 0 ? i18n.t("painel:reconcile.summaryFail", { count: failed }) : "",
    orphan: orphans > 0 ? i18n.t("painel:reconcile.summaryOrphan", { count: orphans }) : "",
  });
}

/** Monitor de reconciliação sobre a ponte SSE→Query (F3): substitui as DUAS
 *  cópias do padrão SSE+poll que viviam no App (boot retomando reconcile em
 *  andamento + botão Reconciliar). Progresso e resumo viram mensagens de
 *  status; o término invalida stats/triagem/histórico. */
export function useReconcileMonitor({ onStatus }: { onStatus: (msg: string, severity?: StatusSeverity) => void }) {
  const scopeLabelRef = useRef<string | undefined>(undefined);
  const startedHereRef = useRef(false);

  const channel = useSseChannel<ReconcileStatus>({
    queryKey: qk.reconcileStatus(),
    fetchSnapshot: fetchReconcileStatus,
    streamUrl: getReconcileStatusStreamUrl,
    isActive: (status) => !!status.running,
    onFinished: (latest) => {
      invalidateAfterReconcile();
      // Resumo apenas quando houve uma execução observada (summary presente) —
      // um boot com status idle não deve anunciar "concluída"
      if (latest.summary && (startedHereRef.current || latest.last_run_finished_at)) {
        onStatus(summaryMessage(latest, scopeLabelRef.current));
      }
      startedHereRef.current = false;
      scopeLabelRef.current = undefined;
    },
    pollMs: 1500,
  });

  const status = channel.data ?? null;

  // Progresso ao vivo (SSE ou poll) vira o toast único de status
  useEffect(() => {
    if (status?.running) onStatus(progressMessage(status));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  return {
    reconcileStatus: status,
    reconciling: channel.active,
    /** Dispara a reconciliação e liga o acompanhamento. */
    start: async (projectId: string | undefined, scopeLabel: string) => {
      scopeLabelRef.current = scopeLabel;
      startedHereRef.current = true;
      onStatus(i18n.t("painel:reconcile.starting", { scope: scopeLabel }));
      await runReconcile(projectId);
      await channel.refresh();
    },
  };
}
