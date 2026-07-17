import { useRef } from "react";
import { AnimatedNumber } from "./animated-number";
import { cn } from "../../lib/utils";

type Props = {
  icon?: React.ReactNode;
  value: number;
  label: string;
  hint?: string;
  className?: string;
  /** Formatação do valor (ex.: tokens abreviados, USD). */
  format?: (n: number) => string;
  /** Tamanho reduzido para grids densos (6 colunas). */
  dense?: boolean;
};

/** Tile de estatística com cursor-glow (radial seguindo o mouse via CSS vars). */
export function StatTile({ icon, value, label, hint, className, format, dense }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  function handleMouseMove(event: React.MouseEvent<HTMLDivElement>) {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--glow-x", `${event.clientX - rect.left}px`);
    el.style.setProperty("--glow-y", `${event.clientY - rect.top}px`);
  }

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      className={cn(
        "group relative overflow-hidden rounded-lg border border-border bg-card",
        dense ? "p-3" : "p-4",
        "transition-[border-color,box-shadow] duration-200 hover:border-border-strong",
        className
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100 motion-reduce:hidden"
        style={{
          background: "radial-gradient(180px circle at var(--glow-x, 50%) var(--glow-y, 50%), var(--accent-soft), transparent 70%)",
        }}
      />
      <div className="relative flex items-start gap-3">
        {icon && <span className={cn("mt-1 text-accent", dense ? "[&_svg]:size-4" : "[&_svg]:size-5")}>{icon}</span>}
        <div className="min-w-0">
          <AnimatedNumber
            value={value}
            format={format}
            className={cn(
              "block font-display font-bold leading-none tracking-tight text-foreground-strong",
              dense ? "text-xl" : "text-3xl"
            )}
          />
          <p className="mt-1.5 text-xs text-muted-foreground">{label}</p>
          {hint && <p className="font-mono text-[0.65rem] text-tertiary">{hint}</p>}
        </div>
      </div>
    </div>
  );
}
