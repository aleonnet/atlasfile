import type { Locale } from "date-fns";
import { enUS as dateFnsEnUS, ptBR as dateFnsPtBR } from "date-fns/locale";
import i18n from "../i18n";

/** Formatação regional central (F5): todo número, data, percentual e moeda
 *  exibidos passam por aqui — `Intl.*` no idioma ativo, com formatters
 *  memoizados por idioma+opções. Fora deste módulo não deve existir
 *  toLocale* nem literal "pt-BR" (grep de guarda na F6). */

const numberCache = new Map<string, Intl.NumberFormat>();
const dateCache = new Map<string, Intl.DateTimeFormat>();

function lang(): string {
  return i18n.language || "pt-BR";
}

function numberFormatter(options?: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = `${lang()}|${JSON.stringify(options ?? {})}`;
  let cached = numberCache.get(key);
  if (!cached) {
    cached = new Intl.NumberFormat(lang(), options);
    numberCache.set(key, cached);
  }
  return cached;
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return numberFormatter(options).format(value);
}

/** Percentual a partir da RAZÃO (0.92 → "92,0%" | "92.0%"). */
export function formatPercent(ratio: number, fractionDigits = 1): string {
  return numberFormatter({
    style: "percent",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(ratio);
}

/** USD no idioma ativo ("US$ 1,23" | "$1.23"). */
export function formatUsd(value: number, fractionDigits = 2): string {
  return numberFormatter({
    style: "currency",
    currency: "USD",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

/** Sem options: só a data ("19/07/2026" | "7/19/2026"). Valor inválido volta cru. */
export function formatDate(value: Date | string | number, options?: Intl.DateTimeFormatOptions): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const key = `${lang()}|${JSON.stringify(options ?? {})}`;
  let cached = dateCache.get(key);
  if (!cached) {
    cached = new Intl.DateTimeFormat(lang(), options);
    dateCache.set(key, cached);
  }
  return cached.format(date);
}

/** Data e hora curtas ("19/07/2026, 14:35" | "7/19/26, 2:35 PM"). */
export function formatDateTimeShort(value: Date | string | number): string {
  return formatDate(value, { dateStyle: "short", timeStyle: "short" });
}

/** Só a hora ("14:35" | "2:35 PM"). */
export function formatTimeShort(value: Date | string | number): string {
  return formatDate(value, { hour: "numeric", minute: "2-digit" });
}

const DATE_FNS_LOCALES: Record<string, Locale> = {
  "pt-BR": dateFnsPtBR,
  "en-US": dateFnsEnUS,
};

/** Locale do date-fns correspondente ao idioma ativo (UsageView, date pickers). */
export function dateFnsLocale(): Locale {
  return DATE_FNS_LOCALES[lang()] ?? dateFnsPtBR;
}
