import { RotateCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { deleteRejectedTriage, fetchRejectedTriage, restoreRejectedTriage, type RejectedTriageItem } from "../../api";
import { onDataRefresh } from "../../lib/refreshBus";
import { ProcessingAura } from "../../components/ui/processing-aura";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { CollapsibleSection, rowDeleteButtonClass } from "../../components/ui/collapsible-section";
import { cn } from "../../lib/utils";

type Props = {
  projectId: string;
  onStatus: (msg: string) => void;
  /** Restaurar devolve o doc à fila — o Painel precisa recarregar triagem/stats. */
  onChanged: () => void;
};

function formatWhen(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

/** Rejeitados com visibilidade e ações: antes desta seção, rejeitar um documento
 *  só o fazia sumir da fila — o arquivo ficava invisível em _TRIAGE_REVIEW/rejected. */
export function RejectedCard({ projectId, onStatus, onChanged }: Props) {
  const [items, setItems] = useState<RejectedTriageItem[]>([]);
  const [busyDocId, setBusyDocId] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<"restore" | "delete" | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) {
      setItems([]);
      return;
    }
    fetchRejectedTriage(projectId)
      .then(setItems)
      .catch(() => setItems([]));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  // Reativo: rejeições emitem no bus — o card aparece na hora, sem reload
  useEffect(() => onDataRefresh(load), [load]);

  if (items.length === 0) return null;

  async function handleRestore(item: RejectedTriageItem) {
    setBusyDocId(item.doc_id);
    setBusyAction("restore");
    try {
      await restoreRejectedTriage(projectId, item.doc_id);
      onStatus(`"${item.original_filename}" devolvido à fila de triagem`);
      load();
      onChanged();
    } catch (e) {
      onStatus(e instanceof Error ? e.message : "Falha ao restaurar");
    } finally {
      setBusyDocId(null);
      setBusyAction(null);
    }
  }

  async function handleDelete(item: RejectedTriageItem) {
    setConfirmDeleteId(null);
    setBusyDocId(item.doc_id);
    setBusyAction("delete");
    try {
      await deleteRejectedTriage(projectId, item.doc_id);
      onStatus(`"${item.original_filename}" excluído definitivamente`);
      load();
      // Notifica o Painel: o badge no Processamentos vira "excluído" sem reload
      onChanged();
    } catch (e) {
      onStatus(e instanceof Error ? e.message : "Falha ao excluir");
    } finally {
      setBusyDocId(null);
      setBusyAction(null);
    }
  }

  return (
    <Card>
      <CardContent className="pt-5">
        <CollapsibleSection
          title="Rejeitados"
          badge={`${items.length} arquivo${items.length !== 1 ? "s" : ""}`}
          className="border-0 bg-transparent [&>summary]:px-0 [&>div]:border-0 [&>div]:px-0"
        >
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
            {items.map((item) => {
              const isOrphan = item.decision === "orphaned_missing_source" || !item.file_exists;
              return (
                <li
                  key={item.doc_id}
                  className="relative isolate flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border bg-elevated px-3 py-2"
                >
                  <span className="min-w-0 flex-1 truncate text-sm text-foreground" title={item.original_filename}>
                    {item.original_filename}
                  </span>
                  <span className={cn("font-mono text-[0.68rem]", isOrphan ? "text-tertiary" : "text-muted-foreground")}>
                    {isOrphan ? "registro órfão (sem arquivo)" : item.decision_note || "rejeitado"} · {formatWhen(item.processed_at)}
                  </span>
                  {!isOrphan && (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={busyDocId === item.doc_id}
                      title="Devolver à fila de triagem"
                      onClick={() => void handleRestore(item)}
                    >
                      <RotateCcw />
                      Restaurar
                    </Button>
                  )}
                  <div className="relative">
                    <button
                      type="button"
                      className={rowDeleteButtonClass}
                      aria-label={`Excluir ${item.original_filename} definitivamente`}
                      disabled={busyDocId === item.doc_id}
                      onClick={() => setConfirmDeleteId(item.doc_id)}
                    >
                      ×
                    </button>
                    {confirmDeleteId === item.doc_id && (
                      <div className="absolute right-0 top-[calc(100%+6px)] z-20 flex min-w-60 flex-col gap-2 rounded-md border border-border bg-panel p-3 shadow-[0_4px_12px_rgba(0,0,0,0.25)]">
                        <p className="m-0 text-[0.82rem] text-foreground">
                          Excluir definitivamente? O arquivo será apagado do disco.
                        </p>
                        <div className="flex gap-1.5">
                          <Button variant="destructive" size="sm" onClick={() => void handleDelete(item)}>
                            Excluir
                          </Button>
                          <Button variant="secondary" size="sm" onClick={() => setConfirmDeleteId(null)}>
                            Cancelar
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                  {busyDocId === item.doc_id && (
                    <ProcessingAura
                      compact
                      className="w-full"
                      label={busyAction === "restore" ? "Restaurando — devolvendo à fila de triagem" : "Excluindo — apagando arquivo e registro"}
                    />
                  )}
                </li>
              );
            })}
          </ul>
        </CollapsibleSection>
      </CardContent>
    </Card>
  );
}
