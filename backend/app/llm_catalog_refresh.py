"""
Refresh do catálogo de modelos a partir do JSON comunitário LiteLLM
(model_prices_and_context_window.json) — a mesma informação das páginas oficiais
de modelos/preços da OpenAI e Anthropic, já estruturada e mantida.

Filtra apenas modelos de chat com tool use (requisito do assistente AtlasFile),
excluindo por construção whisper/embeddings/tts/imagem/realtime. Grava:
- catalog_cache.json (consumido por llm_catalog.load_catalog)
- usage_costs_override.json (mesclado por usage_costs sobre o config builtin)
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.llm_catalog import llm_state_dir, save_catalog_cache
from app.models import ModelOption
from app.utils import utc_now_iso

LITELLM_CATALOG_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)

_SUPPORTED_PROVIDERS = {"openai", "anthropic", "moonshot"}

_PROVIDER_LABELS = {"openai": "OpenAI", "anthropic": "Anthropic", "moonshot": "Moonshot"}

# Snapshots datados (gpt-4o-2024-08-06, claude-...-20250929) poluem o combobox;
# os aliases estáveis dos mesmos modelos permanecem no catálogo.
_DATED_SUFFIX = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{8})$")

# mode=="chat" não basta: variantes de áudio/realtime/busca têm mode chat no LiteLLM.
_NAME_EXCLUDES = ("audio", "realtime", "transcribe", "tts", "search-preview", "computer-use")


def usage_costs_override_path():
    return llm_state_dir() / "usage_costs_override.json"


def catalog_source_path():
    return llm_state_dir() / "catalog_source.json"


def get_catalog_source_url() -> str:
    """URL configurada pelo usuário (persistida em _ATLASFILE/llm/) ou a default."""
    try:
        data = json.loads(catalog_source_path().read_text(encoding="utf-8"))
        url = str(data.get("url") or "").strip()
        return url or LITELLM_CATALOG_URL
    except (OSError, json.JSONDecodeError):
        return LITELLM_CATALOG_URL


def set_catalog_source_url(url: str) -> str:
    """Persiste a URL da fonte (vazia/default → remove o override). Retorna a URL efetiva."""
    cleaned = (url or "").strip()
    path = catalog_source_path()
    if not cleaned or cleaned == LITELLM_CATALOG_URL:
        path.unlink(missing_ok=True)
        return LITELLM_CATALOG_URL
    if not cleaned.startswith("https://"):
        raise ValueError("A URL da fonte do catálogo deve usar https://")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"url": cleaned}, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def _is_chat_candidate(name: str, entry: dict[str, Any]) -> bool:
    if entry.get("litellm_provider") not in _SUPPORTED_PROVIDERS:
        return False
    if entry.get("mode") != "chat":
        return False
    if not entry.get("supports_function_calling"):
        return False
    if _DATED_SUFFIX.search(name):
        return False
    lowered = name.lower()
    return not any(token in lowered for token in _NAME_EXCLUDES)


# Modelos OpenAI PÓS-gpt-5.2 (exclusive: 5.3+) exigem /v1/responses para
# tools+reasoning (400 no chat/completions: "use /v1/responses or set
# reasoning_effort to 'none'"). O gpt-5.2 em si ainda funciona no chat/completions.
_GPT_VERSION = re.compile(r"^gpt-(\d+)\.(\d+)")


def _infer_openai_api(name: str, entry: dict[str, Any]) -> str:
    endpoints = entry.get("supported_endpoints")
    if isinstance(endpoints, list) and endpoints and "/v1/chat/completions" not in endpoints:
        return "responses"
    if entry.get("supports_reasoning"):
        m = _GPT_VERSION.match(name)
        if m and (int(m.group(1)), int(m.group(2))) > (5, 2):
            return "responses"
    return "chat_completions"


def _to_model_option(name: str, entry: dict[str, Any]) -> ModelOption:
    provider = str(entry["litellm_provider"])
    # LiteLLM prefixa provedores não-OpenAI no nome ("moonshot/kimi-k2-...");
    # o id de modelo enviado à API do provedor é o nome SEM o prefixo.
    if name.startswith(f"{provider}/"):
        name = name[len(provider) + 1:]
    reasoning = bool(entry.get("supports_reasoning"))
    thinking = None
    if provider == "anthropic" and reasoning:
        thinking = "adaptive" if entry.get("supports_adaptive_thinking") else "enabled"
    context = entry.get("max_input_tokens") or entry.get("max_tokens")
    return ModelOption(
        provider=provider,
        model=name,
        label=f"{_PROVIDER_LABELS.get(provider, provider)} {name}",
        context_tokens=int(context) if context else None,
        max_output_tokens=int(entry["max_output_tokens"]) if entry.get("max_output_tokens") else None,
        supports_reasoning_effort=reasoning,
        anthropic_thinking_type=thinking,
        openai_api=_infer_openai_api(name, entry) if provider == "openai" else "chat_completions",
    )


def _cost_entry(entry: dict[str, Any]) -> dict[str, float] | None:
    input_cost = entry.get("input_cost_per_token")
    output_cost = entry.get("output_cost_per_token")
    if input_cost is None or output_cost is None:
        return None
    per_1m = lambda value: round(float(value or 0) * 1_000_000, 6)  # noqa: E731
    return {
        "input": per_1m(input_cost),
        "output": per_1m(output_cost),
        "cache_read": per_1m(entry.get("cache_read_input_token_cost")),
        "cache_write": per_1m(entry.get("cache_creation_input_token_cost")),
    }


def parse_litellm_catalog(data: dict[str, Any]) -> tuple[list[ModelOption], dict[str, dict]]:
    """Separado do fetch para testes com fixture. Retorna (models, costs_by_provider)."""
    models: list[ModelOption] = []
    costs: dict[str, dict] = {p: {} for p in _SUPPORTED_PROVIDERS}
    for name, entry in data.items():
        if name == "sample_spec" or not isinstance(entry, dict):
            continue
        if not _is_chat_candidate(name, entry):
            continue
        try:
            option = _to_model_option(name, entry)
        except Exception:
            continue
        models.append(option)
        cost = _cost_entry(entry)
        if cost is not None:
            costs[option.provider][option.model] = cost
    models.sort(key=lambda m: (m.provider, m.model))
    return models, costs


def refresh_catalog(timeout: float = 20.0, *, dry_run: bool = False, url: str | None = None) -> dict[str, Any]:
    """Busca o JSON da fonte, filtra/mapeia e persiste cache do catálogo + override de custos.
    dry_run: só valida (fetch + parse + contagens), sem persistir nada — usado para testar a URL."""
    source_url = (url or "").strip() or get_catalog_source_url()
    if not source_url.startswith("https://"):
        raise ValueError("A URL da fonte do catálogo deve usar https://")
    response = httpx.get(source_url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    models, costs = parse_litellm_catalog(response.json())
    if not models:
        raise ValueError("A fonte retornou 0 modelos compatíveis — formato inesperado?")

    result = {
        "dry_run": dry_run,
        "source_url": source_url,
        "models_total": len(models),
        "openai": sum(1 for m in models if m.provider == "openai"),
        "anthropic": sum(1 for m in models if m.provider == "anthropic"),
        "priced_models": sum(len(v) for v in costs.values()),
    }
    if dry_run:
        return result

    refreshed_at = utc_now_iso()
    save_catalog_cache(models, refreshed_at)

    costs_path = usage_costs_override_path()
    costs_path.parent.mkdir(parents=True, exist_ok=True)
    costs_path.write_text(json.dumps(costs, ensure_ascii=False, indent=2), encoding="utf-8")

    result["refreshed_at"] = refreshed_at
    return result
