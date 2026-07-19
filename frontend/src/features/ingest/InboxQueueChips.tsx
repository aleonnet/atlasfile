import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { deleteInboxFile } from "../../api";
import { useInboxFilesQuery } from "../../lib/queries";
import { qk } from "../../lib/queryKeys";
import { rowDeleteButtonClass } from "../../components/ui/collapsible-section";

type Props = {
  projectId: string;
  onStatus: (msg: string) => void;
};

/** Fila da INBOX visível: o usuário vê O QUE o Processar INBOX vai processar,
 *  com remoção por arquivo — nada de scans misteriosos de sobras invisíveis. */
export function InboxQueueChips({ projectId, onStatus }: Props) {
  const { t } = useTranslation();
  // Reativo via cache: scans invalidam inbox-files — a fila atualiza sozinha
  const queryClient = useQueryClient();
  const { data } = useInboxFilesQuery(projectId);
  const files = data?.files ?? [];

  if (files.length === 0) return null;

  return (
    <div className="rounded-md border border-border bg-elevated px-3 py-2.5">
      <p className="font-mono text-[0.65rem] uppercase tracking-wide text-tertiary">
        {t("ingest:queue.title", { count: files.length })}
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
              aria-label={t("ingest:queue.removeAria", { filename: file.filename })}
              onClick={() => {
                void deleteInboxFile(projectId, file.filename)
                  .then(() => queryClient.invalidateQueries({ queryKey: qk.inboxFiles(projectId) }))
                  .catch(() => onStatus(t("ingest:queue.removeFailed")));
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
