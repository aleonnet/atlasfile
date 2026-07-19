import { useTranslation } from "react-i18next";
import { Badge } from "../../components/ui/badge";
import { cn } from "../../lib/utils";
import type { LayoutPlanResponse } from "./types";

type Props = {
  plan: LayoutPlanResponse | null;
};

const opBadgeClass: Record<string, string> = {
  mkdir: "bg-success-subtle text-success",
  move: "bg-accent-soft text-accent",
  rename: "bg-accent-purple/10 text-accent-purple",
  conflict: "bg-destructive/10 text-destructive",
};

export function LayoutPlanPreview({ plan }: Props) {
  const { t } = useTranslation();
  if (!plan) return null;
  const skipCount = plan.plan.ops.filter((op) => op.op === "skip").length;
  const rmdirCount = plan.plan.ops.filter((op) => op.op === "rmdir_empty").length;
  const conflictItems = plan.plan.ops.filter((op) => op.op === "conflict").slice(0, 8);
  const actionItems = plan.plan.ops.filter((op) => op.op === "move" || op.op === "mkdir" || op.op === "rename_dir").slice(0, 40);

  const kpis: Array<[string, number]> = [
    ["rename", plan.summary.renames ?? 0],
    ["mkdir", plan.summary.mkdirs],
    ["move", plan.summary.moves],
    ["conflicts", plan.summary.conflicts],
    ["skip", skipCount],
    ["rmdir_empty", rmdirCount],
  ];

  return (
    <section className="rounded-lg border border-border bg-panel-strong/30 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-display text-sm font-bold text-foreground-strong">{t("profileLayout:preview.title")}</h4>
        <Badge variant="outline">plan_id: {plan.plan_id}</Badge>
      </div>

      <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.72rem] text-muted-foreground">
        {kpis.map(([label, value]) => (
          <span key={label}>
            {label}:{" "}
            <strong className={cn("text-foreground-strong", label === "conflicts" && value > 0 && "text-destructive")}>
              {value}
            </strong>
          </span>
        ))}
      </div>

      {actionItems.length > 0 && (
        <div className="mt-3">
          <h5 className="mb-1.5 font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">{t("profileLayout:preview.opsSample")}</h5>
          <div className="max-h-56 space-y-0.5 overflow-y-auto">
            {actionItems.map((op, idx) => {
              const kind = op.op === "rename_dir" ? "rename" : op.op;
              return (
                <div key={`op-${idx}`} className="flex flex-wrap items-baseline gap-2 font-mono text-[0.72rem]">
                  <code className={cn("rounded px-1.5 py-0.5 text-[0.65rem]", opBadgeClass[kind] ?? "bg-panel-strong text-muted-foreground")}>
                    {op.op === "mkdir" ? "+" : op.op === "rename_dir" ? "↷" : ">"} {kind}
                  </code>
                  <span className="min-w-0 truncate text-foreground">{op.src || op.dst || "-"}</span>
                  {(op.op === "move" || op.op === "rename_dir") && op.dst && (
                    <span className="truncate text-tertiary">→ {op.dst}</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {conflictItems.length > 0 && (
        <div className="mt-3">
          <h5 className="mb-1.5 font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">{t("profileLayout:preview.conflicts")}</h5>
          <div className="space-y-0.5">
            {conflictItems.map((op, idx) => (
              <div key={`conflict-${idx}`} className="flex flex-wrap items-baseline gap-2 font-mono text-[0.72rem]">
                <code className={cn("rounded px-1.5 py-0.5 text-[0.65rem]", opBadgeClass.conflict)}>! conflict</code>
                <span className="text-foreground">{op.reason || t("profileLayout:preview.destExists")}</span>
                <small className="truncate text-tertiary">{op.src || op.dst || "-"}</small>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="mt-3 font-mono text-[0.7rem] text-tertiary">
        {t("profileLayout:preview.strategyLabel")} <strong className="text-foreground">{plan.plan.strategy.replace(/_/g, " ")}</strong>
      </p>
    </section>
  );
}
