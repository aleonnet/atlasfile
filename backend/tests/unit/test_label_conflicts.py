"""Testes do módulo de conflitos de rótulo (resolução via UI)."""
from __future__ import annotations

import json

import pytest

from app import label_conflicts
from app.evaluation_dataset import TrainingPoolRecord


@pytest.fixture()
def datasets_root(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    (root / "validation_set" / "files").mkdir(parents=True)
    (root / "training_pool" / "files").mkdir(parents=True)
    (root / "splits").mkdir(parents=True)
    (root / "validation_set" / "expected.json").write_text("[]\n", encoding="utf-8")
    (root / "training_pool" / "records.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("CLASSIFIER_DATASETS_ROOT", str(root))
    return root


def _write_reconciliation(root, entries):
    with (root / "label_reconciliation.jsonl").open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _pending_entry(sha: str) -> dict:
    return {
        "sha256": sha,
        "refs": ["proj/a.docx"],
        "canonical_business_domain": "",
        "canonical_document_type": "",
        "labeled_by": "pending_human",
        "llm_proposal": {"business_domain": "operacoes", "document_type": "plano", "confidence": 0.93, "justificativa": "x"},
        "sources": [
            {"source": "project_tree", "ref": "v070/a.docx", "business_domain": "operacoes", "document_type": "contrato", "authoritative": False},
            {"source": "project_tree", "ref": "v080/a.docx", "business_domain": "operacoes", "document_type": "apresentacao", "authoritative": False},
        ],
    }


def test_list_pending_conflicts(datasets_root):
    _write_reconciliation(datasets_root, [_pending_entry("sha-1"), {**_pending_entry("sha-2"), "labeled_by": "consensus"}])
    pending = label_conflicts.list_pending_conflicts()
    assert [p["sha256"] for p in pending] == ["sha-1"]


def test_resolve_marca_human_confirmed_llm_quando_igual_a_proposta(datasets_root):
    _write_reconciliation(datasets_root, [_pending_entry("sha-1")])
    result = label_conflicts.resolve_conflict("sha-1", "operacoes", "plano")
    assert result["labeled_by"] == "human_confirmed_llm"
    entries = label_conflicts.load_reconciliation()
    assert entries[0]["canonical_document_type"] == "plano"
    assert label_conflicts.list_pending_conflicts() == []


def test_resolve_propaga_para_training_e_derivados(datasets_root):
    _write_reconciliation(datasets_root, [_pending_entry("sha-1")])
    record = TrainingPoolRecord(
        doc_id="d1", project_id="p", original_filename="a.docx", path="x", business_domain="operacoes",
        document_type="contrato", decision="approved", sha256="sha-1",
    )
    (datasets_root / "training_pool" / "records.jsonl").write_text(record.model_dump_json() + "\n", encoding="utf-8")
    (datasets_root / "corpus.jsonl").write_text(
        json.dumps({"doc_id": "doc_0001", "sha256": "sha-1", "business_domain": "operacoes", "document_type": "contrato"}) + "\n",
        encoding="utf-8",
    )
    (datasets_root / "splits" / "train.jsonl").write_text(
        json.dumps({"doc_id": "doc_0001", "sha256": "sha-1", "business_domain": "operacoes", "document_type": "contrato"}) + "\n",
        encoding="utf-8",
    )

    result = label_conflicts.resolve_conflict("sha-1", "operacoes", "plano")
    assert result["updated_training"] == 1
    assert result["updated_derived"] == 2  # corpus + split train

    updated = json.loads((datasets_root / "training_pool" / "records.jsonl").read_text().splitlines()[0])
    assert updated["document_type"] == "plano"
    assert "reconciled:ui" in updated["notes"]
    corpus = json.loads((datasets_root / "corpus.jsonl").read_text().splitlines()[0])
    assert corpus["document_type"] == "plano"


def test_resolve_sha_inexistente_levanta_keyerror(datasets_root):
    _write_reconciliation(datasets_root, [])
    with pytest.raises(KeyError):
        label_conflicts.resolve_conflict("nao-existe", "a", "b")
