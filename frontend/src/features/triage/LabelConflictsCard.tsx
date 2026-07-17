import { motion, useReducedMotion } from "framer-motion";
import { Check, GitCompareArrows, Pencil, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { fetchLabelConflicts, resolveLabelConflict } from "../../api";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "../../components/ui/modal-shell";
import { toast } from "../../components/ui/sonner";
import { cn } from "../../lib/utils";
import type { LabelConflict } from "../../types";

const CUSTOM = "__custom__";

function fileName(ref: string): string {
  const base = ref.split("/").pop() || ref;
  // nome canônico: 20260717__projeto__original__v01.ext → original.ext
  const match = base.match(/^\d{8}__[^_]+(?:_[^_]+)*__(.+)__v\d+(\.[^.]+)$/);
  return match ? `${match[1]}${match[2]}` : base;
}

function sourceLabel(ref: string): string {
  return ref.split("/")[0] || ref;
}

/**
 * Conflitos de rótulo (mesmo arquivo, curadorias divergentes) — arbitragem em
 * um clique, no mesmo músculo da Triagem: aceitar a proposta do LLM ou
 * corrigir escolhendo o rótulo canônico. Some quando não há pendências.
 */
export function LabelConflictsCard({ onResolved }: { onResolved?: () => void }) {
  const reducedMotion = useReducedMotion();
  const [conflicts, setConflicts] = useState<LabelConflict[]>([]);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState<LabelConflict | null>(null);
  const [choice, setChoice] = useState<string>("");
  const [customBd, setCustomBd] = useState("");
  const [customDt, setCustomDt] = useState("");

  const load = useCallback(() => {
    fetchLabelConflicts()
      .then((res) => setConflicts(res.items))
      .catch(() => setConflicts([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function resolve(conflict: LabelConflict, businessDomain: string, documentType: string) {
    setSubmitting(conflict.sha256);
    try {
      const result = await resolveLabelConflict(conflict.sha256, businessDomain, documentType);
      toast.success(
        `Rótulo canônico aplicado: ${businessDomain}/${documentType}` +
          (result.labeled_by === "human_confirmed_llm" ? " (proposta do LLM confirmada)" : "")
      );
      setConflicts((prev) => prev.filter((c) => c.sha256 !== conflict.sha256));
      setCorrecting(null);
      onResolved?.();
    } catch {
      toast.error("Falha ao aplicar a resolução do conflito");
    } finally {
      setSubmitting(null);
    }
  }

  function openCorrect(conflict: LabelConflict) {
    setCorrecting(conflict);
    const proposal = conflict.llm_proposal;
    setChoice(
      proposal?.business_domain && proposal?.document_type
        ? `${proposal.business_domain}/${proposal.document_type}`
        : CUSTOM
    );
    setCustomBd("");
    setCustomDt("");
  }

  if (conflicts.length === 0) return null;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitCompareArrows size={15} className="text-accent" aria-hidden />
            Conflitos de rótulo
            <span className="relative inline-flex">
              <Badge variant="purple">{conflicts.length}</Badge>
              <span
                aria-hidden
                className="absolute inset-0 rounded-full bg-accent-soft [animation:atlas-fade-in_1.6s_var(--ease-in-out)_infinite_alternate] motion-reduce:hidden"
              />
            </span>
          </CardTitle>
          <CardDescription>
            O mesmo arquivo recebeu rótulos diferentes em curadorias distintas — escolha o canônico. A decisão
            atualiza os dados de treino/validação do classificador.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
            {conflicts.map((conflict, index) => {
              const proposal = conflict.llm_proposal || {};
              const hasProposal = Boolean(proposal.business_domain && proposal.document_type);
              const busy = submitting === conflict.sha256;
              return (
                <motion.li
                  key={conflict.sha256}
                  initial={reducedMotion ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1], delay: Math.min(index * 0.03, 0.3) }}
                  className="rounded-lg border border-border bg-card p-4 shadow-[inset_2px_0_0_var(--accent-purple)] transition-[border-color] hover:border-border-strong"
                >
                  <p className="font-display text-sm font-semibold text-foreground-strong">
                    {fileName(conflict.refs[0] || conflict.sha256)}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {conflict.sources.map((src, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-panel px-2.5 py-1 font-mono text-[0.68rem] text-muted-foreground"
                        title={src.ref}
                      >
                        <span className="text-tertiary">{sourceLabel(src.ref)}</span>
                        <span className="text-foreground">{src.business_domain}/{src.document_type}</span>
                      </span>
                    ))}
                  </div>

                  {hasProposal && (
                    <div className="mt-2.5 rounded-md border border-accent-purple/25 bg-accent-purple/[0.07] p-2.5">
                      <p className="flex items-center gap-1.5 font-mono text-[0.7rem] text-accent-purple">
                        <Sparkles size={12} aria-hidden />
                        proposta do LLM: <strong>{proposal.business_domain}/{proposal.document_type}</strong>
                        {proposal.confidence != null && <span className="text-tertiary">conf {proposal.confidence.toFixed(2)}</span>}
                      </p>
                      {proposal.justificativa && (
                        <p className="mt-1 text-[0.78rem] leading-relaxed text-muted-foreground">{proposal.justificativa}</p>
                      )}
                    </div>
                  )}

                  <div className="mt-3 flex gap-2">
                    <Button
                      size="sm"
                      disabled={!hasProposal || busy}
                      onClick={() => void resolve(conflict, proposal.business_domain!, proposal.document_type!)}
                    >
                      <Check />
                      {busy ? "Aplicando..." : "Aceitar proposta"}
                    </Button>
                    <Button size="sm" variant="secondary" disabled={busy} onClick={() => openCorrect(conflict)}>
                      <Pencil />
                      Corrigir
                    </Button>
                  </div>
                </motion.li>
              );
            })}
          </ul>
        </CardContent>
      </Card>

      {correcting && (
        <ModalShell label="Resolver conflito de rótulo" title="Resolver conflito de rótulo">
          <p className="text-sm">
            Arquivo: <strong className="text-foreground-strong">{fileName(correcting.refs[0] || "")}</strong>
          </p>

          <label className={fieldLabelClass} htmlFor="conflict-choice">Rótulo canônico</label>
          <select
            id="conflict-choice"
            className={nativeSelectClass}
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
          >
            {correcting.llm_proposal?.business_domain && correcting.llm_proposal?.document_type && (
              <option value={`${correcting.llm_proposal.business_domain}/${correcting.llm_proposal.document_type}`}>
                {correcting.llm_proposal.business_domain}/{correcting.llm_proposal.document_type} — proposta do LLM
              </option>
            )}
            {[...new Set(correcting.sources.map((s) => `${s.business_domain}/${s.document_type}`))].map((pair) => (
              <option key={pair} value={pair}>
                {pair}
              </option>
            ))}
            <option value={CUSTOM}>Personalizado…</option>
          </select>

          {choice === CUSTOM && (
            <div className="mt-1 grid grid-cols-2 gap-2">
              <div>
                <label className={fieldLabelClass} htmlFor="conflict-custom-bd">business_domain</label>
                <input
                  id="conflict-custom-bd"
                  className={cn(nativeSelectClass, "font-mono")}
                  value={customBd}
                  onChange={(e) => setCustomBd(e.target.value)}
                  placeholder="ex: operacoes"
                />
              </div>
              <div>
                <label className={fieldLabelClass} htmlFor="conflict-custom-dt">document_type</label>
                <input
                  id="conflict-custom-dt"
                  className={cn(nativeSelectClass, "font-mono")}
                  value={customDt}
                  onChange={(e) => setCustomDt(e.target.value)}
                  placeholder="ex: plano"
                />
              </div>
            </div>
          )}

          <ModalActions>
            <Button variant="secondary" disabled={submitting !== null} onClick={() => setCorrecting(null)}>
              Cancelar
            </Button>
            <Button
              disabled={
                submitting !== null ||
                (choice === CUSTOM ? !customBd.trim() || !customDt.trim() : !choice.includes("/"))
              }
              onClick={() => {
                const [bd, dt] =
                  choice === CUSTOM ? [customBd.trim(), customDt.trim()] : (choice.split("/", 2) as [string, string]);
                void resolve(correcting, bd, dt);
              }}
            >
              {submitting !== null ? "Aplicando..." : "Aplicar canônico"}
            </Button>
          </ModalActions>
        </ModalShell>
      )}
    </>
  );
}
