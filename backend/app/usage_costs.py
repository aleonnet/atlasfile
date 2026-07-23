"""
Usage cost estimation: $/1M tokens per provider/model (input, output, cache).
Loaded from config (JSON); used to compute estimated_cost_usd from token counts.
Ref.: OpenClaw src/utils/usage-format.ts (estimateUsageCost, resolveModelCostConfig).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings

# Cached after first load; key by path so config path change is respected.
_LOADED: dict[str, dict] = {}


def _override_path() -> Path:
    """Override gravado pelo refresh do catálogo (fonte LiteLLM) — runtime-writable."""
    return Path(settings.projects_root) / "_ATLASFILE" / "llm" / "usage_costs_override.json"


# Memo do override por mtime (arquivo pequeno, mas lido a cada chamada LLM).
_override_memo: tuple[float | None, dict] | None = None


def _load_override() -> dict:
    global _override_memo
    path = _override_path()
    try:
        mtime: float | None = path.stat().st_mtime
    except OSError:
        mtime = None
    if _override_memo is not None and _override_memo[0] == mtime:
        return _override_memo[1]
    data: dict = {}
    if mtime is not None:
        try:
            with path.open(encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            data = {}
    _override_memo = (mtime, data)
    return data


def _load_config() -> dict:
    """Load usage costs em 3 camadas: config (JSON) → snapshot embarcado → override do refresh.
    Cada camada vence por modelo sobre a anterior."""
    path_str = (settings.usage_costs_config_path or "").strip()
    base: dict = {}
    if path_str:
        path = Path(path_str)
        if not path.is_absolute():
            path = Path.cwd() / path_str
        if not path.exists():
            # Fallback: path default aponta para o container (/workspace); em execução
            # local (scripts no venv) usa o config/usage_costs.json do repositório.
            repo_fallback = Path(__file__).resolve().parents[2] / "config" / "usage_costs.json"
            if repo_fallback.exists():
                path = repo_fallback
        if path not in _LOADED:
            try:
                if path.exists():
                    with path.open(encoding="utf-8") as f:
                        _LOADED[str(path)] = json.load(f)
                else:
                    _LOADED[str(path)] = {}
            except (json.JSONDecodeError, OSError):
                _LOADED[str(path)] = {}
        base = _LOADED.get(str(path), {})
    merged = {k: dict(v) for k, v in base.items() if isinstance(v, dict)}
    from app.llm_catalog import snapshot_costs

    for layer in (snapshot_costs(), _load_override()):
        for provider, models in (layer or {}).items():
            if not isinstance(models, dict):
                continue
            merged.setdefault(provider, {}).update(models)
    return merged


def get_cost_per_1m(provider: str, model: str) -> tuple[float, float, float, float] | None:
    """Return (input, output, cache_read, cache_write) $/1M tokens from config, or None if unknown."""
    config = _load_config()
    prov = config.get((p := provider.strip().lower()), {})
    if not isinstance(prov, dict):
        return None
    entry = prov.get(model.strip())
    if not isinstance(entry, dict) or not entry:
        return None
    try:
        input_p = float(entry.get("input", 0) or 0)
        output_p = float(entry.get("output", 0) or 0)
        cache_read_p = float(entry.get("cache_read", 0) or 0)
        cache_write_p = float(entry.get("cache_write", 0) or 0)
        return (input_p, output_p, cache_read_p, cache_write_p)
    except (TypeError, ValueError):
        return None


def estimate_usage_cost(
    usage: dict[str, int | float] | None,
    provider: str,
    model: str,
) -> float:
    """
    Estimate cost in USD from usage dict (input_tokens, output_tokens, cache_*).
    usage keys: input_tokens (or prompt_tokens), output_tokens (or completion_tokens),
    cache_read_input_tokens, cache_creation_input_tokens (or cache_write) if present.
    Returns 0.0 if usage is None/empty or model not in config.
    """
    if not usage or not isinstance(usage, dict):
        return 0.0
    cost_per = get_cost_per_1m(provider, model)
    if not cost_per:
        return 0.0
    input_per, output_per, cache_read_per, cache_write_per = cost_per

    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    cache_write = int(usage.get("cache_creation_input_tokens") or usage.get("cache_write_input_tokens") or 0)

    total_usd = (
        (input_tokens / 1_000_000) * input_per
        + (output_tokens / 1_000_000) * output_per
        + (cache_read / 1_000_000) * cache_read_per
        + (cache_write / 1_000_000) * cache_write_per
    )
    return round(total_usd, 6)
