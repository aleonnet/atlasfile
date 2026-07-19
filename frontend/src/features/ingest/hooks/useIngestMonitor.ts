import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { fetchIngestStatus, getIngestStatusStreamUrl } from "../../../api";
import { useSseChannel } from "../../../hooks/useSseChannel";
import { invalidateAfterScan } from "../../../lib/mutations";
import { qk } from "../../../lib/queryKeys";
import type { IngestOperationStatus } from "../../../types";

function buildPendingIngestStatus(projectId: string | null): IngestOperationStatus {
  return {
    last_run_started_at: null,
    last_run_finished_at: null,
    duration_seconds: null,
    project_id: projectId,
    running: true,
    phase: "starting",
    progress_current: 0,
    progress_total: 0,
    progress_file: null,
    processed_count: 0,
    failed_count: 0,
    last_error: null,
  };
}

/** Monitor de ingestão sobre a ponte única SSE→Query (F3): o snapshot vive no
 *  cache, o SSE alimenta, o poll só assume com o stream caído, e o término
 *  invalida os recursos afetados pelo scan. API pública preservada. */
export function useIngestMonitor() {
  const queryClient = useQueryClient();
  const channel = useSseChannel<IngestOperationStatus>({
    queryKey: qk.ingestStatus(),
    fetchSnapshot: fetchIngestStatus,
    streamUrl: getIngestStatusStreamUrl,
    isActive: (status) => !!status.running,
    onFinished: (status) => {
      if (status.last_run_finished_at) invalidateAfterScan();
    },
    pollMs: 500,
  });

  const setPending = useCallback(
    (projectId: string | null) => {
      // Cancela snapshot em voo: um idle atrasado não pode atropelar o placeholder
      void queryClient.cancelQueries({ queryKey: qk.ingestStatus() });
      queryClient.setQueryData(qk.ingestStatus(), buildPendingIngestStatus(projectId));
    },
    [queryClient]
  );

  const startMonitor = useCallback(
    (requestPromise: Promise<unknown>) => {
      // O canal liga sozinho ao ver running=true; ao settle da request, um
      // refresh garante o snapshot final mesmo se o SSE não tiver aberto.
      void requestPromise.finally(() => void channel.refresh());
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const refreshStatus = useCallback(() => {
    void channel.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    ingestStatus: channel.data ?? null,
    startMonitor,
    /** Sem-op: o canal fecha sozinho quando running=false (mantido por compat). */
    stopMonitor: () => {},
    setPending,
    refreshStatus,
  };
}
