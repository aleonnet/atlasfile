from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.classification_bootstrap import (
    classify_bootstrap,
    detect_document_type,
)
from app.profile_schema_v2 import ProjectProfileV2
from app.project_profile import profile_v2_to_runtime

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEMPLATE_PATH = REPO_ROOT / "config" / "templates" / "default.json"


def _load_template_data() -> dict:
    return json.loads(DEFAULT_TEMPLATE_PATH.read_text(encoding="utf-8"))


def _load_runtime_profile() -> dict:
    raw = _load_template_data()
    model = ProjectProfileV2.model_validate(raw)
    return profile_v2_to_runtime(model, Path(raw["project_root"]))


def test_default_template_validates_new_bootstrap_contract() -> None:
    model = ProjectProfileV2.model_validate(_load_template_data())

    classification = _load_template_data()["classification"]
    assert "document_type_priors" not in classification
    assert "entity_domain_affinity" not in classification
    assert "context_boosts" not in classification
    assert "thresholds" not in classification
    assert any(row.key == "suprimentos" for row in model.classification.business_domains)
    assert any(row.key == "edital" for row in model.classification.document_types)
    assert any(row.key == "plano" for row in model.classification.document_types)


def test_profile_validation_requires_business_domains() -> None:
    raw = _load_template_data()
    raw["classification"]["business_domains"] = []

    with pytest.raises(Exception):
        ProjectProfileV2.model_validate(raw)


def test_detect_document_type_uses_configured_structural_rule_for_edital() -> None:
    profile = _load_runtime_profile()

    result = detect_document_type(
        profile=profile,
        source_path=Path("Projeto TV - Edital do Procedimento Competitivo.docx"),
        text_excerpt="Edital do procedimento competitivo para alienação de ativos.",
    )

    assert result["document_type"] == "edital"
    assert result["document_type_reason"] == "structural_header"


def test_slide_pdf_classifica_pelo_genero_nao_pelo_formato() -> None:
    """Taxonomia essencial (v0.39.0): PDF de slides sobre planejamento é PLANO —
    o formato (apresentação) virou faceta doc_kind, não engole mais o gênero."""
    profile = _load_runtime_profile()

    result = detect_document_type(
        profile=profile,
        source_path=Path("Neptune_Milestones_Read-Only.pdf"),
        text_excerpt="MATERIAL CONFIDENCIAL | SLIDE Nº 1\nPlanejamento preliminar de milestones\nPlano de trabalho e frentes.",
    )

    assert result["document_type"] == "plano"


def test_classify_bootstrap_never_returns_empty_even_without_clear_signal() -> None:
    profile = _load_runtime_profile()

    result = classify_bootstrap(
        profile=profile,
        source_path=Path("Documento_sem_contexto.pdf"),
        text_excerpt="Conteúdo genérico sem pistas fortes.",
    )

    assert result["document_type"]
    assert result["business_domain"]
    assert result["confidence"] >= 0.0


def test_classify_bootstrap_uses_domain_aliases_for_parecer() -> None:
    profile = _load_runtime_profile()

    result = classify_bootstrap(
        profile=profile,
        source_path=Path("Parecer_Trabalhista.pdf"),
        text_excerpt="Parecer jurídico sobre passivo contingente e litígio em andamento.",
    )

    assert result["document_type"] == "parecer"
    assert result["business_domain"] == "juridico"


def test_classify_bootstrap_uses_domain_aliases_for_suprimentos() -> None:
    profile = _load_runtime_profile()

    result = classify_bootstrap(
        profile=profile,
        source_path=Path("Contratos Vigentes Fornecedores.xlsx"),
        text_excerpt="Planilha de procurement com fornecedores, sourcing, vendor e status contratual.",
    )

    # v0.39.0: "planilha" (formato) saiu — o conteúdo (lista de contratos
    # vigentes) classifica como gênero; o formato vive na faceta doc_kind
    assert result["document_type"] in ("relatorio", "contrato")
    assert result["business_domain"] == "suprimentos"


def test_classify_bootstrap_uses_sap_contract_context_for_ti() -> None:
    profile = _load_runtime_profile()

    result = classify_bootstrap(
        profile=profile,
        source_path=Path("CT_4600052462_Contrato_Servicos_TI.pdf"),
        text_excerpt="CONTRATO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS. SAP Business One. Serviços de TI.",
    )

    assert result["document_type"] == "contrato"
    assert result["business_domain"] == "ti"


def test_classify_bootstrap_uses_tsa_contract_context_for_operacoes() -> None:
    profile = _load_runtime_profile()

    result = classify_bootstrap(
        profile=profile,
        source_path=Path("Project Neptune _ TSA_v. Assinada.pdf"),
        text_excerpt="CONTRATO DE COMPARTILHAMENTO DE SERVIÇOS ADMINISTRATIVOS. TSA. Transitional services agreement.",
    )

    assert result["document_type"] == "contrato"
    assert result["business_domain"] == "operacoes"


def test_head_chars_limita_regra_de_cabecalho_a_abertura() -> None:
    """Regra com head_chars só enxerga a abertura — menção profunda no corpo não
    dispara (a causa dos falsos 0.96+ que o atalho de extensão mascarava)."""
    from app.classification_bootstrap import _rule_matches_text

    rule = {"any_of": ["edital"], "confidence": 0.96, "head_chars": 600}
    head_text = "edital de procedimento competitivo " + ("x" * 700)
    deep_text = ("apresentacao de kickoff do projeto " * 20) + " mencionando o edital ao final"

    assert _rule_matches_text(head_text, ".pdf", rule) is True
    assert _rule_matches_text(deep_text, ".pdf", rule) is False
    # sem head_chars: comportamento antigo (texto inteiro) preservado
    assert _rule_matches_text(deep_text, ".pdf", {"any_of": ["edital"], "confidence": 0.96}) is True
