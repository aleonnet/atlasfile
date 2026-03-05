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
  if (!item) return null;
  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Aprovar com correcao">
      <div className="modal">
        <h3>Aprovar com correcao</h3>
        <p>
          Arquivo: <strong>{item.filename}</strong>
        </p>
        <label htmlFor="area-select">Area destino</label>
        <select
          id="area-select"
          value={areaValue}
          onChange={(e: InputLikeEvent) => onChangeArea(e.target.value)}
          disabled={submitting}
        >
          {areaOptions.map((area) => (
            <option key={area.key} value={area.key}>
              {area.label} ({area.key})
            </option>
          ))}
        </select>
        <div className="modal-actions">
          <button className="btn" disabled={submitting} onClick={onCancel}>
            Cancelar
          </button>
          <button className="btn primary" disabled={submitting || !areaValue} onClick={onSubmit}>
            {submitting ? "Aprovando..." : "Aprovar e mover"}
          </button>
        </div>
      </div>
    </div>
  );
}

