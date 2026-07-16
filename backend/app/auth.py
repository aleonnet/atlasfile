"""Autenticação mínima por API key + escopo de projeto.

Fundação de permissões do plano rag_hibrido_permissoes_ui_v2 (Fase 4):
- API key via ``Authorization: Bearer <key>`` ou ``X-API-Key: <key>``.
- Cada key tem um escopo de projetos (``["*"]`` = irrestrito).
- ``api_auth_enabled=False`` (default) mantém compatibilidade total: tudo passa
  com escopo irrestrito. Sem usuários/RBAC — isso fica para uma fase futura.

Formato de ``config/api_keys.json`` (real fora do git; template versionado em
``config/api_keys.example.json``)::

    {"keys": [
        {"key": "atlas_sk_...", "name": "mcp-server", "projects": ["*"]},
        {"key": "atlas_sk_...", "name": "cliente-x", "projects": ["projeto-a"]}
    ]}
"""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from .config import settings

logger = logging.getLogger(__name__)

_UNAUTHENTICATED_PATHS = {"/health"}


@dataclass(frozen=True)
class AuthContext:
    name: str
    allowed_projects: tuple[str, ...]

    @property
    def unrestricted(self) -> bool:
        return "*" in self.allowed_projects

    def can_access_project(self, project_id: str) -> bool:
        return self.unrestricted or project_id in self.allowed_projects


_ANONYMOUS = AuthContext(name="anonymous", allowed_projects=("*",))

# Cache do arquivo de keys por (path, mtime) — recarrega quando o arquivo muda.
_KEYS_CACHE: dict[str, Any] = {"path": None, "mtime": None, "entries": []}


def _resolve_keys_path() -> Path | None:
    raw = (settings.api_keys_config_path or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / raw
    if not path.exists():
        # Fallback: path default aponta para o container (/workspace); execução
        # local usa o config/api_keys.json do repositório (mesmo padrão de usage_costs).
        repo_fallback = Path(__file__).resolve().parents[2] / "config" / "api_keys.json"
        if repo_fallback.exists():
            return repo_fallback
        return None
    return path


def _load_key_entries() -> list[dict[str, Any]]:
    path = _resolve_keys_path()
    if path is None:
        return []
    try:
        mtime = path.stat().st_mtime
        if _KEYS_CACHE["path"] == str(path) and _KEYS_CACHE["mtime"] == mtime:
            return _KEYS_CACHE["entries"]
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
        entries = [
            entry
            for entry in (raw.get("keys") or [])
            if isinstance(entry, dict) and str(entry.get("key") or "").strip()
        ]
        _KEYS_CACHE.update({"path": str(path), "mtime": mtime, "entries": entries})
        return entries
    except Exception:
        logger.exception("Falha ao carregar api_keys de %s", path)
        return []


def resolve_api_key(raw_key: str) -> AuthContext | None:
    """Compara em tempo constante contra todas as keys configuradas."""
    candidate = (raw_key or "").strip()
    if not candidate:
        return None
    matched: AuthContext | None = None
    for entry in _load_key_entries():
        expected = str(entry.get("key") or "")
        # Sempre percorre todas as entradas (sem early-return) para não vazar timing.
        if secrets.compare_digest(candidate, expected):
            projects = tuple(str(p) for p in (entry.get("projects") or ["*"]) if str(p).strip()) or ("*",)
            matched = AuthContext(name=str(entry.get("name") or "unnamed"), allowed_projects=projects)
    return matched


def _extract_key(request: Request) -> str:
    authorization = request.headers.get("Authorization") or ""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    header_key = (request.headers.get("X-API-Key") or "").strip()
    if header_key:
        return header_key
    # Fallback para contextos sem header: EventSource (SSE) e links de download.
    return (request.query_params.get("api_key") or "").strip()


async def require_auth(request: Request) -> AuthContext:
    """Dependency global de autenticação.

    - ``api_auth_enabled=False`` → passa com escopo irrestrito (backward compat).
    - ``/health`` e preflight CORS (OPTIONS) nunca exigem key.
    """
    if not getattr(settings, "api_auth_enabled", False):
        return _ANONYMOUS
    if request.method == "OPTIONS" or request.url.path in _UNAUTHENTICATED_PATHS:
        return _ANONYMOUS
    raw_key = _extract_key(request)
    if not raw_key:
        raise HTTPException(status_code=401, detail="API key ausente (Authorization: Bearer ou X-API-Key)")
    context = resolve_api_key(raw_key)
    if context is None:
        raise HTTPException(status_code=401, detail="API key inválida")
    return context


def enforce_project_scope(auth: AuthContext, project_id: str | None) -> None:
    """403 quando a key não tem acesso ao projeto. project_id vazio não bloqueia
    (listagens sem projeto filtram pelo escopo, não bloqueiam)."""
    pid = str(project_id or "").strip()
    if not pid:
        return
    if not auth.can_access_project(pid):
        raise HTTPException(status_code=403, detail=f"API key '{auth.name}' sem acesso ao projeto '{pid}'")
