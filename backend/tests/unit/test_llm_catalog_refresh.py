"""Refresh do catálogo (fonte LiteLLM): filtro, mapeamento e merge com o builtin."""
from __future__ import annotations

import json

import pytest

from app import llm_catalog
from app.llm_catalog import LLM_MODEL_CATALOG, load_catalog, save_catalog_cache
from app.llm_catalog_refresh import parse_litellm_catalog

LITELLM_FIXTURE = {
    "sample_spec": {"max_tokens": "set to max output tokens"},
    "gpt-9-turbo": {
        "litellm_provider": "openai",
        "mode": "chat",
        "supports_function_calling": True,
        "supports_reasoning": True,
        "max_input_tokens": 500_000,
        "max_output_tokens": 64_000,
        "input_cost_per_token": 2e-06,
        "output_cost_per_token": 8e-06,
        "cache_read_input_token_cost": 5e-07,
    },
    "gpt-9-turbo-2027-01-15": {  # snapshot datado — fora
        "litellm_provider": "openai",
        "mode": "chat",
        "supports_function_calling": True,
    },
    "gpt-9-audio": {  # áudio — fora mesmo com mode chat
        "litellm_provider": "openai",
        "mode": "chat",
        "supports_function_calling": True,
    },
    "whisper-2": {"litellm_provider": "openai", "mode": "audio_transcription"},
    "text-embedding-9": {"litellm_provider": "openai", "mode": "embedding"},
    "claude-nova-5": {
        "litellm_provider": "anthropic",
        "mode": "chat",
        "supports_function_calling": True,
        "supports_reasoning": True,
        "supports_adaptive_thinking": True,
        "max_input_tokens": 1_000_000,
        "max_output_tokens": 128_000,
        "input_cost_per_token": 5e-06,
        "output_cost_per_token": 2.5e-05,
        "cache_creation_input_token_cost": 6.25e-06,
    },
    "claude-nova-5-no-tools": {  # sem tool use — fora
        "litellm_provider": "anthropic",
        "mode": "chat",
        "supports_function_calling": False,
    },
    "gemini-x": {"litellm_provider": "vertex_ai", "mode": "chat", "supports_function_calling": True},
    "gpt-5.6": {  # reasoning pós-5.2 → exige Responses API
        "litellm_provider": "openai",
        "mode": "chat",
        "supports_function_calling": True,
        "supports_reasoning": True,
        "max_input_tokens": 400_000,
        "max_output_tokens": 128_000,
    },
    "gpt-7-nova": {  # sinal explícito: só /v1/responses nos endpoints
        "litellm_provider": "openai",
        "mode": "chat",
        "supports_function_calling": True,
        "supported_endpoints": ["/v1/responses"],
    },
    "moonshot/kimi-k3": {  # provider moonshot aceito com custo; prefixo LiteLLM removido do id
        "litellm_provider": "moonshot",
        "mode": "chat",
        "supports_function_calling": True,
        "max_input_tokens": 256_000,
        "max_output_tokens": 32_768,
        "input_cost_per_token": 6e-07,
        "output_cost_per_token": 2.5e-06,
    },
}


def test_parse_filters_to_chat_tool_use_models_only():
    models, costs = parse_litellm_catalog(LITELLM_FIXTURE)
    names = {(m.provider, m.model) for m in models}
    assert names == {
        ("openai", "gpt-9-turbo"),
        ("anthropic", "claude-nova-5"),
        ("openai", "gpt-5.6"),
        ("openai", "gpt-7-nova"),
        ("moonshot", "kimi-k3"),
    }
    assert costs["openai"]["gpt-9-turbo"] == {
        "input": 2.0,
        "output": 8.0,
        "cache_read": 0.5,
        "cache_write": 0.0,
    }
    assert costs["anthropic"]["claude-nova-5"]["cache_write"] == 6.25
    assert costs["moonshot"]["kimi-k3"]["input"] == 0.6


def test_parse_infers_openai_api_por_versao_e_endpoints():
    models, _ = parse_litellm_catalog(LITELLM_FIXTURE)
    by_name = {m.model: m for m in models}
    # reasoning + versão ≥ 5.2 → responses
    assert by_name["gpt-5.6"].openai_api == "responses"
    # sinal explícito supported_endpoints sem /v1/chat/completions → responses
    assert by_name["gpt-7-nova"].openai_api == "responses"
    # reasoning mas sem versão gpt-X.Y parseável → caminho atual
    assert by_name["gpt-9-turbo"].openai_api == "chat_completions"
    # não-openai nunca vira responses
    assert by_name["kimi-k3"].openai_api == "chat_completions"
    assert by_name["kimi-k3"].label == "Moonshot kimi-k3"


