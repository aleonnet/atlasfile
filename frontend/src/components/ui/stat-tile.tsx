import { useRef } from "react";
import { AnimatedNumber } from "./animated-number";
import { cn } from "../../lib/utils";

type Props = {
  icon?: React.ReactNode;
  value: number;
  label: string;
  hint?: string;
  className?: string;
};

/** Tile de estatística com cursor-glow (radial seguindo o mouse via CSS vars). */
export function StatTile({ icon, value, label, hint, className }: Props) {
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
        "group relative overflow-hidden rounded-lg border border-border bg-card p-4",
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
        {icon && <span className="mt-1 text-accent [&_svg]:size-5">{icon}</span>}
        <div className="min-w-0">
          <AnimatedNumber
            value={value}
            className="block font-display text-3xl font-bold leading-none tracking-tight text-foreground-strong"
          />
          <p className="mt-1.5 text-xs text-muted-foreground">{label}</p>
          {hint && <p className="font-mono text-[0.65rem] text-tertiary">{hint}</p>}
        </div>
      </div>
    </div>
  );
}
