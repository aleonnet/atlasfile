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
  /** Chamado UMA vez quando o status transiciona ativo→terminado (invalidations). */
  onFinished?: (data: T) => void;
  /** Poll de fallback quando o SSE está caído (ms). */
  pollMs?: number;
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
}: UseSseChannelOptions<T>) {
  const queryClient = useQueryClient();
  const [sseConnected, setSseConnected] = useState(false);
  const finishedRef = useRef(false);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;

  const snapshotQuery = useQuery({
    queryKey: queryKey as unknown[],
    queryFn: fetchSnapshot,
    // Poll de fallback: apenas com operação ativa e SSE caído
    refetchInterval: (query) => {
      const data = query.state.data as T | undefined;
      if (!data || !isActive(data) || sseConnected) return false;
      return pollMs;
    },
    refetchIntervalInBackground: false,
  });

  const data = snapshotQuery.data as T | undefined;
  const active = data !== undefined && isActive(data);

  // Transição ativo→terminado: onFinished uma única vez por operação
  useEffect(() => {
    if (active) {
      finishedRef.current = false;
      return;
    }
    if (data !== undefined && !finishedRef.current) {
      finishedRef.current = true;
      onFinishedRef.current?.(data);
    }
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
