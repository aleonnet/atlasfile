"""Sonda de saúde da raiz de projetos (PROJECTS_ROOT).

Cenário real: o usuário deleta a pasta do host com o stack no ar — o bind mount
fica quebrado e QUALQUER operação de projeto estoura PermissionError, que sem
tratamento vira 500 cru ("NetworkError" no browser). A sonda distingue:

- raiz SAUDÁVEL (existe, é diretório, gravável) — inclusive vazia: estado
  legítimo de instância nova, onde a limpeza de órfãos do índice é segura;
- raiz INDISPONÍVEL (ausente/mount quebrado/sem permissão) — operações devem
  falhar com código estável `PROJECTS_ROOT_UNAVAILABLE` e a limpeza de órfãos
  deve ser PULADA (proteção contra apagar o índice por um mount transitório).
"""
from __future__ import annotations

import os
from typing import Any

from .config import settings


def projects_root_health() -> dict[str, Any]:
    """Retorna {ok, exists, is_dir, writable, error}. Nunca levanta exceção."""
    root = settings.projects_root
    result: dict[str, Any] = {"ok": False, "exists": False, "is_dir": False, "writable": False, "error": None}
    try:
        st_exists = os.path.exists(root)
        result["exists"] = st_exists
        if not st_exists:
            result["error"] = "projects_root_missing"
            return result
        result["is_dir"] = os.path.isdir(root)
        if not result["is_dir"]:
            result["error"] = "projects_root_not_a_directory"
            return result
        # os.listdir denuncia mount quebrado que os.path.exists não pega
        os.listdir(root)
        result["writable"] = os.access(root, os.W_OK)
        if not result["writable"]:
            result["error"] = "projects_root_not_writable"
            return result
        result["ok"] = True
        return result
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
