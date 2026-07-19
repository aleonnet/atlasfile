import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Alternador discreto de idioma para as telas de primeiro acesso (AuthGate e
 *  wizard) — a detecção do navegador pode errar e o seletor de Configuração
 *  só é alcançável depois do setup. Troca AO VIVO: changeLanguage re-renderiza
 *  tudo que está inscrito e o detector persiste a escolha sozinho. */
export function LanguageQuickSwitch({ className = "" }: { className?: string }) {
  const { t, i18n } = useTranslation();

  const handleChange = (lng: string) => {
    void i18n.changeLanguage(lng);
  };

  return (
    <label className={`inline-flex items-center gap-1.5 text-[0.75rem] text-tertiary ${className}`}>
      <Languages className="size-3.5" aria-hidden />
      <select
        aria-label={t("settings:language.label")}
        className="cursor-pointer border-0 bg-transparent p-0 font-body text-[0.75rem] text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        value={i18n.resolvedLanguage ?? "pt-BR"}
        onChange={(e) => handleChange(e.target.value)}
      >
        <option value="pt-BR">{t("settings:language.ptBR")}</option>
        <option value="en-US">{t("settings:language.enUS")}</option>
      </select>
    </label>
  );
}
