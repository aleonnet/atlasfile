import { afterEach, describe, expect, it } from "vitest";
import i18n from "../../i18n";
import { formatTokens, formatUsd, formatUsd4 } from "./UsageView";

/** F5: os formatters seguem o idioma ativo (Intl). PT-BR usa vírgula decimal
 *  e "US$" com espaço não separável ( ); EN-US usa ponto e "$". */

afterEach(async () => {
  await i18n.changeLanguage("pt-BR");
});

describe("formatUsd (pt-BR)", () => {
  it("returns dash for zero", () => {
    expect(formatUsd(0)).toBe("—");
  });
  it("rounds US$ 0,0567 to US$ 0,06 (not truncate)", () => {
    expect(formatUsd(0.0567)).toBe("US$ 0,06");
  });
  it("rounds US$ 0,051 to US$ 0,05", () => {
    expect(formatUsd(0.051)).toBe("US$ 0,05");
  });
  it("rounds US$ 1,999 to US$ 2,00", () => {
    expect(formatUsd(1.999)).toBe("US$ 2,00");
  });
});

describe("formatUsd (en-US)", () => {
  it("uses $ and decimal point", async () => {
    await i18n.changeLanguage("en-US");
    expect(formatUsd(0.0567)).toBe("$0.06");
    expect(formatUsd(1.999)).toBe("$2.00");
  });
});

describe("formatUsd4", () => {
  it("returns dash for zero", () => {
    expect(formatUsd4(0)).toBe("—");
  });
  it("rounds to 4 decimal places", () => {
    expect(formatUsd4(0.00056)).toBe("US$ 0,0006");
  });
  it("keeps exact values", () => {
    expect(formatUsd4(0.0042)).toBe("US$ 0,0042");
  });
});

describe("formatTokens", () => {
  it("formats millions (decimal separator by language)", () => {
    expect(formatTokens(1_500_000)).toBe("1,5m");
  });
  it("formats thousands", () => {
    expect(formatTokens(357_000)).toBe("357k");
  });
  it("formats small thousands with decimal", () => {
    expect(formatTokens(5_200)).toBe("5,2k");
  });
  it("formats small numbers as-is", () => {
    expect(formatTokens(42)).toBe("42");
  });
  it("uses decimal point in en-US", async () => {
    await i18n.changeLanguage("en-US");
    expect(formatTokens(1_500_000)).toBe("1.5m");
    expect(formatTokens(5_200)).toBe("5.2k");
  });
});
