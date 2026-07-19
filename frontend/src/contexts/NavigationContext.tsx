import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type ViewKind = "painel" | "assistente" | "config";

const VIEWS: ViewKind[] = ["painel", "assistente", "config"];

function viewFromHash(hash: string): ViewKind | null {
  const clean = hash.replace(/^#\/?/, "").split("?")[0];
  return (VIEWS as string[]).includes(clean) ? (clean as ViewKind) : null;
}

type NavigationContextValue = {
  /** Intent de busca do handoff paleta→Painel (análogo de query-param de rota). */
  searchIntent: string | null;
  /** Navega ao Painel carregando a busca — o padrão VS Code/Slack de handoff. */
  requestSearch: (query: string) => void;
  clearSearchIntent: () => void;
  view: ViewKind;
  setView: (view: ViewKind) => void;
};

const NavigationContext = createContext<NavigationContextValue | null>(null);

/** Navegação por hash (deep-link barato, sem react-router). */
export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const [view, setViewState] = useState<ViewKind>(() => {
    if (typeof window === "undefined") return "painel";
    return viewFromHash(window.location.hash) ?? "painel";
  });

  useEffect(() => {
    const onHashChange = () => {
      const next = viewFromHash(window.location.hash);
      if (next) setViewState(next);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const [searchIntent, setSearchIntent] = useState<string | null>(null);
  const requestSearch = useCallback((query: string) => {
    setSearchIntent(query);
    setViewState("painel");
    window.location.hash = "#/painel";
  }, []);
  const clearSearchIntent = useCallback(() => setSearchIntent(null), []);

  const setView = useCallback((next: ViewKind) => {
    setViewState(next);
    try {
      // replaceState evita poluir o histórico a cada troca de aba
      window.history.replaceState(null, "", `#/${next}`);
    } catch {
      window.location.hash = `/${next}`;
    }
  }, []);

  const value = useMemo(
    () => ({ view, setView, searchIntent, requestSearch, clearSearchIntent }),
    [view, setView, searchIntent, requestSearch, clearSearchIntent]
  );
  return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>;
}

export function useNavigation(): NavigationContextValue {
  const context = useContext(NavigationContext);
  if (!context) throw new Error("useNavigation deve ser usado dentro de <NavigationProvider>");
  return context;
}
