import { describe, expect, it } from "vitest";
import { extractCitations } from "./ChatPanel";

describe("extractCitations", () => {
  it("extrai nomes entre aspas/backticks (com espaços) e tokens simples", () => {
    const text =
      'Encontrei em "Project Neptune _ TSA_v. Assinada.pdf" e também no Contrato_Servicos_TI.docx a cláusula.';
    expect(extractCitations(text)).toEqual([
      "Project Neptune _ TSA_v. Assinada.pdf",
      "Contrato_Servicos_TI.docx",
    ]);
  });

  it("deduplica case-insensitive e limita a 6", () => {
    const text = Array.from({ length: 10 }, (_, i) => `doc${i}.pdf DOC${i}.pdf`).join(" ");
    const result = extractCitations(text);
    expect(result).toHaveLength(6);
    expect(result[0]).toBe("doc0.pdf");
  });

  it("ignora texto sem documentos", () => {
    expect(extractCitations("nenhum arquivo citado aqui, só texto. www.site.com")).toEqual([]);
  });
});
