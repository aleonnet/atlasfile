import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchDocuments } from "../api";
import { useProject } from "../contexts/ProjectContext";
import { qk } from "../lib/queryKeys";

/** Busca rápida da CommandPalette (⌘K) — autônoma, padrão VS Code/Slack:
 *  dona do próprio input; resultados no cache por chave (a mesma busca na
 *  página cheia reaproveita o aquecimento). Handoff para a busca completa é
 *  navegação com intent (NavigationContext.requestSearch), nunca estado
 *  compartilhado. */
export function useQuickSearch() {
  const { selectedProject, selectedProjectScope } = useProject();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 220);
    return () => window.clearTimeout(timer);
  }, [query]);

  const hitsQuery = useQuery({
    queryKey: qk.search(selectedProjectScope, { q: debounced, quick: true }),
    queryFn: () => searchDocuments(debounced, selectedProjectScope, 1, 6),
    enabled: open && debounced.length >= 2,
    staleTime: 30_000,
  });

  // Atalho ⌘K / Ctrl+K (Escape com input vazio fecha)
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      if (isCmdK) {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape" && open && !query.trim()) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, query]);

  // Trocar de projeto invalida o contexto visual do modal
  useEffect(() => {
    setQuery("");
  }, [selectedProject]);

  return {
    query,
    setQuery,
    open,
    setOpen,
    hits: open && debounced.length >= 2 ? hitsQuery.data?.hits ?? [] : [],
    loading: hitsQuery.isFetching,
  };
}
