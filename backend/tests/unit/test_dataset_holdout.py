"""Hold-out operacional: roteador de decisões humanas, backfill e readiness."""
from __future__ import annotations

from pathlib import Path

import pytest

from app import dataset_holdout
from app.dataset_holdout import (
    backfill_validation_from_training_pool,
    dataset_readiness,
    route_labeled_document,
    should_hold_out,
)
from app.evaluation_dataset import (
    load_training_pool_records,
    load_validation_set,
    validation_set_files_dir,
)
from app.utils import sha256_file


@pytest.fixture()
def datasets_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CLASSIFIER_DATASETS_ROOT", str(tmp_path / "datasets"))
    docs = tmp_path / "docs"
    docs.mkdir()
    yield docs


def _make_doc(docs_dir: Path, name: str, content: str) -> Path:
    path = docs_dir / name
    path.write_text(content, encoding="utf-8")
    return path


def _route(path: Path, bd: str = "financeiro", dt: str = "contrato", **kw):
    return route_labeled_document(
        source_path=path,
        doc_id=f"doc-{path.stem}",
        project_id="proj",
        original_filename=path.name,
        business_domain=bd,
        document_type=dt,
        decision="approved",
        topics=[],
        entities=[],
        **kw,
    )


def test_should_hold_out_deterministic_and_toggleable():
    sha = "ab" * 32
    assert should_hold_out(sha, modulus=5) == should_hold_out(sha, modulus=5)
    assert should_hold_out(sha, modulus=0) is False
    assert should_hold_out("nao-hex", modulus=5) is False
    hits = sum(1 for i in range(1000) if should_hold_out(f"{i:064x}", modulus=5))
    assert 150 < hits < 250  # ~20%


def test_seed_rule_first_eligible_doc_goes_to_validation(datasets_root, monkeypatch):
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_min_train_per_class", 0)
    doc = _make_doc(datasets_root, "primeiro.txt", "conteudo unico 1")
    result = _route(doc)
    assert result["dataset_route"] == "validation"
    entries = load_validation_set()
    assert len(entries) == 1 and entries[0].is_labeled()
    assert entries[0].business_domain == "financeiro"
    assert (validation_set_files_dir() / entries[0].file).exists()
    assert load_training_pool_records() == []


def test_warmup_routes_first_n_per_class_to_training(datasets_root, monkeypatch):
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_min_train_per_class", 3)
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_modulus", 1)  # tudo iria p/ validação
    # Warm-up vence a semente: os 3 primeiros da classe vão para treino mesmo com modulus=1
    for i in range(3):
        doc = _make_doc(datasets_root, f"warm{i}.txt", f"conteudo warm {i}")
        assert _route(doc)["dataset_route"] == "training"
    # O 4º (classe aquecida, validação vazia) → semente → validação
    doc4 = _make_doc(datasets_root, "warm3.txt", "conteudo warm 3")
    assert _route(doc4)["dataset_route"] == "validation"


def test_sha_already_in_training_stays_training(datasets_root, monkeypatch):
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_min_train_per_class", 0)
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_modulus", 1)
    seed = _make_doc(datasets_root, "seed.txt", "seed")
    _route(seed)  # validação (semente)
    doc = _make_doc(datasets_root, "treino.txt", "vai para treino? nao: modulus=1...")
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_modulus", 0)  # desliga → treino
    assert _route(doc)["dataset_route"] == "training"
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_modulus", 1)  # religou
    same_content = _make_doc(datasets_root, "copia_treino.txt", "vai para treino? nao: modulus=1...")
    result = _route(same_content)
    assert result["dataset_route"] == "training"  # mesmo SHA já treinado nunca migra


def test_human_decision_updates_validation_labels(datasets_root, monkeypatch):
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_min_train_per_class", 0)
    doc = _make_doc(datasets_root, "valida.txt", "conteudo v")
    assert _route(doc)["dataset_route"] == "validation"
    # Humano corrige depois (ex.: move) — mesma SHA → entry atualizada, sem ir ao treino
    copy = _make_doc(datasets_root, "valida_copy.txt", "conteudo v")
    result = _route(copy, bd="juridico", dt="parecer")
    assert result["dataset_route"] == "validation_updated"
    entries = load_validation_set()
    assert entries[0].business_domain == "juridico"
    assert entries[0].document_type == "parecer"
    assert load_training_pool_records() == []


def _fill_training(datasets_root, monkeypatch, n_por_classe: dict[str, int]):
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_modulus", 0)  # tudo treino
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_min_train_per_class", 0)
    i = 0
    for bd, n in n_por_classe.items():
        for k in range(n):
            doc = _make_doc(datasets_root, f"{bd}_{k}.txt", f"conteudo {bd} {k} {i}")
            _route(doc, bd=bd, dt=f"tipo_{bd}")
            i += 1


def test_backfill_stratified_and_idempotent(datasets_root, monkeypatch):
    _fill_training(datasets_root, monkeypatch, {"financeiro": 10, "juridico": 5, "raro": 2})
    preview = backfill_validation_from_training_pool(dry_run=True)
    assert preview["dry_run"] is True
    assert preview["moved"] > 0
    assert "raro" not in preview["per_class"]  # classes < 3 não cedem
    assert load_validation_set() == []  # dry_run não muta

    result = backfill_validation_from_training_pool()
    assert result["moved"] == preview["moved"]
    assert result["validation_labeled_total"] == result["moved"]
    # treino não pode ficar abaixo de 2 por classe cedente
    remaining = load_training_pool_records()
    from collections import Counter

    bd_counts = Counter(r.business_domain for r in remaining)
    assert bd_counts["financeiro"] >= 2 and bd_counts["juridico"] >= 2

    # Idempotência: segunda chamada é no-op
    again = backfill_validation_from_training_pool()
    assert again["moved"] == 0


def test_readiness_blockers_and_suggestions(datasets_root, monkeypatch):
    ready0 = dataset_readiness()
    assert ready0["cycle_ready"] is False
    assert ready0["blockers"][0]["code"] == "validation_empty"
    assert all(s["code"] != "backfill_available" for s in ready0["suggestions"])  # pool vazio

    _fill_training(datasets_root, monkeypatch, {"financeiro": 10, "juridico": 5})
    ready1 = dataset_readiness()
    assert ready1["cycle_ready"] is False
    codes = {s["code"] for s in ready1["suggestions"]}
    assert "backfill_available" in codes
    assert "sparse_gate_not_met" in codes  # 15 < 100

    backfill_validation_from_training_pool()
    ready2 = dataset_readiness()
    assert ready2["cycle_ready"] is True
    assert ready2["blockers"] == []
    assert ready2["validation"]["labeled"] > 0
