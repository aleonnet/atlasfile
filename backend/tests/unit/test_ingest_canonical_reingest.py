"""v0.45.0 (W-D): reingestão de arquivo JÁ canônico não re-embrulha o nome.

Caso real que motivou o item (2026-07-25): reingestão produziu
20260725__taxonomia_e2e_v080__20260320__taxonomia_e2e_v080__societario__DocuSign_..._v_A__v01__v01
— prefixo duplicado E linhagem de versão quebrada (title_token embrulhado nunca
encontra as versões anteriores).
"""
from __future__ import annotations

from app.ingestion import _unwrap_canonical_stem
from app.utils import DEFAULT_CANONICAL_PATTERN, build_canonical_filename


def _profile(pattern: str = DEFAULT_CANONICAL_PATTERN) -> dict:
    return {
        "project_id": "taxonomia_e2e_v080",
        "naming": {"canonical_pattern": pattern},
        "classification": {
            "business_domains": [{"key": "societario"}, {"key": "juridico"}, {"key": "financeiro"}],
            "document_types": [{"key": "contrato"}],
        },
    }


def test_nome_comum_nao_e_desembrulhado():
    assert _unwrap_canonical_stem("DocuSign Project Neptune - SPA.pdf", _profile()) is None
    # cauda __vNN precisa de estrutura canônica à frente; sem prefixo não parseia
    assert _unwrap_canonical_stem("nota__v01", _profile()) is None


def test_desembrulha_canonico_do_pattern_default():
    canonical = build_canonical_filename(
        pattern=DEFAULT_CANONICAL_PATTERN,
        fields={"project": "taxonomia_e2e_v080", "original_name": "DocuSign_Project_Neptune___SPA__Anexos_v_A"},
        original_suffix=".pdf",
        version=1,
        date_override="20260320",
    )
    assert _unwrap_canonical_stem(canonical, _profile()) == "DocuSign_Project_Neptune___SPA__Anexos_v_A.pdf"


def test_desembrulha_pattern_com_dominio_via_residuo():
    """Nome criado com pattern de 3 segmentos num profile hoje em 2 segmentos
    (migração de naming): o candidato do pattern atual sobra com 'societario__'
    na frente — resíduo (domínio conhecido do profile) é preterido pela
    variante de 3 segmentos da cadeia."""
    canonical = "20260320__taxonomia_e2e_v080__societario__DocuSign_Project_Neptune___SPA__Anexos_v_A__v01.pdf"
    assert (
        _unwrap_canonical_stem(canonical, _profile())
        == "DocuSign_Project_Neptune___SPA__Anexos_v_A.pdf"
    )


def test_caso_real_embrulho_duplo():
    wrapped = (
        "20260725__taxonomia_e2e_v080__20260320__taxonomia_e2e_v080__societario__"
        "DocuSign_Project_Neptune___SPA__Anexos_v_A__v01__v01.pdf"
    )
    assert (
        _unwrap_canonical_stem(wrapped, _profile())
        == "DocuSign_Project_Neptune___SPA__Anexos_v_A.pdf"
    )


def test_titulo_com_underscores_duplos_sobrevive_uma_passada():
    """Título original contendo '__' não é destruído: a extração pelo pattern do
    profile pula exatamente os segmentos do prefixo e para (sem cauda no resto)."""
    canonical = build_canonical_filename(
        pattern=DEFAULT_CANONICAL_PATTERN,
        fields={"project": "taxonomia_e2e_v080", "original_name": "relatorio__final__rev2"},
        original_suffix=".docx",
        version=3,
        date_override="20260101",
    )
    assert _unwrap_canonical_stem(canonical, _profile()) == "relatorio__final__rev2.docx"
