import { useTranslation } from "react-i18next";
import { Badge } from "./ui/badge";

/** Cabeçalho rico de projeto (ícone + "Project: label" + badge do profile +
 *  ID/Versão/Última alteração) — extraído do ProfileLayoutWorkspace para as
 *  telas que operam sobre o profile do projeto (Configuração, Classificador)
 *  falarem a mesma língua visual. Reusa as chaves i18n profileLayout.workspace. */
export function ProjectHeaderMeta({
  icon,
  projectLabel,
  projectId,
  version,
  updatedBy,
  extra,
}: {
  icon: React.ReactNode;
  projectLabel: string;
  projectId: string;
  version?: number | null;
  updatedBy?: string | null;
  extra?: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex w-full flex-row flex-wrap items-center justify-between gap-x-4 gap-y-1">
      <span className="flex min-h-9 items-center gap-2 font-display text-base font-bold leading-tight text-foreground-strong">
        {icon}
        {t("profileLayout:workspace.projectTitle", { label: projectLabel })}
        <Badge variant="outline">{t("profileLayout:workspace.profileBadge")}</Badge>
        {extra}
      </span>
      <span className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.7rem] text-tertiary">
        <span>{t("profileLayout:workspace.idLabel")} <span className="text-muted-foreground">{projectId}</span></span>
        {version != null && (
          <span>{t("profileLayout:workspace.versionLabel")} <span className="text-foreground">{version}</span></span>
        )}
        {updatedBy && (
          <span>{t("profileLayout:workspace.lastLabel")} <span className="text-foreground">{updatedBy}</span></span>
        )}
      </span>
    </div>
  );
}
