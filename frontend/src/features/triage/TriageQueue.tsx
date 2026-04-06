import type { TriageItem } from "../../types";

type Props = {
  triageItems: TriageItem[];
  projectLabelById: Map<string, string>;
  onDecision: (item: TriageItem, action: "approve" | "correct" | "reject") => void;
};

function formatPct(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatClassifierModeLabel(mode?: string | null): string {
  return mode || "—";
}

export function TriageQueue({ triageItems, projectLabelById, onDecision }: Props) {
  if (triageItems.length === 0) return null;

  return (
    <section className="panel card triage-queue-card">
      <div className="panel-head card-header">
        <h2>Triagem pendente</h2>
        <span className="triage-queue-badge">{triageItems.length}</span>
      </div>
      <p className="triage-queue-subtitle">
        {triageItems.length} documento{triageItems.length !== 1 ? "s" : ""} aguardando decisão
      </p>
      <ul className="list triage-queue-list">
        {triageItems.map((item) => {
          const hasLlmContext =
            item.classifier_mode ||
            item.llm_explanation ||
            item.rule_business_domain ||
            item.llm_proposed_business_domain ||
            item.business_domain_confidence != null ||
            item.document_type_confidence != null ||
            item.classifier_fallback_reason;
          const suggestedBusinessDomain = item.suggested_business_domain;
          return (
            <li key={item.doc_id} className="list-item triage-queue-item">
              <strong className="list-title">{item.filename}</strong>
              <div className="sub list-meta">
                projeto: {projectLabelById.get(item.project_id) || item.project_id} | sugestão:{" "}
                {suggestedBusinessDomain || "sem sugestão"}
                {item.suggested_document_type ? ` / ${item.suggested_document_type}` : ""}
                {" "}| confiança: {item.confidence_score.toFixed(2)}
              </div>

              {hasLlmContext && (
                <div className="itc-triage-llm-context">
                  <p>
                    Classificador: <code>{formatClassifierModeLabel(item.classifier_mode)}</code>
                    {item.classifier_requested_mode && item.classifier_requested_mode !== item.classifier_mode
                      ? ` (solicitado: ${formatClassifierModeLabel(item.classifier_requested_mode)})`
                      : ""}
                  </p>
                  <p>
                    Scores: domínio {formatPct(item.business_domain_confidence)} | tipo {formatPct(item.document_type_confidence)} | final {item.confidence_score.toFixed(2)}
                  </p>
                  {item.classifier_fallback_reason && (
                    <p>Fallback: <code>{item.classifier_fallback_reason}</code></p>
                  )}
                  {item.rule_business_domain && (
                    <p>Regra: <code>{item.rule_business_domain}</code> (conf {(item.rule_confidence ?? 0).toFixed(2)})</p>
                  )}
                  {item.llm_explanation && <p>LLM: <em>{item.llm_explanation}</em></p>}
                  {item.llm_proposed_business_domain && (
                    <p className="itc-proposed-area">Domínio proposto: <code>{item.llm_proposed_business_domain}</code></p>
                  )}
                </div>
              )}

              <div className="row">
                <button
                  className="btn"
                  disabled={!suggestedBusinessDomain}
                  title={!suggestedBusinessDomain ? "Sem sugestão de domínio" : ""}
                  onClick={() => void onDecision(item, "approve")}
                >
                  Aprovar
                </button>
                <button className="btn" onClick={() => void onDecision(item, "correct")}>
                  Corrigir
                </button>
                <button className="btn danger" onClick={() => void onDecision(item, "reject")}>
                  Rejeitar
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
