/** Bus mínimo de reatividade — EM MIGRAÇÃO para TanStack Query (F1→F2).
 *
 *  F1 (atual): os emissores existentes continuam; um adaptador único traduz o
 *  evento para invalidations de cache — componentes já migrados para useQuery
 *  atualizam via cache e param de assinar o bus diretamente.
 *  F2: emissores viram useMutation com invalidations específicas e este canal
 *  morre; o arquivo fica só com o sinal de UI `atlas:ingest-active` (orb). */
import { queryClient } from "./queryClient";
import { qk } from "./queryKeys";

const EVENT = "atlas:data-refresh";

export function emitDataRefresh(): void {
  window.dispatchEvent(new CustomEvent(EVENT));
}

/** Assina o evento; retorna o unsubscribe (usar no cleanup do useEffect). */
export function onDataRefresh(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}

/** Adaptador transitório F1: evento legado → invalidation dos recursos que os
 *  antigos assinantes recarregavam. Amplo por design (o evento não tem payload);
 *  a granularidade fina chega na F2 com as mutations. */
export function installRefreshBusQueryAdapter(): () => void {
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: qk.triage.scope() });
    void queryClient.invalidateQueries({ queryKey: ["stats"] });
    void queryClient.invalidateQueries({ queryKey: ["inbox-files"] });
    void queryClient.invalidateQueries({ queryKey: ["ingest-history"] });
    void queryClient.invalidateQueries({ queryKey: qk.labelConflicts() });
    void queryClient.invalidateQueries({ queryKey: qk.projects() });
    void queryClient.invalidateQueries({ queryKey: ["profile"] });
    void queryClient.invalidateQueries({ queryKey: qk.classifier.scope() });
  };
  window.addEventListener(EVENT, invalidate);
  return () => window.removeEventListener(EVENT, invalidate);
}
