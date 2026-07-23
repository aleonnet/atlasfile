"""Sonda de saúde da raiz de projetos (PROJECTS_ROOT).

Cenário real: o usuário deleta a pasta do host com o stack no ar — o bind mount
fica quebrado e QUALQUER operação de projeto estoura PermissionError, que sem
tratamento vira 500 cru ("NetworkError" no browser). A sonda distingue:

- raiz SAUDÁVEL (existe, é diretório, gravável) — inclusive vazia: estado
  legítimo de instância nova, onde a limpeza de órfãos do índice é segura;
- raiz INDISPONÍVEL (ausente/mount quebrado/sem permissão) — operações devem
  falhar com código estável `PROJECTS_ROOT_UNAVAILABLE` e a limpeza de órfãos
  deve ser PULADA (proteção contra apagar o índice por um mount transitório);
- raiz ESVAZIADA (`emptied`) — saudável, mas o marcador `.atlasfile_root` sumiu
  E há evidência de vida anterior (índice com documentos). É a assinatura da
  pasta host deletada sob bind mount no macOS/VirtioFS: o container passa a ver
  um diretório fantasma vazio (writes vão para um inode deletado e se perdem).
  A cura exige reiniciar o container (o Docker recria a pasta e re-vincula o
  mount) — ver POST /api/system/restart.
"""
from __future__ import annotations

import os
from typing import Any

from .config import settings

ROOT_MARKER_NAME = ".atlasfile_root"


def _marker_path() -> str:
    return os.path.join(settings.projects_root, ROOT_MARKER_NAME)


def ensure_root_marker() -> bool:
    """Grava o marcador na raiz SAUDÁVEL (idempotente; nunca levanta exceção).

    Chamado no startup — momento em que o bind mount está garantidamente
    vinculado ao diretório real do host."""
    if not projects_root_health()["ok"]:
        return False
    try:
        path = _marker_path()
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("AtlasFile projects root marker — não remova.\n")
        return True
    except OSError:
        return False


def projects_root_state(*, has_prior_data: bool) -> dict[str, Any]:
    """Classifica a raiz em `ok` | `unavailable` | `emptied`.

    `has_prior_data`: evidência externa de vida anterior (ex.: índice de busca
    com documentos). Sem ela, raiz vazia sem marcador é instância nova — `ok`."""
    health = projects_root_health()
    if not health["ok"]:
        return {"state": "unavailable", "error": health.get("error")}
    if has_prior_data and not os.path.exists(_marker_path()):
        return {"state": "emptied", "error": "projects_root_marker_missing"}
    return {"state": "ok", "error": None}


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
