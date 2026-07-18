import { AlertTriangle, Download, FolderCog } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { createTemplate } from "../../api";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { CollapsibleSection } from "../../components/ui/collapsible-section";
import { EmptyState } from "../../components/ui/empty-state";
import { Input, Textarea } from "../../components/ui/input";
import { fieldLabelClass, ModalActions, ModalShell } from "../../components/ui/modal-shell";
import { Skeleton } from "../../components/ui/skeleton";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { emitDataRefresh } from "../../lib/refreshBus";
import { applyLayout, getProfile, getProfileHistory, planLayout, saveProfile, validateProfile } from "./api";
import { LayoutPlanPreview } from "./LayoutPlanPreview";
import { ProfileLayoutEditor } from "./ProfileLayoutEditor";
import type { LayoutPlanResponse, ProfileHistoryEntry, ProjectProfileV2 } from "./types";

type Props = {
  projectRef: string;
  disabled?: boolean;
  onStatus?: (msg: string) => void;
};

type ConflictStrategy = "rename_with_suffix" | "skip" | "overwrite";

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return `{${Object.keys(obj)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function comparableProfile(profile: ProjectProfileV2): Record<string, unknown> {
  const { version, updated_at, updated_by, ...rest } = profile;
  return rest as Record<string, unknown>;
}

export function ProfileLayoutWorkspace({ projectRef, disabled = false, onStatus }: Props) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState<ProjectProfileV2 | null>(null);
  const [draft, setDraft] = useState<ProjectProfileV2 | null>(null);
  const [history, setHistory] = useState<ProfileHistoryEntry[]>([]);
  const [plan, setPlan] = useState<LayoutPlanResponse | null>(null);
  const [applyConfirmed, setApplyConfirmed] = useState(false);
  const [conflictStrategy, setConflictStrategy] = useState<ConflictStrategy>("rename_with_suffix");
  const [cleanupEmptyDirs, setCleanupEmptyDirs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationMessage, setValidationMessage] = useState<string>("");
  const [saveAsTemplateOpen, setSaveAsTemplateOpen] = useState(false);
  useEscapeKey(saveAsTemplateOpen ? () => setSaveAsTemplateOpen(false) : null);
  const [templateName, setTemplateName] = useState("");
  const [templateSlug, setTemplateSlug] = useState("");
  const [templateDesc, setTemplateDesc] = useState("");
  const [templateSaving, setTemplateSaving] = useState(false);

  const isDirty = useMemo(() => {
    if (!profile || !draft) return false;
    return stableStringify(comparableProfile(profile)) !== stableStringify(comparableProfile(draft));
  }, [profile, draft]);

  const layoutChanged = useMemo(() => {
    if (!profile || !draft) return false;
    return stableStringify(profile.layout) !== stableStringify(draft.layout);
  }, [profile, draft]);

  async function loadWorkspace() {
    if (!projectRef || disabled) return;
    setLoading(true);
    setError(null);
    setPlan(null);
    setApplyConfirmed(false);
    try {
      const [profileResp, historyList] = await Promise.all([getProfile(projectRef), getProfileHistory(projectRef)]);
      setProfile(profileResp.profile);
      setDraft(profileResp.profile);
      setHistory(historyList);
      setValidationMessage("");
    } catch {
      setError("Falha ao carregar profile/layout do projeto.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadWorkspace();
  }, [projectRef, disabled]);

  async function handleValidate() {
    if (!draft) return;
    try {
      const result = await validateProfile(projectRef, draft);
      if (result.valid) {
        setValidationMessage("Profile válido.");
        onStatus?.("Profile validado com sucesso");
      } else {
        const errs = (result as { errors?: string[] }).errors ?? [];
        setValidationMessage(`Profile inválido: ${errs.join("; ") || "erro de validação"}`);
        onStatus?.("Profile inválido");
      }
    } catch {
      setValidationMessage("Profile inválido.");
      onStatus?.("Falha ao validar profile");
    }
  }

  async function handleSave() {
    if (!draft || !profile) return;
    if (!isDirty) {
      onStatus?.("Sem alterações para salvar");
      return;
    }
    setSaving(true);
    try {
      const saved = await saveProfile(projectRef, draft, profile.version);
      setProfile(saved.profile);
      setDraft(saved.profile);
      onStatus?.(saved.version === profile.version ? "Sem alterações no profile" : "Profile salvo");
      emitDataRefresh();
      await loadWorkspace();
    } catch {
      onStatus?.("Falha ao salvar profile");
      setError("Não foi possível salvar o profile (versão desatualizada ou payload inválido).");
    } finally {
      setSaving(false);
    }
  }

  async function handlePlan() {
    if (!draft) return;
    if (!layoutChanged) {
      onStatus?.("Sem alterações de layout para planejar");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const next = await planLayout(projectRef, draft, { strategy: conflictStrategy, cleanup_empty_dirs: cleanupEmptyDirs });
      setPlan(next);
      setApplyConfirmed(false);
      onStatus?.(`Plano gerado: ${next.summary.ops} operação(ões)`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Falha ao gerar plano";
      onStatus?.(msg);
      setError(msg);
    } finally {
      setSaving(false);
    }
  }

  async function handleApply() {
    if (!draft || !profile || !plan) return;
    setSaving(true);
    try {
      await applyLayout(projectRef, draft, plan.plan_id, profile.version, {
        strategy: conflictStrategy,
        cleanup_empty_dirs: cleanupEmptyDirs
      });
      onStatus?.("Layout aplicado com sucesso");
      emitDataRefresh();
      await loadWorkspace();
    } catch {
      onStatus?.("Falha ao aplicar layout");
      setError("Aplicação de layout falhou.");
    } finally {
      setSaving(false);
    }
  }

  function handleDownloadPlan() {
    if (!plan) return;
    const blob = new Blob([JSON.stringify(plan, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `layout-plan-${plan.plan_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (disabled) {
    return (
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="flex min-h-9 items-center gap-2">
            <FolderCog className="size-4 text-accent" aria-hidden />
            Perfil e Organização
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={<FolderCog aria-hidden />}
            title="Nenhum projeto selecionado"
            description="Selecione um projeto específico para editar perfil e organização."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      {/* ── Cabeçalho com metadados do projeto ── */}
      {draft && (
        <CardHeader className="flex-row flex-wrap items-center justify-between space-y-0 pb-0">
          <CardTitle className="flex min-h-9 items-center gap-2">
            <FolderCog className="size-4 text-accent" aria-hidden />
            Projeto: {draft.project_label}
            <Badge variant="outline">Profile v2 JSON</Badge>
          </CardTitle>
          <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.7rem] text-tertiary">
            <span>ID: <span className="text-muted-foreground">{draft.project_id}</span></span>
            <span>Versão: <span className="text-foreground">{draft.version}</span></span>
            {draft.updated_by && <span>Última: <span className="text-foreground">{draft.updated_by}</span></span>}
          </div>
        </CardHeader>
      )}
      <CardContent className="space-y-4 pt-4">

      {/* ── Barra de ações ── */}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => void loadWorkspace()} disabled={loading || saving}>
          Recarregar
        </Button>
        <Button variant="secondary" onClick={() => void handleValidate()} disabled={!draft || loading || saving}>
          Validar alterações
        </Button>
        <Button onClick={() => void handleSave()} disabled={!draft || !isDirty || loading || saving}>
          Salvar Profile
        </Button>
        <Button variant="outline" onClick={() => setSaveAsTemplateOpen(true)} disabled={!profile || loading}>
          Salvar como Template
        </Button>
      </div>

      {loading && <Skeleton className="h-24" />}
      {error && (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[0.8rem] text-destructive">{error}</p>
      )}
      {validationMessage && (
        <p
          className={
            validationMessage.startsWith("Profile válido")
              ? "rounded-md border border-success/30 bg-success-subtle px-3 py-2 text-[0.8rem] text-success"
              : "rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[0.8rem] text-destructive"
          }
        >
          {validationMessage}
        </p>
      )}
      {!isDirty && draft && !error && (
        <p className="font-mono text-[0.7rem] text-tertiary">Sem alterações pendentes no profile.</p>
      )}

      {/* ── Editor (modo, raízes, áreas, geral) ── */}
      {draft && <ProfileLayoutEditor profile={draft} onChange={setDraft} />}

      {/* ── Seção: Migração ── */}
      <section className="rounded-lg border border-border p-4">
        {layoutChanged ? (
          <div className="space-y-3">
            <div className="flex items-start gap-2.5 rounded-md border border-accent/30 bg-accent-soft px-3 py-2.5">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-accent" aria-hidden />
              <div>
                <p className="text-[0.82rem] font-medium text-foreground">Alterações detectadas em layout (areas_root/business_domain_folders)</p>
                <p className="text-[0.72rem] text-muted-foreground">Salvar o profile NÃO move arquivos automaticamente.</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <Button variant="secondary" onClick={() => void handlePlan()} disabled={!draft || !layoutChanged || loading || saving}>
                Simular
              </Button>
              <span className="font-mono text-[0.7rem] uppercase tracking-wide text-tertiary">Estratégia conflito:</span>
              <div className="flex gap-3">
                {([["rename_with_suffix", "renomear"], ["skip", "pular"], ["overwrite", "sobrescrever"]] as const).map(([val, label]) => (
                  <label key={val} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="radio"
                      name="conflict-strategy"
                      className="size-3.5 accent-[var(--accent)]"
                      value={val}
                      checked={conflictStrategy === val}
                      onChange={() => setConflictStrategy(val)}
                      disabled={loading || saving}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              <label className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  className="size-3.5 accent-[var(--accent)]"
                  checked={cleanupEmptyDirs}
                  onChange={(e) => setCleanupEmptyDirs(e.target.checked)}
                  disabled={loading || saving}
                />
                <span>Excluir pastas vazias</span>
              </label>
            </div>
          </div>
        ) : (
          <p className="font-mono text-[0.7rem] text-tertiary">Sem alterações de layout pendentes. Edite raízes ou mapeamento de áreas para simular.</p>
        )}
      </section>

      {/* ── Preview do plano ── */}
      <LayoutPlanPreview plan={plan} />

      {plan && (
        <div className="space-y-2.5">
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void handleApply()} disabled={!applyConfirmed || loading || saving}>
              Aplicar migração
            </Button>
            <Button variant="secondary" onClick={() => setPlan(null)}>
              Cancelar
            </Button>
            <Button variant="outline" onClick={handleDownloadPlan}>
              <Download />
              Baixar plano (.json)
            </Button>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-3.5 accent-[var(--accent)]"
              checked={applyConfirmed}
              onChange={(e) => setApplyConfirmed(e.target.checked)}
            />
            <span>Confirmo a aplicação do plano de layout no projeto selecionado.</span>
          </label>
        </div>
      )}

      {/* ── Histórico ── */}
      {history.length > 0 && (
        <CollapsibleSection title="Histórico" badge={String(history.length)}>
          <div className="space-y-1">
            {history.slice(0, 8).map((entry) => (
              <div key={entry.entry} className="flex items-baseline justify-between gap-2 font-mono text-[0.72rem]">
                <span className="truncate text-foreground">{entry.entry}</span>
                <small className="shrink-0 text-tertiary">v{entry.version} · {entry.updated_by || "—"}</small>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}
      {saveAsTemplateOpen && (
        <ModalShell label="Salvar como template" title="Salvar profile como template">
            <label className={fieldLabelClass} htmlFor="tmpl-save-name">Nome</label>
            <Input id="tmpl-save-name" value={templateName} onChange={(e) => {
              setTemplateName(e.target.value);
              if (!templateSlug || templateSlug === templateName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")) {
                setTemplateSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, ""));
              }
            }} />
            <label className={fieldLabelClass} htmlFor="tmpl-save-slug">Slug</label>
            <Input id="tmpl-save-slug" className="font-mono" value={templateSlug} onChange={(e) => setTemplateSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))} />
            <label className={fieldLabelClass} htmlFor="tmpl-save-desc">Descrição</label>
            <Textarea id="tmpl-save-desc" value={templateDesc} onChange={(e) => setTemplateDesc(e.target.value)} />
            <ModalActions>
              <Button variant="secondary" onClick={() => setSaveAsTemplateOpen(false)} disabled={templateSaving}>Cancelar</Button>
              <Button
                disabled={templateSaving || !templateSlug || !templateName}
                onClick={async () => {
                  setTemplateSaving(true);
                  try {
                    await createTemplate({
                      from_profile: projectRef,
                      slug: templateSlug,
                      name: templateName,
                      description: templateDesc,
                    });
                    onStatus?.("Template salvo com sucesso");
                    setSaveAsTemplateOpen(false);
                    setTemplateName("");
                    setTemplateSlug("");
                    setTemplateDesc("");
                  } catch {
                    onStatus?.("Falha ao salvar template");
                  } finally {
                    setTemplateSaving(false);
                  }
                }}
              >
                {templateSaving ? "Salvando..." : "Salvar template"}
              </Button>
            </ModalActions>
        </ModalShell>
      )}
      </CardContent>
    </Card>
  );
}
