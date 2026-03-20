"""Unit tests for LLM policy merge/override behavior in ingestion."""
from __future__ import annotations

from app.ingestion import _apply_llm_policy


def _profile_with_mode(mode: str) -> dict:
    return {
        "business_domains": [{"key": "juridica"}, {"key": "financeiro"}],
        "classification": {
            "llm_policy": {
                "enabled": True,
                "mode": mode,
                "allow_override_fields": ["document_type", "tags", "confidence", "topics"],
                "override_guardrails": {
                    "business_domain_override_only_if_rule_confidence_below": 0.65,
                    "require_explanation": True,
                    "max_business_domain_changes": 1,
                },
            }
        },
    }


def test_llm_policy_tag_only_enriches_without_business_domain_override() -> None:
    classification = {"business_domain": "juridica", "confidence": 0.7, "reason": "rule"}
    llm_result = {
        "business_domain": "financeiro",
        "confidence": 0.92,
        "tags": ["LLM_TAG"],
        "topics": ["tsa"],
        "document_type": "memo",
    }
    merged, force_triage = _apply_llm_policy(
        profile=_profile_with_mode("tag_only"),
        classification=classification,
        llm_result=llm_result,
    )
    assert force_triage is False
    assert merged["business_domain"] == "juridica"
    assert merged["confidence"] == 0.92
    assert merged["suggested_tags"] == ["LLM_TAG"]
    assert merged["suggested_topics"] == ["tsa"]
    assert merged["document_type"] == "memo"


def test_llm_policy_review_forces_triage_on_business_domain_divergence() -> None:
    classification = {"business_domain": "juridica", "confidence": 0.4, "reason": "rule"}
    llm_result = {"business_domain": "financeiro", "confidence": 0.8, "explanation": "mais aderente"}
    merged, force_triage = _apply_llm_policy(
        profile=_profile_with_mode("review"),
        classification=classification,
        llm_result=llm_result,
    )
    assert merged["business_domain"] == "juridica"
    assert merged["reason"] == "llm_review_divergence"
    assert force_triage is True


def test_llm_policy_full_override_when_guardrails_pass() -> None:
    classification = {"business_domain": "juridica", "confidence": 0.3, "reason": "rule"}
    llm_result = {"business_domain": "financeiro", "confidence": 0.85, "explanation": "evidencia melhor"}
    merged, force_triage = _apply_llm_policy(
        profile=_profile_with_mode("full_override"),
        classification=classification,
        llm_result=llm_result,
    )
    assert force_triage is False
    assert merged["business_domain"] == "financeiro"
    assert merged["reason"] == "llm_full_override"
    assert merged["llm_explanation"] == "evidencia melhor"


def test_llm_policy_full_override_blocked_without_explanation() -> None:
    classification = {"business_domain": "juridica", "confidence": 0.2, "reason": "rule"}
    llm_result = {"business_domain": "financeiro", "confidence": 0.9, "explanation": ""}
    merged, force_triage = _apply_llm_policy(
        profile=_profile_with_mode("full_override"),
        classification=classification,
        llm_result=llm_result,
    )
    assert merged["business_domain"] == "juridica"
    assert merged["reason"] == "llm_override_guardrail_blocked"
    assert force_triage is True

