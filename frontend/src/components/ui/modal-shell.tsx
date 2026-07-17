import { cn } from "../../lib/utils";

export const fieldLabelClass = "mb-1 mt-3 block font-mono text-[0.68rem] uppercase tracking-wide text-tertiary first:mt-0";

export const nativeSelectClass =
  "flex h-9 w-full rounded-md border border-input bg-panel px-3 py-1 text-sm text-foreground shadow-none " +
  "transition-[border-color,box-shadow] hover:border-border-strong focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft " +
  "disabled:cursor-not-allowed disabled:opacity-50";

type ModalShellProps = {
  label: string;
  title?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
  children: React.ReactNode;
};

const SIZES = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-3xl" } as const;

/**
 * Casca de modal do design system para componentes com gestão própria de estado
 * (glass overlay + painel elevado). Para novos fluxos prefira ui/dialog (Radix).
 */
export function ModalShell({ label, title, size = "md", className, children }: ModalShellProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={label}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/55 p-6 backdrop-blur-[6px] [animation:atlas-fade-in_150ms_var(--ease-out)] motion-reduce:animate-none"
    >
      <div
        className={cn(
          "my-auto w-full rounded-xl border border-border-subtle bg-panel p-6 text-foreground",
          "shadow-[0_12px_28px_rgba(0,0,0,0.35)] [animation:atlas-slide-in_200ms_var(--ease-out)] motion-reduce:animate-none",
          SIZES[size],
          className
        )}
      >
        {title && <h3 className="mb-3 font-display text-lg font-bold leading-tight text-foreground-strong">{title}</h3>}
        {children}
      </div>
    </div>
  );
}

/** Rodapé padrão de ações do modal (alinhado à direita). */
export function ModalActions({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-5 flex justify-end gap-2", className)} {...props} />;
}
