"""Tests for classify() alias scoring with the audited alias sets.

Each test builds a minimal profile from the default template's work_areas and
verifies that representative documents classify into the expected area.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ingestion import _score_area, classify


def _load_template() -> dict:
    template_path = Path(__file__).resolve().parents[3] / "config" / "templates" / "default.json"
    with open(template_path) as f:
        return json.load(f)


def _load_template_work_areas() -> list[dict]:
    return _load_template()["classification"]["work_areas"]


def _load_template_routing_rules() -> list[dict]:
    return _load_template()["classification"]["routing_rules"]


def _profile_with_areas(work_areas: list[dict], routing_rules: list[dict] | None = None) -> dict:
    return {
        "work_areas": work_areas,
        "routing_rules": routing_rules or [],
    }


def _full_profile() -> dict:
    tmpl = _load_template()
    return {
        "work_areas": tmpl["classification"]["work_areas"],
        "routing_rules": tmpl["classification"]["routing_rules"],
    }


WORK_AREAS = _load_template_work_areas()
PROFILE = _profile_with_areas(WORK_AREAS)
FULL_PROFILE = _full_profile()


# -- financeiro --

def test_financial_summary_classifies_as_financeiro():
    result = classify(
        profile=PROFILE,
        source_path=Path("Slide Resumo Jan25 - 27022025.pdf"),
        text_excerpt="Resumo Executivo do Resultado Financeiro. RECEITA BRUTA 31.525. EBITDA 271.963. CUSTOS E DESPESAS 29.446.",
    )
    assert result["area_key"] == "financeiro"


def test_dre_classifies_as_financeiro():
    result = classify(
        profile=PROFILE,
        source_path=Path("DRE_Consolidado_2025.xlsx"),
        text_excerpt="Demonstrativo de Resultado do Exercício. Receita líquida. Margem EBITDA. Resultado operacional.",
    )
    assert result["area_key"] == "financeiro"


def test_budget_classifies_as_financeiro():
    result = classify(
        profile=PROFILE,
        source_path=Path("Budget_2025_v3.xlsx"),
        text_excerpt="Orçamento consolidado. Budget forecast. Fluxo de caixa projetado. Balanço patrimonial.",
    )
    assert result["area_key"] == "financeiro"


# -- contratos_comunicacao --

def test_contrato_servicos_classifies_as_contratos():
    result = classify(
        profile=PROFILE,
        source_path=Path("Contrato_Prestacao_Servicos.pdf"),
        text_excerpt="Contrato de prestação de serviços entre as partes. Preâmbulo. Fornecedor contratado para SLA.",
    )
    assert result["area_key"] == "contratos_comunicacao"


def test_nda_classifies_as_contratos():
    result = classify(
        profile=PROFILE,
        source_path=Path("NDA_Parceiro_XYZ.pdf"),
        text_excerpt="Acordo de confidencialidade (NDA) entre as partes. Distrato em caso de violação.",
    )
    assert result["area_key"] == "contratos_comunicacao"


# -- false positive: financeiro doc should NOT go to contratos even with 'cliente' in text --

def test_financial_with_cliente_not_contratos():
    """A financial doc mentioning 'cliente' should still classify as financeiro, not contratos."""
    result = classify(
        profile=PROFILE,
        source_path=Path("Resumo_Financeiro.pdf"),
        text_excerpt="Receita por cliente CO. EBITDA consolidado. Custos e margem. Resultado do exercício. Balanço.",
    )
    assert result["area_key"] == "financeiro"


# -- societario_fiscal --

def test_cnpj_classifies_as_societario():
    result = classify(
        profile=PROFILE,
        source_path=Path("Relatorio_CNPJ_Filiais.pdf"),
        text_excerpt="Listagem de CNPJs das filiais e estabelecimentos. Regime tributário. Enquadramento fiscal.",
    )
    assert result["area_key"] == "societario_fiscal"


# -- juridica --

def test_parecer_juridico_classifies_as_juridica():
    result = classify(
        profile=PROFILE,
        source_path=Path("Parecer_Trabalhista.pdf"),
        text_excerpt="Parecer jurídico sobre passivo contingente. Litígio em andamento. Sentença desfavorável.",
    )
    assert result["area_key"] == "juridica"


# -- ativos --

def test_imobilizado_classifies_as_ativos():
    result = classify(
        profile=PROFILE,
        source_path=Path("CMDB_Ativos_Imobilizado.xlsx"),
        text_excerpt="Inventário de ativos imobilizados. Depreciação acumulada. Patrimônio segregado. Cessão de bens.",
    )
    assert result["area_key"] == "ativos"


# -- pessoas --

def test_organograma_classifies_as_pessoas():
    result = classify(
        profile=PROFILE,
        source_path=Path("Organograma_RH_2025.pdf"),
        text_excerpt="Organograma da diretoria. Colaboradores por gerência. Folha de pagamento. Headcount operacional.",
    )
    assert result["area_key"] == "pessoas"


# -- sistemas_migracao --

def test_migracao_sap_classifies_as_sistemas():
    result = classify(
        profile=PROFILE,
        source_path=Path("Plano_Migracao_SAP.pdf"),
        text_excerpt="Migração de sistemas SAP. Integração com plataforma cloud. Infraestrutura banco de dados.",
    )
    assert result["area_key"] == "sistemas_migracao"


# -- processos_tsa --

def test_tsa_process_classifies_as_processos():
    result = classify(
        profile=PROFILE,
        source_path=Path("TSA_Processos_Operacionais.pdf"),
        text_excerpt="Processos operacionais TSA. Procedimento SOX. Fluxograma de atendimento pós-closing.",
    )
    assert result["area_key"] == "processos_tsa"


# -- entregaveis --

def test_cronograma_classifies_as_entregaveis():
    result = classify(
        profile=PROFILE,
        source_path=Path("Cronograma_Workstream.xlsx"),
        text_excerpt="Cronograma de milestones por workstream. Baseline do escopo. Métricas de output.",
    )
    assert result["area_key"] == "entregaveis"


# ======================================================================
# Word-boundary tests: false positives that substring matching would hit
# ======================================================================

def test_word_boundary_ativo_not_in_interativo():
    """'ativo' alias must NOT match inside 'interativo'."""
    area = {"key": "ativos", "aliases": ["ativo"]}
    score = _score_area(area, "sistema interativo de gestao")
    assert score == 0.0


def test_word_boundary_ativo_matches_standalone():
    """'ativo' alias must match as standalone word."""
    area = {"key": "ativos", "aliases": ["ativo"]}
    score = _score_area(area, "relatorio de ativo imobilizado")
    assert score > 0.0


def test_word_boundary_sistema_not_in_sistematica():
    """'sistema' alias must NOT match inside 'sistematica'."""
    area = {"key": "sistemas_migracao", "aliases": ["sistema"]}
    score = _score_area(area, "revisao sistematica do processo")
    assert score == 0.0


def test_word_boundary_regime_not_in_regimento():
    """'regime' alias must NOT match inside 'regimento'."""
    area = {"key": "societario_fiscal", "aliases": ["regime"]}
    score = _score_area(area, "regimento interno da empresa")
    assert score == 0.0


# ======================================================================
# Compound alias tests (aliases with underscores / hyphens)
# ======================================================================

def test_compound_alias_fluxo_caixa():
    """Compound alias 'fluxo_caixa' matches when text contains it
    (underscores normalized to spaces for matching)."""
    area = {"key": "financeiro", "aliases": ["fluxo_caixa"]}
    score = _score_area(area, "projecao de fluxo_caixa para 2025")
    assert score > 0.0


def test_compound_alias_fluxo_caixa_with_spaces():
    """Compound alias 'fluxo_caixa' also matches 'fluxo caixa' (space)."""
    area = {"key": "financeiro", "aliases": ["fluxo_caixa"]}
    score = _score_area(area, "projecao de fluxo caixa para 2025")
    assert score > 0.0


def test_compound_alias_pos_closing():
    """Hyphenated alias 'pos-closing' matches in text."""
    area = {"key": "processos_tsa", "aliases": ["pos-closing"]}
    score = _score_area(area, "atendimento pos-closing ao cliente")
    assert score > 0.0


def test_compound_alias_migracao_sistemas():
    area = {"key": "sistemas_migracao", "aliases": ["migracao_sistemas"]}
    score = _score_area(area, "plano de migracao_sistemas para cloud")
    assert score > 0.0


# ======================================================================
# New routing rules tests (4 areas that were uncovered)
# ======================================================================

def test_routing_rule_parecer_routes_juridica():
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("Parecer_Trabalhista.pdf"),
        text_excerpt="Conteúdo genérico sem aliases relevantes.",
    )
    assert result["area_key"] == "juridica"
    assert result["reason"] == "filename_contains:parecer"
    assert result["confidence"] == 0.9


def test_routing_rule_dre_routes_financeiro():
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("DRE_Consolidado_2025.xlsx"),
        text_excerpt="Conteúdo genérico.",
    )
    assert result["area_key"] == "financeiro"
    assert result["reason"] == "filename_contains:dre"


def test_routing_rule_budget_routes_financeiro():
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("Budget_2025_v3.xlsx"),
        text_excerpt="Conteúdo genérico.",
    )
    assert result["area_key"] == "financeiro"
    assert result["reason"] == "filename_contains:budget"


def test_routing_rule_migracao_routes_sistemas():
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("Plano_Migracao_SAP.pdf"),
        text_excerpt="Conteúdo genérico.",
    )
    assert result["area_key"] == "sistemas_migracao"
    assert result["reason"] == "filename_contains:migracao"


def test_routing_rule_tsa_routes_processos():
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("TSA_Processos_Operacionais.pdf"),
        text_excerpt="Conteúdo genérico.",
    )
    assert result["area_key"] == "processos_tsa"
    assert result["reason"] == "filename_contains:tsa"


def test_routing_rule_sox_routes_processos():
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("Controles_SOX_2025.xlsx"),
        text_excerpt="Conteúdo genérico.",
    )
    assert result["area_key"] == "processos_tsa"
    assert result["reason"] == "filename_contains:sox"


def test_routing_rule_fluxograma_routes_processos():
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("Fluxograma_Atendimento.pdf"),
        text_excerpt="Conteúdo genérico.",
    )
    assert result["area_key"] == "processos_tsa"
    assert result["reason"] == "filename_contains:fluxograma"


# ======================================================================
# Sqrt normalization: areas with more aliases no longer penalized
# ======================================================================

def test_sqrt_scoring_financeiro_beats_contratos_with_more_hits():
    """With sqrt normalization, financeiro (17 aliases, 5 hits) scores
    higher than contratos (9 aliases, 2 hits)."""
    financeiro = next(a for a in WORK_AREAS if a["key"] == "financeiro")
    contratos = next(a for a in WORK_AREAS if a["key"] == "contratos_comunicacao")

    text = "receita ebitda custos margem resultado"
    fin_score = _score_area(financeiro, text)
    con_score = _score_area(contratos, text)
    assert fin_score > con_score
    assert fin_score > 0.5, f"financeiro score too low: {fin_score}"


def test_sqrt_scoring_single_alias_area():
    """Area with 1 alias and 1 hit should score 1.0."""
    area = {"key": "test", "aliases": ["unico"]}
    score = _score_area(area, "termo unico presente")
    assert score == 1.0


def test_sqrt_scoring_capped_at_one():
    """Score must never exceed 1.0 even with many hits."""
    area = {"key": "test", "aliases": ["a", "b", "c", "d"]}
    score = _score_area(area, "a b c d")
    assert score <= 1.0


def test_sqrt_scoring_no_hits_is_zero():
    area = {"key": "test", "aliases": ["xyz", "qqq"]}
    score = _score_area(area, "nenhum match aqui")
    assert score == 0.0


# ======================================================================
# Routing rules: word boundary prevents false positives
# ======================================================================

def test_routing_rule_ativo_not_in_criativo():
    """'ativo' routing rule must NOT match filename 'Criativo_Design.pdf'."""
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("Criativo_Design.pdf"),
        text_excerpt="Design criativo para campanha de marketing.",
    )
    assert result["area_key"] != "ativos" or result["reason"] == "alias_scoring"


def test_routing_rule_sap_not_in_terapia():
    """'sap' routing rule must NOT match filename 'Terapia_Ocupacional.pdf'.
    Note: 'sap' is NOT a substring of 'terapia' in Python, but this test
    guards against future aliases that could be substrings."""
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("Terapia_Ocupacional.pdf"),
        text_excerpt="Programa de terapia para colaboradores.",
    )
    assert result["area_key"] != "sistemas_migracao" or result["reason"] == "alias_scoring"


# ======================================================================
# Existing routing rules still work with word boundary
# ======================================================================

def test_routing_output_dir_still_works():
    """'output/' path routing rule still matches with word boundary."""
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("output/consolidado_final.pdf"),
        text_excerpt="Conteúdo genérico.",
    )
    assert result["area_key"] == "entregaveis"
    assert result["reason"] == "path_contains:output/"


def test_routing_contrato_still_works():
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("Contrato_Servicos.pdf"),
        text_excerpt="Conteúdo genérico.",
    )
    assert result["area_key"] == "contratos_comunicacao"
    assert result["reason"] == "filename_contains:contrato"


def test_routing_cnpj_still_works():
    result = classify(
        profile=FULL_PROFILE,
        source_path=Path("Lista_CNPJ_Filiais.xlsx"),
        text_excerpt="Conteúdo genérico.",
    )
    assert result["area_key"] == "societario_fiscal"
    assert result["reason"].startswith("filename_contains:")
