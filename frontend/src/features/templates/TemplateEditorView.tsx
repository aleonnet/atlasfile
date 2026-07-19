import { FileStack, Pencil, Plus, Replace, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createTemplate, deleteTemplate, getTemplate, saveTemplate } from "../../api";
import { useTemplatesQuery } from "../../lib/queries";
import { qk } from "../../lib/queryKeys";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { CollapsibleSection, editTableClass, rowDeleteButtonClass, tableInputClass } from "../../components/ui/collapsible-section";
import { EmptyState } from "../../components/ui/empty-state";
import { Input, Textarea } from "../../components/ui/input";
import { Skeleton } from "../../components/ui/skeleton";
import { fieldLabelClass, nativeSelectClass } from "../../components/ui/modal-shell";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { cn } from "../../lib/utils";
import type { TemplateMeta } from "../../types";
import { CreateTaxonomyEntryModal } from "./CreateTaxonomyEntryModal";
import { TaxonomyMigrateModal } from "./TaxonomyMigrateModal";

type EditorState = {
  slug: string;
  name: string;
  description: string;
  isNew: boolean;
  profileData: Record<string, unknown> | null;
};

const selectClass = nativeSelectClass;

/**
 * Input de lista (CSV) para células de tabela: edita o texto cru livremente
 * (vírgulas e espaços preservados) e comita o array no blur/Enter — um input
 * controlado que parseia a cada tecla "come" a vírgula digitada e impede
 * múltiplos itens.
 */
