import { motion, useReducedMotion } from "framer-motion";
import { Check, Inbox, Pencil, X } from "lucide-react";
import { useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { cn } from "../../lib/utils";
import { ProcessingAura } from "../../components/ui/processing-aura";
import type { TriageItem } from "../../types";

type Props = {
  triageItems: TriageItem[];
  projectLabelById: Map<string, string>;
  onDecision: (item: TriageItem, action: "approve" | "correct" | "reject") => void | Promise<void>;
};

function formatPct(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatClassifierModeLabel(mode?: string | null): string {
  return mode || "—";
}

export function TriageQueue({ triageItems, projectLabelById, onDecision }: Props) {
  const reducedMotion = useReducedMotion();
  // Trava de duplo clique: uma decisão em voo por item — o backend também tem
  // claim atômico (409), mas a UI nem deve deixar a segunda requisição sair.
  const [busyDocId, setBusyDocId] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<"approve" | "correct" | "reject" | null>(null);

  async function decide(item: TriageItem, action: "approve" | "correct" | "reject") {
    if (busyDocId) return;
    setBusyDocId(item.doc_id);
    setBusyAction(action);
    try {
      await onDecision(item, action);
    } finally {
      setBusyDocId(null);
      setBusyAction(null);
    }
  }

  if (triageItems.length === 0) return null;

  return (
    <Card className="triage-queue-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Inbox size={15} className="text-accent" aria-hidden />
          Triagem pendente
          {/* Luz laranja = semântica de vida: pendência "respira" pedindo atenção */}
          <span className="relative inline-flex">
            <Badge>{triageItems.length}</Badge>
            <span
              aria-hidden
              className="absolute inset-0 rounded-full bg-accent-soft [animation:atlas-fade-in_1.6s_var(--ease-in-out)_infinite_alternate] motion-reduce:hidden"
            />
          </span>
        </CardTitle>
        <CardDescription>
          {triageItems.length} documento{triageItems.length !== 1 ? "s" : ""} aguardando decisão
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
          {triageItems.map((item, index) => {
            const hasLlmContext =
              item.classifier_mode ||
              item.llm_explanation ||
              item.rule_business_domain ||
              item.llm_proposed_business_domain ||
              item.business_domain_confidence != null ||
              item.document_type_confidence != null ||
              item.classifier_fallback_reason;
            const suggestedBusinessDomain = item.suggested_business_domain;
            return (
              <motion.li
                key={item.doc_id}
                initial={reducedMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1], delay: Math.min(index * 0.03, 0.3) }}
                className="relative isolate rounded-lg border border-border bg-card p-4 shadow-[inset_2px_0_0_var(--accent)] transition-[border-color] hover:border-border-strong"
              >
                <p className="font-display text-sm font-semibold text-foreground-strong">{item.filename}</p>
                <p className="mt-0.5 font-mono text-[0.7rem] text-tertiary">
                  {projectLabelById.get(item.project_id) || item.project_id}
                  {" · "}
                  {suggestedBusinessDomain ? (
                    <>
                      sugestão: <span className="text-foreground">{suggestedBusinessDomain}</span>
                      {item.suggested_document_type ? ` / ${item.suggested_document_type}` : ""}
                    </>
                  ) : item.reason === "sem_texto_extraivel" ? (
                    <span className="text-accent">sem texto extraível (OCR vazio) — decida manualmente</span>
                  ) : (
                    "sem sugestão"
                  )}
                  {" · "}confiança {item.confidence_score.toFixed(2)}
                </p>

                {hasLlmContext && (
                  <div className="mt-2 space-y-0.5 rounded-md bg-panel-strong p-2.5 font-mono text-[0.7rem] text-muted-foreground">
                    <p>
                      classificador: <span className="text-accent-light">{formatClassifierModeLabel(item.classifier_mode)}</span>
                      {item.classifier_requested_mode && item.classifier_requested_mode !== item.classifier_mode
                        ? ` (solicitado: ${formatClassifierModeLabel(item.classifier_requested_mode)})`
                        : ""}
                    </p>
                    <p>
                      scores: domínio {formatPct(item.business_domain_confidence)} | tipo {formatPct(item.document_type_confidence)} | final {item.confidence_score.toFixed(2)}
                    </p>
                    {item.classifier_fallback_reason && (
                      <p>
                        fallback: <span className="text-accent-light">{item.classifier_fallback_reason}</span>
                      </p>
                    )}
                    {item.rule_business_domain && (
                      <p>
                        regra: <span className="text-accent-light">{item.rule_business_domain}</span> (conf{" "}
                        {(item.rule_confidence ?? 0).toFixed(2)})
                      </p>
                    )}
                    {item.llm_explanation && <p className="text-foreground/80">LLM: {item.llm_explanation}</p>}
                    {item.llm_proposed_business_domain && (
                      <p>
                        domínio proposto: <span className="text-accent-purple">{item.llm_proposed_business_domain}</span>
                      </p>
                    )}
                  </div>
                )}

                <div className={cn("mt-3 flex gap-2", busyDocId === item.doc_id && "opacity-50")}>
                  <Button
                    size="sm"
                    disabled={!suggestedBusinessDomain || busyDocId === item.doc_id}
                    title={!suggestedBusinessDomain ? "Sem sugestão de domínio" : undefined}
                    onClick={() => void decide(item, "approve")}
                  >
                    <Check />
                    Aprovar
                  </Button>
                  <Button size="sm" variant="secondary" disabled={busyDocId === item.doc_id} onClick={() => void decide(item, "correct")}>
                    <Pencil />
                    Corrigir
                  </Button>
                  <Button size="sm" variant="destructive" disabled={busyDocId === item.doc_id} onClick={() => void decide(item, "reject")}>
                    <X />
                    Rejeitar
                  </Button>
                </div>
                {busyDocId === item.doc_id && busyAction && (
                  <ProcessingAura
                    label={
                      busyAction === "approve"
                        ? "Aprovando — movendo, extraindo e indexando"
                        : busyAction === "reject"
                          ? "Rejeitando — movendo para rejeitados"
                          : "Abrindo correção"
                    }
                  />
                )}
              </motion.li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
