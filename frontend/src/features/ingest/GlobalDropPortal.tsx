import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { CheckCircle2, File as FileIcon, FileSpreadsheet, FileText, Loader2, Presentation, UploadCloud, X, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { triggerScan, uploadFileWithProgress } from "../../api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { toast } from "../../components/ui/sonner";
import { ALL_PROJECTS, useProject } from "../../contexts/ProjectContext";
import { projectColor, projectInitial } from "../../layouts/projectVisual";
import { cn } from "../../lib/utils";

type QueueItemStatus = "aguardando" | "enviando" | "enviado" | "erro";

type QueueItem = {
  id: string;
  file: File;
  progress: number;
  status: QueueItemStatus;
  error?: string;
};

type Props = {
  /** Chamado após o scan da inbox concluir (refresh de triagem/stats). */
  onScanComplete: () => void;
  /** Desativa o portal (ex.: durante onboarding). */
  disabled?: boolean;
};

function docIcon(filename: string) {
  const ext = (filename.split(".").pop() || "").toLowerCase();
  if (["xlsx", "xls", "xlsm", "csv"].includes(ext)) return <FileSpreadsheet size={15} aria-hidden />;
  if (["ppt", "pptx"].includes(ext)) return <Presentation size={15} aria-hidden />;
  if (["doc", "docx", "pdf", "txt", "md"].includes(ext)) return <FileText size={15} aria-hidden />;
  return <FileIcon size={15} aria-hidden />;
}

function dragHasFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes("Files");
}

/** Partículas convergindo ao centro do portal (CSS vars por partícula). */
function ConvergingParticles() {
  const particles = Array.from({ length: 10 }, (_, i) => {
    const angle = (i / 10) * Math.PI * 2;
    const radius = 150 + (i % 3) * 40;
    return {
      x: `${Math.round(Math.cos(angle) * radius)}px`,
      y: `${Math.round(Math.sin(angle) * radius)}px`,
      delay: `${(i * 0.18) % 1.4}s`,
    };
  });
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center motion-reduce:hidden">
      {particles.map((p, i) => (
        <span
          key={i}
          className="absolute size-1.5 rounded-full bg-accent-light shadow-[0_0_8px_var(--accent)] [animation:atlas-converge_1.6s_var(--ease-out)_infinite]"
          style={{ "--from-x": p.x, "--from-y": p.y, animationDelay: p.delay } as React.CSSProperties}
        />
      ))}
    </div>
  );
}

