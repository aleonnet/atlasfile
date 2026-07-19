import { afterAll, describe, expect, it } from "vitest";
import i18n from "./index";
import { enUS } from "./locales/en-US";
import { ptBR } from "./locales/pt-BR";

/** F5 — Paridade estrutural PT-BR × EN-US: mesmo conjunto de chaves (recursivo)
 *  e mesmas interpolações {{param}} em cada valor correspondente. */

type Bundle = Record<string, unknown>;

const NAMESPACES = Object.keys(ptBR) as Array<keyof typeof ptBR>;

/** Achata um objeto aninhado em Map<"a.b.c", valorFolha>. */
function flatten(obj: Bundle, prefix = "", out = new Map<string, string>()): Map<string, string> {
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object") {
      flatten(value as Bundle, path, out);
    } else {
      out.set(path, String(value));
    }
  }
  return out;
}

/** Extrai o conjunto de parâmetros de interpolação {{param}} de um valor. */
function interpolationParams(value: string): Set<string> {
  const params = new Set<string>();
  for (const match of value.matchAll(/\{\{\s*([^}]+?)\s*\}\}/g)) {
    params.add(match[1]);
  }
  return params;
}

describe("i18n parity pt-BR × en-US", () => {
  it("expõe os mesmos namespaces nos dois bundles", () => {
    expect(Object.keys(enUS).sort()).toEqual(Object.keys(ptBR).sort());
  });

  describe.each(NAMESPACES)("namespace %s", (ns) => {
    const pt = flatten(ptBR[ns] as Bundle);
    const en = flatten((enUS as Record<string, Bundle>)[ns] ?? {});

    it("tem exatamente as mesmas chaves", () => {
      const missingInEn = [...pt.keys()].filter((k) => !en.has(k));
      const extraInEn = [...en.keys()].filter((k) => !pt.has(k));
      expect(
        { missingInEn, extraInEn },
        `Divergência de chaves em ${ns} — faltando no en-US: [${missingInEn.join(", ")}] · sobrando no en-US: [${extraInEn.join(", ")}]`,
      ).toEqual({ missingInEn: [], extraInEn: [] });
    });

    it("preserva todas as interpolações {{param}} em ambas as direções", () => {
      const issues: string[] = [];
      for (const [key, ptValue] of pt) {
        const enValue = en.get(key);
        if (enValue === undefined) continue; // já reportado no teste de chaves
        const ptParams = interpolationParams(ptValue);
        const enParams = interpolationParams(enValue);
        for (const p of ptParams) {
          if (!enParams.has(p)) issues.push(`${ns}:${key} — {{${p}}} presente no pt-BR e ausente no en-US`);
        }
        for (const p of enParams) {
          if (!ptParams.has(p)) issues.push(`${ns}:${key} — {{${p}}} presente no en-US e ausente no pt-BR`);
        }
      }
      expect(issues, issues.join("\n")).toEqual([]);
    });
  });

  describe("resolução EN-US em runtime", () => {
    afterAll(async () => {
      // A suíte roda pinada em PT-BR (src/test/setup.ts) — restaurar o contrato.
      await i18n.changeLanguage("pt-BR");
    });

    it("resolve chaves em en-US após changeLanguage", async () => {
      await i18n.changeLanguage("en-US");
      expect(i18n.t("common:action.approve")).toBe("Approve");
      expect(i18n.t("painel:shell.navPainel")).toBe("Dashboard");
      expect(i18n.t("chat:session.autoTitle", { date: "01/01/2026" })).toBe("Chat 01/01/2026");
      expect(i18n.t("common:unit.result", { count: 2 })).toBe("2 results");
    });
  });
});
