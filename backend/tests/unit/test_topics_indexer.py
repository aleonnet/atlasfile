"""Unit tests for controlled topics and profile-aware indexing enrichment."""
from __future__ import annotations

import zipfile
from pathlib import Path

from app.indexer import _enrich_search_fields
from app.topics import match_topics, resolve_topics_path


def test_match_topics_uses_custom_topics_path_and_area_bias(tmp_path: Path) -> None:
    topics_file = tmp_path / "topics.yaml"
    topics_file.write_text(
        """
max_topics_per_document: 5
topics:
  - key: passivo_juridico
    synonyms: ["contingencia", "processo judicial"]
    area_bias: ["juridica"]
  - key: financeiro_caixa
    synonyms: ["fluxo de caixa"]
    area_bias: ["financeiro"]
        """.strip(),
        encoding="utf-8",
    )
    profile = {"indexing": {"topics_path": str(topics_file)}}

    topics, source = match_topics(
        text="Existe contingencia relevante no processo judicial.",
        area_key="juridica",
        profile=profile,
    )
    assert source == "synonym_match"
    assert topics
    assert topics[0] == "passivo_juridico"


def test_enrich_search_fields_preserves_llm_topics_source(tmp_path: Path) -> None:
    f = tmp_path / "memo.txt"
    f.write_text("texto base para indexacao", encoding="utf-8")
    payload = {
        "doc_id": "d1",
        "project_id": "p1",
        "title": "Memo",
        "original_filename": "memo.txt",
        "canonical_filename": "memo.txt",
        "path": str(f),
        "area_key": "juridica",
        "topics": ["tema_llm"],
        "topics_source": "llm_policy",
    }
    out = _enrich_search_fields(payload, profile=None)
    assert out["topics"] == ["tema_llm"]
    assert out["topics_source"] == "llm_policy"


def test_enrich_search_fields_derives_doc_kind_for_new_formats(tmp_path: Path) -> None:
    html_path = tmp_path / "doc.html"
    html_path.write_text("<html><body>conteudo</body></html>", encoding="utf-8")
    msg_path = tmp_path / "mail.msg"
    msg_path.write_bytes(b"fake-msg")
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("a.txt", "x")

    html_out = _enrich_search_fields(
        {
            "doc_id": "h1",
            "project_id": "p1",
            "title": "HTML",
            "original_filename": "doc.html",
            "canonical_filename": "doc.html",
            "path": str(html_path),
            "area_key": "juridica",
        },
        profile=None,
    )
    msg_out = _enrich_search_fields(
        {
            "doc_id": "m1",
            "project_id": "p1",
            "title": "MSG",
            "original_filename": "mail.msg",
            "canonical_filename": "mail.msg",
            "path": str(msg_path),
            "area_key": "juridica",
        },
        profile=None,
    )
    zip_out = _enrich_search_fields(
        {
            "doc_id": "z1",
            "project_id": "p1",
            "title": "ZIP",
            "original_filename": "bundle.zip",
            "canonical_filename": "bundle.zip",
            "path": str(zip_path),
            "area_key": "juridica",
        },
        profile=None,
    )

    assert html_out["doc_kind"] == "html"
    assert msg_out["doc_kind"] == "msg"
    assert zip_out["doc_kind"] == "archive_listing"


def test_topics_config_is_exact_copy_of_plan_source() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    config_path = repo_root / "config" / "topics_v1.yaml"
    plan_path = repo_root / "docs" / "plano_profile" / "topics_v1.yaml"
    assert config_path.read_text(encoding="utf-8") == plan_path.read_text(encoding="utf-8")


def test_topics_default_path_points_to_config_copy() -> None:
    path = resolve_topics_path(profile=None)
    assert path.as_posix().endswith("/config/topics_v1.yaml")


def test_semantic_topics_regression_with_official_dictionary() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    profile = {"indexing": {"topics_path": str(repo_root / "config" / "topics_v1.yaml")}}
    cases = [
        ("Documento com assinatura no DocuSign e envelope assinado.", "juridica", "docusign"),
        ("Relatorio com fluxo de caixa e tesouraria mensal.", "financeiro", "fluxo_caixa"),
        ("Acordo de transitional services para fase pos-closing.", "processos_tsa", "tsa"),
        ("Organograma com headcount e diretoria executiva.", "pessoas", "estrutura_organizacional"),
        ("Processo de recuperação judicial com assembleia de credores.", "juridica", "falencia_rj"),
    ]
    for text, area_key, expected in cases:
        topics, source = match_topics(text=text, area_key=area_key, profile=profile)
        assert source == "synonym_match"
        assert expected in topics

