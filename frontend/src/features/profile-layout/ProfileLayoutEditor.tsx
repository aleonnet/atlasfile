import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "../../components/ui/button";
import { CollapsibleSection, editTableClass, tableInputClass } from "../../components/ui/collapsible-section";
import { Input } from "../../components/ui/input";
import { nativeSelectClass } from "../../components/ui/modal-shell";
import type { ProjectProfileV2 } from "./types";

const fieldLabelClass = "mb-1 block font-mono text-[0.68rem] uppercase tracking-wide text-tertiary";

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
  const { t } = useTranslation();
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
    <div className="flex flex-col gap-2.5">
      {/* ── Estrutura de Layout (Modo + Raízes + Areas root) ── */}
      <CollapsibleSection title={t("profileLayout:editor.layoutSection")} defaultOpen>
        <div className="flex gap-4">
          <label className="flex items-center gap-1.5 text-sm">
            <input type="radio" name="layout-mode" className="size-3.5 accent-[var(--accent)]" value="para_jd" checked={profile.layout.mode === "para_jd"} onChange={() => updateMode("para_jd")} />
            <span>{t("profileLayout:editor.modePara")}</span>
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <input type="radio" name="layout-mode" className="size-3.5 accent-[var(--accent)]" value="custom" checked={profile.layout.mode === "custom"} onChange={() => updateMode("custom")} />
            <span>{t("profileLayout:editor.modeCustom")}</span>
          </label>
        </div>

        <span className="mt-3 block font-mono text-[0.68rem] uppercase tracking-wide text-tertiary">{t("profileLayout:editor.rootsLabel")}</span>
        <div className="mt-1.5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {(["projects", "areas", "resources", "archive"] as const).map((key) => (
            <label key={key} className="block">
              <span className={fieldLabelClass}>{key}</span>
              <Input className="font-mono" value={profile.layout.roots[key]} onChange={(e) => updateRoot(key, e.target.value)} />
            </label>
          ))}
        </div>

        <label className="mt-3 block">
          <span className={fieldLabelClass}>{t("profileLayout:editor.areasRootLabel")}</span>
          <Input className="font-mono" value={profile.layout.areas_root} onChange={(e) => updateAreasRoot(e.target.value)} />
        </label>
      </CollapsibleSection>

      {/* ── Mapeamento domínios → pastas ── */}
      <CollapsibleSection title={t("profileLayout:editor.domainMappingSection")} badge={String(folders.length)}>
        <table className={editTableClass}>
          <thead>
            <tr>
              <th>business_domain</th>
              <th>folder</th>
              <th style={{ width: 40 }} />
            </tr>
          </thead>
          <tbody>
            {folders.map((row, idx) => (
              <tr key={idx}>
                <td>
                  <input className={tableInputClass} value={row.business_domain} onChange={(e) => updateAreaKey(idx, e.target.value)} />
                </td>
                <td>
                  <input className={tableInputClass} value={row.folder} onChange={(e) => updateFolder(idx, e.target.value)} />
                </td>
                <td>
                  <Button variant="ghost" size="icon" className="size-7 text-tertiary hover:text-destructive" title={t("profileLayout:editor.removeTitle")} aria-label={t("profileLayout:editor.removeRowAria")} onClick={() => removeAreaFolder(row.business_domain)}>
                    <X className="size-3.5" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Button variant="outline" size="sm" className="mt-2" onClick={addAreaFolder}>{t("profileLayout:editor.addDomainFolder")}</Button>
      </CollapsibleSection>

      {/* ── Naming (formato canônico) ── */}
      <CollapsibleSection title={t("profileLayout:editor.namingSection")}>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className={fieldLabelClass}>{t("profileLayout:editor.canonicalPattern")}</span>
            <Input
              className="font-mono"
              value={profile.naming?.canonical_pattern ?? "{date}__{project}__{original_name}"}
              onChange={(e) => onChange({ ...profile, naming: { ...profile.naming, canonical_pattern: e.target.value } })}
            />
            <span className="mt-1 block text-[0.7rem] text-tertiary">
              {t("profileLayout:editor.patternHint")}
            </span>
          </label>
          <label className="block">
            <span className={fieldLabelClass}>{t("profileLayout:editor.dateFormat")}</span>
            <Input
              className="font-mono"
              value={profile.naming?.date_format ?? "%Y%m%d"}
              onChange={(e) => onChange({ ...profile, naming: { ...profile.naming, date_format: e.target.value } })}
            />
          </label>
        </div>
      </CollapsibleSection>

      {/* ── Geral (collapsed by default) ── */}
      <CollapsibleSection title={t("profileLayout:editor.generalSection")}>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className={fieldLabelClass}>{t("profileLayout:editor.projectLabel")}</span>
            <Input value={profile.project_label} onChange={(e) => updateField("project_label", e.target.value)} />
          </label>
          <label className="block">
            <span className={fieldLabelClass}>{t("profileLayout:editor.inboxPath")}</span>
            <Input className="font-mono" value={profile.paths.inbox} onChange={(e) => updateInbox(e.target.value)} />
          </label>
          <label className="block">
            <span className={fieldLabelClass}>{t("profileLayout:editor.extractionMode")}</span>
            <select
              className={nativeSelectClass}
              value={profile.indexing.extraction_mode}
              onChange={(e) => onChange({ ...profile, indexing: { ...profile.indexing, extraction_mode: e.target.value as "all" | "excerpt" } })}
            >
              <option value="excerpt">excerpt</option>
              <option value="all">all</option>
            </select>
          </label>
        </div>
      </CollapsibleSection>
    </div>
  );
}
