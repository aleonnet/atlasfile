import { useEffect, useMemo, useState } from "react";

import { applyLayout, getProfile, getProfileHistory, planLayout, saveProfile, validateProfile } from "./api";
import { LayoutPlanPreview } from "./LayoutPlanPreview";
import { ProfileLayoutEditor } from "./ProfileLayoutEditor";
import type { LayoutPlanResponse, ProfileHistoryEntry, ProjectProfileV2 } from "./types";
import "./profileLayout.css";

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
      <section className="panel card">
        <div className="panel-head card-header">
          <h2>Profile & Layout por projeto</h2>
        </div>
        <p className="card-intro">Selecione um projeto específico para editar profile/layout.</p>
      </section>
    );
  }

  return (
    <section className="panel card pl-shell">
      {/* ── Cabeçalho com metadados do projeto ── */}
      {draft && (
        <div className="pl-project-header">
          <div className="pl-project-header-main">
            <h2 className="pl-project-title">
              Projeto: {draft.project_label}
              <span className="pl-project-meta-badge">Profile v2 JSON</span>
            </h2>
          </div>
          <div className="pl-project-header-meta">
            <span>ID: <code>{draft.project_id}</code></span>
            <span>Versão: <strong>{draft.version}</strong></span>
            {draft.updated_by && <span>Última: <strong>{draft.updated_by}</strong></span>}
          </div>
        </div>
      )}

      {/* ── Barra de ações ── */}
      <div className="pl-toolbar">
        <button className="btn" onClick={() => void loadWorkspace()} disabled={loading || saving}>
          Recarregar
        </button>
        <button className="btn" onClick={() => void handleValidate()} disabled={!draft || loading || saving}>
          Validar alterações
        </button>
        <button className="btn primary" onClick={() => void handleSave()} disabled={!draft || !isDirty || loading || saving}>
          Salvar Profile
        </button>
      </div>

      {loading && <p className="card-intro">Carregando profile...</p>}
      {error && <p className="pl-msg-error">{error}</p>}
      {validationMessage && <p className={validationMessage.startsWith("Profile válido") ? "pl-msg-ok" : "pl-msg-error"}>{validationMessage}</p>}
      {!isDirty && draft && !error && <p className="pl-msg-muted pl-msg-idle">Sem alterações pendentes no profile.</p>}

      {/* ── Editor (modo, raízes, áreas, geral) ── */}
      {draft && <ProfileLayoutEditor profile={draft} onChange={setDraft} />}

      {/* ── Seção: Migração ── */}
      <section className="pl-section pl-migration-section">
        {layoutChanged ? (
          <>
            <div className="pl-migration-warning">
              <span className="pl-migration-icon">⚠</span>
              <div>
                <p className="pl-migration-warn-text">Alterações detectadas em layout (areas_root/area_folders)</p>
                <p className="pl-migration-warn-sub">Salvar o profile NÃO move arquivos automaticamente.</p>
              </div>
            </div>
            <div className="pl-migration-controls">
              <div className="pl-migration-row-main">
                <button className="btn" onClick={() => void handlePlan()} disabled={!draft || !layoutChanged || loading || saving}>
                  Simular
                </button>
                <span className="pl-strategy-label">Estratégia conflito:</span>
                <div className="pl-strategy-radios">
                  {([["rename_with_suffix", "renomear"], ["skip", "pular"], ["overwrite", "sobrescrever"]] as const).map(([val, label]) => (
                    <label key={val} className="pl-radio">
                      <input
                        type="radio"
                        name="conflict-strategy"
                        value={val}
                        checked={conflictStrategy === val}
                        onChange={() => setConflictStrategy(val)}
                        disabled={loading || saving}
                      />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <label className="pl-checkbox pl-cleanup-check">
                <input
                  type="checkbox"
                  checked={cleanupEmptyDirs}
                  onChange={(e) => setCleanupEmptyDirs(e.target.checked)}
                  disabled={loading || saving}
                />
                <span>Excluir pastas vazias</span>
              </label>
            </div>
          </>
        ) : (
          <p className="pl-msg-muted">Sem alterações de layout pendentes. Edite raízes ou mapeamento de áreas para simular.</p>
        )}
      </section>

      {/* ── Preview do plano ── */}
      <LayoutPlanPreview plan={plan} />

      {plan && (
        <>
          <div className="pl-plan-actions">
            <button className="btn primary" onClick={() => void handleApply()} disabled={!applyConfirmed || loading || saving}>
              Aplicar migração
            </button>
            <button type="button" className="btn" onClick={() => setPlan(null)}>
              Cancelar
            </button>
            <button type="button" className="btn" onClick={handleDownloadPlan}>
              Baixar plano (.json)
            </button>
          </div>
          <label className="pl-checkbox pl-confirm-check">
            <input
              type="checkbox"
              checked={applyConfirmed}
              onChange={(e) => setApplyConfirmed(e.target.checked)}
            />
            <span>Confirmo a aplicação do plano de layout no projeto selecionado.</span>
          </label>
        </>
      )}

      {/* ── Histórico ── */}
      {history.length > 0 && (
        <details className="pl-collapsible">
          <summary className="pl-collapsible-header">Histórico ({history.length})</summary>
          <div className="pl-collapsible-body">
            <div className="pl-history-list">
              {history.slice(0, 8).map((entry) => (
                <div key={entry.entry} className="pl-history-row">
                  <span>{entry.entry}</span>
                  <small>v{entry.version} · {entry.updated_by || "—"}</small>
                </div>
              ))}
            </div>
          </div>
        </details>
      )}
    </section>
  );
}
