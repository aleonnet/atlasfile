import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useProject } from "../contexts/ProjectContext";
import { useNavigation, type ViewKind } from "../contexts/NavigationContext";

// Chaves (não textos) em escopo de módulo: o texto resolve no render, então a
// troca de idioma ao vivo (i18n.changeLanguage) atualiza sem reload.
const VIEW_LABEL_KEY: Record<ViewKind, string> = {
  painel: "painel:shell.navPainel",
  assistente: "painel:shell.navAssistente",
  classificador: "painel:shell.navClassificador",
  config: "painel:shell.navConfig",
};

type Props = {
  /** Ações contextuais à direita (ex.: botão dev de onboarding). */
  children?: React.ReactNode;
};

/** Topbar reduzida: breadcrumb da seção + ações contextuais. A navegação vive na sidebar. */
export function Topbar({ children }: Props) {
  const { t } = useTranslation();
  const { view } = useNavigation();
  const { selectedProjectLabel } = useProject();

  return (
    <header className="sticky top-0 z-20 flex h-12 shrink-0 items-center justify-between border-b border-border bg-[var(--bg-translucent)] px-5 backdrop-blur-md">
      <nav aria-label={t("painel:shell.breadcrumbAria")} className="flex min-w-0 items-center gap-1.5 text-sm">
        <span className="font-display font-semibold text-foreground-strong">{t(VIEW_LABEL_KEY[view])}</span>
        <ChevronRight size={13} className="shrink-0 text-tertiary" aria-hidden />
        <span className="truncate font-mono text-xs text-muted-foreground">{selectedProjectLabel}</span>
      </nav>
      <div className="flex items-center gap-2">{children}</div>
    </header>
  );
}
