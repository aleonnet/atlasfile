import { motion, useReducedMotion } from "framer-motion";
import { Check, GitCompareArrows, Pencil, PlusCircle, Sparkles } from "lucide-react";
import { useState } from "react";
import { createTaxonomyEntry, resolveLabelConflict } from "../../api";
import { useLabelConflictsQuery, useTaxonomyQuery } from "../../lib/queries";
import { useQueryClient } from "@tanstack/react-query";
import { qk } from "../../lib/queryKeys";
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
  // Reativo via cache: decisões/correções invalidam label-conflicts — o card
  // aparece/some sozinho; taxonomia é quase-estática (staleTime longo)
  const queryClient = useQueryClient();
  const { data: conflictsData } = useLabelConflictsQuery();
  const conflicts = conflictsData?.items ?? [];
  const { data: taxonomy = null } = useTaxonomyQuery();
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState<LabelConflict | null>(null);
  const [choice, setChoice] = useState<string>("");
  const [customBd, setCustomBd] = useState("");
  const [customDt, setCustomDt] = useState("");
  // Fluxo "criar taxonomia e aplicar": itens faltantes + campos editáveis
  const [creating, setCreating] = useState<{
    conflict: LabelConflict;
    businessDomain: string;
    documentType: string;
    missing: { kind: "business_domain" | "document_type"; key: string; label: string; aliases: string }[];
  } | null>(null);

  const reloadConflicts = () => void queryClient.invalidateQueries({ queryKey: qk.labelConflicts() });

  /** Itens da escolha que ainda não existem na taxonomia do template. */
  function missingEntries(businessDomain: string, documentType: string) {
    if (!taxonomy) return [];
    const missing: { kind: "business_domain" | "document_type"; key: string; label: string; aliases: string }[] = [];
    if (businessDomain && !taxonomy.business_domains.includes(businessDomain)) {
      missing.push({ kind: "business_domain", key: businessDomain, label: businessDomain, aliases: businessDomain });
    }
    if (documentType && !taxonomy.document_types.includes(documentType)) {
      missing.push({ kind: "document_type", key: documentType, label: documentType, aliases: documentType });
    }
    return missing;
  }

  /** Resolve direto, ou abre o fluxo de criação quando a taxonomia não cobre a escolha. */
  function resolveOrCreate(conflict: LabelConflict, businessDomain: string, documentType: string) {
    const missing = missingEntries(businessDomain, documentType);
    if (missing.length > 0) {
      setCorrecting(null);
      setCreating({ conflict, businessDomain, documentType, missing });
      return;
    }
    void resolve(conflict, businessDomain, documentType);
  }

  async function confirmCreateAndResolve() {
    if (!creating) return;
    setSubmitting(creating.conflict.sha256);
    try {
      for (const item of creating.missing) {
        const result = await createTaxonomyEntry({
          kind: item.kind,
          key: item.key,
          label: item.label.trim() || item.key,
          aliases: item.aliases.split(",").map((a) => a.trim()).filter(Boolean),
          created_from: `conflito:${creating.conflict.sha256.slice(0, 12)}`,
        });
        toast.success(
          `${item.kind === "document_type" ? "Tipo" : "Domínio"} \`${result.key}\` criado no template` +
            (result.updated_projects.length ? ` e em ${result.updated_projects.length} projeto(s)` : "")
        );
      }
      await queryClient.invalidateQueries({ queryKey: qk.taxonomy() });
      const { conflict, businessDomain, documentType } = creating;
      setCreating(null);
      await resolve(conflict, businessDomain, documentType);
    } catch {
      toast.error("Falha ao criar entrada de taxonomia");
      setSubmitting(null);
    }
  }

  async function resolve(conflict: LabelConflict, businessDomain: string, documentType: string) {
    setSubmitting(conflict.sha256);
    try {
      const result = await resolveLabelConflict(conflict.sha256, businessDomain, documentType);
      toast.success(
        `Rótulo canônico aplicado: ${businessDomain}/${documentType}` +
          (result.labeled_by === "human_confirmed_llm" ? " (proposta do LLM confirmada)" : "")
      );
      reloadConflicts();
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
                      {missingEntries(proposal.business_domain!, proposal.document_type!).length > 0 && (
                        <p className="mt-1.5 flex items-center gap-1.5 font-mono text-[0.68rem] text-accent">
                          <PlusCircle size={11} aria-hidden />
                          usa taxonomia nova — aceitar vai propor a criação no template
                        </p>
                      )}
                    </div>
                  )}

                  <div className="mt-3 flex gap-2">
                    <Button
                      size="sm"
                      disabled={!hasProposal || busy}
                      onClick={() => resolveOrCreate(conflict, proposal.business_domain!, proposal.document_type!)}
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
                resolveOrCreate(correcting, bd, dt);
              }}
            >
              {submitting !== null ? "Aplicando..." : "Aplicar canônico"}
            </Button>
          </ModalActions>
        </ModalShell>
      )}

      {creating && (
        <ModalShell label="Criar taxonomia" title="Criar no template e aplicar">
          <p className="text-sm text-muted-foreground">
            A escolha{" "}
            <strong className="font-mono text-foreground-strong">
              {creating.businessDomain}/{creating.documentType}
            </strong>{" "}
            usa {creating.missing.length === 1 ? "uma entrada que não existe" : "entradas que não existem"} na
            taxonomia. Criar agora atualiza o template <code className="font-mono text-accent">default</code> e os
            profiles de todos os projetos — o classificador bootstrap passa a reconhecer imediatamente pelos aliases.
          </p>

          {creating.missing.map((item, idx) => (
            <div key={item.kind} className="mt-4 rounded-md border border-border bg-panel-strong/40 p-3">
              <p className="font-mono text-[0.7rem] uppercase tracking-wide text-tertiary">
                {item.kind === "document_type" ? "Novo tipo documental" : "Novo domínio de negócio"}:{" "}
                <span className="text-accent">{item.key}</span>
              </p>
              <label className={fieldLabelClass} htmlFor={`tax-label-${idx}`}>Label</label>
              <input
                id={`tax-label-${idx}`}
                className={cn(nativeSelectClass)}
                value={item.label}
                onChange={(e) =>
                  setCreating((prev) =>
                    prev
                      ? {
                          ...prev,
                          missing: prev.missing.map((m, i) => (i === idx ? { ...m, label: e.target.value } : m)),
                        }
                      : prev
                  )
                }
              />
              <label className={fieldLabelClass} htmlFor={`tax-aliases-${idx}`}>
                Aliases (vírgula) — é o que o bootstrap usa para classificar
              </label>
              <input
                id={`tax-aliases-${idx}`}
                className={cn(nativeSelectClass, "font-mono")}
                value={item.aliases}
                onChange={(e) =>
                  setCreating((prev) =>
                    prev
                      ? {
                          ...prev,
                          missing: prev.missing.map((m, i) => (i === idx ? { ...m, aliases: e.target.value } : m)),
                        }
                      : prev
                  )
                }
                placeholder="ex: plano, plano de trabalho, cronograma"
              />
            </div>
          ))}

          <ModalActions>
            <Button variant="secondary" disabled={submitting !== null} onClick={() => setCreating(null)}>
              Cancelar
            </Button>
            <Button disabled={submitting !== null} onClick={() => void confirmCreateAndResolve()}>
              <PlusCircle />
              {submitting !== null ? "Criando..." : "Criar e aplicar"}
            </Button>
          </ModalActions>
        </ModalShell>
      )}
    </>
  );
}
