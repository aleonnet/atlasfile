"""
Catálogo de modelos LLM com limites documentados (contexto e max output).
Usado por GET /api/models e pelo orchestrator para truncar resultado de tools por modelo.
"""
from __future__ import annotations

from app.models import ModelOption

# Limites oficiais: OpenAI e Anthropic (context window, max output tokens).
# OpenAI: https://platform.openai.com/docs/models
# Anthropic: https://docs.anthropic.com/en/docs/build-with-claude/context-windows
LLM_MODEL_CATALOG: list[ModelOption] = [
    ModelOption(
        provider="openai",
        model="gpt-4o-mini",
        label="OpenAI gpt-4o-mini (base)",
        context_tokens=128_000,
        max_output_tokens=16_384,
    ),
    ModelOption(
        provider="openai",
        model="gpt-4.1",
        label="OpenAI gpt-4.1 (médio)",
        context_tokens=1_047_576,
        max_output_tokens=32_768,
    ),
    ModelOption(
        provider="openai",
        model="gpt-5.1",
        label="OpenAI gpt-5.1 (high-end)",
        context_tokens=400_000,
        max_output_tokens=128_000,
    ),
    ModelOption(
        provider="anthropic",
        model="claude-haiku-4-5",
        label="Anthropic Claude Haiku 4.5 (base)",
        context_tokens=200_000,
        max_output_tokens=64_000,
    ),
    ModelOption(
        provider="anthropic",
        model="claude-sonnet-4-6",
        label="Anthropic Claude Sonnet 4.6 (médio)",
        context_tokens=200_000,
        max_output_tokens=64_000,
    ),
    ModelOption(
        provider="anthropic",
        model="claude-opus-4-6",
        label="Anthropic Claude Opus 4.6 (high-end)",
        context_tokens=200_000,
        max_output_tokens=128_000,
    ),
]

# Fração do contexto reservada para um único resultado de tool (~20%) e teto em caracteres.
# ~4 chars/token; cap evita payloads gigantes mesmo em modelos 1M contexto.
_TOOL_RESULT_FRACTION = 0.2
_CHARS_PER_TOKEN = 4
_MAX_TOOL_RESULT_CHARS_CAP = 400_000
_FALLBACK_MAX_TOOL_RESULT_CHARS = 120_000


def get_max_tool_result_chars(provider: str, model: str) -> int:
    """Retorna o limite de caracteres para resultado de tool conforme o modelo (contexto documentado)."""
    for opt in LLM_MODEL_CATALOG:
        if opt.provider == provider and opt.model == model and opt.context_tokens is not None:
            return min(
                int(opt.context_tokens * _CHARS_PER_TOKEN * _TOOL_RESULT_FRACTION),
                _MAX_TOOL_RESULT_CHARS_CAP,
            )
    return _FALLBACK_MAX_TOOL_RESULT_CHARS
