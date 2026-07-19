import { useEffect, useRef } from "react";
import { fetchReconcileStatus, getReconcileStatusStreamUrl, runReconcile } from "../api";
import { invalidateAfterReconcile } from "../lib/mutations";
import { qk } from "../lib/queryKeys";
import { useSseChannel } from "./useSseChannel";
import type { ReconcileStatus } from "../types";

function progressMessage(latest: ReconcileStatus): string {
  const proj = latest.progress_project ?? "—";
  const file = latest.progress_file ?? "—";
  const skip = (latest.progress_skipped ?? 0) > 0 ? ` (skip: ${latest.progress_skipped})` : "";
  return `Reconciliando: ${latest.progress_current ?? 0} / ${latest.progress_total ?? 0} docs | Projeto: ${proj} | Arquivo: ${file}${skip}`;
}

function summaryMessage(latest: ReconcileStatus, scopeLabel?: string): string {
  const skipMsg = Number(latest.summary?.skipped_docs) > 0 ? `, ${latest.summary?.skipped_docs} skip (inalterados)` : "";
  const failMsg = Number(latest.summary?.failed_docs) > 0 ? `, ${latest.summary?.failed_docs} falha(s)` : "";
  const orphanMsg =
    Number(latest.summary?.orphan_docs_deleted) > 0 ? `, ${latest.summary?.orphan_docs_deleted} orfao(s) removido(s)` : "";
  const scope = scopeLabel ? ` (${scopeLabel})` : "";
  return `Reconciliacao concluida${scope}: ${latest.summary?.adjustments_applied ?? 0} ajuste(s), ${latest.summary?.indexed_docs ?? 0} doc(s) indexado(s)${skipMsg}${failMsg}${orphanMsg}`;
}

/** Monitor de reconciliação sobre a ponte SSE→Query (F3): substitui as DUAS
 *  cópias do padrão SSE+poll que viviam no App (boot retomando reconcile em
 *  andamento + botão Reconciliar). Progresso e resumo viram mensagens de
 *  status; o término invalida stats/triagem/histórico. */
export function useReconcileMonitor({ onStatus }: { onStatus: (msg: string) => void }) {
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
      onStatus(`Iniciando reconciliacao de ${scopeLabel}...`);
      await runReconcile(projectId);
      await channel.refresh();
    },
  };
}
