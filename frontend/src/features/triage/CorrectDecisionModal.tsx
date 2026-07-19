import { useTranslation } from "react-i18next";
import { Button } from "../../components/ui/button";
import { MiniOrb } from "../../components/ui/processing-aura";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "../../components/ui/modal-shell";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import type { ProjectArea, ProjectDocumentType, TriageItem } from "../../types";

type Props = {
  item: TriageItem | null;
  submitting: boolean;
  businessDomainValue: string;
  businessDomainOptions: ProjectArea[];
  documentTypeValue: string;
  documentTypeOptions: ProjectDocumentType[];
  onChangeBusinessDomain: (value: string) => void;
  onChangeDocumentType: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
  /** Abre a criação governada de taxonomia (novo domínio/tipo) sem sair do fluxo. */
  onCreateTaxonomyEntry?: () => void;
};

const warningClass =
  "mt-3 rounded-md border border-accent/30 bg-accent-soft px-3 py-2 text-[0.78rem] text-foreground [&_code]:font-mono [&_code]:text-accent";

export function CorrectDecisionModal({
  item,
  submitting,
  businessDomainValue,
  businessDomainOptions,
  documentTypeValue,
  documentTypeOptions,
  onChangeBusinessDomain,
  onChangeDocumentType,
  onCancel,
  onSubmit,
  onCreateTaxonomyEntry
}: Props) {
  const { t } = useTranslation();
  useEscapeKey(item ? onCancel : null);

  if (!item) return null;

  const existingDomains = new Set(businessDomainOptions.map((a) => a.key));
  const existingDocumentTypes = new Set(documentTypeOptions.map((a) => a.key));
  const suggestedBusinessDomain = (item.suggested_business_domain || "").trim();
  const suggestedDocumentType = (item.suggested_document_type || "").trim();
  const llmProposedBusinessDomain = (item.llm_proposed_business_domain || "").trim();
  const suggestedBusinessDomainMissing = !!suggestedBusinessDomain && !existingDomains.has(suggestedBusinessDomain);
  const suggestedDocumentTypeMissing = !!suggestedDocumentType && !existingDocumentTypes.has(suggestedDocumentType);
  const llmProposedBusinessDomainMissing =
    !!llmProposedBusinessDomain &&
    llmProposedBusinessDomain !== suggestedBusinessDomain &&
    !existingDomains.has(llmProposedBusinessDomain);

  function handleSubmit() {
    onSubmit();
  }

  return (
    <ModalShell label={t("triage:correctModal.label")} title={t("triage:correctModal.title")}>
      <p className="text-sm">
        {t("triage:correctModal.fileLabel")} <strong className="text-foreground-strong">{item.filename}</strong>
      </p>

      {item.llm_explanation && (
        <div className="mt-3 space-y-0.5 rounded-md bg-panel-strong p-2.5 font-mono text-[0.72rem] text-muted-foreground">
          {item.rule_business_domain && (
            <p>
              regra: <span className="text-accent-light">{item.rule_business_domain}</span> (conf{" "}
              {(item.rule_confidence ?? 0).toFixed(2)})
            </p>
          )}
          <p className="text-foreground/80">LLM: {item.llm_explanation}</p>
          {item.llm_proposed_business_domain && (
            <p>
              domínio proposto: <span className="text-accent-purple">{item.llm_proposed_business_domain}</span>
            </p>
          )}
        </div>
      )}

      {suggestedBusinessDomainMissing && (
        <p className={warningClass}>
          {t("triage:correctModal.domainMissingBefore")} <code>{suggestedBusinessDomain}</code>{" "}
          {t("triage:correctModal.domainMissingAfter")}
        </p>
      )}

      {llmProposedBusinessDomainMissing && (
        <p className={warningClass}>
          {t("triage:correctModal.llmDomainMissingBefore")} <code>{llmProposedBusinessDomain}</code>{" "}
          {t("triage:correctModal.llmDomainMissingAfter")}
        </p>
      )}

      {suggestedDocumentTypeMissing && (
        <p className={warningClass}>
          {t("triage:correctModal.typeMissingBefore")} <code>{suggestedDocumentType}</code>{" "}
          {t("triage:correctModal.typeMissingAfter")}
        </p>
      )}

      <label className={fieldLabelClass} htmlFor="business-domain-select">{t("triage:correctModal.targetDomain")}</label>
      <select
        id="business-domain-select"
        className={nativeSelectClass}
        value={businessDomainValue}
        onChange={(e) => onChangeBusinessDomain(e.target.value)}
        disabled={submitting}
      >
        {businessDomainOptions.map((area) => (
          <option key={area.key} value={area.key}>
            {area.label} ({area.key})
          </option>
        ))}
      </select>

      <label className={fieldLabelClass} htmlFor="document-type-select">{t("triage:correctModal.documentType")}</label>
      <select
        id="document-type-select"
        className={nativeSelectClass}
        value={documentTypeValue}
        onChange={(e) => onChangeDocumentType(e.target.value)}
        disabled={submitting}
      >
        {documentTypeOptions.map((option) => (
          <option key={option.key} value={option.key}>
            {option.label} ({option.key})
          </option>
        ))}
      </select>

      {onCreateTaxonomyEntry && (
        <button
          type="button"
          className="mt-3 border-0 bg-transparent p-0 font-mono text-[0.72rem] text-accent shadow-none hover:underline"
          disabled={submitting}
          onClick={onCreateTaxonomyEntry}
        >
          {t("triage:correctModal.createLink")}
        </button>
      )}

      <ModalActions>
        <Button variant="secondary" disabled={submitting} onClick={onCancel}>
          {t("common:action.cancel")}
        </Button>
        <Button disabled={submitting || !businessDomainValue || !documentTypeValue} onClick={handleSubmit}>
          {submitting ? <><MiniOrb className="size-3" /> {t("triage:correctModal.approving")}</> : t("triage:correctModal.submit")}
        </Button>
      </ModalActions>
    </ModalShell>
  );
}
