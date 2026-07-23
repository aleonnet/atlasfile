/** Invalidations por domínio (F2) — cada mutação derruba exatamente os caches
 *  que o backend alterou. Substituem o bus `atlas:data-refresh` (amplo e cego):
 *  a granularidade aqui é o contrato de reatividade do app. Usam o queryClient
 *  singleton para poderem ser chamadas fora de componentes (portal, SSE). */
import { queryClient } from "./queryClient";
import { qk } from "./queryKeys";

function invalidate(keys: readonly (readonly unknown[])[]): void {
  for (const queryKey of keys) {
    void queryClient.invalidateQueries({ queryKey: queryKey as unknown[] });
  }
}

/** Decisão de triagem (aprovar/corrigir/rejeitar) ou restauração/exclusão de
 *  rejeitado: mexe em fila, índice, histórico, datasets e conflitos. */
export function invalidateAfterTriageDecision(): void {
  invalidate([
    qk.triage.scope(),
    ["stats"],
    ["ingest-history"],
    qk.labelConflicts(),
    qk.classifier.scope(),
  ]);
}

/** Scan da INBOX concluído (portal ou botão): novos docs, fila e histórico. */
export function invalidateAfterScan(): void {
  invalidate([
    qk.triage.scope(),
    ["stats"],
    ["inbox-files"],
    ["ingest-history"],
    qk.classifier.scope(),
  ]);
}

/** Reconciliação concluída: índice ajustado (órfãos removidos, docs indexados). */
export function invalidateAfterReconcile(): void {
  invalidate([["stats"], qk.triage.scope(), ["ingest-history"], qk.reconcileStatus()]);
}

/** Profile salvo/layout aplicado/política LLM alterada: catálogo do projeto,
 *  labels da sidebar e pastas mudam. */
export function invalidateAfterProfileChange(projectRef?: string): void {
  invalidate([
    projectRef ? qk.profile(projectRef) : ["profile"],
    qk.projects(),
    ["stats"],
    qk.taxonomy(),
  ]);
}

/** Migração/remoção de taxonomia: move físico + índice + datasets + templates. */
export function invalidateAfterTaxonomyChange(): void {
  invalidate([
    qk.taxonomy(),
    ["profile"],
    qk.templates.scope(),
    ["stats"],
    ["ingest-history"],
    qk.classifier.scope(),
    ["search"],
    ["alias-suggestions"],
  ]);
}

/** Documento movido de domínio/tipo (histórico ou busca). */
export function invalidateAfterMove(): void {
  invalidate([["ingest-history"], ["stats"], ["search"], qk.classifier.scope()]);
}
