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
};

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
  onSubmit
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
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Aprovar com correcao">
      <div className="modal">
        <h3>Aprovar com correção</h3>
        <p>
          Arquivo: <strong>{item.filename}</strong>
        </p>

        {item.llm_explanation && (
          <div className="modal-llm-context">
            {item.rule_business_domain && (
              <p>Regra: <code>{item.rule_business_domain}</code> (conf {(item.rule_confidence ?? 0).toFixed(2)})</p>
            )}
            <p>LLM: <em>{item.llm_explanation}</em></p>
            {item.llm_proposed_business_domain && (
              <p>Domínio proposto: <code>{item.llm_proposed_business_domain}</code></p>
            )}
          </div>
        )}

        {suggestedBusinessDomainMissing && (
          <p className="modal-new-area-warning">
            A sugestão de domínio <code>{suggestedBusinessDomain}</code> não existe na taxonomia do projeto.
            Selecione um domínio já configurado.
          </p>
        )}

        {llmProposedBusinessDomainMissing && (
          <p className="modal-new-area-warning">
            O domínio proposto pelo LLM <code>{llmProposedBusinessDomain}</code> não está configurado no projeto.
            Escolha um domínio válido do catálogo.
          </p>
        )}

        {suggestedDocumentTypeMissing && (
          <p className="modal-new-area-warning">
            O tipo documental sugerido <code>{suggestedDocumentType}</code> não existe no profile atual.
            Selecione um tipo já configurado.
          </p>
        )}

        <label htmlFor="business-domain-select">Domínio destino</label>
        <select
          id="business-domain-select"
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

        <label htmlFor="document-type-select">Tipo documental</label>
        <select
          id="document-type-select"
          value={documentTypeValue}
          onChange={(e) => onChangeDocumentType(e.target.value)}
          disabled={submitting}
        >
          {documentTypeOptions.map((item) => (
            <option key={item.key} value={item.key}>
              {item.label} ({item.key})
            </option>
          ))}
        </select>

        <div className="modal-actions">
          <button
            className="btn"
            disabled={submitting}
            onClick={() => {
              onCancel();
            }}
          >
            Cancelar
          </button>
          <button
            className="btn primary"
            disabled={submitting || !businessDomainValue || !documentTypeValue}
            onClick={handleSubmit}
          >
            {submitting ? "Aprovando..." : "Aprovar e mover"}
          </button>
        </div>
      </div>
    </div>
  );
}

