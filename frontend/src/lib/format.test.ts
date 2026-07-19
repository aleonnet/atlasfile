import { enUS, ptBR } from "date-fns/locale";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import { dateFnsLocale, formatDate, formatDateTimeShort, formatNumber, formatPercent, formatTimeShort, formatUsd } from "./format";

const SAMPLE = new Date(2026, 6, 19, 14, 35, 37); // 19/07/2026 14:35:37 local

/** Normaliza espaços tipográficos do ICU (NBSP/NNBSP variam por versão). */
function plainSpaces(s: string): string {
  return s.replace(/[  ]/g, " ");
}

afterEach(async () => {
  await i18n.changeLanguage("pt-BR");
});

describe("formatNumber", () => {
  it("pt-BR usa ponto de milhar e vírgula decimal", () => {
    expect(formatNumber(1234)).toBe("1.234");
    expect(formatNumber(1.5, { minimumFractionDigits: 1 })).toBe("1,5");
  });
  it("en-US usa vírgula de milhar e ponto decimal", async () => {
    await i18n.changeLanguage("en-US");
    expect(formatNumber(1234)).toBe("1,234");
    expect(formatNumber(1.5, { minimumFractionDigits: 1 })).toBe("1.5");
  });
});

describe("formatPercent", () => {
  it("recebe a razão e formata por idioma", async () => {
    expect(formatPercent(0.92)).toBe("92,0%");
    await i18n.changeLanguage("en-US");
    expect(formatPercent(0.92)).toBe("92.0%");
  });
});

describe("formatUsd", () => {
  it("moeda USD por idioma", async () => {
    expect(plainSpaces(formatUsd(1.23))).toBe("US$ 1,23");
    await i18n.changeLanguage("en-US");
    expect(formatUsd(1.23)).toBe("$1.23");
  });
});

describe("formatDate e derivados", () => {
  it("sem options: só a data", async () => {
    expect(formatDate(SAMPLE)).toBe("19/07/2026");
    await i18n.changeLanguage("en-US");
    expect(formatDate(SAMPLE)).toBe("7/19/2026");
  });
  it("dateStyle/timeStyle", () => {
    expect(formatDate(SAMPLE, { dateStyle: "short", timeStyle: "medium" })).toBe("19/07/2026, 14:35:37");
    expect(formatDateTimeShort(SAMPLE)).toBe("19/07/2026, 14:35");
  });
  it("hora curta por idioma", async () => {
    expect(formatTimeShort(SAMPLE)).toBe("14:35");
    await i18n.changeLanguage("en-US");
    expect(plainSpaces(formatTimeShort(SAMPLE))).toBe("2:35 PM");
  });
  it("valor inválido volta cru", () => {
    expect(formatDate("nao-e-data")).toBe("nao-e-data");
  });
});

describe("dateFnsLocale", () => {
  it("mapeia idioma → locale do date-fns", async () => {
    expect(dateFnsLocale()).toBe(ptBR);
    await i18n.changeLanguage("en-US");
    expect(dateFnsLocale()).toBe(enUS);
  });
});
