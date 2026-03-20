from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.ingestion import process_inbox_file
from app.profile_store import create_default_profile, save_profile
from app.project_profile import load_project_profile


@patch("app.ingestion.ensure_project_structure")
@patch("app.ingestion.sha256_file", return_value="runtime_sha")
@patch("app.ingestion._find_original_in_triage", return_value=None)
@patch("app.ingestion._find_original_in_search_index", return_value=None)
@patch("app.ingestion.classify_with_operational_mode")
@patch("app.ingestion.read_text_excerpt", return_value="excerpt text")
@patch("app.ingestion.index_document")
@patch("app.ingestion._append_index_md")
def test_load_project_profile_preserves_naming_for_ingestion(
    mock_append: MagicMock,
    mock_index: MagicMock,
    mock_excerpt: MagicMock,
    mock_classify: MagicMock,
    mock_find_index: MagicMock,
    mock_find_triage: MagicMock,
    mock_sha: MagicMock,
    mock_ensure: MagicMock,
    tmp_path: Path,
) -> None:
    profile = create_default_profile(
        project_root=tmp_path,
        project_id="proj_runtime",
        project_label="Projeto Runtime",
    )
    profile.naming.canonical_pattern = "{date}__{project}__{business_domain}__{original_name}"
    save_profile(project_root=tmp_path, profile=profile, updated_by="tests")

    runtime = load_project_profile(tmp_path)

    assert runtime["naming"]["canonical_pattern"] == "{date}__{project}__{business_domain}__{original_name}"
    assert runtime["naming"]["date_format"] == "%Y%m%d"

    mock_classify.return_value = {
        "business_domain": "juridico",
        "document_type": "contrato",
        "document_type_confidence": 0.96,
        "business_domain_confidence": 0.92,
        "confidence": 0.92,
        "reason": "alias_match",
        "top_candidates": [{"business_domain": "juridico", "score": 0.92}],
    }

    inbox_file = tmp_path / "_INBOX_DROP" / "Contrato_Runtime.txt"
    inbox_file.parent.mkdir(parents=True, exist_ok=True)
    inbox_file.write_text("Contrato de prestacao de servicos juridicos.", encoding="utf-8")
    (tmp_path / "02_AREAS" / "juridico" / "contrato").mkdir(parents=True, exist_ok=True)

    result = process_inbox_file(
        client=MagicMock(),
        project_root=tmp_path,
        profile=runtime,
        inbox_file=inbox_file,
    )

    assert result["naming_pattern"] == "{date}__{project}__{business_domain}__{original_name}"
    assert "__juridico__" in result["canonical_filename"]
    mock_index.assert_called_once()
    mock_append.assert_called_once()
