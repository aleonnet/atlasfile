import { cn } from "../../lib/utils";

/** Wrapper com scroll horizontal para tabelas largas. */
export function TableWrap({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("overflow-x-auto rounded-lg border border-border", className)} {...props} />;
}

/**
 * Tabela de dados do design system: headers mono uppercase, células numéricas
 * à direita (marque a coluna de texto com className "left"), zebra sutil.
 */
export function DataTable({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <table
      className={cn(
        "w-full border-collapse text-[0.82rem]",
        "[&_th]:whitespace-nowrap [&_th]:border-b [&_th]:border-border [&_th]:bg-panel-strong [&_th]:px-3 [&_th]:py-2",
        "[&_th]:text-right [&_th]:font-mono [&_th]:text-[0.65rem] [&_th]:font-normal [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-tertiary",
        "[&_th.left]:text-left",
        "[&_td]:border-b [&_td]:border-border/50 [&_td]:px-3 [&_td]:py-1.5 [&_td]:text-right [&_td]:font-mono [&_td]:text-[0.78rem]",
        "[&_td.left]:text-left [&_td.left]:font-body",
        "[&_tbody_tr:hover]:bg-panel-strong/50",
        "[&_tbody_tr:last-child_td]:border-b-0",
        "[&_td.empty]:py-6 [&_td.empty]:text-center [&_td.empty]:text-tertiary",
        "[&_tfoot_td]:border-t [&_tfoot_td]:border-border [&_tfoot_td]:bg-panel-strong/60 [&_tfoot_td]:font-semibold [&_tfoot_td]:text-foreground-strong",
        className
      )}
      {...props}
    />
  );
}
