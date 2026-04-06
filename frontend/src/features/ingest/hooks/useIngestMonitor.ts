import { useCallback, useRef, useState } from "react";
import { fetchIngestStatus, getIngestStatusStreamUrl } from "../../../api";
import type { IngestOperationStatus } from "../../../types";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

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

export function useIngestMonitor() {
  const [ingestStatus, setIngestStatus] = useState<IngestOperationStatus | null>(null);
  const monitorStopRef = useRef<(() => void) | null>(null);

  const stopMonitor = useCallback(() => {
    monitorStopRef.current?.();
    monitorStopRef.current = null;
  }, []);

  const startMonitor = useCallback(
    (requestPromise: Promise<unknown>) => {
      stopMonitor();
      let cancelled = false;
      let requestSettled = false;
      let stream: EventSource | null = null;

      void requestPromise.finally(() => {
        requestSettled = true;
      });

      const closeStream = () => {
        stream?.close();
        stream = null;
      };

      const applyStatus = (data: IngestOperationStatus) => {
        if (!cancelled) {
          setIngestStatus(data);
        }
      };

      const pollUntilFinished = async (): Promise<void> => {
        while (!cancelled) {
          try {
            const latest = await fetchIngestStatus();
            if (cancelled) return;
            applyStatus(latest);
            if (latest.running && typeof window !== "undefined" && typeof window.EventSource !== "undefined") {
              closeStream();
              stream = new window.EventSource(getIngestStatusStreamUrl());
              stream.onmessage = (event) => {
                try {
                  const data = JSON.parse(event.data) as IngestOperationStatus;
                  applyStatus(data);
                  if (!data.running) {
                    closeStream();
                  }
                } catch {
                  /* ignore */
                }
              };
              stream.onerror = () => {
                closeStream();
                if (!cancelled) {
                  void pollUntilFinished();
                }
              };
              return;
            }
            if (!latest.running && requestSettled) {
              return;
            }
          } catch {
            if (requestSettled) {
              return;
            }
          }
          await sleep(250);
        }
      };

      void pollUntilFinished();

      const stop = () => {
        cancelled = true;
        closeStream();
      };
      monitorStopRef.current = stop;
      return stop;
    },
    [stopMonitor]
  );

  const setPending = useCallback((projectId: string | null) => {
    setIngestStatus(buildPendingIngestStatus(projectId));
  }, []);

  const refreshStatus = useCallback(() => {
    void fetchIngestStatus().then(setIngestStatus).catch(() => {});
  }, []);

  return {
    ingestStatus,
    setIngestStatus,
    startMonitor,
    stopMonitor,
    setPending,
    refreshStatus,
  };
}
