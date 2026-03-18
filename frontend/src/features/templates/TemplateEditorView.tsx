import { useCallback, useEffect, useState } from "react";
import { createTemplate, deleteTemplate, getTemplate, listTemplates, saveTemplate } from "../../api";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import type { TemplateMeta } from "../../types";
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

  useEscapeKey(confirmDelete ? () => setConfirmDelete(null) : editor ? () => setEditor(null) : null);

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
        layout: {
          mode: "para_jd",
          roots: { projects: "01_PROJECTS", areas: "02_AREAS", resources: "03_RESOURCES", archive: "04_ARCHIVE" },
          areas_root: "02_AREAS",
          business_domain_folders: []
        },
        classification: {
          business_domains: [],
          document_types: [],
          entity_catalog: [],
        },
        naming: { canonical_pattern: "{date}__{project}__{original_name}", date_format: "%Y%m%d" },
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
      const data = buildTemplatePayload(editor.profileData, {
        slug: editor.slug,
        name: editor.name,
        description: editor.description,
      });
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

  function buildTemplatePayload(
    profileData: Record<string, unknown>,
    templateMeta: { slug: string; name: string; description: string }
  ) {
    const classification = (profileData.classification as Record<string, unknown>) ?? {};
    const layout = (profileData.layout as Record<string, unknown>) ?? {};
    const { area_folders: _ignoredAreaFolders, ...layoutWithoutLegacy } = layout;
    const businessDomains =
      ((classification.business_domains as Array<Record<string, unknown>> | undefined) ?? []).map((domain) => ({
        key: String(domain.key ?? "").trim(),
        label: String(domain.label ?? ""),
        aliases: Array.isArray(domain.aliases) ? domain.aliases : [],
        primary_scope: String(domain.primary_scope ?? ""),
        subfunction_topics: Array.isArray(domain.subfunction_topics) ? domain.subfunction_topics : [],
      }));
    const domainFolders =
      ((layout.business_domain_folders as Array<Record<string, unknown>> | undefined) ?? []).map((row) => ({
        business_domain: String(row.business_domain ?? "").trim(),
        folder: String(row.folder ?? "").trim(),
      })).filter((row) => row.business_domain);
    const documentTypes =
      ((classification.document_types as Array<Record<string, unknown>> | undefined) ?? []).map((row) => ({
        ...row,
        key: String(row.key ?? "").trim(),
        label: String(row.label ?? ""),
        aliases: Array.isArray(row.aliases) ? row.aliases : [],
        extensions: Array.isArray(row.extensions) ? row.extensions : [],
        folder: String(row.folder ?? "").trim(),
      }));
    const entityCatalog =
      ((classification.entity_catalog as Array<Record<string, unknown>> | undefined) ?? []).map((row) => ({
        type: String(row.type ?? "").trim(),
        value: String(row.value ?? "").trim(),
        aliases: Array.isArray(row.aliases) ? row.aliases : [],
      })).filter((row) => row.type && row.value);

    return {
      ...profileData,
      template_meta: {
        slug: templateMeta.slug,
        name: templateMeta.name,
        description: templateMeta.description,
      },
      layout: {
        ...layoutWithoutLegacy,
        business_domain_folders: domainFolders,
      },
      classification: {
        business_domains: businessDomains,
        document_types: documentTypes,
        entity_catalog: entityCatalog,
      },
    };
  }

  // Editor modal
  if (editor) {
    const cls = editor.profileData?.classification as Record<string, unknown> | undefined;
    const layoutData = (editor.profileData?.layout as Record<string, unknown>) ?? {};
    const workAreas = (cls?.work_areas as Array<Record<string, unknown>> | undefined) ?? [];
    const workAreaMap = new Map(
      workAreas
        .map((row) => [String(row.key ?? ""), row] as const)
        .filter(([key]) => key)
    );
    const rawDomains =
      (cls?.business_domains as Array<Record<string, unknown>> | undefined) ??
      workAreas ??
      [];
    const folderRows =
      (layoutData.business_domain_folders as Array<Record<string, unknown>> | undefined) ??
      (layoutData.area_folders as Array<Record<string, unknown>> | undefined)?.map((row) => ({
        business_domain: row.area_key,
        folder: row.folder
      })) ??
      [];
    const folderMap = new Map(
      folderRows
        .map((row) => [String(row.business_domain ?? ""), String(row.folder ?? "")] as const)
        .filter(([key]) => key)
    );
    const domains: Array<Record<string, unknown>> = rawDomains.map((row) => ({
      ...(workAreaMap.get(String(row.key ?? "")) ?? {}),
      ...row,
      aliases: Array.isArray(row.aliases)
        ? row.aliases
        : Array.isArray((workAreaMap.get(String(row.key ?? "")) ?? {}).aliases)
          ? ((workAreaMap.get(String(row.key ?? "")) ?? {}).aliases as unknown[])
          : [],
      primary_scope: row.primary_scope ?? "",
      subfunction_topics: Array.isArray(row.subfunction_topics) ? row.subfunction_topics : [],
      jd_number: row.jd_number ?? (workAreaMap.get(String(row.key ?? "")) ?? {}).jd_number ?? null,
      folder: String(row.folder ?? folderMap.get(String(row.key ?? "")) ?? row.key ?? "")
    }));
    const documentTypes = (cls?.document_types as Array<Record<string, unknown>>) ?? [];
    const entityCatalog = (cls?.entity_catalog as Array<Record<string, unknown>>) ?? [];
    const naming = (editor.profileData?.naming as Record<string, unknown>) ?? {};
    const indexing = (editor.profileData?.indexing as Record<string, unknown>) ?? {};

    function updateClassification(field: string, value: unknown) {
      if (!editor?.profileData) return;
      const c = { ...(editor.profileData.classification as Record<string, unknown>), [field]: value };
      setEditor({ ...editor, profileData: { ...editor.profileData, classification: c } });
    }

    function updateNaming(field: string, value: unknown) {
      if (!editor?.profileData) return;
      const n = { ...(editor.profileData.naming as Record<string, unknown> ?? {}), [field]: value };
      setEditor({ ...editor, profileData: { ...editor.profileData, naming: n } });
    }

    function updateIndexing(field: string, value: unknown) {
      if (!editor?.profileData) return;
      const idx = { ...(editor.profileData.indexing as Record<string, unknown>), [field]: value };
      setEditor({ ...editor, profileData: { ...editor.profileData, indexing: idx } });
    }

    function syncDomainMirrors(nextDomains: Array<Record<string, unknown>>) {
      if (!editor?.profileData) return;
      const classification = { ...(editor.profileData.classification as Record<string, unknown>) };
      const layout = { ...(editor.profileData.layout as Record<string, unknown>) };
      const normalizedDomains = nextDomains.map((domain) => ({
        key: String(domain.key ?? ""),
        label: String(domain.label ?? ""),
        aliases: Array.isArray(domain.aliases) ? domain.aliases : [],
        primary_scope: String(domain.primary_scope ?? ""),
        subfunction_topics: Array.isArray(domain.subfunction_topics) ? domain.subfunction_topics : [],
        jd_number: Number.isFinite(Number(domain.jd_number)) && Number(domain.jd_number) > 0
          ? Number(domain.jd_number)
          : undefined,
        folder: String(domain.folder ?? domain.key ?? "")
      }));
      const normalizedFolders = normalizedDomains
        .map((domain) => ({
          business_domain: domain.key,
          folder: domain.folder
        }))
        .filter((row) => row.business_domain);
      classification.business_domains = normalizedDomains.map(({ folder, jd_number, ...domain }) => domain);
      classification.work_areas = normalizedDomains.map((domain, index) => ({
        key: domain.key,
        jd_number: domain.jd_number ?? index + 1,
        aliases: domain.aliases
      }));
      layout.business_domain_folders = normalizedFolders;
      layout.area_folders = normalizedFolders.map((row) => ({ area_key: row.business_domain, folder: row.folder }));
      setEditor({ ...editor, profileData: { ...editor.profileData, classification, layout } });
    }

    function updateArea(idx: number, field: string, value: unknown) {
      const nextDomains = [...domains];
      nextDomains[idx] = { ...nextDomains[idx], [field]: value };
      syncDomainMirrors(nextDomains);
    }

    function addArea() {
      if (!editor?.profileData) return;
      syncDomainMirrors([...domains, { key: "", label: "", aliases: [], folder: "" }]);
    }

    function removeArea(idx: number) {
      const nextDomains = [...domains];
      nextDomains.splice(idx, 1);
      syncDomainMirrors(nextDomains);
    }

    function updateDocumentType(idx: number, field: string, value: unknown) {
      if (!editor?.profileData) return;
      const classification = { ...(editor.profileData.classification as Record<string, unknown>) };
      const updated = [...documentTypes];
      updated[idx] = { ...updated[idx], [field]: value };
      classification.document_types = updated;
      setEditor({ ...editor, profileData: { ...editor.profileData, classification } });
    }

    function addDocumentType() {
      if (!editor?.profileData) return;
      const classification = { ...(editor.profileData.classification as Record<string, unknown>) };
      classification.document_types = [
        ...documentTypes,
        {
          key: "",
          label: "",
          aliases: [],
          extensions: [],
          folder: "",
          extension_confidence_by_extension: {},
          fallback_priority: 100,
          detection_rules: []
        }
      ];
      setEditor({ ...editor, profileData: { ...editor.profileData, classification } });
    }

    function removeDocumentType(idx: number) {
      if (!editor?.profileData) return;
      const classification = { ...(editor.profileData.classification as Record<string, unknown>) };
      const updated = [...documentTypes];
      updated.splice(idx, 1);
      classification.document_types = updated;
      setEditor({ ...editor, profileData: { ...editor.profileData, classification } });
    }

    function updateEntity(idx: number, field: string, value: unknown) {
      const updated = [...entityCatalog];
      updated[idx] = { ...updated[idx], [field]: value };
      updateClassification("entity_catalog", updated);
    }

    function addEntity() {
      updateClassification("entity_catalog", [...entityCatalog, { type: "", value: "", aliases: [] }]);
    }

    function removeEntity(idx: number) {
      const updated = [...entityCatalog];
      updated.splice(idx, 1);
      updateClassification("entity_catalog", updated);
    }

    const inputStyle = { width: "100%", padding: "4px 6px", border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg)", color: "var(--text)", fontSize: "0.85rem" } as const;

    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Editar template">
        <div className="modal tmpl-editor-modal">
          <div className="modal-header">
            <h3>{editor.isNew ? "Novo template" : `Editar template: ${editor.name}`}</h3>
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

          {/* ── Naming ── */}
          <details className="itc-collapsible" open>
            <summary className="itc-collapsible-header">Naming (formato canônico)</summary>
            <div className="itc-collapsible-body">
              <div className="tmpl-grid-2">
                <div className="tmpl-field">
                  <label htmlFor="tmpl-naming-pattern">Canonical pattern</label>
                  <input
                    id="tmpl-naming-pattern"
                    value={String(naming.canonical_pattern ?? "{date}__{project}__{original_name}")}
                    onChange={(e) => updateNaming("canonical_pattern", e.target.value)}
                    placeholder="{date}__{project}__{original_name}"
                  />
                  <p className="onboarding-hint" style={{ margin: "4px 0 0", fontSize: "0.75rem" }}>
                    Campos: {"{date}"}, {"{project}"}, {"{area}"}, {"{original_name}"}, {"{document_type}"}. Sufixo __vNN.ext adicionado automaticamente.
                  </p>
                </div>
                <div className="tmpl-field">
                  <label htmlFor="tmpl-naming-datefmt">Date format</label>
                  <input
                    id="tmpl-naming-datefmt"
                    value={String(naming.date_format ?? "%Y%m%d")}
                    onChange={(e) => updateNaming("date_format", e.target.value)}
                    placeholder="%Y%m%d"
                  />
                </div>
              </div>
            </div>
          </details>

          {/* ── Estrutura de Layout ── */}
          <details className="itc-collapsible" open>
            <summary className="itc-collapsible-header">
              Estrutura de Layout
              <span className="itc-badge-count">{domains.length} domínios</span>
            </summary>
            <div className="itc-collapsible-body">
              <table className="itc-scan-table">
                <thead>
                  <tr>
                    <th>BUSINESS_DOMAIN</th>
                    <th>LABEL</th>
                    <th>ALIASES</th>
                    <th>PASTA</th>
                    <th style={{ width: 40 }} />
                  </tr>
                </thead>
                <tbody>
                  {domains.map((a, i) => (
                    <tr key={i}>
                      <td><input style={inputStyle} value={String(a.key ?? "")} onChange={(e) => updateArea(i, "key", e.target.value)} /></td>
                      <td><input style={inputStyle} value={String(a.label ?? "")} onChange={(e) => updateArea(i, "label", e.target.value)} /></td>
                      <td>
                        <input
                          style={inputStyle}
                          value={Array.isArray(a.aliases) ? a.aliases.join(", ") : ""}
                          onChange={(e) => updateArea(i, "aliases", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                        />
                      </td>
                      <td><input style={inputStyle} value={String(a.folder ?? "")} onChange={(e) => updateArea(i, "folder", e.target.value)} /></td>
                      <td><button className="btn danger" style={{ padding: "2px 6px", fontSize: "0.75rem" }} onClick={() => removeArea(i)}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button className="btn" style={{ marginTop: 8, fontSize: "0.82rem" }} onClick={addArea}>+ Adicionar domínio</button>
            </div>
          </details>

          <details className="itc-collapsible" open>
            <summary className="itc-collapsible-header">
              Tipos documentais
              <span className="itc-badge-count">{documentTypes.length} tipos</span>
            </summary>
            <div className="itc-collapsible-body">
              <table className="itc-scan-table">
                <thead>
                  <tr>
                    <th>KEY</th>
                    <th>LABEL</th>
                    <th>ALIASES</th>
                    <th>EXTENSÕES</th>
                    <th>PASTA</th>
                    <th style={{ width: 40 }} />
                  </tr>
                </thead>
                <tbody>
                  {documentTypes.map((row, i) => (
                    <tr key={i}>
                      <td><input style={inputStyle} value={String(row.key ?? "")} onChange={(e) => updateDocumentType(i, "key", e.target.value)} /></td>
                      <td><input style={inputStyle} value={String(row.label ?? "")} onChange={(e) => updateDocumentType(i, "label", e.target.value)} /></td>
                      <td>
                        <input
                          style={inputStyle}
                          value={Array.isArray(row.aliases) ? row.aliases.join(", ") : ""}
                          onChange={(e) => updateDocumentType(i, "aliases", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                        />
                      </td>
                      <td>
                        <input
                          style={inputStyle}
                          value={Array.isArray(row.extensions) ? row.extensions.join(", ") : ""}
                          onChange={(e) => updateDocumentType(i, "extensions", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                        />
                      </td>
                      <td><input style={inputStyle} value={String(row.folder ?? "")} onChange={(e) => updateDocumentType(i, "folder", e.target.value)} /></td>
                      <td><button className="btn danger" style={{ padding: "2px 6px", fontSize: "0.75rem" }} onClick={() => removeDocumentType(i)}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button className="btn" style={{ marginTop: 8, fontSize: "0.82rem" }} onClick={addDocumentType}>+ Adicionar tipo</button>
            </div>
          </details>

          <details className="itc-collapsible">
            <summary className="itc-collapsible-header">
              Catálogo de entidades
              <span className="itc-badge-count">{entityCatalog.length} entidades</span>
            </summary>
            <div className="itc-collapsible-body">
              <table className="itc-scan-table">
                <thead>
                  <tr>
                    <th>TIPO</th>
                    <th>VALOR</th>
                    <th>ALIASES</th>
                    <th style={{ width: 36 }} />
                  </tr>
                </thead>
                <tbody>
                  {entityCatalog.map((row, i) => (
                    <tr key={i}>
                      <td><input style={inputStyle} value={String(row.type ?? "")} onChange={(e) => updateEntity(i, "type", e.target.value)} /></td>
                      <td><input style={inputStyle} value={String(row.value ?? "")} onChange={(e) => updateEntity(i, "value", e.target.value)} /></td>
                      <td>
                        <input
                          style={inputStyle}
                          value={Array.isArray(row.aliases) ? row.aliases.join(", ") : ""}
                          onChange={(e) => updateEntity(i, "aliases", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                        />
                      </td>
                      <td><button className="btn danger" style={{ padding: "2px 6px", fontSize: "0.75rem" }} onClick={() => removeEntity(i)}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button className="btn" style={{ marginTop: 8, fontSize: "0.82rem" }} onClick={addEntity}>+ Adicionar entidade</button>
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
                {t.areas_count} domínios | Atualizado em {t.updated_at ? new Date(t.updated_at).toLocaleDateString("pt-BR") : "—"}
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
