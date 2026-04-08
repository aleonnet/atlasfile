import { useState } from "react";
import { useEscapeKey } from "../hooks/useEscapeKey";
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
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Mover documento">
      <div className="modal">
        <h3>Mover documento</h3>
        <p>
          Arquivo: <strong>{filename}</strong>
        </p>
        <p className="sub">
          Origem: {currentBusinessDomain} / {currentDocumentType}
        </p>

        <label htmlFor="move-bd-select">Domínio destino</label>
        <select
          id="move-bd-select"
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

        <label htmlFor="move-dt-select">Tipo documental destino</label>
        <select
          id="move-dt-select"
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
          <p className="modal-move-summary">
            Mover de <code>{currentBusinessDomain}/{currentDocumentType}</code> para <code>{bdValue}/{dtValue}</code>
          </p>
        )}

        {errorMessage && (
          <p className="modal-move-error">{errorMessage}</p>
        )}

        <div className="modal-actions">
          <button className="btn" disabled={submitting} onClick={onCancel}>
            Cancelar
          </button>
          <button
            className="btn primary"
            disabled={submitting || !changed || !bdValue || !dtValue}
            onClick={() => onConfirm(bdValue, dtValue)}
          >
            {submitting ? "Movendo..." : "Confirmar"}
          </button>
        </div>
      </div>
    </div>
  );
}