def test_cache_antigo_sem_campo_openai_api_usa_default(catalog_cache):
    """Cache gravado antes do campo novo (JSON sem openai_api) → default chat_completions."""
    path = llm_catalog.catalog_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = {
        "refreshed_at": "2026-01-01T00:00:00+00:00",
        "models": [{
            "provider": "openai",
            "model": "gpt-legacy",
            "label": "OpenAI gpt-legacy",
            "context_tokens": 128000,
            "supports_reasoning_effort": True,
        }],
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")
    merged = {(m.provider, m.model): m for m in load_catalog()}
    assert merged[("openai", "gpt-legacy")].openai_api == "chat_completions"
    assert llm_catalog.get_openai_api("openai", "gpt-legacy") == "chat_completions"
    # builtin gpt-5.2 marca responses; desconhecido cai no default
    assert llm_catalog.get_openai_api("openai", "gpt-5.2") == "responses"
    assert llm_catalog.get_openai_api("openai", "modelo-desconhecido") == "chat_completions"


def test_parse_maps_limits_and_thinking():
    models, _ = parse_litellm_catalog(LITELLM_FIXTURE)
    by_name = {m.model: m for m in models}
    gpt = by_name["gpt-9-turbo"]
    assert (gpt.context_tokens, gpt.max_output_tokens, gpt.supports_reasoning_effort) == (500_000, 64_000, True)
    assert gpt.anthropic_thinking_type is None
    claude = by_name["claude-nova-5"]
    assert claude.anthropic_thinking_type == "adaptive"
    assert claude.supports_reasoning_effort is True


@pytest.fixture()
def catalog_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_catalog.settings, "projects_root", str(tmp_path))
    monkeypatch.setattr(llm_catalog, "_merged_memo", None)
    yield tmp_path
    llm_catalog._merged_memo = None


def test_load_catalog_without_cache_returns_builtin(catalog_cache):
    assert load_catalog() == list(LLM_MODEL_CATALOG)


def test_load_catalog_merges_cache_overriding_builtin(catalog_cache):
    models, _ = parse_litellm_catalog(LITELLM_FIXTURE)
    updated_builtin = LLM_MODEL_CATALOG[0].model_copy(update={"context_tokens": 999_999})
    save_catalog_cache([*models, updated_builtin], "2026-07-17T00:00:00+00:00")

    merged = load_catalog()
    by_key = {(m.provider, m.model): m for m in merged}
    # builtin atualizado pelo cache
    assert by_key[(updated_builtin.provider, updated_builtin.model)].context_tokens == 999_999
    # extras do cache anexados
    assert ("openai", "gpt-9-turbo") in by_key
    # builtins sem override permanecem
    assert all((b.provider, b.model) in by_key for b in LLM_MODEL_CATALOG)
    # helper consulta o merge
    assert llm_catalog.get_context_tokens("openai", "gpt-9-turbo") == 500_000


def test_load_catalog_ignores_corrupt_cache(catalog_cache):
    path = llm_catalog.catalog_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{corrompido", encoding="utf-8")
    assert load_catalog() == list(LLM_MODEL_CATALOG)


def test_usage_costs_override_merges(catalog_cache, monkeypatch):
    from app import usage_costs

    monkeypatch.setattr(usage_costs.settings, "projects_root", str(catalog_cache))
    monkeypatch.setattr(usage_costs, "_override_memo", None)
    override = catalog_cache / "_ATLASFILE" / "llm" / "usage_costs_override.json"
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_text(
        json.dumps({"openai": {"gpt-9-turbo": {"input": 2.0, "output": 8.0}}}), encoding="utf-8"
    )
    assert usage_costs.get_cost_per_1m("openai", "gpt-9-turbo") == (2.0, 8.0, 0.0, 0.0)
    # builtin continua respondendo
    assert usage_costs.get_cost_per_1m("openai", "gpt-4o-mini") is not None
    # desconhecido continua None (custo não rastreado, não zero fabricado)
    assert usage_costs.get_cost_per_1m("openai", "modelo-inexistente") is None


def test_catalog_source_url_roundtrip(catalog_cache):
    from app.llm_catalog_refresh import (
        LITELLM_CATALOG_URL,
        get_catalog_source_url,
        set_catalog_source_url,
    )

    assert get_catalog_source_url() == LITELLM_CATALOG_URL
    assert set_catalog_source_url("https://exemplo.com/models.json") == "https://exemplo.com/models.json"
    assert get_catalog_source_url() == "https://exemplo.com/models.json"
    # vazio ou default → volta à default (remove override)
    assert set_catalog_source_url("") == LITELLM_CATALOG_URL
    assert get_catalog_source_url() == LITELLM_CATALOG_URL
    with pytest.raises(ValueError, match="https"):
        set_catalog_source_url("http://inseguro.com/x.json")


def test_refresh_dry_run_does_not_persist(catalog_cache, monkeypatch):
    import httpx as _httpx

    from app import llm_catalog_refresh

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return LITELLM_FIXTURE

    monkeypatch.setattr(_httpx, "get", lambda *a, **k: FakeResponse())
    result = llm_catalog_refresh.refresh_catalog(dry_run=True)
    assert result["dry_run"] is True and result["models_total"] == 5
    assert not llm_catalog.catalog_cache_path().exists()
    result2 = llm_catalog_refresh.refresh_catalog()
    assert result2["dry_run"] is False and "refreshed_at" in result2
    assert llm_catalog.catalog_cache_path().exists()
