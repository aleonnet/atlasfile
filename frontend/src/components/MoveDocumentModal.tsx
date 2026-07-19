import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MiniOrb } from "./ui/processing-aura";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { Button } from "./ui/button";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "./ui/modal-shell";
import type { ProjectArea, ProjectDocumentType } from "../types";

type Props = {
  open: boolean;
  filename: string;
  currentBusinessDomain: string;
  currentDocumentType: string;
  businessDomainOptions: ProjectArea[];
  documentTypeOptions: ProjectDocumentType[];
  onCancel: () => void;
  onConfirm: (targetBd: string, targetDt: string) => void;
  submitting?: boolean;
  errorMessage?: string | null;
};

export function MoveDocumentModal({
  open,
  filename,
  currentBusinessDomain,
  currentDocumentType,
  businessDomainOptions,
  documentTypeOptions,
  onCancel,
  onConfirm,
  submitting,
  errorMessage,
}: Props) {
  const { t } = useTranslation();
  const [bdValue, setBdValue] = useState(currentBusinessDomain);
  const [dtValue, setDtValue] = useState(currentDocumentType);

  useEscapeKey(open ? onCancel : null);

  // Sync defaults when modal opens with new doc
  const [prevFilename, setPrevFilename] = useState(filename);
  if (filename !== prevFilename) {
    setPrevFilename(filename);
    setBdValue(currentBusinessDomain);
    setDtValue(currentDocumentType);
  }

  if (!open) return null;

  const changed = bdValue !== currentBusinessDomain || dtValue !== currentDocumentType;

  return (
    <ModalShell label={t("painel:moveModal.title")} title={t("painel:moveModal.title")}>
      <p className="text-sm">
        {t("painel:moveModal.fileLabel")} <strong className="text-foreground-strong">{filename}</strong>
      </p>
      <p className="mt-0.5 font-mono text-[0.7rem] text-tertiary">
        {t("painel:moveModal.origin", { businessDomain: currentBusinessDomain, documentType: currentDocumentType })}
      </p>

      <label className={fieldLabelClass} htmlFor="move-bd-select">{t("painel:moveModal.domainLabel")}</label>
      <select
        id="move-bd-select"
        className={nativeSelectClass}
        value={bdValue}
        onChange={(e) => setBdValue(e.target.value)}
        disabled={submitting}
      >
        {businessDomainOptions.map((area) => (
          <option key={area.key} value={area.key}>
            {area.label} ({area.key})
          </option>
        ))}
      </select>

      <label className={fieldLabelClass} htmlFor="move-dt-select">{t("painel:moveModal.typeLabel")}</label>
      <select
        id="move-dt-select"
        className={nativeSelectClass}
        value={dtValue}
        onChange={(e) => setDtValue(e.target.value)}
        disabled={submitting}
      >
        {documentTypeOptions.map((dt) => (
          <option key={dt.key} value={dt.key}>
            {dt.label} ({dt.key})
          </option>
        ))}
      </select>

      {changed && !errorMessage && (
        <p className="mt-3 rounded-md bg-accent-soft px-3 py-2 font-mono text-[0.75rem] text-accent">
          {t("painel:moveModal.summary", {
            fromBd: currentBusinessDomain,
            fromDt: currentDocumentType,
            toBd: bdValue,
            toDt: dtValue,
          })}
        </p>
      )}

      {errorMessage && (
        <p className="mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[0.8rem] text-destructive">
          {errorMessage}
        </p>
      )}

      <ModalActions>
        <Button variant="secondary" disabled={submitting} onClick={onCancel}>
          {t("common:action.cancel")}
        </Button>
        <Button disabled={submitting || !changed || !bdValue || !dtValue} onClick={() => onConfirm(bdValue, dtValue)}>
          {submitting ? <><MiniOrb className="size-3" /> {t("painel:moveModal.moving")}</> : t("common:action.confirm")}
        </Button>
      </ModalActions>
    </ModalShell>
  );
}
