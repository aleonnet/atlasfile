import { useCallback, useRef, useState } from "react";
import { fetchClassifierCycleStatus, getClassifierCycleStatusStreamUrl } from "../../../api";
import type { ClassifierCycleStatus } from "../../../types";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export function useClassifierCycleMonitor(onFinish?: () => void) {
  const [cycleStatus, setCycleStatus] = useState<ClassifierCycleStatus | null>(null);
  const monitorStopRef = useRef<(() => void) | null>(null);

  const stopMonitor = useCallback(() => {
    monitorStopRef.current?.();
    monitorStopRef.current = null;
  }, []);

  const startMonitor = useCallback(() => {
    stopMonitor();
    let cancelled = false;
    let stream: EventSource | null = null;

    const closeStream = () => {
      stream?.close();
      stream = null;
    };

    const applyStatus = (data: ClassifierCycleStatus) => {
      if (!cancelled) {
        setCycleStatus(data);
      }
    };

    const finish = () => {
      if (!cancelled) {
        onFinish?.();
      }
    };

    const pollUntilFinished = async (): Promise<void> => {
      while (!cancelled) {
        try {
          const latest = await fetchClassifierCycleStatus();
          if (cancelled) return;
          applyStatus(latest);
          if (latest.running && typeof window !== "undefined" && typeof window.EventSource !== "undefined") {
            closeStream();
            stream = new window.EventSource(getClassifierCycleStatusStreamUrl());
            stream.onmessage = (event) => {
              try {
                const data = JSON.parse(event.data) as ClassifierCycleStatus;
                applyStatus(data);
                if (!data.running) {
                  closeStream();
                  finish();
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
          if (!latest.running) {
            finish();
            return;
          }
        } catch {
          /* ignore */
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
  }, [onFinish, stopMonitor]);

  return {
    cycleStatus,
    setCycleStatus,
    startMonitor,
    stopMonitor,
  };
}
