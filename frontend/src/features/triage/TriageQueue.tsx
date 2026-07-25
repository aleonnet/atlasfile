import { motion, useReducedMotion } from "framer-motion";
import { Check, Inbox, Pencil, X } from "lucide-react";
import { useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { cn } from "../../lib/utils";
import { MiniOrb, ProcessingAura } from "../../components/ui/processing-aura";
import { useTranslation } from "react-i18next";
import { formatDecisionAction, formatDecisionPhase, useProcessing } from "../../contexts/ProcessingContext";
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

/** v0.52.0: a causa REAL de não haver texto, em vez do genérico "(OCR vazio)"
 *  — que era impreciso quando o OCR nem chegou a rodar. Código desconhecido
 *  (meta antigo ou versão futura) cai na mensagem genérica, nunca em branco. */
function noTextMessage(cause: string | null | undefined, t: (key: string) => string): string {
  const key = `triage:queue.noText.${cause || "generic"}`;
  const message = t(key);
  return message === key ? t("triage:queue.noText.generic") : message;
}

export function TriageQueue({ triageItems, projectLabelById, onDecision }: Props) {
  const { t } = useTranslation();
  const reducedMotion = useReducedMotion();
  // Trava de duplo clique: uma decisão em voo por item — o backend também tem
  // claim atômico (409), mas a UI nem deve deixar a segunda requisição sair.
  const { active: processingOp, phase: processingPhase } = useProcessing();
  const [busyDocId, setBusyDocId] = useState<string | null>(null);

  async function decide(item: TriageItem, action: "approve" | "correct" | "reject") {
    if (busyDocId) return;
    setBusyDocId(item.doc_id);
    try {
      await onDecision(item, action);
    } finally {
      setBusyDocId(null);
    }
  }

  if (triageItems.length === 0) return null;

  return (
    <Card className="triage-queue-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Inbox size={15} className="text-accent" aria-hidden />
          {t("triage:queue.title")}
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
          {t("triage:queue.waiting", { count: triageItems.length })}
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
                className={cn(
                  "relative isolate rounded-lg border border-border bg-card p-4 shadow-[inset_2px_0_0_var(--accent)] transition-[border-color] hover:border-border-strong",
                  processingOp?.docId === item.doc_id && "z-40"
                )}
              >
                <p className="font-display text-sm font-semibold text-foreground-strong">{item.filename}</p>
                <p className="mt-0.5 font-mono text-[0.7rem] text-tertiary">
                  {projectLabelById.get(item.project_id) || item.project_id}
                  {" · "}
                  {suggestedBusinessDomain ? (
                    <>
                      {t("triage:queue.suggestion")} <span className="text-foreground">{suggestedBusinessDomain}</span>
                      {item.suggested_document_type ? ` / ${item.suggested_document_type}` : ""}
                    </>
                  ) : item.reason === "sem_texto_extraivel" ? (
                    <span className="text-accent">{noTextMessage(item.no_text_cause, t)}</span>
                  ) : (
                    t("triage:queue.noSuggestion")
                  )}
                  {" · "}{t("triage:queue.confidence")} {item.confidence_score.toFixed(2)}
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

                <div className={cn("mt-3 flex gap-2", (busyDocId !== null || processingOp !== null) && "opacity-50")}>
                  <Button
                    size="sm"
                    disabled={!suggestedBusinessDomain || (busyDocId !== null || processingOp !== null)}
                    title={!suggestedBusinessDomain ? t("triage:queue.noDomainSuggestion") : undefined}
                    onClick={() => void decide(item, "approve")}
                  >
                    <Check />
                    {t("common:action.approve")}
                  </Button>
                  <Button size="sm" variant="secondary" disabled={(busyDocId !== null || processingOp !== null)} onClick={() => void decide(item, "correct")}>
                    <Pencil />
                    {t("common:action.correct")}
                  </Button>
                  <Button size="sm" variant="destructive" disabled={(busyDocId !== null || processingOp !== null)} onClick={() => void decide(item, "reject")}>
                    <X />
                    {t("common:action.reject")}
                  </Button>
                </div>
                {processingOp?.docId === item.doc_id && (
                  <ProcessingAura
                    startedAt={processingOp.startedAt}
                    label={`${formatDecisionAction(processingOp.action)} — ${formatDecisionPhase(processingPhase)}`}
                  />
                )}
                {/* v0.47.0 (achado do usuário): card em ESPERA explica por que os
                    botões estão travados — sem isso, um doc que cai na fila
                    durante um processamento parece quebrado */}
                {processingOp && processingOp.docId !== item.doc_id && (
                  <p className="mt-2 flex items-center gap-1.5 font-mono text-[0.7rem] text-tertiary">
                    <MiniOrb className="size-2.5" />
                    {t("triage:queue.waitingOther", { filename: processingOp.filename })}
                  </p>
                )}
              </motion.li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
