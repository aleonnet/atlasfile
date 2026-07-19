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
    <ModalShell label="Aprovar com correcao" title="Aprovar com correção">
      <p className="text-sm">
        Arquivo: <strong className="text-foreground-strong">{item.filename}</strong>
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
          A sugestão de domínio <code>{suggestedBusinessDomain}</code> não existe na taxonomia do projeto.
          Selecione um domínio já configurado.
        </p>
      )}

      {llmProposedBusinessDomainMissing && (
        <p className={warningClass}>
          O domínio proposto pelo LLM <code>{llmProposedBusinessDomain}</code> não está configurado no projeto.
          Escolha um domínio válido do catálogo.
        </p>
      )}

      {suggestedDocumentTypeMissing && (
        <p className={warningClass}>
          O tipo documental sugerido <code>{suggestedDocumentType}</code> não existe no profile atual.
          Selecione um tipo já configurado.
        </p>
      )}

      <label className={fieldLabelClass} htmlFor="business-domain-select">Domínio destino</label>
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

      <label className={fieldLabelClass} htmlFor="document-type-select">Tipo documental</label>
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
          + O destino certo não existe? Criar novo tipo ou domínio
        </button>
      )}

      <ModalActions>
        <Button variant="secondary" disabled={submitting} onClick={onCancel}>
          Cancelar
        </Button>
        <Button disabled={submitting || !businessDomainValue || !documentTypeValue} onClick={handleSubmit}>
          {submitting ? <><MiniOrb className="size-3" /> Aprovando — movendo e indexando…</> : "Aprovar e mover"}
        </Button>
      </ModalActions>
    </ModalShell>
  );
}
