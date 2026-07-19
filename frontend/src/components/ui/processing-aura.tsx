import { useEffect, useState } from "react";
import { cn } from "../../lib/utils";

/** Mini-orb pulsante da marca (CSS puro) — sinal vivo de trabalho em curso. */
export function MiniOrb({ className }: { className?: string }) {
  return <span aria-hidden className={cn("atlas-mini-orb inline-block size-3.5 shrink-0 rounded-full", className)} />;
}

function useElapsedSeconds(): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((v) => v + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return seconds;
}

type Props = {
  /** Rótulo honesto da ação em curso (ex.: "Aprovando — movendo, extraindo e indexando"). */
  label: string;
  /** Variante compacta para linhas (rejeitados, modais). */
  compact?: boolean;
  className?: string;
};

/** Aura de processamento para operações longas: halo conic-gradient da marca
 *  girando ao redor do card (mesma arte do compose do chat), mini-orb pulsante,
 *  rótulo com varredura de gradiente e tempo decorrido REAL — nunca uma barra
 *  de progresso inventada. Renderizar condicionalmente dentro de um container
 *  com `relative isolate` (o halo fica atrás do fundo do próprio container). */
export function ProcessingAura({ label, compact = false, className }: Props) {
  const seconds = useElapsedSeconds();
  return (
    <>
      <span aria-hidden className="atlas-aura pointer-events-none absolute -inset-[3px] -z-10 rounded-[inherit]" />
      <div
        role="status"
        className={cn(
          "flex items-center gap-2 font-mono text-[0.72rem]",
          compact ? "py-1" : "mt-3",
          className
        )}
      >
        <MiniOrb />
        <span className="atlas-thinking-text">{label}…</span>
        <span className="ml-auto tabular-nums text-tertiary">{seconds}s</span>
      </div>
    </>
  );
}
