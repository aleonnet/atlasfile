import { RefreshCw, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchHealth, fetchReconcileStatus, restartSystem, runReconcile } from "../../api";
import { Button } from "../../components/ui/button";
import { ModalActions, ModalShell } from "../../components/ui/modal-shell";

type Props = {
  open: boolean;
  /** Caminho físico da pasta no host (informativo). */
  hostRoot?: string;
  /** Revalida o setup status (caso o usuário tenha restaurado por fora). */
  onRevalidate: () => void;
};

type Phase = "idle" | "restarting" | "reconciling" | "failed";

const HEALTH_POLL_MS = 2_000;
const HEALTH_TIMEOUT_MS = 90_000;
const RECONCILE_POLL_MS = 1_500;
const RECONCILE_TIMEOUT_MS = 60_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Recuperação da raiz de projetos esvaziada (pasta host deletada sob bind
 * mount): um clique reinicia a aplicação — o Docker recria a pasta e religa o
 * mount —, o índice órfão é limpo e a página recarrega no onboarding.
 */
export function RootRecoveryModal({ open, hostRoot, onRevalidate }: Props) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<Phase>("idle");

  if (!open) return null;

  async function handleRestart() {
    setPhase("restarting");
    try {
      await restartSystem();
    } catch {
      // o processo pode encerrar antes da resposta chegar — o polling decide
    }
    const healthDeadline = Date.now() + HEALTH_TIMEOUT_MS;
    let healthy = false;
    while (Date.now() < healthDeadline) {
      await sleep(HEALTH_POLL_MS);
      try {
        const health = await fetchHealth();
        if (health.ok) {
          healthy = true;
          break;
        }
      } catch {
        // ainda reiniciando
      }
    }
    if (!healthy) {
      setPhase("failed");
      return;
    }
    setPhase("reconciling");
    try {
      await runReconcile();
      const reconcileDeadline = Date.now() + RECONCILE_TIMEOUT_MS;
      while (Date.now() < reconcileDeadline) {
        await sleep(RECONCILE_POLL_MS);
        const status = await fetchReconcileStatus();
        if (!status.running && status.last_run_finished_at) break;
      }
    } catch {
      // índice será reconciliado pelo ciclo automático; não trava a recuperação
    }
    window.location.reload();
  }

  return (
    <ModalShell label={t("painel:recovery.label")} title={t("painel:recovery.title")} size="md">
      <div className="flex flex-col gap-3 text-sm text-muted-foreground">
        <p className="flex items-start gap-2">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          <span>
            {t("painel:recovery.body")}
            {hostRoot && <code className="ml-1 rounded bg-panel-strong px-1 py-0.5 font-mono text-[0.75rem]">{hostRoot}</code>}
          </span>
        </p>
        <p>{t("painel:recovery.explain")}</p>
        {phase === "restarting" && (
          <p className="flex items-center gap-2 font-mono text-[0.8rem] text-accent">
            <RefreshCw className="size-3.5 animate-spin" aria-hidden /> {t("painel:recovery.waitingHealth")}
          </p>
        )}
        {phase === "reconciling" && (
          <p className="flex items-center gap-2 font-mono text-[0.8rem] text-accent">
            <RefreshCw className="size-3.5 animate-spin" aria-hidden /> {t("painel:recovery.reconciling")}
          </p>
        )}
        {phase === "failed" && (
          <p role="alert" className="text-destructive">{t("painel:recovery.failed")}</p>
        )}
      </div>
      <ModalActions>
        <Button variant="outline" onClick={onRevalidate} disabled={phase === "restarting" || phase === "reconciling"}>
          {t("painel:recovery.actionRevalidate")}
        </Button>
        <Button onClick={() => void handleRestart()} disabled={phase === "restarting" || phase === "reconciling"}>
          <RefreshCw /> {t("painel:recovery.actionRestart")}
        </Button>
      </ModalActions>
    </ModalShell>
  );
}
