import { PlusCircle } from "lucide-react";
import { useState } from "react";
import { createTaxonomyEntry } from "../../api";
import { Button } from "../../components/ui/button";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "../../components/ui/modal-shell";
import { toast } from "../../components/ui/sonner";
import { cn } from "../../lib/utils";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Notifica criação bem-sucedida (para recarregar template/taxonomia). */
  onCreated?: () => void;
};

/**
 * Criação direta de entrada de taxonomia (tipo documental ou domínio de
 * negócio): atualiza o template default e propaga aos profiles de todos os
 * projetos. Mesmo endpoint usado pelo fluxo de conflitos de rótulo.
 */
const EXAMPLES = {
  document_type: {
    key: "ex: memorando",
    label: "ex: Memorando",
    aliases: "ex: memorando, memo, comunicado interno",
  },
  business_domain: {
    key: "ex: compliance",
    label: "ex: Compliance",
    aliases: "ex: compliance, conformidade, auditoria interna, integridade",
  },
} as const;

export function CreateTaxonomyEntryModal({ open, onClose, onCreated }: Props) {
  const [kind, setKind] = useState<"document_type" | "business_domain">("document_type");
  const [key, setKey] = useState("");
  const [label, setLabel] = useState("");
  const [aliases, setAliases] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  async function handleCreate() {
    setSubmitting(true);
    try {
      const result = await createTaxonomyEntry({
        kind,
        key: key.trim(),
        label: label.trim() || key.trim(),
        aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean),
        created_from: "templates-ui",
      });
      toast.success(
        `${kind === "document_type" ? "Tipo" : "Domínio"} \`${result.key}\` criado no template` +
          (result.updated_projects.length ? ` e propagado a ${result.updated_projects.length} projeto(s)` : "")
      );
      setKey("");
      setLabel("");
      setAliases("");
      onCreated?.();
      onClose();
    } catch {
      toast.error("Falha ao criar entrada de taxonomia");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell label="Novo tipo ou domínio" title="Novo tipo ou domínio">
      <p className="text-sm text-muted-foreground">
        Cria no template <code className="font-mono text-accent">default</code> e propaga aos profiles de todos os
        projetos. O classificador bootstrap reconhece imediatamente pelos aliases; o supervisionado aprende no próximo
        ciclo com exemplos.
      </p>

      <label className={fieldLabelClass} htmlFor="tax-kind">Entrada</label>
      <select
        id="tax-kind"
        className={nativeSelectClass}
        value={kind}
        onChange={(e) => setKind(e.target.value as typeof kind)}
        disabled={submitting}
      >
        <option value="document_type">Tipo documental (document_type)</option>
        <option value="business_domain">Domínio de negócio (business_domain)</option>
      </select>

      <label className={fieldLabelClass} htmlFor="tax-key">Key (identificador técnico)</label>
      <input
        id="tax-key"
        className={cn(nativeSelectClass, "font-mono")}
        value={key}
        onChange={(e) => setKey(e.target.value)}
        placeholder={EXAMPLES[kind].key}
        disabled={submitting}
      />

      <label className={fieldLabelClass} htmlFor="tax-label">Label (exibição)</label>
      <input
        id="tax-label"
        className={nativeSelectClass}
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder={EXAMPLES[kind].label}
        disabled={submitting}
      />

      <label className={fieldLabelClass} htmlFor="tax-aliases">
        Aliases (vírgula) — é o que o bootstrap usa para classificar
      </label>
      <input
        id="tax-aliases"
        className={cn(nativeSelectClass, "font-mono")}
        value={aliases}
        onChange={(e) => setAliases(e.target.value)}
        placeholder={EXAMPLES[kind].aliases}
        disabled={submitting}
      />

      <ModalActions>
        <Button variant="secondary" disabled={submitting} onClick={onClose}>
          Cancelar
        </Button>
        <Button disabled={submitting || !key.trim()} onClick={() => void handleCreate()}>
          <PlusCircle />
          {submitting ? "Criando..." : "Criar e propagar"}
        </Button>
      </ModalActions>
    </ModalShell>
  );
}
