import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStats, searchDocuments } from "../api";
import i18n from "../i18n";
import { useNavigation } from "../contexts/NavigationContext";
import { useProject } from "../contexts/ProjectContext";
import { qk } from "../lib/queryKeys";
import type { SearchFilters, StatsResponse, StatusSeverity } from "../types";

type UsePainelSearchOptions = {
  onStatus: (message: string, severity?: StatusSeverity) => void;
};

type SubmittedSearch = {
  q: string;
  page: number;
  filters: SearchFilters;
};

function activeFilters(filters: SearchFilters): SearchFilters | undefined {
  const out: SearchFilters = {};
  if (filters.doc_kind) out.doc_kind = filters.doc_kind;
  if (filters.document_type) out.document_type = filters.document_type;
  if (filters.business_domain) out.business_domain = filters.business_domain;
  return Object.keys(out).length > 0 ? out : undefined;
}

/** Busca completa do Painel — dona do próprio estado de UI (input, filtros,
 *  página); RESULTADOS vivem no cache por chave [projeto, params] (server
 *  state). Recebe o handoff da paleta via intent de navegação. */
export function usePainelSearch({ onStatus }: UsePainelSearchOptions) {
  const { selectedProjectScope } = useProject();
  const { searchIntent, clearSearchIntent } = useNavigation();
  const [fullSearchInput, setFullSearchInput] = useState("");
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [submitted, setSubmitted] = useState<SubmittedSearch | null>(null);

  const resultsQuery = useQuery({
    queryKey: qk.search(selectedProjectScope, submitted ?? {}),
    queryFn: () =>
      searchDocuments(submitted!.q, selectedProjectScope, submitted!.page, 20, activeFilters(submitted!.filters)),
    enabled: !!submitted && submitted.q.length >= 2,
    staleTime: 30_000,
  });

  const statsQuery = useQuery({
    queryKey: qk.stats(selectedProjectScope),
    queryFn: () => fetchStats(selectedProjectScope),
    enabled: !!submitted,
    staleTime: 60_000,
  });

  // Contagem de resultados como status (comportamento preservado)
  useEffect(() => {
    if (resultsQuery.data && submitted) onStatus(i18n.t("common:unit.result", { count: resultsQuery.data.total }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultsQuery.data]);

  useEffect(() => {
    if (resultsQuery.isError) onStatus(i18n.t("errors:api.search"), "error");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultsQuery.isError]);

  function runFullSearch(page = 1, overrideQuery?: string, overrideFilters?: SearchFilters) {
    const q = (overrideQuery ?? fullSearchInput).trim();
    if (q.length < 2) return;
    const filters = overrideFilters ?? searchFilters;
    setFullSearchInput(q);
    setSubmitted({ q, page, filters });
  }

  function clearSearch() {
    setFullSearchInput("");
    setSearchFilters({});
    setSubmitted(null);
    onStatus(i18n.t("painel:app.searchCleared"));
  }

  // Handoff da paleta (intent de navegação): semeia e dispara a busca
  useEffect(() => {
    if (searchIntent) {
      setFullSearchInput(searchIntent);
      setSubmitted({ q: searchIntent, page: 1, filters: searchFilters });
      clearSearchIntent();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchIntent]);

  const data = submitted ? resultsQuery.data : undefined;
  return {
    fullQuery: submitted?.q ?? "",
    fullResults: data?.hits ?? [],
    fullPage: data?.page ?? submitted?.page ?? 1,
    fullTotalPages: data?.total_pages ?? 1,
    fullTotal: data?.total ?? 0,
    fullLoading: !!submitted && resultsQuery.isFetching,
    fullSearchInput,
    setFullSearchInput,
    searchFilters,
    setSearchFilters,
    searchStats: (submitted ? statsQuery.data : null) as StatsResponse | null,
    runFullSearch,
    clearSearch,
  };
}
