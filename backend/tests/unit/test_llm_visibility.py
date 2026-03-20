"""Tests that _apply_llm_policy preserves LLM visibility fields."""
from __future__ import annotations

from app.ingestion import _apply_llm_policy


def _base_profile(mode: str = "tag_only") -> dict:
    return {
        "business_domains": [
            {"key": "financeiro", "aliases": []},
            {"key": "contratos_comunicacao", "aliases": []},
        ],
        "llm_policy": {
            "enabled": True,
            "mode": mode,
            "allow_override_fields": ["confidence", "tags", "document_type", "topics"],
            "override_guardrails": {
                "business_domain_override_only_if_rule_confidence_below": 0.65,
                "require_explanation": True,
                "max_business_domain_changes": 1,
            },
        },
    }


def test_preserves_rule_business_domain_and_confidence():
    classification = {
        "business_domain": "contratos_comunicacao",
        "confidence": 0.40,
        "reason": "alias_scoring",
        "top_candidates": [],
    }
    llm_result = {
        "business_domain": "financeiro",
        "confidence": 0.85,
        "explanation": "Resumo financeiro com EBITDA e receita",
        "tags": ["financeiro"],
    }
    result, _ = _apply_llm_policy(
        profile=_base_profile("review"),
        classification=classification,
        llm_result=llm_result,
    )
    assert result["_rule_business_domain"] == "contratos_comunicacao"
    assert result["_rule_confidence"] == 0.40


def test_preserves_llm_explanation_in_review_mode():
    classification = {
        "business_domain": "contratos_comunicacao",
        "confidence": 0.40,
        "reason": "alias_scoring",
        "top_candidates": [],
    }
    llm_result = {
        "business_domain": "financeiro",
        "confidence": 0.85,
        "explanation": "Documento financeiro com EBITDA",
    }
    result, force_triage = _apply_llm_policy(
        profile=_base_profile("review"),
        classification=classification,
        llm_result=llm_result,
    )
    assert result["llm_explanation"] == "Documento financeiro com EBITDA"
    assert force_triage is True


def test_preserves_llm_explanation_in_tag_only_mode():
    classification = {
        "business_domain": "financeiro",
        "confidence": 0.60,
        "reason": "alias_scoring",
        "top_candidates": [],
    }
    llm_result = {
        "business_domain": "financeiro",
        "confidence": 0.85,
        "explanation": "Classificacao confirmada pelo LLM",
    }
    result, _ = _apply_llm_policy(
        profile=_base_profile("tag_only"),
        classification=classification,
        llm_result=llm_result,
    )
    assert result["llm_explanation"] == "Classificacao confirmada pelo LLM"


def test_preserves_llm_proposed_business_domain_when_not_in_profile():
    classification = {
        "business_domain": "contratos_comunicacao",
        "confidence": 0.30,
        "reason": "alias_scoring",
        "top_candidates": [],
    }
    llm_result = {
        "business_domain": "esg_sustentabilidade",
        "confidence": 0.80,
        "explanation": "Relatorio ESG sem business_domain existente adequado",
    }
    result, _ = _apply_llm_policy(
        profile=_base_profile("review"),
        classification=classification,
        llm_result=llm_result,
    )
    assert result["llm_proposed_business_domain"] == "esg_sustentabilidade"
    assert result["llm_explanation"] == "Relatorio ESG sem business_domain existente adequado"
    assert result["business_domain"] == "contratos_comunicacao"


def test_full_override_preserves_all_fields():
    classification = {
        "business_domain": "contratos_comunicacao",
        "confidence": 0.30,
        "reason": "alias_scoring",
        "top_candidates": [],
    }
    llm_result = {
        "business_domain": "financeiro",
        "confidence": 0.85,
        "explanation": "Doc financeiro",
    }
    result, _ = _apply_llm_policy(
        profile=_base_profile("full_override"),
        classification=classification,
        llm_result=llm_result,
    )
    assert result["_rule_business_domain"] == "contratos_comunicacao"
    assert result["_rule_confidence"] == 0.30
    assert result["llm_explanation"] == "Doc financeiro"
    assert result["business_domain"] == "financeiro"
    assert result["reason"] == "llm_full_override"


def test_no_llm_result_returns_unchanged():
    classification = {
        "business_domain": "financeiro",
        "confidence": 0.90,
        "reason": "alias_scoring",
        "top_candidates": [],
    }
    result, force = _apply_llm_policy(
        profile=_base_profile("review"),
        classification=classification,
        llm_result=None,
    )
    assert "_rule_business_domain" not in result
    assert "llm_explanation" not in result
    assert force is False
