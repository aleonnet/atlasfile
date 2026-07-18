import { useCallback, useEffect, useState } from "react";
import { deleteInboxFile, fetchInboxFiles } from "../../api";
import { onDataRefresh } from "../../lib/refreshBus";
import { rowDeleteButtonClass } from "../../components/ui/collapsible-section";

type Props = {
  projectId: string;
  onStatus: (msg: string) => void;
};

/** Fila da INBOX visível: o usuário vê O QUE o Processar INBOX vai processar,
 *  com remoção por arquivo — nada de scans misteriosos de sobras invisíveis. */
export function InboxQueueChips({ projectId, onStatus }: Props) {
  const [files, setFiles] = useState<{ filename: string; size: number }[]>([]);

  const load = useCallback(() => {
    if (!projectId) {
      setFiles([]);
      return;
    }
    fetchInboxFiles(projectId)
      .then((res) => setFiles(res.files))
      .catch(() => setFiles([]));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  // Reativo via bus: scans (portal ou botão) recarregam a fila sem reload
  useEffect(() => onDataRefresh(load), [load]);

  if (files.length === 0) return null;

  return (
    <div className="rounded-md border border-border bg-elevated px-3 py-2.5">
      <p className="font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">
        Na fila da INBOX ({files.length})
      </p>
      <ul className="m-0 mt-1.5 flex list-none flex-wrap gap-1.5 p-0">
        {files.map((file) => (
          <li
            key={file.filename}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-panel py-1 pl-2.5 pr-1 font-mono text-[0.7rem] text-foreground"
            title={file.filename}
          >
            <span className="max-w-56 truncate">{file.filename}</span>
            <span className="text-tertiary">{(file.size / 1024).toFixed(0)}kb</span>
            <button
              type="button"
              className={rowDeleteButtonClass}
              aria-label={`Remover ${file.filename} da inbox`}
              onClick={() => {
                void deleteInboxFile(projectId, file.filename)
                  .then(() => load())
                  .catch(() => onStatus("Falha ao remover arquivo da inbox"));
              }}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
