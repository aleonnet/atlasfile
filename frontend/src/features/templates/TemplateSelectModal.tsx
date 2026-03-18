import { useCallback, useEffect, useState } from "react";
import { getTemplate, initializeProject, listTemplates } from "../../api";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import type { TemplateMeta } from "../../types";
import "./templates.css";

type Props = {
  open: boolean;
  projectRef: string;
  projectLabel: string;
  onClose: () => void;
  onInitialized: () => void;
  onCreateTemplate?: () => void;
};

export function TemplateSelectModal({ open, projectRef, projectLabel, onClose, onInitialized, onCreateTemplate }: Props) {
  useEscapeKey(open ? onClose : null);
  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [selected, setSelected] = useState("default");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(false);

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listTemplates();
      setTemplates(list);
      if (list.length > 0 && !list.find((t) => t.slug === selected)) {
        setSelected(list[0].slug);
      }
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    if (open) void loadTemplates();
  }, [open, loadTemplates]);

  useEffect(() => {
    if (!open || !selected) return;
    getTemplate(selected)
      .then((data) => setPreview(data.profile as unknown as Record<string, unknown>))
      .catch(() => setPreview(null));
  }, [open, selected]);

  async function handleInit() {
    setInitializing(true);
    try {
      await initializeProject(projectRef, selected);
      onInitialized();
    } catch {
      /* error handled by caller */
    } finally {
      setInitializing(false);
    }
  }

  if (!open) return null;

  const previewAreas = (preview as Record<string, unknown> | null)
    ? (
        ((preview?.classification as Record<string, unknown>)?.business_domains as Array<Record<string, unknown>> | undefined) ??
        []
      )
    : [];

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Selecionar template">
      <div className="modal tmpl-select-modal">
        <h3 style={{ margin: 0, flexShrink: 0 }}>Inicializar projeto: {projectLabel}</h3>

        <div className="tmpl-select-body">
          <p className="tmpl-hint">
            Selecione um template para configurar o projeto. Domínios, tipos documentais, layout e catálogo de entidades podem ser ajustados depois.
          </p>

          {loading && <p className="tmpl-loading">Carregando templates...</p>}

          <div className="tmpl-list">
            {templates.map((t) => (
              <label key={t.slug} className={`tmpl-item${selected === t.slug ? " selected" : ""}`}>
                <input
                  type="radio"
                  name="template"
                  value={t.slug}
                  checked={selected === t.slug}
                  onChange={() => setSelected(t.slug)}
                />
                <div className="tmpl-item-content">
                  <div className="tmpl-item-title-row">
                    <strong>{t.name}</strong>
                    {t.slug === "default" && <span className="tmpl-badge-default">default</span>}
                    <span className="tmpl-areas-count">{t.areas_count} domínios</span>
                  </div>
                  {t.description && <p className="tmpl-desc">{t.description}</p>}
                </div>
              </label>
            ))}
          </div>

          {previewAreas.length > 0 && (
            <details className="tmpl-preview">
              <summary>Preview do template selecionado</summary>
              <div className="tmpl-preview-list">
                {previewAreas.map((a, i) => (
                  <div key={i} className="tmpl-preview-area">
                    <span className="tmpl-preview-key">{String(a.key)}</span>
                    <span className="tmpl-preview-aliases">
                      {(a.aliases as string[] | undefined)?.slice(0, 4).join(", ")}
                      {((a.aliases as string[])?.length ?? 0) > 4 && "..."}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>

        <div className="modal-actions" style={{ flexShrink: 0 }}>
          {onCreateTemplate && (
            <button type="button" className="tmpl-create-link" onClick={onCreateTemplate}>
              + Criar novo template
            </button>
          )}
          <span style={{ flex: 1 }} />
          <button className="btn" onClick={onClose} disabled={initializing}>Cancelar</button>
          <button className="btn primary" onClick={handleInit} disabled={initializing || !selected}>
            {initializing ? "Inicializando..." : "Inicializar com template"}
          </button>
        </div>
      </div>
    </div>
  );
}
