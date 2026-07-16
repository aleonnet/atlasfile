import * as React from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "./button";
import { cn } from "../../lib/utils";

type EmptyStateProps = React.HTMLAttributes<HTMLDivElement> & {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
};

/** Estado vazio unificado: ícone suave, título display, descrição mono. */
function EmptyState({ icon, title, description, action, className, ...props }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-12 text-center",
        className
      )}
      {...props}
    >
      {icon && <div className="text-tertiary [&_svg]:size-8">{icon}</div>}
      <div className="space-y-1">
        <p className="font-display text-sm font-semibold text-foreground-strong">{title}</p>
        {description && <p className="mx-auto max-w-sm text-xs text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

type ErrorStateProps = React.HTMLAttributes<HTMLDivElement> & {
  title?: string;
  description?: string;
  onRetry?: () => void;
  retryLabel?: string;
};

/** Estado de erro unificado com retry — substitui mensagens soltas no footer. */
function ErrorState({
  title = "Algo deu errado",
  description,
  onRetry,
  retryLabel = "Tentar de novo",
  className,
  ...props
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-6 py-10 text-center",
        className
      )}
      {...props}
    >
      <AlertTriangle className="size-7 text-destructive" />
      <div className="space-y-1">
        <p className="font-display text-sm font-semibold text-foreground-strong">{title}</p>
        {description && <p className="mx-auto max-w-sm text-xs text-muted-foreground">{description}</p>}
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCcw />
          {retryLabel}
        </Button>
      )}
    </div>
  );
}

export { EmptyState, ErrorState };
