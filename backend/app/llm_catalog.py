"""
Catálogo de modelos LLM com limites documentados (contexto e max output).
Usado por GET /api/models e pelo orchestrator para truncar resultado de tools por modelo.

Duas camadas:
1. Snapshot LiteLLM EMBARCADO no app (`app/data/llm_catalog_snapshot.json`, gerado
   por `scripts/update_catalog_snapshot.py`) — garante a lista completa mesmo sem
   rede/refresh. Contém também seções `user_models`/`user_costs` mantidas à mão
   (modelos que o LiteLLM ainda não lista); uma atualização do snapshot NUNCA
   apaga essas linhas — só as promove quando o LiteLLM passa a cobri-las.
2. Cache remoto em {PROJECTS_ROOT}/_ATLASFILE/llm/catalog_cache.json (gravado por
   llm_catalog_refresh em runtime). load_catalog() devolve o merge — cache vence
   por (provider, model).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from app.config import settings
from app.models import ModelOption

SNAPSHOT_PATH = Path(__file__).parent / "data" / "llm_catalog_snapshot.json"

# O snapshot é parte do pacote (imutável em runtime) — uma leitura por processo.
_snapshot_memo: dict | None = None


def _read_snapshot() -> dict:
    global _snapshot_memo
    if _snapshot_memo is None:
        _snapshot_memo = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return _snapshot_memo


def _snapshot_models() -> list[ModelOption]:
    """Modelos do snapshot embarcado: LiteLLM + entradas do usuário (user_models)."""
    data = _read_snapshot()
    models = [ModelOption(**raw) for raw in data.get("models", [])]
    litellm_keys = {(m.provider, m.model) for m in models}
    for raw in data.get("user_models", []):
        opt = ModelOption(**raw)
        if (opt.provider, opt.model) not in litellm_keys:
            models.append(opt)
    # entradas user entram na ordem (provider, model) — não penduradas no fim
    models.sort(key=lambda m: (m.provider, m.model))
    return models


def snapshot_costs() -> dict[str, dict[str, dict[str, float]]]:
    """Custos do snapshot (LiteLLM + user_costs; user só onde o LiteLLM não cobre)."""
    data = _read_snapshot()
    costs: dict[str, dict[str, dict[str, float]]] = {
        p: dict(models) for p, models in (data.get("costs") or {}).items()
    }
    for provider, models in (data.get("user_costs") or {}).items():
        bucket = costs.setdefault(provider, {})
        for model, cost in models.items():
            bucket.setdefault(model, cost)
    return costs


# Camada base do catálogo (falha de leitura aqui é bug de build — o snapshot é
# parte do pacote; sem fallback silencioso).
LLM_MODEL_CATALOG: list[ModelOption] = _snapshot_models()


def llm_state_dir() -> Path:
    return Path(settings.projects_root) / "_ATLASFILE" / "llm"


def catalog_cache_path() -> Path:
    return llm_state_dir() / "catalog_cache.json"


# Memo do merge, invalidado por mtime do cache (get_context_tokens roda por request de chat).
_MERGE_LOCK = threading.Lock()
_merged_memo: tuple[float | None, list[ModelOption]] | None = None


def _cache_mtime() -> float | None:
    try:
        return catalog_cache_path().stat().st_mtime
    except OSError:
        return None


def _read_cache_models() -> list[ModelOption]:
    try:
        data = json.loads(catalog_cache_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    models: list[ModelOption] = []
    for raw in data.get("models", []):
        try:
            models.append(ModelOption(**raw))
        except Exception:
            continue
    return models


def catalog_refreshed_at() -> str | None:
    try:
        data = json.loads(catalog_cache_path().read_text(encoding="utf-8"))
        return data.get("refreshed_at") or None
    except (OSError, json.JSONDecodeError):
        return None


def save_catalog_cache(models: list[ModelOption], refreshed_at: str) -> None:
    global _merged_memo
    path = catalog_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"refreshed_at": refreshed_at, "models": [m.model_dump() for m in models]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with _MERGE_LOCK:
        _merged_memo = None


def load_catalog() -> list[ModelOption]:
    """Builtin + cache remoto mesclados; entradas do cache vencem por (provider, model)."""
    global _merged_memo
    mtime = _cache_mtime()
    with _MERGE_LOCK:
        if _merged_memo is not None and _merged_memo[0] == mtime:
            return _merged_memo[1]
    cached = _read_cache_models()
    by_key = {(m.provider, m.model): m for m in cached}
    merged: list[ModelOption] = []
    seen: set[tuple[str, str]] = set()
    for builtin in LLM_MODEL_CATALOG:
        key = (builtin.provider, builtin.model)
        merged.append(by_key.get(key, builtin))
        seen.add(key)
    extras = [m for m in cached if (m.provider, m.model) not in seen]
    extras.sort(key=lambda m: (m.provider, m.model))
    merged.extend(extras)
    with _MERGE_LOCK:
        _merged_memo = (mtime, merged)
    return merged


def _find(provider: str, model: str) -> ModelOption | None:
    for opt in load_catalog():
        if opt.provider == provider and opt.model == model:
            return opt
    return None


def get_anthropic_thinking_type(provider: str, model: str) -> str | None:
    """Para Anthropic: "adaptive" (4.6+) ou "enabled" (4.5 e anteriores). None se não for modelo com thinking."""
    opt = _find(provider, model)
    if opt is not None:
        return opt.anthropic_thinking_type or ("enabled" if opt.supports_reasoning_effort else None)
    return None


def supports_reasoning_effort(provider: str, model: str) -> bool:
    """True se o modelo aceita reasoning/thinking (OpenAI reasoning_effort ou Anthropic Extended Thinking)."""
    opt = _find(provider, model)
    return opt.supports_reasoning_effort if opt is not None else False


def get_openai_api(provider: str, model: str) -> str:
    """"chat_completions" ou "responses" — qual endpoint OpenAI o modelo exige para tools+reasoning."""
    opt = _find(provider, model)
    return opt.openai_api if opt is not None else "chat_completions"

_FALLBACK_CONTEXT_TOKENS = 128_000


def get_context_tokens(provider: str, model: str) -> int:
    """Return the context window size (tokens) for a given model, or fallback."""
    opt = _find(provider, model)
    if opt is not None and opt.context_tokens is not None:
        return opt.context_tokens
    return _FALLBACK_CONTEXT_TOKENS


# Fração do contexto reservada para um único resultado de tool (~20%) e teto em caracteres.
# ~4 chars/token; cap evita payloads gigantes mesmo em modelos 1M contexto.
_TOOL_RESULT_FRACTION = 0.2
_CHARS_PER_TOKEN = 4
_MAX_TOOL_RESULT_CHARS_CAP = 400_000
_FALLBACK_MAX_TOOL_RESULT_CHARS = 120_000


def get_max_tool_result_chars(provider: str, model: str) -> int:
    """Retorna o limite de caracteres para resultado de tool conforme o modelo (contexto documentado)."""
    opt = _find(provider, model)
    if opt is not None and opt.context_tokens is not None:
        return min(
            int(opt.context_tokens * _CHARS_PER_TOKEN * _TOOL_RESULT_FRACTION),
            _MAX_TOOL_RESULT_CHARS_CAP,
        )
    return _FALLBACK_MAX_TOOL_RESULT_CHARS
