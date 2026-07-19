"""Erros HTTP com código estável (contrato aditivo para i18n do frontend).

O ``detail`` passa a ser um dict ``{"code", "params", "message"}``:

- ``code``: identificador SCREAMING_SNAKE semântico e estável, usado pelo
  cliente para mapear a mensagem traduzida;
- ``params``: valores dinâmicos interpolados na mensagem (dict vazio se não houver);
- ``message``: a mensagem legada exata (byte a byte) — fallback de compatibilidade.

Status codes e logs permanecem inalterados.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def http_error(status_code: int, code: str, message: str, **params: Any) -> HTTPException:
    """Constrói uma HTTPException com detail estruturado ``{code, params, message}``."""
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "params": params, "message": message},
    )
