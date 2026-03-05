import { useCallback, useEffect, useState } from "react";
import { createTemplate, deleteTemplate, fetchModels, getTemplate, listTemplates, saveTemplate } from "../../api";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import type { ModelOption, TemplateMeta } from "../../types";
import "./templates.css";

type EditorState = {
  slug: string;
  name: string;
  description: string;
  isNew: boolean;
  profileData: Record<string, unknown> | null;
};

export function TemplateEditorView() {
  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [modelCatalog, setModelCatalog] = useState<ModelOption[]>([]);

  useEscapeKey(confirmDelete ? () => setConfirmDelete(null) : editor ? () => setEditor(null) : null);

  useEffect(() => {
    void fetchModels().then(setModelCatalog).catch(() => setModelCatalog([]));
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setTemplates(await listTemplates());
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handleEdit(slug: string) {
    try {
      const tmpl = await getTemplate(slug);
      const profile = tmpl.profile as unknown as Record<string, unknown>;
      setEditor({
        slug,
        name: tmpl.name,
        description: tmpl.description,
        isNew: false,
        profileData: profile,
      });
    } catch {
      /* ignore */
    }
  }

  function handleNew() {
    setEditor({
      slug: "",
      name: "",
      description: "",
      isNew: true,
      profileData: {
        profile_version: 2,
        project_id: "__PROJECT_ID__",
        project_label: "__PROJECT_LABEL__",
        project_root: "__PROJECT_ROOT__",
        paths: { inbox: "_INBOX_DROP", triage: { pending: "_TRIAGE_REVIEW/pending", resolved: "_TRIAGE_REVIEW/resolved", rejected: "_TRIAGE_REVIEW/rejected" } },
        layout: { mode: "para_jd", roots: { projects: "01_PROJECTS", areas: "02_AREAS", resources: "03_RESOURCES", archive: "04_ARCHIVE" }, areas_root: "02_AREAS", area_folders: [] },
        classification: {
          work_areas: [],
          routing_rules: [],
          confidence_thresholds: { auto_route_min: 0.85, triage_min: 0.5 },
          llm_policy: { enabled: false, provider: "openai", model: "gpt-4o-mini", mode: "tag_only", allow_override_fields: ["document_type", "tags", "confidence", "topics"], override_guardrails: { area_override_only_if_rule_confidence_below: 0.65, require_explanation: true, max_area_changes: 1 } },
        },
        indexing: { topics_path: "config/topics_v1.yaml", extraction_max_chars: 50000, extraction_mode: "all" },
        version: 1,
      },
    });
  }

  async function handleDuplicate(slug: string) {
    try {
      const tmpl = await getTemplate(slug);
      const profile = tmpl.profile as unknown as Record<string, unknown>;
      setEditor({
        slug: `${slug}_copy`,
        name: `${tmpl.name} (cópia)`,
        description: tmpl.description,
        isNew: true,
        profileData: profile,
      });
    } catch {
      /* ignore */
    }
  }

  async function handleDeleteConfirmed() {
    if (!confirmDelete) return;
    try {
      await deleteTemplate(confirmDelete);
      await reload();
    } catch {
      /* ignore */
    } finally {
      setConfirmDelete(null);
    }
  }

  async function handleSave() {
    if (!editor || !editor.profileData) return;
    setSaving(true);
    try {
      const data = {
        ...editor.profileData,
        template_meta: {
          slug: editor.slug,
          name: editor.name,
          description: editor.description,
        },
      };
      if (editor.isNew) {
        await createTemplate(data);
      } else {
        await saveTemplate(editor.slug, data);
      }
      setEditor(null);
      await reload();
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  }

  // Editor modal
  if (editor) {
    const cls = editor.profileData?.classification as Record<string, unknown> | undefined;
    const areas = (cls?.work_areas as Array<Record<string, unknown>>) ?? [];
    const rules = (cls?.routing_rules as Array<Record<string, unknown>>) ?? [];
    const thresholds = (cls?.confidence_thresholds as Record<string, number>) ?? { auto_route_min: 0.85, triage_min: 0.5 };
    const llm = (cls?.llm_policy as Record<string, unknown>) ?? {};
    const guardrails = (llm.override_guardrails as Record<string, unknown>) ?? {};
    const indexing = (editor.profileData?.indexing as Record<string, unknown>) ?? {};
    const areaKeys = areas.map((a) => String(a.key ?? "")).filter(Boolean);

    function updateClassification(field: string, value: unknown) {
      if (!editor?.profileData) return;
      const c = { ...(editor.profileData.classification as Record<string, unknown>), [field]: value };
      setEditor({ ...editor, profileData: { ...editor.profileData, classification: c } });
    }

    function updateThresholds(field: string, value: number) {
      updateClassification("confidence_thresholds", { ...thresholds, [field]: value });
    }

    function updateLlmPolicy(field: string, value: unknown) {
      const updated = { ...llm, [field]: value };
      updateClassification("llm_policy", updated);
    }

    function updateGuardrails(field: string, value: unknown) {
      updateLlmPolicy("override_guardrails", { ...guardrails, [field]: value });
    }

    function updateIndexing(field: string, value: unknown) {
      if (!editor?.profileData) return;
      const idx = { ...(editor.profileData.indexing as Record<string, unknown>), [field]: value };
      setEditor({ ...editor, profileData: { ...editor.profileData, indexing: idx } });
    }

    function updateArea(idx: number, field: string, value: unknown) {
      if (!editor?.profileData) return;
      const classification = { ...(editor.profileData.classification as Record<string, unknown>) };
      const wa = [...(classification.work_areas as Array<Record<string, unknown>>)];
      wa[idx] = { ...wa[idx], [field]: value };
      classification.work_areas = wa;
      setEditor({ ...editor, profileData: { ...editor.profileData, classification } });
    }

    function addArea() {
      if (!editor?.profileData) return;
      const classification = { ...(editor.profileData.classification as Record<string, unknown>) };
      const wa = [...(classification.work_areas as Array<Record<string, unknown>>)];
      const usedJd = wa.map((a) => Number(a.jd_number) || 0);
      const nextJd = Math.max(0, ...usedJd) + 1;
      wa.push({ key: "", jd_number: nextJd, aliases: [] });
      classification.work_areas = wa;
      const layout = { ...(editor.profileData.layout as Record<string, unknown>) };
      const af = [...((layout.area_folders as Array<Record<string, unknown>>) || [])];
      af.push({ area_key: "", folder: `${String(nextJd).padStart(2, "0")}_` });
      layout.area_folders = af;
      setEditor({ ...editor, profileData: { ...editor.profileData, classification, layout } });
    }

    function removeArea(idx: number) {
      if (!editor?.profileData) return;
      const classification = { ...(editor.profileData.classification as Record<string, unknown>) };
      const wa = [...(classification.work_areas as Array<Record<string, unknown>>)];
      const removed = wa.splice(idx, 1)[0];
      classification.work_areas = wa;
      const layout = { ...(editor.profileData.layout as Record<string, unknown>) };
      const af = ((layout.area_folders as Array<Record<string, unknown>>) || []).filter((f) => f.area_key !== removed.key);
      layout.area_folders = af;
      setEditor({ ...editor, profileData: { ...editor.profileData, classification, layout } });
    }

    function updateRule(idx: number, field: string, value: unknown) {
      const updated = [...rules];
      updated[idx] = { ...updated[idx], [field]: value };
      updateClassification("routing_rules", updated);
    }

    function addRule() {
      updateClassification("routing_rules", [...rules, { when_filename_contains: [], route_to: areaKeys[0] ?? "", confidence: 0.9 }]);
    }

    function removeRule(idx: number) {
      const updated = [...rules];
      updated.splice(idx, 1);
      updateClassification("routing_rules", updated);
    }

    const inputStyle = { width: "100%", padding: "4px 6px", border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg)", color: "var(--text)", fontSize: "0.85rem" } as const;

    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Editar template">
        <div className="modal tmpl-editor-modal">
          <div className="modal-header">
            <h3>{editor.isNew ? "Novo template" : `Editar template: ${editor.name}`}</h3>
            <button className="modal-close" onClick={() => setEditor(null)} aria-label="Fechar">&times;</button>
          </div>

          <div className="tmpl-editor-fields">
            <div className="tmpl-editor-field">
              <label htmlFor="tmpl-name">Nome</label>
              <input id="tmpl-name" value={editor.name} onChange={(e) => setEditor({ ...editor, name: e.target.value })} />
            </div>
            <div className="tmpl-editor-field">
              <label htmlFor="tmpl-slug">Slug</label>
              <input
                id="tmpl-slug"
                value={editor.slug}
                onChange={(e) => setEditor({ ...editor, slug: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") })}
                readOnly={!editor.isNew}
              />
            </div>
            <div className="tmpl-editor-field">
              <label htmlFor="tmpl-desc">Descrição</label>
              <textarea id="tmpl-desc" value={editor.description} onChange={(e) => setEditor({ ...editor, description: e.target.value })} />
            </div>
          </div>

          {/* ── Estrutura de Layout ── */}
          <details className="itc-collapsible" open>
            <summary className="itc-collapsible-header">
              Estrutura de Layout
              <span className="itc-badge-count">{areas.length} áreas</span>
            </summary>
            <div className="itc-collapsible-body">
              <table className="itc-scan-table">
                <thead>
                  <tr>
                    <th style={{ width: 30 }}>#</th>
                    <th>AREA_KEY</th>
                    <th>ALIASES</th>
                    <th style={{ width: 40 }} />
                  </tr>
                </thead>
                <tbody>
                  {areas.map((a, i) => (
                    <tr key={i}>
                      <td style={{ textAlign: "center", color: "var(--muted)", fontSize: "0.78rem" }}>{String(a.jd_number ?? "")}</td>
                      <td><input style={inputStyle} value={String(a.key ?? "")} onChange={(e) => updateArea(i, "key", e.target.value)} /></td>
                      <td>
                        <input
                          style={inputStyle}
                          value={Array.isArray(a.aliases) ? a.aliases.join(", ") : ""}
                          onChange={(e) => updateArea(i, "aliases", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                        />
                      </td>
                      <td><button className="btn danger" style={{ padding: "2px 6px", fontSize: "0.75rem" }} onClick={() => removeArea(i)}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button className="btn" style={{ marginTop: 8, fontSize: "0.82rem" }} onClick={addArea}>+ Adicionar área</button>
            </div>
          </details>

          {/* ── Routing Rules ── */}
          <details className="itc-collapsible">
            <summary className="itc-collapsible-header">
              Routing Rules
              <span className="itc-badge-count">{rules.length} regras</span>
            </summary>
            <div className="itc-collapsible-body">
              <table className="itc-scan-table">
                <thead>
                  <tr>
                    <th style={{ width: 90 }}>Tipo</th>
                    <th style={{ minWidth: 220 }}>Patterns</th>
                    <th style={{ width: 160 }}>Área destino</th>
                    <th style={{ width: 70 }}>Conf.</th>
                    <th style={{ width: 36 }} />
                  </tr>
                </thead>
                <tbody>
                  {rules.map((r, i) => {
                    const isPath = Array.isArray(r.when_path_contains) && (r.when_path_contains as string[]).length > 0;
                    const patterns = isPath
                      ? (r.when_path_contains as string[]).join(", ")
                      : Array.isArray(r.when_filename_contains) ? (r.when_filename_contains as string[]).join(", ") : "";
                    return (
                      <tr key={i}>
                        <td>
                          <select
                            style={{ ...inputStyle, width: "100%" }}
                            value={isPath ? "path" : "filename"}
                            onChange={(e) => {
                              const type = e.target.value;
                              const vals = patterns.split(",").map((s) => s.trim()).filter(Boolean);
                              if (type === "path") {
                                const u = { ...r, when_path_contains: vals, when_filename_contains: undefined };
                                const updated = [...rules]; updated[i] = u; updateClassification("routing_rules", updated);
                              } else {
                                const u = { ...r, when_filename_contains: vals, when_path_contains: undefined };
                                const updated = [...rules]; updated[i] = u; updateClassification("routing_rules", updated);
                              }
                            }}
                          >
                            <option value="filename">filename</option>
                            <option value="path">path</option>
                          </select>
                        </td>
                        <td>
                          <input
                            style={inputStyle}
                            value={patterns}
                            onChange={(e) => {
                              const vals = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
                              if (isPath) updateRule(i, "when_path_contains", vals);
                              else updateRule(i, "when_filename_contains", vals);
                            }}
                          />
                        </td>
                        <td>
                          <select style={{ ...inputStyle, width: "100%" }} value={String(r.route_to ?? "")} onChange={(e) => updateRule(i, "route_to", e.target.value)}>
                            {areaKeys.map((k) => <option key={k} value={k}>{k}</option>)}
                            {!areaKeys.includes(String(r.route_to ?? "")) && <option value={String(r.route_to ?? "")}>{String(r.route_to ?? "")}</option>}
                          </select>
                        </td>
                        <td>
                          <input
                            type="number"
                            step="0.05"
                            min="0"
                            max="1"
                            style={{ ...inputStyle, width: 60 }}
                            value={Number(r.confidence ?? 0.9)}
                            onChange={(e) => updateRule(i, "confidence", parseFloat(e.target.value) || 0)}
                          />
                        </td>
                        <td><button className="btn danger" style={{ padding: "2px 6px", fontSize: "0.75rem" }} onClick={() => removeRule(i)}>×</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <button className="btn" style={{ marginTop: 8, fontSize: "0.82rem" }} onClick={addRule}>+ Adicionar regra</button>
            </div>
          </details>

          {/* ── Confidence Thresholds ── */}
          <details className="itc-collapsible">
            <summary className="itc-collapsible-header">Confidence Thresholds</summary>
            <div className="itc-collapsible-body">
              <div className="tmpl-grid-2">
                <div className="tmpl-field">
                  <label htmlFor="tmpl-auto-route-min">Auto-route mínimo</label>
                  <input id="tmpl-auto-route-min" type="number" step="0.05" min="0" max="1" value={thresholds.auto_route_min ?? 0.85} onChange={(e) => updateThresholds("auto_route_min", parseFloat(e.target.value) || 0)} />
                </div>
                <div className="tmpl-field">
                  <label htmlFor="tmpl-triage-min">Triage mínimo</label>
                  <input id="tmpl-triage-min" type="number" step="0.05" min="0" max="1" value={thresholds.triage_min ?? 0.5} onChange={(e) => updateThresholds("triage_min", parseFloat(e.target.value) || 0)} />
                </div>
              </div>
            </div>
          </details>

          {/* ── LLM Policy ── */}
          <details className="itc-collapsible">
            <summary className="itc-collapsible-header">
              LLM Policy
              <span className="itc-badge-count">{llm.enabled ? "ativado" : "desativado"}</span>
            </summary>
            <div className="itc-collapsible-body">
              <div className="tmpl-llm-row">
                <label>
                  LLM ativado
                  <button
                    type="button"
                    className={`tmpl-toggle ${llm.enabled ? "active" : ""}`}
                    onClick={() => updateLlmPolicy("enabled", !llm.enabled)}
                    aria-pressed={!!llm.enabled}
                    aria-label="Ativar LLM"
                  />
                </label>
              </div>
              <div className="tmpl-grid-2">
                <div className="tmpl-field">
                  <label htmlFor="tmpl-llm-model">Modelo</label>
                  <select
                    id="tmpl-llm-model"
                    value={`${String(llm.provider ?? "openai")}/${String(llm.model ?? "")}`}
                    onChange={(e) => {
                      const [prov, ...rest] = e.target.value.split("/");
                      updateLlmPolicy("provider", prov);
                      updateLlmPolicy("model", rest.join("/"));
                    }}
                  >
                    {modelCatalog.map((m) => (
                      <option key={`${m.provider}/${m.model}`} value={`${m.provider}/${m.model}`}>{m.label}</option>
                    ))}
                    {!modelCatalog.some((m) => `${m.provider}/${m.model}` === `${String(llm.provider ?? "openai")}/${String(llm.model ?? "")}`) && (
                      <option value={`${String(llm.provider ?? "openai")}/${String(llm.model ?? "")}`}>
                        {String(llm.provider ?? "openai")}/{String(llm.model ?? "")}
                      </option>
                    )}
                  </select>
                </div>
                <div className="tmpl-field">
                  <label htmlFor="tmpl-llm-mode">Modo</label>
                  <select id="tmpl-llm-mode" value={String(llm.mode ?? "tag_only")} onChange={(e) => updateLlmPolicy("mode", e.target.value)}>
                    <option value="tag_only">tag_only</option>
                    <option value="review">review</option>
                    <option value="full_override">full_override</option>
                  </select>
                </div>
              </div>

              <div className="tmpl-guardrails-label">Guardrails</div>
              <div className="tmpl-grid-2">
                <div className="tmpl-field">
                  <label htmlFor="tmpl-guard-threshold">Override se conf. abaixo de</label>
                  <input
                    id="tmpl-guard-threshold"
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={Number(guardrails.area_override_only_if_rule_confidence_below ?? 0.65)}
                    onChange={(e) => updateGuardrails("area_override_only_if_rule_confidence_below", parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="tmpl-field">
                  <label htmlFor="tmpl-guard-max-changes">Max area changes</label>
                  <input
                    id="tmpl-guard-max-changes"
                    type="number"
                    step="1"
                    min="0"
                    value={Number(guardrails.max_area_changes ?? 1)}
                    onChange={(e) => updateGuardrails("max_area_changes", parseInt(e.target.value) || 0)}
                  />
                </div>
              </div>
              <div style={{ marginTop: 8 }}>
                <label className="tmpl-checkbox">
                  <input
                    type="checkbox"
                    checked={!!guardrails.require_explanation}
                    onChange={(e) => updateGuardrails("require_explanation", e.target.checked)}
                  />
                  Exigir explicação
                </label>
              </div>
            </div>
          </details>

          {/* ── Indexação ── */}
          <details className="itc-collapsible">
            <summary className="itc-collapsible-header">Indexação</summary>
            <div className="itc-collapsible-body">
              <div className="tmpl-grid-2">
                <div className="tmpl-field">
                  <label htmlFor="tmpl-idx-topics">Topics path</label>
                  <input id="tmpl-idx-topics" value={String(indexing.topics_path ?? "config/topics_v1.yaml")} onChange={(e) => updateIndexing("topics_path", e.target.value)} />
                </div>
                <div className="tmpl-field">
                  <label htmlFor="tmpl-idx-mode">Modo extração</label>
                  <select id="tmpl-idx-mode" value={String(indexing.extraction_mode ?? "all")} onChange={(e) => updateIndexing("extraction_mode", e.target.value)}>
                    <option value="all">all</option>
                    <option value="excerpt">excerpt</option>
                  </select>
                </div>
              </div>
              <div className="tmpl-grid-2" style={{ marginTop: 8 }}>
                <div className="tmpl-field">
                  <label htmlFor="tmpl-idx-maxchars">Max chars extração</label>
                  <input
                    id="tmpl-idx-maxchars"
                    type="number"
                    step="1000"
                    min="1000"
                    value={Number(indexing.extraction_max_chars ?? 50000)}
                    onChange={(e) => updateIndexing("extraction_max_chars", parseInt(e.target.value) || 50000)}
                  />
                </div>
              </div>
            </div>
          </details>

          <div className="modal-actions" style={{ marginTop: 14 }}>
            <button className="btn" onClick={() => setEditor(null)} disabled={saving}>Cancelar</button>
            <button className="btn primary" onClick={handleSave} disabled={saving || !editor.slug || !editor.name}>
              {saving ? "Salvando..." : "Salvar template"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Template list view
  return (
    <section className="panel card tmpl-editor-view">
      <div className="tmpl-editor-header">
        <h2>Templates de projeto</h2>
        <button className="btn primary" onClick={handleNew}>+ Novo template</button>
      </div>

      {loading && <p className="tmpl-loading">Carregando...</p>}

      <div className="tmpl-card-list">
        {templates.map((t) => (
          <div key={t.slug} className="tmpl-card">
            <div className="tmpl-card-info">
              <strong>
                {t.name}
                {t.slug === "default" && <span className="tmpl-badge-default">default</span>}
                <span className={`tmpl-badge-source tmpl-badge-source--${t.source ?? "builtin"}`}>
                  {t.source === "user" ? "user" : "builtin"}
                </span>
              </strong>
              <div className="tmpl-card-meta">
                {t.areas_count} áreas | Atualizado em {t.updated_at ? new Date(t.updated_at).toLocaleDateString("pt-BR") : "—"}
                <span className="tmpl-card-slug">{t.slug}.json</span>
              </div>
              {t.description && <div className="tmpl-card-desc">{t.description}</div>}
            </div>
            <div className="tmpl-card-actions">
              <button className="btn" onClick={() => handleEdit(t.slug)}>Editar</button>
              <button className="btn" onClick={() => handleDuplicate(t.slug)}>Duplicar</button>
              {t.source === "user" && (
                <button className="btn danger" onClick={() => setConfirmDelete(t.slug)}>Excluir</button>
              )}
            </div>
          </div>
        ))}
      </div>

      {confirmDelete && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Confirmar exclusão">
          <div className="modal tmpl-confirm-modal">
            <div className="modal-header">
              <h3>Excluir template</h3>
              <button className="modal-close" onClick={() => setConfirmDelete(null)} aria-label="Fechar">&times;</button>
            </div>
            <p style={{ margin: "12px 0 18px", fontSize: "0.88rem", color: "var(--text)" }}>
              Tem certeza que deseja excluir o template <strong>{confirmDelete}</strong>? Esta ação não pode ser desfeita.
            </p>
            <div className="modal-actions">
              <button className="btn" onClick={() => setConfirmDelete(null)}>Cancelar</button>
              <button className="btn danger" onClick={handleDeleteConfirmed}>Excluir</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