/** Drag'n'drop global: overlay "portal" + fila de upload com progresso por arquivo. */
export function GlobalDropPortal({ onScanComplete, disabled = false }: Props) {
  const { projects, selectedProject, selectedProjectLabel } = useProject();
  const reducedMotion = useReducedMotion();
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [queueProject, setQueueProject] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[] | null>(null);
  const processing = useRef(false);
  // Garante 1 scan por lote: sem isso, o efeito re-dispara enquanto a fila
  // concluída espera os 4s de auto-fechamento (scanning volta a false antes).
  const scanFired = useRef(false);

  const enqueue = useCallback((projectId: string, files: File[]) => {
    if (!files.length) return;
    scanFired.current = false;
    setQueueProject(projectId);
    setQueue((prev) => [
      ...prev,
      ...files.map((file, i) => ({
        id: `${Date.now()}-${i}-${file.name}`,
        file,
        progress: 0,
        status: "aguardando" as QueueItemStatus,
      })),
    ]);
  }, []);

  // Sinaliza ingestão ativa para o resto do shell (orb da sidebar → "ingesting")
  const ingestActive = scanning || queue.some((i) => i.status === "aguardando" || i.status === "enviando");
  useEffect(() => {
    window.dispatchEvent(new CustomEvent("atlas:ingest-active", { detail: ingestActive }));
  }, [ingestActive]);

  // Processa a fila sequencialmente; ao terminar, dispara o scan da inbox.
  useEffect(() => {
    if (processing.current || !queueProject) return;
    const next = queue.find((item) => item.status === "aguardando");
    if (!next) {
      const finished = queue.length > 0 && queue.every((item) => item.status === "enviado" || item.status === "erro");
      const anySent = queue.some((item) => item.status === "enviado");
      if (finished && anySent && !scanFired.current) {
        scanFired.current = true;
        setScanning(true);
        triggerScan(queueProject)
          .then((result) => {
            if (result.failed_count > 0) {
              const firstError = result.errors?.[0];
              toast.error(
                `${result.processed_count} processado(s), ${result.failed_count} falha(s)` +
                  (firstError ? ` — ${firstError.filename}: ${firstError.error}` : ""),
                { duration: 8000 }
              );
            } else {
              toast.success(`Inbox processada: ${result.processed_count} documento(s)`);
            }
            onScanComplete();
          })
          .catch(() => toast.error("Upload concluído, mas o processamento da inbox falhou"))
          .finally(() => {
            setScanning(false);
            window.setTimeout(() => {
              setQueue([]);
              setQueueProject(null);
            }, 4000);
          });
      }
      return;
    }
    processing.current = true;
    setQueue((prev) => prev.map((item) => (item.id === next.id ? { ...item, status: "enviando" } : item)));
    uploadFileWithProgress(queueProject, next.file, (pct) => {
      setQueue((prev) => prev.map((item) => (item.id === next.id ? { ...item, progress: pct } : item)));
    })
      .then(() => {
        setQueue((prev) =>
          prev.map((item) => (item.id === next.id ? { ...item, status: "enviado", progress: 100 } : item))
        );
      })
      .catch((error: Error) => {
        setQueue((prev) =>
          prev.map((item) => (item.id === next.id ? { ...item, status: "erro", error: error.message } : item))
        );
      })
      .finally(() => {
        processing.current = false;
        // re-dispara o efeito
        setQueue((prev) => [...prev]);
      });
  }, [queue, queueProject, scanning, onScanComplete]);

  useEffect(() => {
    if (disabled) return;

    function onDragEnter(event: DragEvent) {
      if (!dragHasFiles(event)) return;
      event.preventDefault();
      dragDepth.current += 1;
      setDragging(true);
    }
    function onDragOver(event: DragEvent) {
      if (!dragHasFiles(event)) return;
      event.preventDefault();
    }
    function onDragLeave(event: DragEvent) {
      if (!dragHasFiles(event)) return;
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDragging(false);
    }
    function onDrop(event: DragEvent) {
      if (!dragHasFiles(event)) return;
      event.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      const files = Array.from(event.dataTransfer?.files ?? []);
      if (!files.length) return;
      if (selectedProject === ALL_PROJECTS) {
        setPendingFiles(files); // sem projeto: pede a escolha
      } else {
        enqueue(selectedProject, files);
      }
    }

    // Arquivos escolhidos via file picker (ex.: DropHintCard) entram na mesma fila
    function onPickedFiles(event: Event) {
      const files = (event as CustomEvent<File[]>).detail ?? [];
      if (!files.length) return;
      if (selectedProject === ALL_PROJECTS) {
        setPendingFiles(files);
      } else {
        enqueue(selectedProject, files);
      }
    }

    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    window.addEventListener("atlas:pick-files", onPickedFiles);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("atlas:pick-files", onPickedFiles);
    };
  }, [disabled, selectedProject, enqueue]);

  const isAll = selectedProject === ALL_PROJECTS;

  return (
    <>
      <AnimatePresence>
        {dragging && (
          <motion.div
            initial={reducedMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-md"
            data-testid="drop-overlay"
          >
            <ConvergingParticles />
            <motion.div
              initial={reducedMotion ? false : { scale: 0.92, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 24 }}
              className="relative flex size-64 items-center justify-center"
            >
              {/* Anel do portal: conic gradient girando */}
              <div
                aria-hidden
                className="absolute inset-0 rounded-full opacity-90 [animation:atlas-portal-spin_3.2s_linear_infinite] motion-reduce:animate-none"
                style={{
                  background: "conic-gradient(from 0deg, transparent 10%, var(--accent) 35%, var(--accent-purple) 55%, transparent 90%)",
                  mask: "radial-gradient(farthest-side, transparent calc(100% - 3px), black calc(100% - 2px))",
                  WebkitMask: "radial-gradient(farthest-side, transparent calc(100% - 3px), black calc(100% - 2px))",
                }}
              />
              <div
                aria-hidden
                className="absolute inset-4 rounded-full"
                style={{ background: "radial-gradient(circle, var(--accent-soft), transparent 70%)" }}
              />
              <div className="relative flex flex-col items-center gap-2 text-center">
                <UploadCloud size={28} className="text-accent" aria-hidden />
                {isAll ? (
                  <>
                    <p className="font-display text-base font-bold text-white">Solte para enviar</p>
                    <p className="max-w-44 font-mono text-[0.7rem] text-white/70">você escolhe o projeto em seguida</p>
                  </>
                ) : (
                  <>
                    <p className="font-display text-base font-bold text-white">Enviar para</p>
                    <span className="flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1">
                      <span
                        aria-hidden
                        className="flex size-4 items-center justify-center rounded font-display text-[0.6rem] font-bold text-white"
                        style={{ background: projectColor(selectedProject) }}
                      >
                        {projectInitial(selectedProjectLabel)}
                      </span>
                      <span className="font-mono text-xs text-white">{selectedProjectLabel}</span>
                    </span>
                  </>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Escolha de projeto quando o drop acontece em "todos os projetos" */}
      <Dialog open={pendingFiles !== null} onOpenChange={(open) => !open && setPendingFiles(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Para qual projeto?</DialogTitle>
            <DialogDescription>
              {pendingFiles?.length ?? 0} arquivo(s) aguardando destino.
            </DialogDescription>
          </DialogHeader>
          <div className="flex max-h-64 flex-col gap-1 overflow-y-auto">
            {projects.filter((p) => p.initialized).map((project) => (
              <button
                key={project.project_id}
                type="button"
                className="flex w-full items-center gap-2 rounded-md border-0 bg-transparent px-2 py-2 text-left text-sm shadow-none hover:bg-accent-soft hover:text-accent focus-visible:outline-none focus-visible:bg-accent-soft"
                onClick={() => {
                  if (pendingFiles) enqueue(project.project_id, pendingFiles);
                  setPendingFiles(null);
                }}
              >
                <span
                  aria-hidden
                  className="flex size-5 items-center justify-center rounded font-display text-[0.65rem] font-bold text-white"
                  style={{ background: projectColor(project.project_id) }}
                >
                  {projectInitial(project.project_label)}
                </span>
                {project.project_label}
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Fila de upload (canto inferior esquerdo; sonner ocupa o direito) */}
      <AnimatePresence>
        {queue.length > 0 && (
          <motion.div
            initial={reducedMotion ? false : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            className="fixed bottom-4 left-4 z-[60] w-80 rounded-lg border border-border-subtle bg-panel p-3 shadow-[0_12px_28px_rgba(0,0,0,0.35)]"
            data-testid="upload-queue"
          >
            <div className="mb-2 flex items-center justify-between">
              <p className="font-display text-xs font-semibold text-foreground-strong">
                {scanning
                  ? "Processando inbox..."
                  : `Upload — ${projects.find((p) => p.project_id === queueProject)?.project_label ?? queueProject ?? ""}`}
              </p>
              {scanning ? (
                <Loader2 size={13} className="animate-spin text-accent" aria-hidden />
              ) : (
                <button
                  type="button"
                  aria-label="Fechar fila de upload"
                  className="rounded border-0 bg-transparent p-0.5 text-tertiary shadow-none hover:text-foreground"
                  onClick={() => {
                    setQueue([]);
                    setQueueProject(null);
                  }}
                >
                  <X size={13} aria-hidden />
                </button>
              )}
            </div>
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {queue.map((item) => (
                <li key={item.id} className="text-xs">
                  <div className="flex items-center gap-1.5">
                    <span className="shrink-0 text-muted-foreground">{docIcon(item.file.name)}</span>
                    <span className="min-w-0 flex-1 truncate text-foreground" title={item.file.name}>
                      {item.file.name}
                    </span>
                    {item.status === "enviado" && <CheckCircle2 size={13} className="shrink-0 text-success" aria-hidden />}
                    {item.status === "erro" && <XCircle size={13} className="shrink-0 text-destructive" aria-hidden />}
                    {item.status === "enviando" && (
                      <span className="shrink-0 font-mono text-[0.65rem] text-accent">{item.progress}%</span>
                    )}
                    {item.status === "aguardando" && (
                      <span className="shrink-0 font-mono text-[0.65rem] text-tertiary">aguardando</span>
                    )}
                  </div>
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-panel-strong">
                    <div
                      className={cn(
                        "h-full rounded-full transition-[width] duration-200",
                        item.status === "erro"
                          ? "bg-destructive"
                          : "bg-gradient-to-r from-accent to-accent-light shadow-[0_0_8px_var(--accent-soft)]"
                      )}
                      style={{ width: `${item.status === "enviado" ? 100 : item.progress}%` }}
                    />
                  </div>
                  {item.error && <p className="mt-0.5 font-mono text-[0.65rem] text-destructive">{item.error}</p>}
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
