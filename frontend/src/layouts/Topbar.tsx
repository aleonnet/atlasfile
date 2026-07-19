import { ChevronRight } from "lucide-react";
import { useProject } from "../contexts/ProjectContext";
import { useNavigation, type ViewKind } from "../contexts/NavigationContext";

const VIEW_LABEL: Record<ViewKind, string> = {
  painel: "Painel",
  assistente: "Assistente",
  classificador: "Classificador",
  config: "Configuração",
};

type Props = {
  /** Ações contextuais à direita (ex.: botão dev de onboarding). */
  children?: React.ReactNode;
};

/** Topbar reduzida: breadcrumb da seção + ações contextuais. A navegação vive na sidebar. */
export function Topbar({ children }: Props) {
  const { view } = useNavigation();
  const { selectedProjectLabel } = useProject();

  return (
    <header className="sticky top-0 z-20 flex h-12 shrink-0 items-center justify-between border-b border-border bg-[var(--bg-translucent)] px-5 backdrop-blur-md">
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-sm">
        <span className="font-display font-semibold text-foreground-strong">{VIEW_LABEL[view]}</span>
        <ChevronRight size={13} className="shrink-0 text-tertiary" aria-hidden />
        <span className="truncate font-mono text-xs text-muted-foreground">{selectedProjectLabel}</span>
      </nav>
      <div className="flex items-center gap-2">{children}</div>
    </header>
  );
}
