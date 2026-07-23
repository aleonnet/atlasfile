"""
Registro central de providers LLM: metadados de autenticação, base_url e
sabor de SDK. Substitui os ternários openai/anthropic espalhados por
orchestrator/main e é o único ponto a tocar para adicionar um provider novo.

Providers OpenAI-compatíveis (moonshot, ollama) usam o SDK openai com
base_url custom — o base_url é resolvido em call-time a partir de settings
para respeitar monkeypatch em testes e overrides por env.

Os imports dos SDKs ficam DENTRO das factories: os testes do projeto
substituem o módulo via sys.modules (Padrão A) ou patch("openai.AsyncOpenAI")
(Padrão B), e um import de módulo aqui congelaria a referência.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.config import settings


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    sdk_flavor: str  # "openai" | "anthropic"
    key_header: str
    key_env: str
    requires_key: bool = True
    # Nome do atributo em settings com o base_url (None = default do SDK)
    base_url_setting: str | None = None
    # SDK openai exige api_key não-vazia mesmo em servidores sem auth (Ollama)
    placeholder_key: str | None = None


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        name="openai",
        label="OpenAI",
        sdk_flavor="openai",
        key_header="X-OpenAI-API-Key",
        key_env="OPENAI_API_KEY",
    ),
    "anthropic": ProviderSpec(
        name="anthropic",
        label="Anthropic",
        sdk_flavor="anthropic",
        key_header="X-Anthropic-API-Key",
        key_env="ANTHROPIC_API_KEY",
    ),
    "moonshot": ProviderSpec(
        name="moonshot",
        label="Moonshot",
        sdk_flavor="openai",
        key_header="X-Moonshot-API-Key",
        key_env="MOONSHOT_API_KEY",
        base_url_setting="moonshot_base_url",
    ),
    "ollama": ProviderSpec(
        name="ollama",
        label="Ollama",
        sdk_flavor="openai",
        key_header="X-Ollama-API-Key",
        key_env="OLLAMA_API_KEY",
        requires_key=False,
        base_url_setting="ollama_base_url",
        placeholder_key="ollama",
    ),
}


def get_provider(name: str) -> ProviderSpec | None:
    return PROVIDERS.get((name or "").strip().lower())


def resolve_base_url(spec: ProviderSpec) -> str | None:
    if not spec.base_url_setting:
        return None
    return getattr(settings, spec.base_url_setting, None) or None


def resolve_api_key(spec: ProviderSpec, transient: str | None) -> str | None:
    """Chave efetiva: transiente (header) > env do provider > placeholder > None.

    Para openai/anthropic (sem base_url), retorna `transient or None` — o
    próprio SDK cai no env correspondente, preservando o comportamento
    histórico byte-a-byte."""
    if transient:
        return transient
    if spec.base_url_setting is None:
        return None
    env_key = os.environ.get(spec.key_env) or None
    return env_key or spec.placeholder_key


def _openai_client_kwargs(spec: ProviderSpec, api_key: str | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"api_key": resolve_api_key(spec, api_key)}
    base_url = resolve_base_url(spec)
    if base_url:
        kwargs["base_url"] = base_url
    return kwargs


def make_async_client(provider: str, api_key: str | None) -> Any:
    spec = get_provider(provider)
    if spec is None:
        raise ValueError(f"Unknown provider: {provider}")
    if spec.sdk_flavor == "anthropic":
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=resolve_api_key(spec, api_key))
    from openai import AsyncOpenAI

    return AsyncOpenAI(**_openai_client_kwargs(spec, api_key))


def make_sync_client(provider: str, api_key: str | None) -> Any:
    spec = get_provider(provider)
    if spec is None:
        raise ValueError(f"Unknown provider: {provider}")
    if spec.sdk_flavor == "anthropic":
        import anthropic as anthropic_sdk

        return anthropic_sdk.Anthropic(api_key=resolve_api_key(spec, api_key))
    import openai as openai_sdk

    return openai_sdk.OpenAI(**_openai_client_kwargs(spec, api_key))