function ListInput({ value, onCommit, className, placeholder }: {
  value: string[];
  onCommit: (items: string[]) => void;
  className?: string;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState(value.join(", "));
  const focusedRef = useRef(false);

  useEffect(() => {
    if (!focusedRef.current) setDraft(value.join(", "));
  }, [value]);

  function commit() {
    onCommit(draft.split(",").map((s) => s.trim()).filter(Boolean));
  }

  return (
    <input
      className={className}
      value={draft}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onFocus={() => (focusedRef.current = true)}
      onBlur={() => {
        focusedRef.current = false;
        commit();
      }}
      onKeyDown={(e) => e.key === "Enter" && commit()}
    />
  );
}

/** Overlay de edição (mantém details/labels/tabela — contrato dos testes). */
function EditorOverlay({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={label}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/55 p-6 backdrop-blur-[6px]"
    >
      <div className="w-full max-w-3xl rounded-xl border border-border-subtle bg-panel p-6 shadow-[0_12px_28px_rgba(0,0,0,0.35)] [animation:atlas-slide-in_200ms_var(--ease-out)] motion-reduce:animate-none">
        {children}
      </div>
    </div>
  );
}

export function TemplateEditorView() {
  const queryClient = useQueryClient();
  const templatesQuery = useTemplatesQuery();
  const templates = templatesQuery.data ?? [];
  const loading = templatesQuery.isPending;
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [taxonomyModalOpen, setTaxonomyModalOpen] = useState(false);
  const [migrateModalOpen, setMigrateModalOpen] = useState(false);

  useEscapeKey(confirmDelete ? () => setConfirmDelete(null) : editor ? () => setEditor(null) : null);

  const reload = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: qk.templates.scope() });
  }, [queryClient]);

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
        ...layout,
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
    const rawDomains =
      (cls?.business_domains as Array<Record<string, unknown>> | undefined) ??
      [];
    const folderRows =
      (layoutData.business_domain_folders as Array<Record<string, unknown>> | undefined) ??
      [];
    const folderMap = new Map(
      folderRows
        .map((row) => [String(row.business_domain ?? ""), String(row.folder ?? "")] as const)
        .filter(([key]) => key)
    );
    const domains: Array<Record<string, unknown>> = rawDomains.map((row) => ({
      ...row,
      aliases: Array.isArray(row.aliases) ? row.aliases : [],
      primary_scope: row.primary_scope ?? "",
      subfunction_topics: Array.isArray(row.subfunction_topics) ? row.subfunction_topics : [],
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
        folder: String(domain.folder ?? domain.key ?? "")
      }));
      const normalizedFolders = normalizedDomains
        .map((domain) => ({
          business_domain: domain.key,
          folder: domain.folder
        }))
        .filter((row) => row.business_domain);
      classification.business_domains = normalizedDomains.map(({ folder, ...domain }) => domain);
      layout.business_domain_folders = normalizedFolders;
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

    const removeRowButton = (onClick: () => void) => (
      <button type="button" className={rowDeleteButtonClass} onClick={onClick} aria-label="Remover linha">
        ×
      </button>
    );

    return (
      <EditorOverlay label="Editar template">
        <h3 className="font-display text-lg font-bold text-foreground-strong">
          {editor.isNew ? "Novo template" : `Editar template: ${editor.name}`}
        </h3>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <label className={fieldLabelClass} htmlFor="tmpl-name">Nome</label>
            <Input id="tmpl-name" value={editor.name} onChange={(e) => setEditor({ ...editor, name: e.target.value })} />
          </div>
          <div>
            <label className={fieldLabelClass} htmlFor="tmpl-slug">Slug</label>
            <Input
              id="tmpl-slug"
              className="font-mono"
              value={editor.slug}
              onChange={(e) => setEditor({ ...editor, slug: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") })}
              readOnly={!editor.isNew}
            />
          </div>
          <div className="sm:col-span-2">
            <label className={fieldLabelClass} htmlFor="tmpl-desc">Descrição</label>
            <Textarea id="tmpl-desc" value={editor.description} onChange={(e) => setEditor({ ...editor, description: e.target.value })} />
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-2.5">
          <CollapsibleSection title="Naming (formato canônico)" defaultOpen>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className={fieldLabelClass} htmlFor="tmpl-naming-pattern">Canonical pattern</label>
                <Input
                  id="tmpl-naming-pattern"
                  className="font-mono"
                  value={String(naming.canonical_pattern ?? "{date}__{project}__{original_name}")}
                  onChange={(e) => updateNaming("canonical_pattern", e.target.value)}
                  placeholder="{date}__{project}__{original_name}"
                />
                <p className="mt-1 text-[0.7rem] text-tertiary">
                  Campos: {"{date}"}, {"{project}"}, {"{business_domain}"}, {"{original_name}"}, {"{document_type}"}. Sufixo __vNN.ext adicionado automaticamente.
                </p>
              </div>
              <div>
                <label className={fieldLabelClass} htmlFor="tmpl-naming-datefmt">Date format</label>
                <Input
                  id="tmpl-naming-datefmt"
                  className="font-mono"
                  value={String(naming.date_format ?? "%Y%m%d")}
                  onChange={(e) => updateNaming("date_format", e.target.value)}
                  placeholder="%Y%m%d"
                />
              </div>
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="Estrutura de Layout" badge={`${domains.length} domínios`} defaultOpen>
            <table className={editTableClass}>
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
                    <td><input className={tableInputClass} value={String(a.key ?? "")} onChange={(e) => updateArea(i, "key", e.target.value)} /></td>
                    <td><input className={tableInputClass} value={String(a.label ?? "")} onChange={(e) => updateArea(i, "label", e.target.value)} /></td>
                    <td>
                      <ListInput
                        className={tableInputClass}
                        value={Array.isArray(a.aliases) ? a.aliases.map(String) : []}
                        onCommit={(items) => updateArea(i, "aliases", items)}
                      />
                    </td>
                    <td><input className={tableInputClass} value={String(a.folder ?? "")} onChange={(e) => updateArea(i, "folder", e.target.value)} /></td>
                    <td>{removeRowButton(() => removeArea(i))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Button variant="outline" size="sm" className="mt-2" onClick={addArea}>
              + Adicionar domínio
            </Button>
          </CollapsibleSection>

          <CollapsibleSection title="Tipos documentais" badge={`${documentTypes.length} tipos`} defaultOpen>
            <table className={editTableClass}>
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
                    <td><input className={tableInputClass} value={String(row.key ?? "")} onChange={(e) => updateDocumentType(i, "key", e.target.value)} /></td>
                    <td><input className={tableInputClass} value={String(row.label ?? "")} onChange={(e) => updateDocumentType(i, "label", e.target.value)} /></td>
                    <td>
                      <ListInput
                        className={tableInputClass}
                        value={Array.isArray(row.aliases) ? row.aliases.map(String) : []}
                        onCommit={(items) => updateDocumentType(i, "aliases", items)}
                      />
                    </td>
                    <td>
                      <ListInput
                        className={tableInputClass}
                        value={Array.isArray(row.extensions) ? row.extensions.map(String) : []}
                        onCommit={(items) => updateDocumentType(i, "extensions", items.map((x) => x.toLowerCase()))}
                        placeholder=".msg, .eml, .pdf"
                      />
                    </td>
                    <td><input className={tableInputClass} value={String(row.folder ?? "")} onChange={(e) => updateDocumentType(i, "folder", e.target.value)} /></td>
                    <td>{removeRowButton(() => removeDocumentType(i))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Button variant="outline" size="sm" className="mt-2" onClick={addDocumentType}>
              + Adicionar tipo
            </Button>
          </CollapsibleSection>

          <CollapsibleSection title="Catálogo de entidades" badge={`${entityCatalog.length} entidades`}>
            <table className={editTableClass}>
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
                    <td><input className={tableInputClass} value={String(row.type ?? "")} onChange={(e) => updateEntity(i, "type", e.target.value)} /></td>
                    <td><input className={tableInputClass} value={String(row.value ?? "")} onChange={(e) => updateEntity(i, "value", e.target.value)} /></td>
                    <td>
                      <ListInput
                        className={tableInputClass}
                        value={Array.isArray(row.aliases) ? row.aliases.map(String) : []}
                        onCommit={(items) => updateEntity(i, "aliases", items)}
                      />
                    </td>
                    <td>{removeRowButton(() => removeEntity(i))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Button variant="outline" size="sm" className="mt-2" onClick={addEntity}>
              + Adicionar entidade
            </Button>
          </CollapsibleSection>

          <CollapsibleSection title="Indexação">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className={fieldLabelClass} htmlFor="tmpl-idx-topics">Topics path</label>
                <Input id="tmpl-idx-topics" className="font-mono" value={String(indexing.topics_path ?? "config/topics_v1.yaml")} onChange={(e) => updateIndexing("topics_path", e.target.value)} />
              </div>
              <div>
                <label className={fieldLabelClass} htmlFor="tmpl-idx-mode">Modo extração</label>
                <select id="tmpl-idx-mode" className={selectClass} value={String(indexing.extraction_mode ?? "all")} onChange={(e) => updateIndexing("extraction_mode", e.target.value)}>
                  <option value="all">all</option>
                  <option value="excerpt">excerpt</option>
                </select>
              </div>
              <div>
                <label className={fieldLabelClass} htmlFor="tmpl-idx-maxchars">Max chars extração</label>
                <Input
                  id="tmpl-idx-maxchars"
                  type="number"
                  step="1000"
                  min="1000"
                  value={Number(indexing.extraction_max_chars ?? 50000)}
                  onChange={(e) => updateIndexing("extraction_max_chars", parseInt(e.target.value) || 50000)}
                />
              </div>
            </div>
          </CollapsibleSection>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setEditor(null)} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving || !editor.slug || !editor.name}>
            {saving ? "Salvando..." : "Salvar template"}
          </Button>
        </div>
      </EditorOverlay>
    );
  }

  // Template list view
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <FileStack className="size-4 text-accent" aria-hidden />
          Templates de projeto
        </CardTitle>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setMigrateModalOpen(true)}>
            <Replace />
            Migrar / remover
          </Button>
          <Button variant="secondary" onClick={() => setTaxonomyModalOpen(true)}>
            <Plus />
            Novo tipo/domínio
          </Button>
          <Button onClick={handleNew}>
            <Plus />
            Novo template
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </div>
        )}

        {!loading && templates.length === 0 && (
          <EmptyState
            icon={<FileStack aria-hidden />}
            title="Nenhum template"
            description="Crie um template para padronizar a estrutura dos seus projetos."
          />
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {templates.map((t) => (
            <div
              key={t.slug}
              className={cn(
                "group flex flex-col gap-2 rounded-lg border border-border bg-card p-4",
                "transition-[border-color,box-shadow] duration-200 hover:border-accent/40 hover:shadow-[0_0_20px_var(--accent-soft)]"
              )}
            >
              <div className="flex items-center gap-2">
                <strong className="min-w-0 flex-1 truncate font-display text-sm font-semibold text-foreground-strong">
                  {t.name}
                </strong>
                {t.slug === "default" && <Badge>default</Badge>}
                <Badge variant={t.source === "user" ? "purple" : "outline"}>{t.source === "user" ? "user" : "builtin"}</Badge>
              </div>
              <p className="font-mono text-[0.7rem] text-tertiary">
                {t.areas_count} domínios · atualizado {t.updated_at ? new Date(t.updated_at).toLocaleDateString("pt-BR") : "—"} ·{" "}
                <span className="text-muted-foreground">{t.slug}.json</span>
              </p>
              {t.description && <p className="line-clamp-2 text-xs text-muted-foreground">{t.description}</p>}
              <div className="mt-auto flex gap-1.5 pt-1">
                <Button variant="secondary" size="sm" onClick={() => handleEdit(t.slug)}>
                  <Pencil />
                  Editar
                </Button>
                <Button variant="ghost" size="sm" onClick={() => handleDuplicate(t.slug)}>
                  Duplicar
                </Button>
                {t.source === "user" && (
                  <Button variant="destructive" size="sm" className="ml-auto" onClick={() => setConfirmDelete(t.slug)}>
                    <Trash2 />
                    Excluir
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>

        {confirmDelete && (
          <EditorOverlay label="Confirmar exclusão">
            <h3 className="font-display text-lg font-bold text-foreground-strong">Excluir template</h3>
            <p className="mt-3 text-sm text-muted-foreground">
              Tem certeza que deseja excluir o template <strong className="text-foreground">{confirmDelete}</strong>? Esta
              ação não pode ser desfeita.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setConfirmDelete(null)}>
                Cancelar
              </Button>
              <Button variant="destructive" onClick={handleDeleteConfirmed}>
                Excluir
              </Button>
            </div>
          </EditorOverlay>
        )}

        <CreateTaxonomyEntryModal
          open={taxonomyModalOpen}
          onClose={() => setTaxonomyModalOpen(false)}
          onCreated={() => void reload()}
        />
        <TaxonomyMigrateModal
          open={migrateModalOpen}
          onClose={() => setMigrateModalOpen(false)}
          onChanged={() => void reload()}
        />
      </CardContent>
    </Card>
  );
}
