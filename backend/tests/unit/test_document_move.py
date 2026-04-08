from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.profile_store import create_default_profile, save_profile


def _setup_project(tmp_path: Path, project_id: str = "proj") -> tuple[Path, dict]:
    """Create initialized project with a business domain and document type."""
    project_root = tmp_path / project_id
    project_root.mkdir()
    profile = create_default_profile(project_root=project_root, project_id=project_id, project_label="Proj")
    save_profile(project_root=project_root, profile=profile, updated_by="tests")
    profile_dict = profile.model_dump()

    # Ensure area structure exists
    areas_root = project_root / profile_dict["layout"]["areas_root"]
    areas_root.mkdir(parents=True, exist_ok=True)

    return project_root, profile_dict


@pytest.fixture()
def client():
    return TestClient(main_module.app)


def test_move_document_success(client: TestClient, tmp_path: Path):
    project_root, profile = _setup_project(tmp_path)

    # Get bd/dt keys from profile
    bds = profile["classification"]["business_domains"]
    dts = profile["classification"]["document_types"]
    assert len(bds) >= 2, "Need at least 2 business domains in default profile"
    assert len(dts) >= 1, "Need at least 1 document type in default profile"

    source_bd = bds[0]["key"]
    target_bd = bds[1]["key"]
    dt = dts[0]["key"]

    # Create source file in source bd area
    from app.area_resolver import resolve_classification_path
    from app.project_profile import load_project_profile

    loaded_profile = load_project_profile(project_root)
    source_path_rel = resolve_classification_path(
        project_root=project_root,
        profile=loaded_profile,
        business_domain=source_bd,
        document_type=dt,
        create_if_missing=True,
    )
    source_dir = project_root / source_path_rel
    source_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_dir / "test_doc.pdf"
    source_file.write_bytes(b"fake pdf content")

    # Index the document in OpenSearch mock
    doc_id = "test-doc-001"
    os_doc = {
        "_source": {
            "doc_id": doc_id,
            "project_id": "proj",
            "business_domain": source_bd,
            "document_type": dt,
            "path": str(source_file),
            "original_filename": "test_doc.pdf",
            "canonical_filename": "test_doc.pdf",
            "sha256": "abc123",
            "ingested_at": "2026-04-01T10:00:00Z",
            "confidence_score": 0.95,
            "entities": [],
            "topics": [],
        }
    }

    mock_os = MagicMock()
    mock_os.get.return_value = os_doc
    mock_os.index.return_value = {}

    with (
        patch.object(main_module.settings, "projects_root", str(tmp_path)),
        patch.object(main_module, "os_client", mock_os),
    ):
        resp = client.post(
            f"/api/documents/proj/{doc_id}/move",
            json={"target_business_domain": target_bd, "target_document_type": dt},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["old_business_domain"] == source_bd
    assert data["new_business_domain"] == target_bd
    assert data["old_path"] == str(source_file)
    assert data["new_path"] != str(source_file)
    # Source file should no longer exist at original location
    assert not source_file.exists()


def test_move_document_not_found(client: TestClient, tmp_path: Path):
    _setup_project(tmp_path)

    mock_os = MagicMock()
    mock_os.get.side_effect = Exception("not found")

    with (
        patch.object(main_module.settings, "projects_root", str(tmp_path)),
        patch.object(main_module, "os_client", mock_os),
    ):
        resp = client.post(
            "/api/documents/proj/nonexistent/move",
            json={"target_business_domain": "fiscal", "target_document_type": "contrato"},
        )

    assert resp.status_code == 404


def test_move_document_invalid_bd(client: TestClient, tmp_path: Path):
    project_root, profile = _setup_project(tmp_path)
    dts = profile["classification"]["document_types"]
    dt = dts[0]["key"]

    mock_os = MagicMock()
    mock_os.get.return_value = {
        "_source": {
            "doc_id": "doc-1",
            "project_id": "proj",
            "business_domain": "fiscal",
            "path": str(project_root / "somefile.pdf"),
            "original_filename": "somefile.pdf",
        }
    }
    # Create the file so path validation passes
    fake_file = project_root / "somefile.pdf"
    fake_file.write_bytes(b"content")

    with (
        patch.object(main_module.settings, "projects_root", str(tmp_path)),
        patch.object(main_module, "os_client", mock_os),
    ):
        resp = client.post(
            "/api/documents/proj/doc-1/move",
            json={"target_business_domain": "nonexistent_domain", "target_document_type": dt},
        )

    assert resp.status_code == 400


def test_build_corpus_last_label_wins(tmp_path: Path):
    """Verify _load_existing_labels returns the last record per SHA."""
    import scripts.build_corpus as bc
    import app.evaluation_dataset as eval_ds

    with patch.object(eval_ds, "classifier_datasets_root", return_value=tmp_path):
        eval_ds.ensure_dataset_scaffold()
        tp_path = eval_ds.training_pool_records_path()

        records = [
            json.dumps({"sha256": "same_sha", "business_domain": "first", "document_type": "dt1"}),
            json.dumps({"sha256": "same_sha", "business_domain": "second", "document_type": "dt2"}),
        ]
        tp_path.write_text("\n".join(records) + "\n", encoding="utf-8")

        labels = bc._load_existing_labels()
        assert labels["same_sha"]["business_domain"] == "second"
        assert labels["same_sha"]["document_type"] == "dt2"
