"""Sugeridor de aliases do bootstrap: mineração contrastiva das correções da
triagem (triage_resolved) e o append governado de aliases na taxonomia."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.alias_suggester import suggest_aliases
from app.classification_bootstrap import _word_pattern
from app.triage import triage_resolved_dir

PROFILE = {
    "classification": {
        "business_domains": [
            {"key": "juridico", "label": "Jurídico", "aliases": ["juridico", "contrato social"]},
            {"key": "operacoes", "label": "Operações", "aliases": ["operacoes", "sla"]},
        ],
        "document_types": [
            {"key": "contrato", "label": "Contrato", "aliases": ["contrato", "agreement"], "extensions": [], "folder": "contrato"},
            {"key": "relatorio", "label": "Relatório", "aliases": ["relatorio"], "extensions": [], "folder": "relatorio"},
        ],
    }
}


def _write_resolved(project_root: Path, doc_id: str, *, suggested_bd: str, final_bd: str,
                    suggested_dt: str = "contrato", final_dt: str = "contrato",
                    filename: str = "doc.txt", text: str = "") -> None:
    """Cria o JSON resolvido + o arquivo físico com o texto (o minerador extrai dele)."""
    doc_file = project_root / "files" / f"{doc_id}__{filename}"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text(text, encoding="utf-8")
    resolved = triage_resolved_dir(project_root)
    resolved.mkdir(parents=True, exist_ok=True)
    (resolved / f"{doc_id}.json").write_text(json.dumps({
        "doc_id": doc_id,
        "original_filename": filename,
        "suggested_business_domain": suggested_bd,
        "business_domain": final_bd,
        "suggested_document_type": suggested_dt,
        "document_type": final_dt,
        "final_path": str(doc_file),
    }), encoding="utf-8")


@pytest.fixture()
def project_root(tmp_path) -> Path:
    return tmp_path / "proj"


def test_termo_discriminativo_de_correcoes_e_proposto(project_root):
    # 2 correções para "juridico" com o termo "escritura" (bootstrap não conhecia);
    # 2 docs de "operacoes" SEM o termo dão o contraste
    _write_resolved(project_root, "d1", suggested_bd="operacoes", final_bd="juridico",
                    filename="a.txt", text="escritura publica de imovel lavrada em cartorio")
    _write_resolved(project_root, "d2", suggested_bd="operacoes", final_bd="juridico",
                    filename="b.txt", text="registro da escritura no tabeliao competente")
    _write_resolved(project_root, "d3", suggested_bd="operacoes", final_bd="operacoes",
                    filename="c.txt", text="indicadores mensais de atendimento e backlog")
    _write_resolved(project_root, "d4", suggested_bd="operacoes", final_bd="operacoes",
                    filename="d.txt", text="painel de chamados e disponibilidade")

    result = suggest_aliases(project_root, PROFILE)
    bd = [s for s in result["suggestions"] if s["kind"] == "business_domain"]
    assert bd and bd[0]["key"] == "juridico"
    terms = {t["term"]: t for t in bd[0]["terms"]}
    assert "escritura" in terms
    assert terms["escritura"]["support"] == 2
    assert terms["escritura"]["precision"] == 1.0
    # o termo proposto FUNCIONA no matching real do bootstrap
    assert _word_pattern("escritura").search("a escritura publica")
    assert result["corpus"]["corrected_total"] == 2


def test_termo_generico_morre_na_precisao_e_alias_existente_nao_reaparece(project_root):
    # "documento" aparece nas duas classes → precisão < 0.8; "contrato social" já é alias
    _write_resolved(project_root, "d1", suggested_bd="operacoes", final_bd="juridico",
                    filename="a.txt", text="documento de escritura contrato social firmado")
    _write_resolved(project_root, "d2", suggested_bd="operacoes", final_bd="juridico",
                    filename="b.txt", text="documento com escritura registrada contrato social")
    _write_resolved(project_root, "d3", suggested_bd="operacoes", final_bd="operacoes",
                    filename="c.txt", text="documento de indicadores operacionais")
    _write_resolved(project_root, "d4", suggested_bd="operacoes", final_bd="operacoes",
                    filename="d.txt", text="documento do painel de chamados")

    result = suggest_aliases(project_root, PROFILE)
    bd = [s for s in result["suggestions"] if s["kind"] == "business_domain"]
    assert bd
    terms = {t["term"] for t in bd[0]["terms"]}
    assert "documento" not in terms          # genérico: presente nas 2 classes
    assert "contrato social" not in terms    # já é alias
    assert "escritura" in terms


def test_colisao_com_lexico_de_tipos_nao_vira_alias_de_dominio(project_root):
    # "agreement" é alias do document_type contrato → bootstrap descartaria a colisão
    _write_resolved(project_root, "d1", suggested_bd="operacoes", final_bd="juridico",
                    filename="a.txt", text="master agreement celebrado entre as partes")
    _write_resolved(project_root, "d2", suggested_bd="operacoes", final_bd="juridico",
                    filename="b.txt", text="o agreement rege a prestacao contratada")
    _write_resolved(project_root, "d3", suggested_bd="operacoes", final_bd="operacoes",
                    filename="c.txt", text="indicadores de sla do periodo")
    _write_resolved(project_root, "d4", suggested_bd="operacoes", final_bd="operacoes",
                    filename="d.txt", text="relatorio de chamados abertos")

    result = suggest_aliases(project_root, PROFILE)
    bd = [s for s in result["suggestions"] if s["kind"] == "business_domain"]
    terms = {t["term"] for s in bd for t in s["terms"]}
    assert "agreement" not in terms


def test_dispensado_nao_volta_e_sem_contraste_nao_ha_sugestao(project_root):
    _write_resolved(project_root, "d1", suggested_bd="operacoes", final_bd="juridico",
                    filename="a.txt", text="escritura publica lavrada")
    _write_resolved(project_root, "d2", suggested_bd="operacoes", final_bd="juridico",
                    filename="b.txt", text="escritura registrada em cartorio")

    # todos os docs têm o MESMO rótulo final → sem contraste → nada proposto
    sem_contraste = suggest_aliases(project_root, PROFILE)
    assert sem_contraste["suggestions"] == []

    _write_resolved(project_root, "d3", suggested_bd="operacoes", final_bd="operacoes",
                    filename="c.txt", text="indicadores mensais")
    com_contraste = suggest_aliases(project_root, PROFILE)
    assert any(t["term"] == "escritura" for s in com_contraste["suggestions"] for t in s["terms"])

    dispensado = suggest_aliases(
        project_root, PROFILE, dismissed={"business_domain:juridico:escritura"}
    )
    terms = {t["term"] for s in dispensado["suggestions"] for t in s["terms"]}
    assert "escritura" not in terms


def test_unigrama_redundante_cede_ao_bigrama_mais_especifico(project_root):
    # "lavratura notarial" sempre juntos → o 2-grama fica, os 1-gramas de mesmo suporte saem
    _write_resolved(project_root, "d1", suggested_bd="operacoes", final_bd="juridico",
                    filename="a.txt", text="ato de lavratura notarial do imovel")
    _write_resolved(project_root, "d2", suggested_bd="operacoes", final_bd="juridico",
                    filename="b.txt", text="procedimento de lavratura notarial concluido")
    _write_resolved(project_root, "d3", suggested_bd="operacoes", final_bd="operacoes",
                    filename="c.txt", text="indicadores do periodo corrente")
    _write_resolved(project_root, "d4", suggested_bd="operacoes", final_bd="operacoes",
                    filename="d.txt", text="painel de atendimento consolidado")

    result = suggest_aliases(project_root, PROFILE)
    bd = [s for s in result["suggestions"] if s["kind"] == "business_domain"]
    terms = {t["term"] for t in bd[0]["terms"]}
    assert "lavratura notarial" in terms
    assert "lavratura" not in terms
    assert "notarial" not in terms
