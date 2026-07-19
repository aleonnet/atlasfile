import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import { ApiError, apiErrorFromResponse, apiErrorMessage } from "./apiError";

afterEach(async () => {
  await i18n.changeLanguage("pt-BR");
});

describe("apiErrorMessage", () => {
  it("code conhecido resolve pelo catálogo do idioma ativo", async () => {
    const detail = { code: "RECONCILE_IN_PROGRESS", params: {}, message: "Aguarde a reconciliação terminar" };
    expect(apiErrorMessage(detail)).toBe("Aguarde a reconciliação terminar");
    await i18n.changeLanguage("en-US");
    expect(apiErrorMessage(detail)).toBe("Wait for the reconciliation to finish");
  });

  it("interpola params do backend", () => {
    expect(apiErrorMessage({ code: "PROJECT_NOT_FOUND", params: { project_id: "x1" }, message: "..." })).toBe(
      "Projeto não encontrado: x1"
    );
  });

  it("code desconhecido cai no message", () => {
    expect(apiErrorMessage({ code: "NOVO_CODE_FUTURO", message: "mensagem do backend" })).toBe("mensagem do backend");
  });

  it("string crua (passthrough dinâmico) passa intocada", () => {
    expect(apiErrorMessage("alias duplicado: contrato")).toBe("alias duplicado: contrato");
  });

  it("detail vazio usa o fallback", () => {
    expect(apiErrorMessage(undefined, "fallback")).toBe("fallback");
  });

  it("blockers do dataset readiness usam o mesmo contrato", () => {
    const blocker = { code: "sparse_gate_not_met", params: { records: 3 }, message: "..." };
    expect(apiErrorMessage(blocker)).toBe(
      "Benchmark sparse será pulado: são necessários 100 documentos de treino (há 3)."
    );
  });
});

describe("apiErrorFromResponse", () => {
  it("extrai code e mensagem resolvida da Response", async () => {
    const res = new Response(
      JSON.stringify({ detail: { code: "RECONCILE_IN_PROGRESS", params: {}, message: "Aguarde a reconciliação terminar" } }),
      { status: 409 }
    );
    const err = await apiErrorFromResponse(res, "fallback");
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("RECONCILE_IN_PROGRESS");
    expect(err.message).toBe("Aguarde a reconciliação terminar");
  });

  it("body não-JSON cai no fallback HTTP", async () => {
    const res = new Response("<html>bad gateway</html>", { status: 502 });
    const err = await apiErrorFromResponse(res);
    expect(err.code).toBeUndefined();
    expect(err.message).toBe("HTTP 502");
  });
});
