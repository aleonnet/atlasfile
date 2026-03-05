import { useState } from "react";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import type { ProjectArea, TriageItem } from "../../types";

type InputLikeEvent = { target: { value: string } };

type Props = {
  item: TriageItem | null;
  submitting: boolean;
  areaValue: string;
  areaOptions: ProjectArea[];
  onChangeArea: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
};

export function CorrectDecisionModal({
  item,
  submitting,
  areaValue,
  areaOptions,
  onChangeArea,
  onCancel,
  onSubmit
}: Props) {
  useEscapeKey(item ? onCancel : null);
  const [newAreaKey, setNewAreaKey] = useState("");

  if (!item) return null;

  const isNewArea = newAreaKey.trim().length > 0;
  const effectiveArea = isNewArea ? newAreaKey.trim() : areaValue;
  const existingKeys = new Set(areaOptions.map((a) => a.key));
  const willCreate = isNewArea && !existingKeys.has(newAreaKey.trim());

  function handleSubmit() {
    if (isNewArea) {
      onChangeArea(newAreaKey.trim());
      setTimeout(onSubmit, 0);
    } else {
      onSubmit();
    }
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
            {item.rule_area_key && (
              <p>Regra: <code>{item.rule_area_key}</code> (conf {(item.rule_confidence ?? 0).toFixed(2)})</p>
            )}
            <p>LLM: <em>{item.llm_explanation}</em></p>
            {item.llm_proposed_area && (
              <p>Área proposta: <code>{item.llm_proposed_area}</code></p>
            )}
          </div>
        )}

        <label htmlFor="area-select">Área destino</label>
        <select
          id="area-select"
          value={isNewArea ? "" : areaValue}
          onChange={(e: InputLikeEvent) => {
            onChangeArea(e.target.value);
            setNewAreaKey("");
          }}
          disabled={submitting || isNewArea}
        >
          {areaOptions.map((area) => (
            <option key={area.key} value={area.key}>
              {area.label} ({area.key})
            </option>
          ))}
        </select>

        <div className="modal-new-area">
          <label htmlFor="new-area-input">— ou criar nova área —</label>
          <input
            id="new-area-input"
            type="text"
            placeholder="ex: financeiro_relatorios"
            value={newAreaKey}
            onChange={(e) => setNewAreaKey(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
            disabled={submitting}
          />
          {willCreate && (
            <p className="modal-new-area-warning">
              Esta área será criada automaticamente no profile e no disco.
            </p>
          )}
        </div>

        <div className="modal-actions">
          <button className="btn" disabled={submitting} onClick={() => { setNewAreaKey(""); onCancel(); }}>
            Cancelar
          </button>
          <button className="btn primary" disabled={submitting || !effectiveArea} onClick={handleSubmit}>
            {submitting ? "Aprovando..." : "Aprovar e mover"}
          </button>
        </div>
      </div>
    </div>
  );
}

