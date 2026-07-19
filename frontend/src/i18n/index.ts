import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import { STORAGE_KEYS } from "../lib/storage";
import { ptBR } from "./locales/pt-BR";

/** i18n do AtlasFile (F4): recursos BUNDLED (sem lazy-HTTP — zero flash de
 *  chave, zero suspense) e init síncrono. PT-BR é o idioma-fonte e fallback;
 *  EN-US entra na F5. Detecção: idioma salvo → navegador → PT-BR; a escolha
 *  do usuário persiste em localStorage (STORAGE_KEYS.language). */
void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { "pt-BR": ptBR },
    fallbackLng: "pt-BR",
    supportedLngs: ["pt-BR", "en-US"],
    defaultNS: "common",
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: STORAGE_KEYS.language,
      caches: ["localStorage"],
    },
    returnNull: false,
  });

export default i18n;
