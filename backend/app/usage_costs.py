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


def _load_config() -> dict:
    """Load usage costs from config path (JSON). Empty dict if file missing or invalid."""
    path_str = (settings.usage_costs_config_path or "").strip()
    if not path_str:
        return {}
    path = Path(path_str)
    if not path.is_absolute():
        path = Path.cwd() / path_str
    if path not in _LOADED:
        try:
            if path.exists():
                with path.open(encoding="utf-8") as f:
                    _LOADED[str(path)] = json.load(f)
            else:
                _LOADED[str(path)] = {}
        except (json.JSONDecodeError, OSError):
            _LOADED[str(path)] = {}
    return _LOADED.get(str(path), {})


def get_cost_per_1m(provider: str, model: str) -> tuple[float, float, float, float] | None:
    """Return (input, output, cache_read, cache_write) $/1M tokens from config, or None if unknown."""
    config = _load_config()
    prov = config.get((p := provider.strip().lower()), {})
    if not isinstance(prov, dict):
        return None
    entry = prov.get((m := model.strip()), {})
    if not isinstance(entry, dict):
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
