import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

type UseSseChannelOptions<T> = {
  /** Chave do snapshot no cache (o dado vive no Query, não em useState). */
  queryKey: readonly unknown[];
  /** Snapshot via REST — usado no carregamento inicial e no poll de fallback. */
  fetchSnapshot: () => Promise<T>;
  /** URL do stream SSE (builder — inclui api_key). */
  streamUrl: () => string;
  /** O canal só abre SSE/poll enquanto o status indicar operação em curso. */
  isActive: (data: T) => boolean;
  /** Chamado quando o status transiciona ativo→terminado (invalidations).
   *  `meta.observedTransition` distingue um término REAL observado nesta
   *  sessão do disparo de boot com snapshot idle (que os consumidores não
   *  devem anunciar). */
  onFinished?: (data: T, meta: { observedTransition: boolean }) => void;
  /** Poll de fallback quando o SSE está caído (ms). */
  pollMs?: number;
  /** v0.50.1: poll LENTO enquanto idle (ms) — sem ele, um run iniciado pelo
   *  SERVIDOR (auto-ingest, auto-reconcile) é invisível até um reload: o SSE
   *  só abre com `active` e o poll de fallback também. 0/undefined desliga. */
  idlePollMs?: number;
  /** v0.50.1: identidade do último run terminado (ex.: last_run_finished_at).
   *  Se ela MUDA enquanto idle, um run inteiro aconteceu entre polls (curto
   *  demais para ser visto como running) — onFinished dispara mesmo assim. */
  runStamp?: (data: T) => unknown;
};

/** Ponte única SSE→TanStack Query (F3) — substitui as 3 cópias do padrão
 *  "SSE + fallback poll" (reconcile, ingest, ciclo do classificador).
 *
 *  Regras: o snapshot SEMPRE vive no cache (`setQueryData`); o poll de
 *  fallback só liga quando o SSE está caído E a operação está ativa — nunca
 *  SSE e poll simultâneos (fonte exclusiva, elimina a corrida das cópias
 *  antigas); o evento terminal fecha o stream e dispara `onFinished` para as
 *  invalidations dos recursos afetados. */
export function useSseChannel<T>({
  queryKey,
  fetchSnapshot,
  streamUrl,
  isActive,
  onFinished,
  pollMs = 1000,
  idlePollMs,
  runStamp,
}: UseSseChannelOptions<T>) {
  const queryClient = useQueryClient();
  const [sseConnected, setSseConnected] = useState(false);
  const finishedRef = useRef(false);
  const observedActiveRef = useRef(false);
  const lastStampRef = useRef<unknown>(undefined);
  const stampBaselinedRef = useRef(false);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;

  const snapshotQuery = useQuery({
    queryKey: queryKey as unknown[],
    queryFn: fetchSnapshot,
    refetchInterval: (query) => {
      const data = query.state.data as T | undefined;
      if (!data) return false;
      // Poll de fallback: operação ativa e SSE caído
      if (isActive(data)) return sseConnected ? false : pollMs;
      // Poll lento de vigia: detecta runs iniciados pelo servidor
      return idlePollMs && idlePollMs > 0 ? idlePollMs : false;
    },
    refetchIntervalInBackground: false,
  });

  const data = snapshotQuery.data as T | undefined;
  const active = data !== undefined && isActive(data);

  // Transição ativo→terminado — E término "perdido": se o runStamp muda
  // enquanto idle, um run inteiro rodou entre dois polls (curto demais para
  // aparecer como running); dispara onFinished do mesmo jeito.
  useEffect(() => {
    if (active) {
      observedActiveRef.current = true;
      finishedRef.current = false;
      return;
    }
    if (data === undefined) return;
    const stamp = runStamp?.(data);
    const stampChanged = runStamp !== undefined && stampBaselinedRef.current && stamp !== lastStampRef.current;
    if (runStamp !== undefined) {
      lastStampRef.current = stamp;
      stampBaselinedRef.current = true;
    }
    if (!finishedRef.current || stampChanged) {
      finishedRef.current = true;
      const observedTransition = observedActiveRef.current || stampChanged;
      observedActiveRef.current = false;
      onFinishedRef.current?.(data, { observedTransition });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, data]);

  // Canal SSE: abre enquanto ativo; cada evento vira snapshot no cache
  useEffect(() => {
    if (!active || typeof window === "undefined" || typeof window.EventSource === "undefined") return;
    const stream = new window.EventSource(streamUrl());
    setSseConnected(true);
    stream.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data) as T;
        queryClient.setQueryData(queryKey as unknown[], next);
      } catch {
        /* frame inválido — ignora */
      }
    };
    stream.onerror = () => {
      // SSE caiu: fecha e deixa o poll de fallback assumir (refetchInterval)
      stream.close();
      setSseConnected(false);
    };
    return () => {
      stream.close();
      setSseConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  return {
    /** Snapshot corrente (do cache). */
    data,
    /** Operação em curso? */
    active,
    /** Reconsulta imediata do snapshot (ex.: logo após disparar a operação). */
    refresh: () => queryClient.invalidateQueries({ queryKey: queryKey as unknown[] }),
  };
}
