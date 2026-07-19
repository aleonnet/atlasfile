import i18n from "../i18n";

/** Contrato aditivo da F5: `HTTPException.detail` pode ser um dict
 *  `{code, params, message}` (backend novo) ou uma string crua (backend
 *  antigo / passthroughs dinâmicos). Aqui é o ÚNICO ponto de resolução:
 *  code conhecido → tradução do catálogo `errors:`; caso contrário →
 *  `message`/detail cru. Zero gate de versão. */

export type ApiErrorDetail = {
  code?: string;
  params?: Record<string, unknown>;
  message?: string;
};

export function apiErrorMessage(detail: unknown, fallback = ""): string {
  if (typeof detail === "string") return detail || fallback;
  if (detail && typeof detail === "object") {
    const d = detail as ApiErrorDetail;
    if (typeof d.code === "string" && i18n.exists(`errors:${d.code}`)) {
      return i18n.t(`errors:${d.code}`, { ...(d.params ?? {}), defaultValue: d.message ?? fallback });
    }
    if (typeof d.message === "string" && d.message) return d.message;
  }
  return fallback;
}

/** Error com o code estável do backend — callers tratam casos específicos por
 *  code (nunca por texto, que agora varia com o idioma). */
export class ApiError extends Error {
  readonly code?: string;
  constructor(message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

/** Extrai e resolve o erro de uma Response (body.detail). Não consome o body. */
export async function apiErrorFromResponse(res: Response, fallback = ""): Promise<ApiError> {
  const httpFallback = fallback || `HTTP ${res.status}`;
  try {
    const body = (await res.clone().json()) as { detail?: unknown };
    const detail = body?.detail;
    const code =
      detail && typeof detail === "object" && typeof (detail as ApiErrorDetail).code === "string"
        ? (detail as ApiErrorDetail).code
        : undefined;
    return new ApiError(apiErrorMessage(detail, httpFallback), code);
  } catch {
    return new ApiError(httpFallback);
  }
}
