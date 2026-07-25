import { useEffect, useState } from "react";
import { cn } from "../../lib/utils";
import { BlackholeGL } from "../BlackholeGL/BlackholeGL";

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

/** Aura de processamento para operações longas (v0.47.0, design iterado ao
 *  vivo com o usuário): o card focal ganha o SHADER BACKDROP do blackhole
 *  (deriva + lente gravitacional — a arte do hero/gate) atrás do conteúdo,
 *  borda accent em respiração, e o cursor da página vira "progress" enquanto
 *  roda (um arquivo por vez). Tempo decorrido REAL, nunca barra inventada.
 *  Renderizar dentro de um container `relative isolate`. A variante `compact`
 *  (linhas/listas) é leve: só mini-orb + rótulo, sem cursor. */
export function ProcessingAura({ label, startedAt, compact = false, className }: Props) {
  const seconds = useElapsedSeconds(startedAt);

  // Cursor girando na página inteira enquanto a operação bloqueante roda
  useEffect(() => {
    if (compact) return;
    const previous = document.body.style.cursor;
    document.body.style.cursor = "progress";
    return () => {
      document.body.style.cursor = previous;
    };
  }, [compact]);

  return (
    <>
      {/* Lensing dentro do card focal: shader backdrop com deriva do buraco.
          SEM véu global nem bloqueio de cliques (análise factual 2026-07-25):
          os botões de decisão de todos os cards já desabilitam durante o
          processamento e o backend serializa por claim atômico (409 amigável)
          — o véu era redundante e o usuário o dispensou. */}
      {!compact && (
        <BlackholeGL
          variant="backdrop"
          intensity={0.75}
          starGain={0.5}
          className="pointer-events-none absolute inset-0 -z-10 rounded-[inherit] opacity-70"
        />
      )}
      <span
        aria-hidden
        className="pointer-events-none absolute -inset-[2px] -z-10 rounded-[inherit] border border-accent/35 shadow-[0_0_16px_var(--accent-soft)] [animation:atlas-breathe_2.4s_ease-in-out_infinite] motion-reduce:animate-none"
      />
      <div
        role="status"
        className={cn(
          "flex items-center gap-2 font-mono text-[0.72rem]",
          compact ? "py-1" : "mt-3",
          className
        )}
      >
        {compact ? <MiniOrb className="size-2.5" /> : <BlackholeGL variant="orb" intensity={0.85} starGain={0.35} size={22} />}
        <span className="atlas-thinking-text">{label}…</span>
        <span className="ml-auto tabular-nums text-tertiary">{seconds}s</span>
      </div>
    </>
  );
}
