import { useEffect, useState } from "react";
import { fetchStats, searchDocuments } from "../api";
import { ALL_PROJECTS, useProject } from "../contexts/ProjectContext";
import type { SearchFilters, SearchHit, StatsResponse } from "../types";

type UseSearchOptions = {
  onStatus: (message: string) => void;
};

/** Estado e ações da busca (modal ⌘K + resultados completos do Painel). */
export function useSearch({ onStatus }: UseSearchOptions) {
  const { selectedProject, selectedProjectScope } = useProject();
  const [query, setQuery] = useState("");
  const [modalHits, setModalHits] = useState<SearchHit[]>([]);
  const [searchModalOpen, setSearchModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [fullResults, setFullResults] = useState<SearchHit[]>([]);
  const [fullQuery, setFullQuery] = useState("");
  const [fullPage, setFullPage] = useState(1);
  const [fullTotalPages, setFullTotalPages] = useState(1);
  const [fullTotal, setFullTotal] = useState(0);
  const [fullLoading, setFullLoading] = useState(false);
  const [fullSearchInput, setFullSearchInput] = useState("");
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [searchStats, setSearchStats] = useState<StatsResponse | null>(null);

  function clearSearch() {
    setQuery("");
    setModalHits([]);
    setFullResults([]);
    setFullQuery("");
    setFullSearchInput("");
    setFullPage(1);
    setFullTotalPages(1);
    setFullTotal(0);
    setSearchFilters({});
    setSearchStats(null);
    onStatus("Busca limpa");
  }

  async function loadModalTopHits() {
    const q = query.trim();
    if (q.length < 2) {
      setModalHits([]);
      return;
    }
    setModalLoading(true);
    try {
      const data = await searchDocuments(q, selectedProjectScope, 1, 6);
      setModalHits(data.hits);
    } catch {
      setModalHits([]);
    } finally {
      setModalLoading(false);
    }
  }

  async function runFullSearch(page = 1, overrideQuery?: string, overrideFilters?: SearchFilters) {
    const q = (overrideQuery ?? (fullSearchInput || query)).trim();
    if (q.length < 2) return;
    const filters = overrideFilters ?? searchFilters;
    const activeFilters: SearchFilters = {};
    if (filters.doc_kind) activeFilters.doc_kind = filters.doc_kind;
    if (filters.document_type) activeFilters.document_type = filters.document_type;
    if (filters.business_domain) activeFilters.business_domain = filters.business_domain;
    setFullLoading(true);
    try {
      const data = await searchDocuments(
        q,
        selectedProjectScope,
        page,
        20,
        Object.keys(activeFilters).length > 0 ? activeFilters : undefined
      );
      setFullQuery(q);
      setFullSearchInput(q);
      setFullResults(data.hits);
      setFullPage(data.page);
      setFullTotal(data.total);
      setFullTotalPages(data.total_pages);
      onStatus(`${data.total} resultado(s)`);
      if (!searchStats) {
        fetchStats(selectedProjectScope).then(setSearchStats).catch(() => {});
      }
    } catch {
      onStatus("Falha na busca");
    } finally {
      setFullLoading(false);
    }
  }

  // Debounce da busca do modal
  useEffect(() => {
    const q = query.trim();
    if (!searchModalOpen || q.length < 2) {
      setModalHits([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void loadModalTopHits();
    }, 220);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, selectedProject, searchModalOpen]);

  // Atalho ⌘K / Ctrl+K
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      if (isCmdK) {
        e.preventDefault();
        setSearchModalOpen(true);
      }
      if (e.key === "Escape" && searchModalOpen && !query.trim()) {
        setSearchModalOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [searchModalOpen, query]);

  return {
    query,
    setQuery,
    modalHits,
    modalLoading,
    searchModalOpen,
    setSearchModalOpen,
    fullResults,
    fullQuery,
    fullPage,
    fullTotalPages,
    fullTotal,
    fullLoading,
    fullSearchInput,
    setFullSearchInput,
    searchFilters,
    setSearchFilters,
    searchStats,
    clearSearch,
    runFullSearch,
  };
}

export { ALL_PROJECTS };
