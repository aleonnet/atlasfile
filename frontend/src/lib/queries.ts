/** Hooks de leitura (TanStack Query) — invólucros finos sobre os wrappers de
 *  `api.ts`, que permanece a camada de transporte pura (e o alvo único de
 *  vi.mock nos testes). Nenhum componente chama useQuery com chave solta:
 *  toda chave nasce em `queryKeys.ts`. */
import { useQuery } from "@tanstack/react-query";
import {
  fetchIngestHistory,
  fetchInboxFiles,
  fetchLabelConflicts,
  fetchProjectProfile,
  fetchRejectedTriage,
  fetchTaxonomy,
  getTemplate,
  listTemplates,
} from "../api";
import { qk } from "./queryKeys";

/** Rejeitados da triagem (Painel, projeto único). */
export function useRejectedTriageQuery(projectId: string) {
  return useQuery({
    queryKey: qk.triage.rejected(projectId),
    queryFn: () => fetchRejectedTriage(projectId),
    enabled: !!projectId,
  });
}

/** Fila da INBOX (chips do Painel). */
export function useInboxFilesQuery(projectId: string) {
  return useQuery({
    queryKey: qk.inboxFiles(projectId),
    queryFn: () => fetchInboxFiles(projectId),
    enabled: !!projectId,
  });
}

/** Histórico de processamentos do projeto. */
export function useIngestHistoryQuery(projectId: string, enabled = true) {
  return useQuery({
    queryKey: qk.ingestHistory(projectId),
    queryFn: () => fetchIngestHistory(projectId),
    enabled: enabled && !!projectId,
  });
}

/** Profile completo do projeto (catálogo de domínios/tipos, layout, naming). */
export function useProjectProfileQuery(projectRef: string, enabled = true) {
  return useQuery({
    queryKey: qk.profile(projectRef),
    queryFn: () => fetchProjectProfile(projectRef),
    enabled: enabled && !!projectRef,
    staleTime: 5 * 60_000,
  });
}

/** Conflitos de rótulo (dataset) — global. */
export function useLabelConflictsQuery() {
  return useQuery({ queryKey: qk.labelConflicts(), queryFn: fetchLabelConflicts });
}

/** Taxonomia consolidada (domínios/tipos conhecidos) — quase-estática. */
export function useTaxonomyQuery() {
  return useQuery({ queryKey: qk.taxonomy(), queryFn: fetchTaxonomy, staleTime: 5 * 60_000 });
}

/** Lista de templates — quase-estática. */
export function useTemplatesQuery() {
  return useQuery({ queryKey: qk.templates.list(), queryFn: listTemplates, staleTime: 5 * 60_000 });
}

/** Detalhe de um template. */
export function useTemplateQuery(slug: string, enabled = true) {
  return useQuery({
    queryKey: qk.templates.detail(slug),
    queryFn: () => getTemplate(slug),
    enabled: enabled && !!slug,
  });
}
