import type { LayoutPlanResponse } from "./types";

type Props = {
  plan: LayoutPlanResponse | null;
};

export function LayoutPlanPreview({ plan }: Props) {
  if (!plan) return null;
  const skipCount = plan.plan.ops.filter((op) => op.op === "skip").length;
  const rmdirCount = plan.plan.ops.filter((op) => op.op === "rmdir_empty").length;
  const conflictItems = plan.plan.ops.filter((op) => op.op === "conflict").slice(0, 8);
  const actionItems = plan.plan.ops.filter((op) => op.op === "move" || op.op === "mkdir" || op.op === "rename_dir").slice(0, 40);

  return (
    <section className="pl-section pl-plan-preview">
      <div className="pl-plan-header">
        <h4 className="pl-section-title">Preview: Plano de Migração</h4>
        <span className="profile-layout-pill">plan_id: {plan.plan_id}</span>
      </div>

      <div className="pl-plan-summary">
        <span className="pl-kpi"><strong>rename:</strong> {plan.summary.renames ?? 0}</span>
        <span className="pl-kpi"><strong>mkdir:</strong> {plan.summary.mkdirs}</span>
        <span className="pl-kpi"><strong>move:</strong> {plan.summary.moves}</span>
        <span className="pl-kpi"><strong>conflicts:</strong> {plan.summary.conflicts}</span>
        <span className="pl-kpi"><strong>skip:</strong> {skipCount}</span>
        <span className="pl-kpi"><strong>rmdir_empty:</strong> {rmdirCount}</span>
      </div>

      {actionItems.length > 0 && (
        <div className="pl-plan-ops">
          <h5 className="pl-plan-ops-title">Operações (amostra)</h5>
          <div className="pl-plan-ops-list">
            {actionItems.map((op, idx) => (
              <div key={`op-${idx}`} className="pl-plan-op-row">
                <code className={`pl-op-badge pl-op-${op.op === "rename_dir" ? "rename" : op.op}`}>
                  {op.op === "mkdir" ? "+" : op.op === "rename_dir" ? "↷" : ">"} {op.op === "rename_dir" ? "rename" : op.op}
                </code>
                <span className="pl-op-path">{op.src || op.dst || "-"}</span>
                {(op.op === "move" || op.op === "rename_dir") && op.dst && (
                  <span className="pl-op-dest">→ {op.dst}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {conflictItems.length > 0 && (
        <div className="pl-plan-conflicts">
          <h5 className="pl-plan-ops-title">Conflitos</h5>
          {conflictItems.map((op, idx) => (
            <div key={`conflict-${idx}`} className="pl-plan-conflict-row">
              <code className="pl-op-badge pl-op-conflict">! conflict</code>
              <span className="pl-op-path">{op.reason || "destino já existe"}</span>
              <small className="pl-op-dest">{op.src || op.dst || "-"}</small>
            </div>
          ))}
        </div>
      )}

      <p className="pl-plan-strategy">
        Estratégia de conflito: <strong>{plan.plan.strategy.replace(/_/g, " ")}</strong>
      </p>
    </section>
  );
}
