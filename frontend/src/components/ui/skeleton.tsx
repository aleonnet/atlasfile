import { cn } from "../../lib/utils";

/** Skeleton com shimmer na direção de leitura (esquerda → direita). */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-md bg-panel-strong",
        "after:absolute after:inset-0 after:-translate-x-full",
        "after:bg-gradient-to-r after:from-transparent after:via-white/[0.06] after:to-transparent",
        "after:animate-[atlas-shimmer_1.6s_var(--ease-in-out)_infinite]",
        "motion-reduce:after:animate-none",
        className
      )}
      {...props}
    />
  );
}

export { Skeleton };
