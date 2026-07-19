import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { fetchDecisionStatus } from "../api";

export type ProcessingOp = {
  docId: string;
  projectId: string;
  filename: string;
  action: "approve" | "correct" | "reject";
  /** epoch ms — o tempo decorrido sobrevive a navegação/remount. */
  startedAt: number;
};

type ProcessingContextValue = {
  /** Operação de triagem em andamento (null quando ocioso). */
  active: ProcessingOp | null;
  /** Fase REAL vinda do backend (movendo_arquivo, extraindo_conteudo, indexando...). */
  phase: string;
  start: (op: Omit<ProcessingOp, "startedAt">) => void;
  finish: () => void;
};

const PHASE_LABELS: Record<string, string> = {
  preparando: "preparando",
  movendo_arquivo: "movendo arquivo",
  extraindo_conteudo: "extraindo conteúdo",
  indexando: "indexando para busca",
  atualizando_datasets: "atualizando datasets",
};

export function formatDecisionPhase(phase: string): string {
  return PHASE_LABELS[phase] ?? "processando";
}

export function formatDecisionAction(action: ProcessingOp["action"]): string {
  return action === "approve" ? "Aprovando" : action === "correct" ? "Corrigindo" : "Rejeitando";
}

const inert: ProcessingContextValue = { active: null, phase: "idle", start: () => {}, finish: () => {} };
const ProcessingContext = createContext<ProcessingContextValue>(inert);

/** Estado global de processamento de decisões de triagem: vive no App (nunca
 *  remonta), então sobrevive a troca de tela; enquanto ativo, faz poll da fase
 *  real no backend e sinaliza o orb da sidebar via atlas:ingest-active. */
export function ProcessingProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<ProcessingOp | null>(null);
  const [phase, setPhase] = useState("idle");
  const pollRef = useRef<number | undefined>(undefined);

  const start = useCallback((op: Omit<ProcessingOp, "startedAt">) => {
    setActive({ ...op, startedAt: Date.now() });
    setPhase("preparando");
    window.dispatchEvent(new CustomEvent("atlas:ingest-active", { detail: true }));
  }, []);

  const finish = useCallback(() => {
    setActive(null);
    setPhase("idle");
    window.dispatchEvent(new CustomEvent("atlas:ingest-active", { detail: false }));
  }, []);

  useEffect(() => {
    if (!active) return;
    const poll = async () => {
      try {
        const status = await fetchDecisionStatus();
        if (status.running && status.doc_id === active.docId && status.phase) setPhase(status.phase);
      } catch {
        /* poll é best-effort — a aura segue com a última fase conhecida */
      }
    };
    void poll();
    pollRef.current = window.setInterval(poll, 1000);
    return () => window.clearInterval(pollRef.current);
  }, [active]);

  const value = useMemo(() => ({ active, phase, start, finish }), [active, phase, start, finish]);
  return <ProcessingContext.Provider value={value}>{children}</ProcessingContext.Provider>;
}

export function useProcessing(): ProcessingContextValue {
  return useContext(ProcessingContext);
}
