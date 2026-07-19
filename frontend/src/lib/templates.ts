import i18n from "../i18n";

/** Template builtin sugerido para projetos novos: acompanha o idioma da UI
 *  (palpite inicial, padrão Odoo/localização — o usuário pode escolher
 *  qualquer template na lista; se o slug não existir, os fluxos caem para o
 *  primeiro disponível). */
export function suggestedTemplateSlug(): string {
  return (i18n.resolvedLanguage ?? "pt-BR") === "en-US" ? "default-en" : "default";
}
