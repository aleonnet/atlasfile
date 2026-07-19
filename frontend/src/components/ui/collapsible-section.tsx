import { ChevronRight } from "lucide-react";
import { cn } from "../../lib/utils";

type Props = {
  title: string;
  /** Badge à direita do título: string (chip padrão) ou nó rico (ex.: <Badge/>). */
  badge?: React.ReactNode;
  defaultOpen?: boolean;
  /** Persiste aberto/fechado em localStorage — o estado sobrevive a navegação entre telas. */
  persistKey?: string;
  className?: string;
  children: React.ReactNode;
};

function readPersisted(persistKey: string | undefined, fallback: boolean): boolean {
  if (!persistKey) return fallback;
  try {
    const stored = localStorage.getItem(`atlasfile-collapse-${persistKey}`);
    return stored === null ? fallback : stored === "open";
  } catch {
    return fallback;
  }
}

/** Seção colapsável nativa (details/summary) no padrão do design system. */
export function CollapsibleSection({ title, badge, defaultOpen = false, persistKey, className, children }: Props) {
  return (
    <details
      open={readPersisted(persistKey, defaultOpen)}
      onToggle={(e) => {
        if (!persistKey) return;
        try {
          localStorage.setItem(`atlasfile-collapse-${persistKey}`, (e.target as HTMLDetailsElement).open ? "open" : "closed");
        } catch {
          /* storage indisponível */
        }
      }}
      className={cn("group rounded-lg border border-border bg-panel-strong/40 open:bg-transparent", className)}
    >
      <summary
        className={cn(
          "flex cursor-pointer select-none items-center gap-2 rounded-lg px-3.5 py-2.5",
          "font-display text-sm font-semibold text-foreground-strong",
          "transition-colors hover:bg-panel-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "[&::-webkit-details-marker]:hidden [&::marker]:content-none"
        )}
      >
        <ChevronRight size={14} aria-hidden className="shrink-0 text-tertiary transition-transform group-open:rotate-90" />
        {title}
        {badge !== undefined &&
          (typeof badge === "string" || typeof badge === "number" ? (
            <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[0.65rem] font-normal text-tertiary">
              {badge}
            </span>
          ) : (
            badge
          ))}
      </summary>
      <div className="border-t border-border px-3.5 py-3">{children}</div>
    </details>
  );
}

/** Botão padrão de remover linha em tabelas (pill destructive suave com ×) —
 * o mesmo em todas as tabelas de edição/histórico do app. */
export const rowDeleteButtonClass =
  "inline-flex size-6 items-center justify-center rounded-md border-0 bg-destructive/10 text-xs font-semibold " +
  "text-destructive shadow-none transition-colors hover:bg-destructive/20 " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50";

/** Classes para inputs embutidos em células de tabela de edição. */
export const tableInputClass =
  "w-full rounded border-0 bg-transparent px-1.5 py-1 text-[0.82rem] text-foreground shadow-none outline-none " +
  "transition-colors placeholder:text-tertiary hover:bg-panel-strong focus:bg-panel-strong focus:ring-1 focus:ring-accent-soft";

/** Classes para as tabelas de edição (headers mono, linhas com divisória). */
export const editTableClass =
  "w-full border-collapse text-left " +
  "[&_th]:border-b [&_th]:border-border [&_th]:px-1.5 [&_th]:py-1.5 [&_th]:font-mono [&_th]:text-[0.65rem] [&_th]:font-normal [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-tertiary " +
  "[&_td]:border-b [&_td]:border-border/50 [&_td]:px-0.5 [&_td]:py-0.5 [&_tr:last-child_td]:border-b-0";
