import { PlusCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { createTaxonomyEntry } from "../../api";
import { Button } from "../../components/ui/button";
import { fieldLabelClass, ModalActions, ModalShell, nativeSelectClass } from "../../components/ui/modal-shell";
import { toast } from "../../components/ui/sonner";
import { cn } from "../../lib/utils";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Notifica criação bem-sucedida com o que foi criado (para recarregar e pré-selecionar). */
  onCreated?: (kind: "document_type" | "business_domain", key: string) => void;
};

/**
 * Criação direta de entrada de taxonomia (tipo documental ou domínio de
 * negócio): atualiza o template default e propaga aos profiles de todos os
 * projetos. Mesmo endpoint usado pelo fluxo de conflitos de rótulo.
 */
export function CreateTaxonomyEntryModal({ open, onClose, onCreated }: Props) {
  const { t } = useTranslation();
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
        t("templates:create.createdToast", { kindLabel: t(`templates:kindShort.${kind}`), key: result.key }) +
          (result.updated_projects.length ? t("templates:create.propagatedSuffix", { count: result.updated_projects.length }) : "")
      );
      setKey("");
      setLabel("");
      setAliases("");
      onCreated?.(kind, result.key);
      onClose();
    } catch {
      toast.error(t("templates:create.createFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell label={t("templates:create.title")} title={t("templates:create.title")}>
      <p className="text-sm text-muted-foreground">
        {t("templates:create.introBefore")} <code className="font-mono text-accent">default</code>{" "}
        {t("templates:create.introAfter")}
      </p>

      <label className={fieldLabelClass} htmlFor="tax-kind">{t("templates:create.kindLabel")}</label>
      <select
        id="tax-kind"
        className={nativeSelectClass}
        value={kind}
        onChange={(e) => setKind(e.target.value as typeof kind)}
        disabled={submitting}
      >
        <option value="document_type">{t("templates:kind.document_type")}</option>
        <option value="business_domain">{t("templates:kind.business_domain")}</option>
      </select>

      <label className={fieldLabelClass} htmlFor="tax-key">{t("templates:create.keyLabel")}</label>
      <input
        id="tax-key"
        className={cn(nativeSelectClass, "font-mono")}
        value={key}
        onChange={(e) => setKey(e.target.value)}
        placeholder={t(`templates:create.example.${kind}.key`)}
        disabled={submitting}
      />

      <label className={fieldLabelClass} htmlFor="tax-label">{t("templates:create.labelLabel")}</label>
      <input
        id="tax-label"
        className={nativeSelectClass}
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder={t(`templates:create.example.${kind}.label`)}
        disabled={submitting}
      />

      <label className={fieldLabelClass} htmlFor="tax-aliases">
        {t("templates:create.aliasesLabel")}
      </label>
      <input
        id="tax-aliases"
        className={cn(nativeSelectClass, "font-mono")}
        value={aliases}
        onChange={(e) => setAliases(e.target.value)}
        placeholder={t(`templates:create.example.${kind}.aliases`)}
        disabled={submitting}
      />

      <ModalActions>
        <Button variant="secondary" disabled={submitting} onClick={onClose}>
          {t("common:action.cancel")}
        </Button>
        <Button disabled={submitting || !key.trim()} onClick={() => void handleCreate()}>
          <PlusCircle />
          {submitting ? t("templates:create.creating") : t("templates:create.submit")}
        </Button>
      </ModalActions>
    </ModalShell>
  );
}
