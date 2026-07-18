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


def test_first_doc_goes_to_training_second_seeds_validation(datasets_root, monkeypatch):
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_min_train_per_class", 0)
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_modulus", 5)
    # conteúdo determinístico FORA do módulo (senão o 1º doc poderia cair nos ~20%)
    i = 0
    while True:
        first = _make_doc(datasets_root, f"primeiro{i}.txt", f"conteudo unico {i}")
        if not should_hold_out(sha256_file(first), modulus=5):
            break
        first.unlink()
        i += 1
    assert _route(first)["dataset_route"] == "training"  # semente exige treino não-vazio
    second = _make_doc(datasets_root, "segundo.txt", "conteudo unico 2")
    result = _route(second)
    assert result["dataset_route"] == "validation"
    entries = load_validation_set()
    assert len(entries) == 1 and entries[0].is_labeled()
    assert entries[0].business_domain == "financeiro"
    assert (validation_set_files_dir() / entries[0].file).exists()
    assert len(load_training_pool_records()) == 1


def test_seed_fires_on_second_human_decision_before_warmup(datasets_root, monkeypatch):
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_min_train_per_class", 3)
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_modulus", 5)
    # 1ª decisão: treino (semente exige treino não-vazio para ter o que comparar)
    doc1 = _make_doc(datasets_root, "d1.txt", "conteudo 1")
    assert _route(doc1)["dataset_route"] == "training"
    # 2ª decisão: SEMENTE → validação, mesmo com warm-up não satisfeito
    # (coleções pequenas não podem esperar 3 por classe — sparse exige 100 docs anyway)
    doc2 = _make_doc(datasets_root, "d2.txt", "conteudo 2", )
    assert _route(doc2, bd="juridico", dt="contrato")["dataset_route"] == "validation"
    # 3ª decisão em diante: warm-up volta a valer (classes < 3 → treino)
    doc3 = _make_doc(datasets_root, "d3.txt", "conteudo 3")
    assert _route(doc3)["dataset_route"] == "training"


def test_warmup_holds_after_seed_until_class_warm(datasets_root, monkeypatch):
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_min_train_per_class", 3)
    monkeypatch.setattr(dataset_holdout.settings, "classifier_holdout_modulus", 1)  # pós warm-up, tudo validação
    docs = [_make_doc(datasets_root, f"w{i}.txt", f"conteudo w {i}") for i in range(6)]
    routes = [_route(d)["dataset_route"] for d in docs]
    # d0 treino; d1 semente→validação; d2-d4 warm-up→treino (classe chega a 3+... d2,d3 completam 3);
    assert routes[0] == "training"
    assert routes[1] == "validation"
    assert routes[2] == "training" and routes[3] == "training"
    # classe aquecida (3 no treino) + modulus=1 → validação
    assert routes[4] == "validation"


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
    first = _make_doc(datasets_root, "primeiro.txt", "conteudo primeiro")
    assert _route(first)["dataset_route"] == "training"
    doc = _make_doc(datasets_root, "valida.txt", "conteudo v")
    assert _route(doc)["dataset_route"] == "validation"
    # Humano corrige depois (ex.: move) — mesma SHA → entry atualizada, sem ir ao treino
    copy = _make_doc(datasets_root, "valida_copy.txt", "conteudo v")
    result = _route(copy, bd="juridico", dt="parecer")
    assert result["dataset_route"] == "validation_updated"
    entries = load_validation_set()
    assert entries[0].business_domain == "juridico"
    assert entries[0].document_type == "parecer"
    # a decisão sobre o doc em validação não gera registro de treino novo
    assert len(load_training_pool_records()) == 1


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


def test_readiness_blockers_and_auto_backfill(datasets_root, monkeypatch):
    # Vazio total: bloqueado de verdade (nada a auto-curar)
    ready0 = dataset_readiness()
    assert ready0["cycle_ready"] is False
    assert ready0["blockers"][0]["code"] == "validation_empty"

    # Pool com dados e validação vazia: NÃO bloqueia — o ciclo auto-reserva ao rodar
    _fill_training(datasets_root, monkeypatch, {"financeiro": 10, "juridico": 5})
    ready1 = dataset_readiness()
    assert ready1["cycle_ready"] is True
    assert ready1["blockers"] == []
    codes = {s["code"] for s in ready1["suggestions"]}
    assert "auto_backfill_on_run" in codes
    assert "sparse_gate_not_met" in codes  # 15 < 100

    backfill_validation_from_training_pool()
    ready2 = dataset_readiness()
    assert ready2["cycle_ready"] is True
    assert ready2["validation"]["labeled"] > 0
    assert all(s["code"] != "auto_backfill_on_run" for s in ready2["suggestions"])


def test_readiness_tiny_stuck_pool_is_auto_fixable(datasets_root, monkeypatch):
    # O caso real do usuário: 3 docs de classes diferentes, validação vazia —
    # o fallback do backfill torna o ciclo auto-curável (sem clique extra)
    _fill_training(datasets_root, monkeypatch, {"a": 1, "b": 1, "c": 1})
    ready = dataset_readiness()
    assert ready["cycle_ready"] is True
    assert ready["blockers"] == []
    auto = [s for s in ready["suggestions"] if s["code"] == "auto_backfill_on_run"]
    assert auto and auto[0]["params"]["would_move"] == 1


def test_backfill_emergency_fallback_for_tiny_pools(datasets_root, monkeypatch):
    # Instalação presa: classes pequenas (1 cada), validação vazia — o fallback
    # move exatamente 1 registro para destravar o primeiro ciclo.
    _fill_training(datasets_root, monkeypatch, {"a": 1, "b": 1, "c": 1})
    preview = backfill_validation_from_training_pool(dry_run=True)
    assert preview["moved"] == 1
    result = backfill_validation_from_training_pool()
    assert result["moved"] == 1
    assert result["validation_labeled_total"] == 1
    assert result["training_total"] == 2
    # idempotente: validação deixou de estar vazia → fallback não repete
    again = backfill_validation_from_training_pool()
    assert again["moved"] == 0


def test_benchmark_llm_uses_transient_api_key(monkeypatch):
    """A key do navegador (header) deve valer para o benchmark llm; sem ela e sem env → skip."""
    from app.classifier_cycle import benchmark_llm_candidate

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    skipped = benchmark_llm_candidate(profile={}, validation_examples=[])
    assert skipped["summary"]["skipped"] is True
    assert "llm_api_key_not_configured" in skipped["summary"]["skip_reason"]

    with_key = benchmark_llm_candidate(profile={}, validation_examples=[], api_key="sk-transiente")
    assert with_key["summary"].get("skipped") is not True
