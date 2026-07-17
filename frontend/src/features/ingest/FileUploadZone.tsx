import { Loader2, Upload, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { deleteInboxFile, fetchInboxFiles, uploadToInbox } from "../../api";
import { cn } from "../../lib/utils";
import type { UploadedFile } from "../../types";

const contentClass = "flex flex-col items-center gap-1.5 text-sm text-muted-foreground";

type UploadState = "idle" | "dragover" | "uploading" | "done" | "error";

type Props = {
  projectId: string;
  onUploadComplete: () => void;
  disabled?: boolean;
};

export function FileUploadZone({ projectId, onUploadComplete, disabled }: Props) {
  const [state, setState] = useState<UploadState>("idle");
  const [fileNames, setFileNames] = useState<string[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load existing inbox files on mount
  useEffect(() => {
    if (disabled) return;
    fetchInboxFiles(projectId)
      .then((data) => {
        if (data.files.length > 0) {
          setUploadedFiles(data.files.map((f) => ({ filename: f.filename, saved_as: f.filename })));
          setState("done");
        }
      })
      .catch(() => {});
  }, [projectId, disabled]);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      setFileNames(fileArray.map((f) => f.name));
      setState("uploading");
      setErrorMsg(null);
      try {
        const result = await uploadToInbox(projectId, fileArray);
        setUploadedFiles(result.uploaded);
        setState("done");
        onUploadComplete();
      } catch (e) {
        setErrorMsg(e instanceof Error ? e.message : "Erro ao enviar");
        setState("error");
      }
    },
    [projectId, onUploadComplete]
  );

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) setState("dragover");
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (state === "dragover") setState("idle");
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    const files = e.dataTransfer.files;
    if (files.length > 0) void handleFiles(files);
  }

  function handleClick() {
    if (disabled || state === "done") return;
    inputRef.current?.click();
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (files && files.length > 0) void handleFiles(files);
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleReset() {
    setState("idle");
    setFileNames([]);
    setUploadedFiles([]);
    setErrorMsg(null);
  }

  async function handleDeleteFile(savedAs: string) {
    try {
      await deleteInboxFile(projectId, savedAs);
      const remaining = uploadedFiles.filter((f) => f.saved_as !== savedAs);
      setUploadedFiles(remaining);
      if (remaining.length === 0) handleReset();
    } catch {
      // silently fail — file may have already been processed
    }
  }

  return (
    <div
      className={cn(
        "flex min-h-24 cursor-pointer items-center justify-center rounded-lg border border-dashed p-4 text-center",
        "transition-[border-color,background-color,box-shadow] duration-200",
        state === "idle" && "border-border hover:border-accent/50 hover:bg-accent-soft/20",
        state === "dragover" && "border-accent bg-accent-soft/40 shadow-[0_0_24px_var(--accent-soft)]",
        state === "uploading" && "border-accent/40",
        state === "done" && "cursor-default border-border bg-panel-strong/40",
        state === "error" && "border-destructive/50 bg-destructive/5",
        disabled && "cursor-not-allowed opacity-60"
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleClick}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Zona de upload de arquivos"
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleClick(); }}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleInputChange}
        disabled={disabled}
        data-testid="file-input"
      />

      {state === "idle" && !disabled && (
        <div className={contentClass}>
          <Upload size={20} className="text-accent" aria-hidden />
          <span className="font-display font-medium text-foreground">Arraste arquivos aqui ou clique para selecionar</span>
          <span className="font-mono text-[0.7rem] text-tertiary">PDF, DOCX, XLSX, PPTX, MSG...</span>
        </div>
      )}

      {state === "dragover" && (
        <div className={contentClass}>
          <Upload size={20} className="text-accent" aria-hidden />
          <span className="font-display font-medium text-accent">Solte os arquivos para enviar</span>
        </div>
      )}

      {state === "uploading" && (
        <div className={contentClass}>
          <Loader2 size={18} className="animate-spin text-accent" aria-hidden />
          <span>Enviando {fileNames.length} arquivo{fileNames.length !== 1 ? "s" : ""}...</span>
          <ul className="m-0 list-none p-0 font-mono text-[0.7rem] text-tertiary">
            {fileNames.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </div>
      )}

      {state === "done" && (
        <div className="flex w-full flex-col items-start gap-1.5" onClick={(e) => e.stopPropagation()}>
          <ul className="m-0 flex w-full list-none flex-col gap-1 p-0">
            {uploadedFiles.map((f) => (
              <li key={f.saved_as} className="flex items-center gap-2 text-left text-xs text-foreground">
                <button
                  type="button"
                  className="flex size-5 items-center justify-center rounded border-0 bg-destructive/10 p-0 text-destructive shadow-none transition-colors hover:bg-destructive/25"
                  title="Remover da inbox"
                  aria-label={`Remover ${f.filename} da inbox`}
                  data-testid={`delete-${f.saved_as}`}
                  onClick={(e) => { e.stopPropagation(); void handleDeleteFile(f.saved_as); }}
                ><X size={11} aria-hidden /></button>
                <span className="truncate font-mono text-[0.75rem]">{f.filename}</span>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="border-0 bg-transparent p-0 font-mono text-[0.7rem] text-accent shadow-none hover:underline"
            onClick={handleReset}
          >
            Enviar mais arquivos
          </button>
        </div>
      )}

      {state === "error" && (
        <div className={contentClass} onClick={(e) => { e.stopPropagation(); handleReset(); }}>
          <span className="text-destructive">{errorMsg}</span>
          <span className="font-mono text-[0.7rem] text-tertiary">Clique para tentar novamente</span>
        </div>
      )}

      {disabled && (
        <div className={contentClass}>
          <Upload size={20} aria-hidden />
          <span className="font-mono text-[0.72rem] text-tertiary">Selecione um projeto para enviar arquivos</span>
        </div>
      )}
    </div>
  );
}
