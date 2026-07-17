import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getTemplate, initializeProject, listTemplates } from "../../api";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ModalActions, ModalShell } from "../../components/ui/modal-shell";
import { Skeleton } from "../../components/ui/skeleton";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { cn } from "../../lib/utils";
import type { TemplateMeta } from "../../types";

type Props = {
  open: boolean;
  projectRef: string;
  projectLabel: string;
  onClose: () => void;
  onInitialized: () => void;
  onCreateTemplate?: () => void;
};

export function TemplateSelectModal({ open, projectRef, projectLabel, onClose, onInitialized, onCreateTemplate }: Props) {
  useEscapeKey(open ? onClose : null);
  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [selected, setSelected] = useState("default");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(false);

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listTemplates();
      setTemplates(list);
      if (list.length > 0 && !list.find((t) => t.slug === selected)) {
        setSelected(list[0].slug);
      }
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    if (open) void loadTemplates();
  }, [open, loadTemplates]);

  useEffect(() => {
    if (!open || !selected) return;
    getTemplate(selected)
      .then((data) => setPreview(data.profile as unknown as Record<string, unknown>))
      .catch(() => setPreview(null));
  }, [open, selected]);

  async function handleInit() {
    setInitializing(true);
    try {
      await initializeProject(projectRef, selected);
      onInitialized();
    } catch {
      /* error handled by caller */
    } finally {
      setInitializing(false);
    }
  }

  if (!open) return null;

  const previewAreas = (preview as Record<string, unknown> | null)
    ? (
        ((preview?.classification as Record<string, unknown>)?.business_domains as Array<Record<string, unknown>> | undefined) ??
        []
      )
    : [];

  return (
    <ModalShell label="Selecionar template" title={`Inicializar projeto: ${projectLabel}`}>
      <p className="text-xs text-muted-foreground">
        Selecione um template para configurar o projeto. Domínios, tipos documentais, layout e catálogo de entidades
        podem ser ajustados depois.
      </p>

      {loading && (
        <div className="mt-3 space-y-2">
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      )}

      <div className="mt-3 flex max-h-64 flex-col gap-2 overflow-y-auto">
        {templates.map((t) => (
          <label
            key={t.slug}
            className={cn(
              "flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 transition-[border-color,box-shadow]",
              selected === t.slug
                ? "border-accent/50 bg-accent-soft/40 shadow-[0_0_16px_var(--accent-soft)]"
                : "border-border bg-card hover:border-border-strong"
            )}
          >
            <input
              type="radio"
              name="template"
              className="mt-1 size-3.5 accent-[var(--accent)]"
              value={t.slug}
              checked={selected === t.slug}
              onChange={() => setSelected(t.slug)}
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <strong className="font-display text-sm font-semibold text-foreground-strong">{t.name}</strong>
                {t.slug === "default" && <Badge>default</Badge>}
                <span className="font-mono text-[0.68rem] text-tertiary">{t.areas_count} domínios</span>
              </div>
              {t.description && <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{t.description}</p>}
            </div>
          </label>
        ))}
      </div>

      {previewAreas.length > 0 && (
        <details className="group mt-3 rounded-lg border border-border">
          <summary className="cursor-pointer select-none px-3 py-2 font-display text-xs font-semibold text-foreground-strong [&::-webkit-details-marker]:hidden [&::marker]:content-none">
            Preview do template selecionado
          </summary>
          <div className="max-h-40 space-y-1 overflow-y-auto border-t border-border px-3 py-2">
            {previewAreas.map((a, i) => (
              <div key={i} className="flex items-baseline gap-2 font-mono text-[0.72rem]">
                <span className="text-accent">{String(a.key)}</span>
                <span className="truncate text-tertiary">
                  {(a.aliases as string[] | undefined)?.slice(0, 4).join(", ")}
                  {((a.aliases as string[])?.length ?? 0) > 4 && "..."}
                </span>
              </div>
            ))}
          </div>
        </details>
      )}

      <ModalActions className="items-center">
        {onCreateTemplate && (
          <Button variant="link" className="mr-auto px-0" onClick={onCreateTemplate}>
            <Plus />
            Criar novo template
          </Button>
        )}
        <Button variant="secondary" onClick={onClose} disabled={initializing}>
          Cancelar
        </Button>
        <Button onClick={handleInit} disabled={initializing || !selected}>
          {initializing ? "Inicializando..." : "Inicializar com template"}
        </Button>
      </ModalActions>
    </ModalShell>
  );
}
