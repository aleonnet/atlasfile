"""
Catálogo de modelos LLM com limites documentados (contexto e max output).
Usado por GET /api/models e pelo orchestrator para truncar resultado de tools por modelo.
"""
from __future__ import annotations

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


def get_anthropic_thinking_type(provider: str, model: str) -> str | None:
    """Para Anthropic: "adaptive" (4.6) ou "enabled" (4.5 e anteriores). None se não for modelo com thinking."""
    for opt in LLM_MODEL_CATALOG:
        if opt.provider == provider and opt.model == model:
            return opt.anthropic_thinking_type or ("enabled" if opt.supports_reasoning_effort else None)
    return None


def supports_reasoning_effort(provider: str, model: str) -> bool:
    """True se o modelo aceita reasoning/thinking (OpenAI reasoning_effort ou Anthropic Extended Thinking)."""
    for opt in LLM_MODEL_CATALOG:
        if opt.provider == provider and opt.model == model:
            return opt.supports_reasoning_effort
    return False

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
