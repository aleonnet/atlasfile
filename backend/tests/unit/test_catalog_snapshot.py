"""Snapshot LiteLLM embarcado: camada base do catálogo, linhas do usuário
preservadas em atualizações, custos em camadas e refresh de primeiro boot."""
from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

import app.main as main_module
from app import llm_catalog, usage_costs
from app.llm_catalog import LLM_MODEL_CATALOG, snapshot_costs
from app.models import ModelOption
from scripts.update_catalog_snapshot import merge_snapshot


@pytest.fixture()
def isolated_layers(tmp_path, monkeypatch):
    """Sem cache remoto nem override de custos de máquina de dev."""
    monkeypatch.setattr(llm_catalog.settings, "projects_root", str(tmp_path))
    monkeypatch.setattr(usage_costs.settings, "projects_root", str(tmp_path))
    monkeypatch.setattr(llm_catalog, "_merged_memo", None)
    monkeypatch.setattr(usage_costs, "_override_memo", None)
    yield tmp_path
    llm_catalog._merged_memo = None
    usage_costs._override_memo = None


def test_snapshot_embarcado_e_a_camada_base_completa():
    """Instância nova (sem refresh) já vê o catálogo completo — não a lista mínima."""
    assert len(LLM_MODEL_CATALOG) >= 50
    providers = {m.provider for m in LLM_MODEL_CATALOG}
    assert {"openai", "anthropic", "moonshot"} <= providers


def test_kimi_k3_vem_da_secao_user_com_custos_pesquisados(isolated_layers):
    k3 = next(m for m in LLM_MODEL_CATALOG if (m.provider, m.model) == ("moonshot", "kimi-k3"))
    # id/limites da doc oficial (contexto 1M; saída default 131072); thinking é
    # always-on no servidor — não enviamos reasoning_effort (Moonshot só aceita
    # low/high/max, nosso "medium" daria erro)
    assert k3.context_tokens == 1_048_576
    assert k3.max_output_tokens == 131_072
    assert k3.supports_reasoning_effort is False
    # custos reais ($/1M): input 3.00, output 15.00, cache hit 0.30
    assert usage_costs.get_cost_per_1m("moonshot", "kimi-k3") == (3.0, 15.0, 0.3, 0.0)


def test_snapshot_costs_user_nao_sobrepoe_litellm():
    costs = snapshot_costs()
    # camada litellm presente (ex.: gpt-4o-mini tem preço)
    assert "gpt-4o-mini" in costs.get("openai", {})
    # camada user presente onde o litellm não cobre
    assert "kimi-k3" in costs.get("moonshot", {})


def _mk(provider: str, model: str) -> ModelOption:
    return ModelOption(provider=provider, model=model, label=f"{provider} {model}")


def test_merge_snapshot_preserva_linhas_do_usuario_e_promove_cobertas():
    current = {
        "user_models": [
            {"provider": "moonshot", "model": "kimi-k3", "label": "Moonshot Kimi K3"},
            {"provider": "moonshot", "model": "kimi-k4", "label": "Moonshot Kimi K4"},
        ],
        "user_costs": {
            "moonshot": {
                "kimi-k3": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 0},
                "kimi-k4": {"input": 9.9, "output": 9.9, "cache_read": 0, "cache_write": 0},
            }
        },
    }
    # LiteLLM do dia passou a cobrir o k3 (modelo E custo); k4 segue só do usuário
    litellm_models = [_mk("moonshot", "kimi-k3"), _mk("openai", "gpt-x")]
    litellm_costs = {"moonshot": {"kimi-k3": {"input": 2.5, "output": 12.0, "cache_read": 0.25, "cache_write": 0}}}

    snapshot, summary = merge_snapshot(current, litellm_models, litellm_costs, source_url="https://x")

    user_keys = {(m["provider"], m["model"]) for m in snapshot["user_models"]}
    assert user_keys == {("moonshot", "kimi-k4")}  # k3 promovido, k4 preservado
    assert snapshot["user_costs"] == {"moonshot": {"kimi-k4": {"input": 9.9, "output": 9.9, "cache_read": 0, "cache_write": 0}}}
    # linha que existe em ambos passa a ser gerida pela fonte (valores do LiteLLM)
    assert snapshot["costs"]["moonshot"]["kimi-k3"]["input"] == 2.5
    assert summary == {
        "litellm_models": 2,
        "user_models_kept": 1,
        "user_models_promoted": 1,
        "user_costs_kept": 1,
        "user_costs_promoted": 1,
    }


def test_refresh_no_primeiro_boot_somente_sem_cache(isolated_layers):
    done = threading.Event()
    with patch("app.llm_catalog_refresh.refresh_catalog") as mock_refresh:
        mock_refresh.side_effect = lambda: (done.set(), {"models_total": 1})[1]
        # sem cache → agenda o refresh em background
        assert main_module._maybe_refresh_catalog_on_startup() is True
        assert done.wait(timeout=5)
        assert mock_refresh.call_count == 1
    # com cache presente → não dispara
    path = llm_catalog.catalog_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"refreshed_at": "x", "models": []}', encoding="utf-8")
    assert main_module._maybe_refresh_catalog_on_startup() is False
