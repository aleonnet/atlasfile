import { useEffect, useState } from "react";
import { cn } from "../../lib/utils";

/** Mini-orb pulsante da marca (CSS puro) — sinal vivo de trabalho em curso. */
export function MiniOrb({ className }: { className?: string }) {
  return <span aria-hidden className={cn("atlas-mini-orb inline-block size-3.5 shrink-0 rounded-full", className)} />;
}

function useElapsedSeconds(startedAt?: number): number {
  const compute = () => (startedAt ? Math.max(0, Math.floor((Date.now() - startedAt) / 1000)) : 0);
  const [seconds, setSeconds] = useState(compute);
  useEffect(() => {
    setSeconds(compute());
    const timer = window.setInterval(() => setSeconds((v) => (startedAt ? compute() : v + 1)), 1000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startedAt]);
  return seconds;
}

type Props = {
  /** Rótulo honesto da ação em curso (ex.: "Aprovando — extraindo conteúdo"). */
  label: string;
  /** Início da operação (epoch ms): o tempo decorrido sobrevive a remount/navegação. */
  startedAt?: number;
  /** Variante compacta para linhas (rejeitados, modais). */
  compact?: boolean;
  className?: string;
};

/** Aura de processamento para operações longas: halo conic-gradient da marca
 *  girando ao redor do card (mesma arte do compose do chat), mini-orb pulsante,
 *  rótulo com varredura de gradiente e tempo decorrido REAL — nunca uma barra
 *  de progresso inventada. Renderizar condicionalmente dentro de um container
 *  com `relative isolate` (o halo fica atrás do fundo do próprio container). */
export function ProcessingAura({ label, startedAt, compact = false, className }: Props) {
  const seconds = useElapsedSeconds(startedAt);
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
