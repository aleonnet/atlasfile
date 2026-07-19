import { ArrowRight, Loader2, PlayCircle, SearchCheck, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  deleteTaxonomyEntry,
  fetchTaxonomy,
  migrateTaxonomy,
  type TaxonomyMigrationPlan,
  type TaxonomyMigrationResult,
} from "../../api";
import { Button } from "../../components/ui/button";
import { toast } from "../../components/ui/sonner";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "../../components/ui/modal-shell";
import { cn } from "../../lib/utils";
import { invalidateAfterTaxonomyChange } from "../../lib/mutations";

type Kind = "document_type" | "business_domain";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Notifica mudanças aplicadas (recarregar template no editor). */
  onChanged?: () => void;
};

const hintClass = "mt-1 block text-[0.72rem] text-tertiary";

/** Migração/remoção governada: dry-run primeiro (conta os 9 alvos), aplicar com
 *  confirmação; a key antiga vira alias do destino (bootstrap segue reconhecendo). */
export function TaxonomyMigrateModal({ open, onClose, onChanged }: Props) {
  const { t } = useTranslation();
  const datasetLabel = (key: string) => t(`templates:dataset.${key}`, { defaultValue: key });
  const [kind, setKind] = useState<Kind>("document_type");
  const [taxonomy, setTaxonomy] = useState<{ business_domains: string[]; document_types: string[] }>({
    business_domains: [],
    document_types: [],
  });
  const [fromKey, setFromKey] = useState("");
  const [toKey, setToKey] = useState("");
  const [removeOld, setRemoveOld] = useState(true);
  const [busy, setBusy] = useState<"" | "plan" | "apply" | "delete">("");
  const [plan, setPlan] = useState<TaxonomyMigrationPlan | null>(null);
  const [result, setResult] = useState<TaxonomyMigrationResult | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetchTaxonomy().then(setTaxonomy).catch(() => {});
    setPlan(null);
    setResult(null);
    setConfirmApply(false);
  }, [open]);

  if (!open) return null;

  const keys = kind === "document_type" ? taxonomy.document_types : taxonomy.business_domains;
  const destinations = keys.filter((k) => k !== fromKey);
  const ready = !!fromKey && !!toKey && fromKey !== toKey;

  async function handlePlan() {
    if (!ready) return;
    setBusy("plan");
    setResult(null);
    try {
      const preview = (await migrateTaxonomy({
        kind, from_key: fromKey, to_key: toKey, dry_run: true,
      })) as TaxonomyMigrationPlan;
      setPlan(preview);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("templates:migrate.simulateFailed"));
      setPlan(null);
    } finally {
      setBusy("");
    }
  }

  async function handleApply() {
    setConfirmApply(false);
    setBusy("apply");
    try {
      const applied = (await migrateTaxonomy({
        kind, from_key: fromKey, to_key: toKey, dry_run: false, remove_old: removeOld,
      })) as TaxonomyMigrationResult;
      setResult(applied);
      setPlan(null);
      invalidateAfterTaxonomyChange();
      toast.success(
        t("templates:migrate.appliedToast", {
          docs: t("templates:migrate.docsMoved", { count: applied.moved_total }),
          records: t("templates:migrate.recordsRewritten", { count: Object.values(applied.datasets).reduce((s, n) => s + n, 0) }),
        })
      );
      onChanged?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("templates:migrate.applyFailed"));
    } finally {
      setBusy("");
    }
  }

  async function handleDelete() {
    if (!fromKey) return;
    setBusy("delete");
    try {
      const removed = await deleteTaxonomyEntry(kind, fromKey);
      toast.success(
        t("templates:migrate.removedToast", {
          key: fromKey,
          templates: t("templates:migrate.templatesCount", { count: removed.templates_updated.length }),
          projects: t("templates:migrate.projectsCount", { count: removed.projects_updated.length }),
        })
      );
      setFromKey("");
      setPlan(null);
      fetchTaxonomy().then(setTaxonomy).catch(() => {});
      invalidateAfterTaxonomyChange();
      onChanged?.();
    } catch (e) {
      // 409 do backend explica o uso ativo e aponta para a migração
      toast.error(e instanceof Error ? e.message : t("templates:migrate.removeFailed"));
    } finally {
      setBusy("");
    }
  }

  return (
    <ModalShell label={t("templates:migrate.title")} title={t("templates:migrate.title")} className="max-h-[85vh] overflow-y-auto">
      <p className="text-sm text-muted-foreground">
        {t("templates:migrate.intro")}
      </p>

      <label className={fieldLabelClass} htmlFor="tax-migrate-kind">{t("templates:migrate.kindLabel")}</label>
      <select
        id="tax-migrate-kind"
        className={nativeSelectClass}
        value={kind}
        onChange={(e) => {
          setKind(e.target.value as Kind);
          setFromKey("");
          setToKey("");
          setPlan(null);
          setResult(null);
        }}
      >
        <option value="document_type">{t("templates:kind.document_type")}</option>
        <option value="business_domain">{t("templates:kind.business_domain")}</option>
      </select>

      <div className="mt-1 grid grid-cols-[1fr_auto_1fr] items-end gap-2">
        <div>
          <label className={fieldLabelClass} htmlFor="tax-migrate-from">{t("templates:migrate.from")}</label>
          <select
            id="tax-migrate-from"
            className={nativeSelectClass}
            value={fromKey}
            onChange={(e) => {
              setFromKey(e.target.value);
              setPlan(null);
              setResult(null);
            }}
          >
            <option value="">{t("templates:migrate.selectPlaceholder")}</option>
            {keys.map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
        </div>
        <ArrowRight className="mb-2 size-4 shrink-0 text-tertiary" aria-hidden />
        <div>
          <label className={fieldLabelClass} htmlFor="tax-migrate-to">{t("templates:migrate.to")}</label>
          <select
            id="tax-migrate-to"
            className={nativeSelectClass}
            value={toKey}
            onChange={(e) => {
              setToKey(e.target.value);
              setPlan(null);
              setResult(null);
            }}
          >
            <option value="">{t("templates:migrate.selectPlaceholder")}</option>
            {destinations.map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
        </div>
      </div>
      <span className={hintClass}>
        {t("templates:migrate.destinationHint")}
      </span>

      <label className="mt-3 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-3.5 accent-[var(--accent)]"
          checked={removeOld}
          onChange={(e) => setRemoveOld(e.target.checked)}
        />
        {t("templates:migrate.removeOld")}
      </label>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Button variant="secondary" size="sm" disabled={!ready || busy !== ""} onClick={() => void handlePlan()}>
          {busy === "plan" ? <Loader2 className="animate-spin" /> : <SearchCheck />} {t("templates:migrate.simulate")}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={!fromKey || busy !== ""}
          title={t("templates:migrate.removeSourceTitle")}
          onClick={() => void handleDelete()}
        >
          {busy === "delete" ? <Loader2 className="animate-spin" /> : <Trash2 />} {t("templates:migrate.removeSource")}
        </Button>
      </div>

      {plan && (
        <div className="mt-3 rounded-md border border-border bg-elevated px-3 py-2.5">
          <p className="m-0 font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">
            {t("templates:migrate.planTitle", { from: plan.from_key, to: plan.to_key })}
          </p>
          <ul className="m-0 mt-1.5 list-none space-y-0.5 p-0 text-[0.8rem] text-foreground">
            <li>
              <strong>{plan.documents_total}</strong> {t("templates:migrate.documentsLabel", { count: plan.documents_total })}{" "}
              {Object.entries(plan.documents_by_project).map(([p, n]) => `${p} (${n})`).join(", ") || "—"}
            </li>
            <li>
              {t("templates:migrate.datasetsLabel")}{" "}
              {Object.entries(plan.datasets)
                .filter(([, n]) => n > 0)
                .map(([k, n]) => `${datasetLabel(k)} (${n})`)
                .join(", ") || t("templates:migrate.noRecords")}
            </li>
            <li>{t("templates:migrate.pendingTriage", { value: plan.pending_triage })}</li>
            <li>{t("templates:migrate.templatesAffected", { list: plan.templates.join(", ") || t("templates:migrate.none") })}</li>
            {plan.routing_rules_pointing > 0 && <li>{t("templates:migrate.routingRules", { value: plan.routing_rules_pointing })}</li>}
          </ul>
          {(plan.warnings ?? []).map((w) => (
            <p key={w} className="m-0 mt-1.5 text-[0.75rem] text-accent">⚠ {w}</p>
          ))}
          <div className="relative mt-2">
            <Button size="sm" disabled={busy !== ""} onClick={() => setConfirmApply(true)}>
              {busy === "apply" ? <Loader2 className="animate-spin" /> : <PlayCircle />} {t("templates:migrate.applyMigration")}
            </Button>
            {confirmApply && (
              <div className="absolute left-0 top-[calc(100%+6px)] z-20 flex min-w-72 flex-col gap-2 rounded-md border border-border bg-panel p-3 shadow-[0_4px_12px_rgba(0,0,0,0.25)]">
                <p className="m-0 text-[0.82rem] text-foreground">
                  {t("templates:migrate.confirmApply", { count: plan.documents_total, from: plan.from_key, to: plan.to_key })}
                </p>
                <div className="flex gap-1.5">
                  <Button size="sm" onClick={() => void handleApply()}>{t("common:action.confirm")}</Button>
                  <Button variant="secondary" size="sm" onClick={() => setConfirmApply(false)}>{t("common:action.no")}</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {result && (
        <div className={cn("mt-3 rounded-md border px-3 py-2.5", (result.errors ?? []).length ? "border-destructive/40 bg-destructive/5" : "border-success/40 bg-success-subtle")}>
          <p className="m-0 font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">{t("templates:migrate.resultTitle")}</p>
          <ul className="m-0 mt-1.5 list-none space-y-0.5 p-0 text-[0.8rem] text-foreground">
            <li><strong>{result.moved_total}</strong> {t("templates:migrate.movedResult", { count: result.moved_total, indexOnly: result.index_only })}</li>
            <li>
              {t("templates:migrate.datasetsRewritten")}{" "}
              {Object.entries(result.datasets ?? {}).filter(([, n]) => n > 0).map(([k, n]) => `${datasetLabel(k)} (${n})`).join(", ") || t("templates:migrate.none")}
            </li>
            <li>{t("templates:migrate.pendingRewritten", { value: result.pending_rewritten })}</li>
            <li>{t("templates:migrate.templatesProjects", { templates: (result.templates_updated ?? []).join(", ") || "—", projects: (result.projects_updated ?? []).join(", ") || "—" })}</li>
          </ul>
          {(result.errors ?? []).map((e) => (
            <p key={e.doc_id} className="m-0 mt-1 font-mono text-[0.72rem] text-destructive">{e.doc_id}: {e.error}</p>
          ))}
          {(result.warnings ?? []).map((w) => (
            <p key={w} className="m-0 mt-1.5 text-[0.75rem] text-accent">⚠ {w}</p>
          ))}
        </div>
      )}

      <ModalActions>
        <Button variant="secondary" onClick={onClose}>{t("common:action.close")}</Button>
      </ModalActions>
    </ModalShell>
  );
}
