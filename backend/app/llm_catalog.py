"""
Catálogo de modelos LLM com limites documentados (contexto e max output).
Usado por GET /api/models e pelo orchestrator para truncar resultado de tools por modelo.

Duas camadas: LLM_MODEL_CATALOG (builtin, fallback offline) + cache remoto em
{PROJECTS_ROOT}/_ATLASFILE/llm/catalog_cache.json (gravado por llm_catalog_refresh,
fonte LiteLLM). load_catalog() devolve o merge — cache vence por (provider, model).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from app.config import settings
from app.models import ModelOption

# Limites e suporte a reasoning/thinking conforme documentação oficial.
# OpenAI: https://developers.openai.com/api/docs/models — reasoning_effort em modelos "reasoning" (ex.: gpt-5.1); gpt-4.1 é "non-reasoning".
# Anthropic: Extended Thinking — 4.6 usa adaptive (recomendado); 4.5 e anteriores usam enabled + budget_tokens (deprecated em 4.6).
# https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking
LLM_MODEL_CATALOG: list[ModelOption] = [
    ModelOption(
        provider="openai",
        model="gpt-4o-mini",
        label="OpenAI gpt-4o-mini (base)",
        context_tokens=128_000,
        max_output_tokens=16_384,
        supports_reasoning_effort=False,
    ),
    ModelOption(
        provider="openai",
        model="gpt-4.1",
        label="OpenAI gpt-4.1 (médio)",
        context_tokens=1_047_576,
        max_output_tokens=32_768,
        supports_reasoning_effort=False,
    ),
    ModelOption(
        provider="openai",
        model="gpt-5.1",
        label="OpenAI gpt-5.1 (high-end)",
        context_tokens=400_000,
        max_output_tokens=128_000,
        supports_reasoning_effort=True,
    ),
    ModelOption(
        provider="openai",
        model="gpt-5.2",
        label="OpenAI gpt-5.2 (high-end)",
        context_tokens=400_000,
        max_output_tokens=128_000,
        supports_reasoning_effort=True,
        openai_api="responses",
    ),
    ModelOption(
        provider="moonshot",
        model="kimi-k3",
        label="Moonshot Kimi K3",
        context_tokens=256_000,
        max_output_tokens=32_768,
        supports_reasoning_effort=False,
    ),
    ModelOption(
        provider="anthropic",
        model="claude-haiku-4-5",
        label="Anthropic Claude Haiku 4.5 (base)",
        context_tokens=200_000,
        max_output_tokens=64_000,
        supports_reasoning_effort=False,
    ),
    ModelOption(
        provider="anthropic",
        model="claude-sonnet-4-6",
        label="Anthropic Claude Sonnet 4.6 (médio)",
        context_tokens=200_000,
        max_output_tokens=64_000,
        supports_reasoning_effort=True,
        anthropic_thinking_type="adaptive",
    ),
    ModelOption(
        provider="anthropic",
        model="claude-opus-4-6",
        label="Anthropic Claude Opus 4.6 (high-end)",
        context_tokens=200_000,
        max_output_tokens=128_000,
        supports_reasoning_effort=True,
        anthropic_thinking_type="adaptive",
    ),
]


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
