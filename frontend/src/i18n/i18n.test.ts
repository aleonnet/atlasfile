import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import i18n from "./index";

/** Gate de integridade do i18n (F4): toda chave estática usada em t()/i18n.t()
 *  no código-fonte DEVE existir no catálogo PT-BR. Chaves dinâmicas (template
 *  literals com ${}) são checadas em runtime pelos próprios fluxos. */

const SRC = join(__dirname, "..");
const KEY_RE = /\b(?:i18n\.)?t\(\s*["'`]([a-zA-Z][a-zA-Z0-9]*:[a-zA-Z0-9_.]+)["'`]/g;

function collectSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) collectSourceFiles(full, out);
    else if (/\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry)) out.push(full);
  }
  return out;
}

describe("integridade do catálogo i18n", () => {
  it("toda chave estática usada no código existe no catálogo PT-BR", () => {
    const missing: string[] = [];
    for (const file of collectSourceFiles(SRC)) {
      const source = readFileSync(file, "utf-8");
      for (const match of source.matchAll(KEY_RE)) {
        const key = match[1];
        if (key.includes("${")) continue;
        // chaves de plural: i18next resolve base → _one/_other
        if (!i18n.exists(key) && !i18n.exists(`${key}_other`)) {
          missing.push(`${key}  (${file.replace(SRC, "src")})`);
        }
      }
    }
    expect(missing, `Chaves usadas sem entrada no catálogo:\n${missing.join("\n")}`).toEqual([]);
  });

  it("PT-BR é o idioma resolvido por default nos testes (golden strings)", () => {
    expect(i18n.language === "pt-BR" || i18n.resolvedLanguage === "pt-BR").toBe(true);
    expect(i18n.t("common:action.approve")).toBe("Aprovar");
  });
});
