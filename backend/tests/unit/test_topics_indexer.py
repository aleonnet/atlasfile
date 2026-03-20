"""Unit tests for controlled topics and profile-aware indexing enrichment."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.indexer import _enrich_search_fields
from app.topics import match_topics, resolve_topics_path


def test_match_topics_uses_custom_surface_forms(tmp_path: Path) -> None:
    topics_file = tmp_path / "topics.yaml"
    topics_file.write_text(
        """
max_topics_per_document: 5
topics:
  - key: passivo_juridico
    surface_forms: ["contingencia", "processo judicial"]
  - key: financeiro_caixa
    surface_forms: ["fluxo de caixa"]
        """.strip(),
        encoding="utf-8",
    )
    profile = {"indexing": {"topics_path": str(topics_file)}}

    topics, source = match_topics(
        text="Existe contingencia relevante no processo judicial.",
        business_domain="juridica",
        profile=profile,
    )
    assert source == "surface_form_match"
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
        "business_domain": "juridica",
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
            "business_domain": "juridica",
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
            "business_domain": "juridica",
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
            "business_domain": "juridica",
        },
        profile=None,
    )

    assert html_out["doc_kind"] == "html"
    assert msg_out["doc_kind"] == "msg"
    assert zip_out["doc_kind"] == "archive_listing"


def test_enrich_search_fields_adds_ocr_folded_variants(tmp_path: Path) -> None:
    f = tmp_path / "ocr.txt"
    f.write_text("c o n t r a t o de prestação", encoding="utf-8")
    out = _enrich_search_fields(
        {
            "doc_id": "ocr1",
            "project_id": "p1",
            "title": "C O N T R A T O",
            "original_filename": "C O N T R A T O.pdf",
            "canonical_filename": "C O N T R A T O.pdf",
            "path": str(f),
            "business_domain": "juridica",
        },
        profile=None,
    )

    assert out["title_ocr_folded"] == "contrato"
    assert out["original_filename_ocr_folded"] == "contrato.pdf"
    assert out["canonical_filename_ocr_folded"] == "contrato.pdf"
    assert out["content_chunks"]
    assert out["content_chunks"][0]["text_ocr_folded"].startswith("contrato de prestacao")


def test_topics_config_yaml_is_valid_and_has_expected_structure() -> None:
    import yaml

    repo_root = Path(__file__).resolve().parents[3]
    config_path = repo_root / "config" / "topics_v1.yaml"
    assert config_path.exists(), f"Canonical topics file missing: {config_path}"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "topics" in data
    assert isinstance(data["topics"], list)
    assert len(data["topics"]) > 0
    first = data["topics"][0]
    assert "key" in first
    assert "surface_forms" in first or "synonyms" in first


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
    for text, business_domain, expected in cases:
        topics, source = match_topics(text=text, business_domain=business_domain, profile=profile)
        assert source == "surface_form_match"
        assert expected in topics


def test_default_template_subfunction_topics_exist_in_topics_catalog() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    template_path = repo_root / "config" / "templates" / "default.json"
    topics_path = repo_root / "config" / "topics_v1.yaml"

    template = json.loads(template_path.read_text(encoding="utf-8"))

    import yaml

    topics_cfg = yaml.safe_load(topics_path.read_text(encoding="utf-8")) or {}
    topic_keys = {
        str(topic.get("key", "")).strip()
        for topic in (topics_cfg.get("topics") or [])
        if isinstance(topic, dict) and str(topic.get("key", "")).strip()
    }

    referenced = set()
    for domain in ((template.get("classification") or {}).get("business_domains") or []):
        referenced.update(str(key).strip() for key in (domain.get("subfunction_topics") or []) if str(key).strip())

    assert referenced
    assert referenced.issubset(topic_keys), f"Missing topic keys: {sorted(referenced - topic_keys)}"

