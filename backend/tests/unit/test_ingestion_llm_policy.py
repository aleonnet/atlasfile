"""Unit tests for LLM policy merge/override behavior in ingestion."""
from __future__ import annotations

from app.ingestion import _apply_llm_policy


def _profile_with_mode(mode: str) -> dict:
    return {
        "business_domains": [{"key": "juridica"}, {"key": "financeiro"}],
        "classification": {
            "document_types": [{"key": "memo"}, {"key": "contrato"}],
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



def test_llm_policy_persiste_resposta_crua_do_llm_para_visibilidade() -> None:
    """O histórico mostra o que o LLM respondeu de fato (domínio, tipo, conf),
    não o resultado final relabelado como 'LLM'."""
    classification = {"business_domain": "juridica", "confidence": 0.7, "reason": "rule"}
    llm_result = {
        "business_domain": "financeiro",
        "confidence": 0.92,
        "document_type": "memo",
        "explanation": "parece financeiro",
    }
    merged, _ = _apply_llm_policy(
        profile=_profile_with_mode("tag_only"),
        classification=classification,
        llm_result=llm_result,
    )
    assert merged["llm_business_domain"] == "financeiro"
    assert merged["llm_document_type"] == "memo"
    assert merged["llm_confidence"] == 0.92


def test_llm_document_type_fora_da_taxonomia_nao_e_aplicado() -> None:
    """v0.47.0 (caso real: gpt-5 respondeu a sentinela 'outro' em tag_only e o
    roteamento explodia com 'document_type folder is not configured'): tipo do
    LLM só é aplicado se existir na taxonomia; desconhecido vira
    llm_proposed_document_type (visível ao revisor) e o tipo da regra fica."""
    classification = {"business_domain": "juridica", "document_type": "contrato", "confidence": 0.7, "reason": "rule"}
    merged, force_triage = _apply_llm_policy(
        profile=_profile_with_mode("tag_only"),
        classification=classification,
        llm_result={"document_type": "outro", "confidence": 0.9},
    )
    assert force_triage is False
    assert merged["document_type"] == "contrato"  # regra preservada
    assert merged["llm_proposed_document_type"] == "outro"  # proposta registrada
    assert merged["llm_document_type"] == "outro"  # resposta crua visível


def test_llm_document_type_valido_e_aplicado() -> None:
    classification = {"business_domain": "juridica", "document_type": "contrato", "confidence": 0.7, "reason": "rule"}
    merged, _ = _apply_llm_policy(
        profile=_profile_with_mode("tag_only"),
        classification=classification,
        llm_result={"document_type": "memo", "confidence": 0.9},
    )
    assert merged["document_type"] == "memo"
    assert "llm_proposed_document_type" not in merged


def test_prompt_de_classificacao_bane_a_sentinela_outro() -> None:
    """O prompt não pode mais instruir 'outro' — omissão honesta + justificativa."""
    from app.orchestrator import _build_project_context

    prompt = _build_project_context({
        "project_id": "p1",
        "business_domains": [{"key": "juridica"}],
        "classification": {"document_types": [{"key": "contrato"}]},
    })
    assert "Se nenhum se encaixar, use 'outro'" not in prompt  # instrução antiga banida
    assert "NUNCA use 'outro'" in prompt
    assert "OMITA" in prompt
