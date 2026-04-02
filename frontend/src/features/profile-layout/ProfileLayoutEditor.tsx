import type { ProjectProfileV2 } from "./types";

type Props = {
  profile: ProjectProfileV2;
  onChange: (next: ProjectProfileV2) => void;
};

const PARA_DEFAULTS = {
  projects: "01_PROJECTS",
  areas: "02_AREAS",
  resources: "03_RESOURCES",
  archive: "04_ARCHIVE"
} as const;

export function ProfileLayoutEditor({ profile, onChange }: Props) {
  const folders = profile.layout.business_domain_folders ?? [];

  function updateField<K extends keyof ProjectProfileV2>(key: K, value: ProjectProfileV2[K]) {
    onChange({ ...profile, [key]: value });
  }

  function updateInbox(value: string) {
    onChange({ ...profile, paths: { ...profile.paths, inbox: value } });
  }

  function updateAreasRoot(value: string) {
    onChange({ ...profile, layout: { ...profile.layout, areas_root: value } });
  }

  function updateDomainFolders(nextFolders: Array<{ business_domain: string; folder: string }>) {
    onChange({
      ...profile,
      layout: {
        ...profile.layout,
        business_domain_folders: nextFolders,
      }
    });
  }

  function updateMode(value: "para_jd" | "custom") {
    if (value === "para_jd") {
      onChange({
        ...profile,
        layout: {
          ...profile.layout,
          mode: "para_jd",
          roots: { ...PARA_DEFAULTS },
          areas_root: PARA_DEFAULTS.areas,
        }
      });
    } else {
      onChange({ ...profile, layout: { ...profile.layout, mode: "custom" } });
    }
  }

  function updateRoot(key: "projects" | "areas" | "resources" | "archive", value: string) {
    const newRoots = { ...profile.layout.roots, [key]: value };
    const isParaDefault = (Object.keys(PARA_DEFAULTS) as Array<keyof typeof PARA_DEFAULTS>).every(
      (k) => newRoots[k] === PARA_DEFAULTS[k]
    );
    onChange({
      ...profile,
      layout: {
        ...profile.layout,
        roots: newRoots,
        mode: isParaDefault ? "para_jd" : "custom",
      }
    });
  }

  function updateAreaKey(index: number, nextKey: string) {
    updateDomainFolders(folders.map((r, i) => (i === index ? { ...r, business_domain: nextKey } : r)));
  }

  function updateFolder(index: number, folder: string) {
    updateDomainFolders(folders.map((r, i) => (i === index ? { ...r, folder } : r)));
  }

  function addAreaFolder() {
    const key = `novo_dominio_${folders.length + 1}`;
    updateDomainFolders([...folders, { business_domain: key, folder: key }]);
  }

  function removeAreaFolder(areaKey: string) {
    updateDomainFolders(folders.filter((r) => r.business_domain !== areaKey));
  }

  return (
    <>
      {/* ── Estrutura de Layout (Modo + Raízes + Areas root) ── */}
      <details className="pl-collapsible">
        <summary className="pl-collapsible-header">Estrutura de Layout</summary>
        <div className="pl-collapsible-body">
          <div className="pl-mode-row">
            <label className="pl-radio">
              <input type="radio" name="layout-mode" value="para_jd" checked={profile.layout.mode === "para_jd"} onChange={() => updateMode("para_jd")} />
              <span>PARA</span>
            </label>
            <label className="pl-radio">
              <input type="radio" name="layout-mode" value="custom" checked={profile.layout.mode === "custom"} onChange={() => updateMode("custom")} />
              <span>Custom</span>
            </label>
          </div>

          <span className="pl-sub-label">Raízes (PARA)</span>
          <div className="pl-roots-grid">
            {(["projects", "areas", "resources", "archive"] as const).map((key) => (
              <label key={key} className="pl-field">
                <span className="pl-field-label">{key}</span>
                <input className="pl-input" value={profile.layout.roots[key]} onChange={(e) => updateRoot(key, e.target.value)} />
              </label>
            ))}
          </div>

          <label className="pl-field pl-field-areas-root">
            <span className="pl-field-label">Areas root (onde ficam os domínios)</span>
            <input className="pl-input" value={profile.layout.areas_root} onChange={(e) => updateAreasRoot(e.target.value)} />
          </label>
        </div>
      </details>

      {/* ── Mapeamento domínios → pastas ── */}
      <details className="pl-collapsible">
        <summary className="pl-collapsible-header">Mapeamento de domínios → pastas</summary>
        <div className="pl-collapsible-body">
          <div className="pl-table-wrap">
            <table className="pl-table">
              <thead>
                <tr>
                  <th>business_domain</th>
                  <th>folder</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {folders.map((row, idx) => (
                  <tr key={idx}>
                    <td>
                      <input className="pl-input pl-input-table" value={row.business_domain} onChange={(e) => updateAreaKey(idx, e.target.value)} />
                    </td>
                    <td>
                      <input className="pl-input pl-input-table" value={row.folder} onChange={(e) => updateFolder(idx, e.target.value)} />
                    </td>
                    <td>
                      <button type="button" className="btn danger" style={{ padding: "2px 6px", fontSize: "0.75rem" }} title="Remover" onClick={() => removeAreaFolder(row.business_domain)}>×</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" className="btn pl-add-btn" onClick={addAreaFolder}>+ Adicionar business_domain_folder</button>
        </div>
      </details>

      {/* ── Naming (formato canônico) ── */}
      <details className="pl-collapsible">
        <summary className="pl-collapsible-header">Naming (formato canônico)</summary>
        <div className="pl-collapsible-body">
          <div className="pl-roots-grid">
            <label className="pl-field">
              <span className="pl-field-label">Canonical pattern</span>
              <input
                className="pl-input"
                value={profile.naming?.canonical_pattern ?? "{date}__{project}__{original_name}"}
                onChange={(e) => onChange({ ...profile, naming: { ...profile.naming, canonical_pattern: e.target.value } })}
              />
              <span style={{ fontSize: "0.72rem", color: "var(--muted)", marginTop: 2 }}>
                Campos: {"{date}"}, {"{project}"}, {"{business_domain}"}, {"{original_name}"}, {"{document_type}"}. Sufixo __vNN.ext automático.
              </span>
            </label>
            <label className="pl-field">
              <span className="pl-field-label">Date format</span>
              <input
                className="pl-input"
                value={profile.naming?.date_format ?? "%Y%m%d"}
                onChange={(e) => onChange({ ...profile, naming: { ...profile.naming, date_format: e.target.value } })}
              />
            </label>
          </div>
        </div>
      </details>

      {/* ── Geral (collapsed by default) ── */}
      <details className="pl-collapsible">
        <summary className="pl-collapsible-header">Geral</summary>
        <div className="pl-collapsible-body">
          <div className="pl-roots-grid">
            <label className="pl-field">
              <span className="pl-field-label">Project label</span>
              <input className="pl-input" value={profile.project_label} onChange={(e) => updateField("project_label", e.target.value)} />
            </label>
            <label className="pl-field">
              <span className="pl-field-label">Inbox path</span>
              <input className="pl-input" value={profile.paths.inbox} onChange={(e) => updateInbox(e.target.value)} />
            </label>
            <label className="pl-field">
              <span className="pl-field-label">Extraction mode</span>
              <select
                className="pl-input"
                value={profile.indexing.extraction_mode}
                onChange={(e) => onChange({ ...profile, indexing: { ...profile.indexing, extraction_mode: e.target.value as "all" | "excerpt" } })}
              >
                <option value="excerpt">excerpt</option>
                <option value="all">all</option>
              </select>
            </label>
          </div>
        </div>
      </details>
    </>
  );
}
