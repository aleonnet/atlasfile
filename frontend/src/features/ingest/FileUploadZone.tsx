import { Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { deleteInboxFile, fetchInboxFiles, uploadToInbox } from "../../api";
import type { UploadedFile } from "../../types";

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
      className={`file-upload-zone file-upload-zone--${state}${disabled ? " file-upload-zone--disabled" : ""}`}
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
        className="file-upload-zone__input"
        onChange={handleInputChange}
        disabled={disabled}
        data-testid="file-input"
      />

      {state === "idle" && !disabled && (
        <div className="file-upload-zone__content">
          <Upload size={20} />
          <span>Arraste arquivos aqui ou clique para selecionar</span>
          <span className="sub">PDF, DOCX, XLSX, PPTX, MSG...</span>
        </div>
      )}

      {state === "dragover" && (
        <div className="file-upload-zone__content">
          <Upload size={20} />
          <span>Solte os arquivos para enviar</span>
        </div>
      )}

      {state === "uploading" && (
        <div className="file-upload-zone__content">
          <span className="file-upload-zone__spinner" />
          <span>Enviando {fileNames.length} arquivo{fileNames.length !== 1 ? "s" : ""}...</span>
          <ul className="file-upload-zone__list">
            {fileNames.map((name) => (
              <li key={name} className="sub">{name}</li>
            ))}
          </ul>
        </div>
      )}

      {state === "done" && (
        <div className="file-upload-zone__content" onClick={(e) => e.stopPropagation()}>
          <ul className="file-upload-zone__list file-upload-zone__list--done">
            {uploadedFiles.map((f) => (
              <li key={f.saved_as} className="file-upload-zone__done-item">
                <button
                  type="button"
                  className="btn danger"
                  style={{ padding: "2px 6px", fontSize: "0.75rem" }}
                  title="Remover da inbox"
                  data-testid={`delete-${f.saved_as}`}
                  onClick={(e) => { e.stopPropagation(); void handleDeleteFile(f.saved_as); }}
                >×</button>
                <span className="file-upload-zone__done-name">{f.filename}</span>
              </li>
            ))}
          </ul>
          <span className="sub file-upload-zone__add-more" onClick={handleReset}>Enviar mais arquivos</span>
        </div>
      )}

      {state === "error" && (
        <div className="file-upload-zone__content" onClick={(e) => { e.stopPropagation(); handleReset(); }}>
          <span className="file-upload-zone__error">{errorMsg}</span>
          <span className="sub">Clique para tentar novamente</span>
        </div>
      )}

      {disabled && (
        <div className="file-upload-zone__content">
          <Upload size={20} />
          <span className="sub">Selecione um projeto para enviar arquivos</span>
        </div>
      )}
    </div>
  );
}
