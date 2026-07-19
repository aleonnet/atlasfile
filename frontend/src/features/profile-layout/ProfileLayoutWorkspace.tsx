import { AlertTriangle, Download, FolderCog } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

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
import { invalidateAfterProfileChange } from "../../lib/mutations";
import { ProcessingAura } from "../../components/ui/processing-aura";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "../../lib/queryKeys";
import { applyLayout, getProfile, getProfileHistory, planLayout, saveProfile, validateProfile } from "./api";
import { LayoutPlanPreview } from "./LayoutPlanPreview";
import { ProfileLayoutEditor } from "./ProfileLayoutEditor";
import type { LayoutPlanResponse, ProfileHistoryEntry, ProjectProfileV2 } from "./types";
import type { StatusSeverity } from "../../types";

type Props = {
  projectRef: string;
  disabled?: boolean;
  onStatus?: (msg: string, severity?: StatusSeverity) => void;
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
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [draft, setDraft] = useState<ProjectProfileV2 | null>(null);
  const [plan, setPlan] = useState<LayoutPlanResponse | null>(null);
  const [applyConfirmed, setApplyConfirmed] = useState(false);
  const [conflictStrategy, setConflictStrategy] = useState<ConflictStrategy>("rename_with_suffix");
  const [cleanupEmptyDirs, setCleanupEmptyDirs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationMessage, setValidationMessage] = useState<string>("");
  const [validationOk, setValidationOk] = useState(false);
  const [saveAsTemplateOpen, setSaveAsTemplateOpen] = useState(false);
  useEscapeKey(saveAsTemplateOpen ? () => setSaveAsTemplateOpen(false) : null);
  const [templateName, setTemplateName] = useState("");
  const [templateSlug, setTemplateSlug] = useState("");
  const [templateDesc, setTemplateDesc] = useState("");
  const [templateSaving, setTemplateSaving] = useState(false);

  const queryClient = useQueryClient();
  // Workspace = profile + histórico numa query (mesma chave qk.profile — é o
  // mesmo endpoint; invalidations pós-mutação recarregam draft/histórico)
  const workspaceQuery = useQuery({
    queryKey: [...qk.profile(projectRef), "workspace"],
    queryFn: async () => {
      const [profileResp, historyList] = await Promise.all([getProfile(projectRef), getProfileHistory(projectRef)]);
      return { profileResp, historyList };
    },
    enabled: !!projectRef && !disabled,
  });
  const loading = workspaceQuery.isPending && !!projectRef && !disabled;
  const history = workspaceQuery.data?.historyList ?? [];
  const profile = workspaceQuery.data?.profileResp.profile ?? null;

  // Draft local: nasce do profile carregado; recarregar profile re-semeia o
  // draft apenas quando não há edição em curso (isDirty preservado)
  useEffect(() => {
    if (workspaceQuery.data) {
      setDraft(workspaceQuery.data.profileResp.profile);
      setPlan(null);
      setApplyConfirmed(false);
      setValidationMessage("");
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceQuery.data]);

  async function loadWorkspace() {
    await queryClient.invalidateQueries({ queryKey: qk.profile(projectRef) });
  }

  const isDirty = useMemo(() => {
    if (!profile || !draft) return false;
    return stableStringify(comparableProfile(profile)) !== stableStringify(comparableProfile(draft));
  }, [profile, draft]);

  const layoutChanged = useMemo(() => {
    if (!profile || !draft) return false;
    return stableStringify(profile.layout) !== stableStringify(draft.layout);
  }, [profile, draft]);

  async function handleValidate() {
    if (!draft) return;
    try {
      const result = await validateProfile(projectRef, draft);
      setValidationOk(result.valid);
      if (result.valid) {
        setValidationMessage(t("profileLayout:workspace.validProfile"));
        onStatus?.(t("profileLayout:workspace.validatedStatus"));
      } else {
        const errs = (result as { errors?: string[] }).errors ?? [];
        setValidationMessage(t("profileLayout:workspace.invalidProfile", { errors: errs.join("; ") || t("profileLayout:workspace.validationError") }));
        onStatus?.(t("profileLayout:workspace.invalidStatus"), "error");
      }
    } catch {
      setValidationOk(false);
      setValidationMessage(t("profileLayout:workspace.invalidProfileShort"));
      onStatus?.(t("profileLayout:workspace.validateFailedStatus"), "error");
    }
  }

  async function handleSave() {
    if (!draft || !profile) return;
    if (!isDirty) {
      onStatus?.(t("profileLayout:workspace.noChangesToSave"));
      return;
    }
    setSaving(true);
    try {
      const saved = await saveProfile(projectRef, draft, profile.version);
      setDraft(saved.profile);
      onStatus?.(saved.version === profile.version ? t("profileLayout:workspace.noProfileChanges") : t("profileLayout:workspace.profileSaved"));
      invalidateAfterProfileChange(projectRef);
      await loadWorkspace();
    } catch {
      onStatus?.(t("profileLayout:workspace.saveFailedStatus"), "error");
      setError(t("profileLayout:workspace.saveFailedError"));
    } finally {
      setSaving(false);
    }
  }

  async function handlePlan() {
    if (!draft) return;
    if (!layoutChanged) {
      onStatus?.(t("profileLayout:workspace.noLayoutChangesToPlan"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const next = await planLayout(projectRef, draft, { strategy: conflictStrategy, cleanup_empty_dirs: cleanupEmptyDirs });
      setPlan(next);
      setApplyConfirmed(false);
      onStatus?.(t("profileLayout:workspace.planGenerated", { count: next.summary.ops }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("profileLayout:workspace.planFailed");
      onStatus?.(msg, "error");
      setError(msg);
    } finally {
      setSaving(false);
    }
  }

  async function handleApply() {
    if (!draft || !profile || !plan) return;
    setSaving(true);
    setApplying(true);
    try {
      await applyLayout(projectRef, draft, plan.plan_id, profile.version, {
        strategy: conflictStrategy,
        cleanup_empty_dirs: cleanupEmptyDirs
      });
      onStatus?.(t("profileLayout:workspace.layoutApplied"));
      invalidateAfterProfileChange(projectRef);
      await loadWorkspace();
    } catch {
      onStatus?.(t("profileLayout:workspace.applyFailedStatus"), "error");
      setError(t("profileLayout:workspace.applyFailedError"));
    } finally {
      setSaving(false);
      setApplying(false);
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
            {t("profileLayout:workspace.title")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={<FolderCog aria-hidden />}
            title={t("profileLayout:workspace.emptyTitle")}
            description={t("profileLayout:workspace.emptyDescription")}
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
            {t("profileLayout:workspace.projectTitle", { label: draft.project_label })}
            <Badge variant="outline">{t("profileLayout:workspace.profileBadge")}</Badge>
          </CardTitle>
          <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.7rem] text-tertiary">
            <span>{t("profileLayout:workspace.idLabel")} <span className="text-muted-foreground">{draft.project_id}</span></span>
            <span>{t("profileLayout:workspace.versionLabel")} <span className="text-foreground">{draft.version}</span></span>
            {draft.updated_by && <span>{t("profileLayout:workspace.lastLabel")} <span className="text-foreground">{draft.updated_by}</span></span>}
          </div>
        </CardHeader>
      )}
      <CardContent className="space-y-4 pt-4">

      {/* ── Barra de ações ── */}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => void loadWorkspace()} disabled={loading || saving}>
          {t("common:action.reload")}
        </Button>
        <Button variant="secondary" onClick={() => void handleValidate()} disabled={!draft || loading || saving}>
          {t("profileLayout:workspace.validateChanges")}
        </Button>
        <Button onClick={() => void handleSave()} disabled={!draft || !isDirty || loading || saving}>
          {t("profileLayout:workspace.saveProfile")}
        </Button>
        <Button variant="outline" onClick={() => setSaveAsTemplateOpen(true)} disabled={!profile || loading}>
          {t("profileLayout:workspace.saveAsTemplate")}
        </Button>
      </div>

      {loading && <Skeleton className="h-24" />}
      {error && (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[0.8rem] text-destructive">{error}</p>
      )}
      {validationMessage && (
        <p
          className={
            validationOk
              ? "rounded-md border border-success/30 bg-success-subtle px-3 py-2 text-[0.8rem] text-success"
              : "rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[0.8rem] text-destructive"
          }
        >
          {validationMessage}
        </p>
      )}
      {!isDirty && draft && !error && (
        <p className="font-mono text-[0.7rem] text-tertiary">{t("profileLayout:workspace.noPendingChanges")}</p>
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
                <p className="text-[0.82rem] font-medium text-foreground">{t("profileLayout:workspace.layoutChangesDetected")}</p>
                <p className="text-[0.72rem] text-muted-foreground">{t("profileLayout:workspace.layoutChangesHint")}</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <Button variant="secondary" onClick={() => void handlePlan()} disabled={!draft || !layoutChanged || loading || saving}>
                {t("profileLayout:workspace.simulate")}
              </Button>
              <span className="font-mono text-[0.7rem] uppercase tracking-wide text-tertiary">{t("profileLayout:workspace.conflictStrategy")}</span>
              <div className="flex gap-3">
                {(["rename_with_suffix", "skip", "overwrite"] as const).map((val) => (
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
                    <span>{t(`profileLayout:strategy.${val}`)}</span>
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
                <span>{t("profileLayout:workspace.cleanupEmptyDirs")}</span>
              </label>
            </div>
          </div>
        ) : (
          <p className="font-mono text-[0.7rem] text-tertiary">{t("profileLayout:workspace.noLayoutChanges")}</p>
        )}
      </section>

      {/* ── Preview do plano ── */}
      <LayoutPlanPreview plan={plan} />

      {plan && (
        <div className="relative isolate space-y-2.5 rounded-lg">
          {applying && <ProcessingAura label={t("profileLayout:workspace.applyingAura")} />}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void handleApply()} disabled={!applyConfirmed || loading || saving}>
              {t("profileLayout:workspace.applyMigration")}
            </Button>
            <Button variant="secondary" onClick={() => setPlan(null)}>
              {t("common:action.cancel")}
            </Button>
            <Button variant="outline" onClick={handleDownloadPlan}>
              <Download />
              {t("profileLayout:workspace.downloadPlan")}
            </Button>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-3.5 accent-[var(--accent)]"
              checked={applyConfirmed}
              onChange={(e) => setApplyConfirmed(e.target.checked)}
            />
            <span>{t("profileLayout:workspace.confirmApply")}</span>
          </label>
        </div>
      )}

      {/* ── Histórico ── */}
      {history.length > 0 && (
        <CollapsibleSection title={t("profileLayout:workspace.history")} badge={String(history.length)}>
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
        <ModalShell label={t("profileLayout:workspace.saveTemplateLabel")} title={t("profileLayout:workspace.saveTemplateTitle")}>
            <label className={fieldLabelClass} htmlFor="tmpl-save-name">{t("profileLayout:workspace.name")}</label>
            <Input id="tmpl-save-name" value={templateName} onChange={(e) => {
              setTemplateName(e.target.value);
              if (!templateSlug || templateSlug === templateName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")) {
                setTemplateSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, ""));
              }
            }} />
            <label className={fieldLabelClass} htmlFor="tmpl-save-slug">{t("profileLayout:workspace.slug")}</label>
            <Input id="tmpl-save-slug" className="font-mono" value={templateSlug} onChange={(e) => setTemplateSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))} />
            <label className={fieldLabelClass} htmlFor="tmpl-save-desc">{t("profileLayout:workspace.description")}</label>
            <Textarea id="tmpl-save-desc" value={templateDesc} onChange={(e) => setTemplateDesc(e.target.value)} />
            <ModalActions>
              <Button variant="secondary" onClick={() => setSaveAsTemplateOpen(false)} disabled={templateSaving}>{t("common:action.cancel")}</Button>
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
                    onStatus?.(t("profileLayout:workspace.templateSaved"));
                    setSaveAsTemplateOpen(false);
                    setTemplateName("");
                    setTemplateSlug("");
                    setTemplateDesc("");
                  } catch {
                    onStatus?.(t("profileLayout:workspace.templateSaveFailed"), "error");
                  } finally {
                    setTemplateSaving(false);
                  }
                }}
              >
                {templateSaving ? t("profileLayout:workspace.saving") : t("profileLayout:workspace.saveTemplate")}
              </Button>
            </ModalActions>
        </ModalShell>
      )}
      </CardContent>
    </Card>
  );
}
