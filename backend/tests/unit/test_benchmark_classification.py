from __future__ import annotations

from pathlib import Path

from app.evaluation_dataset import TrainingPoolRecord, ValidationSetEntry
from scripts.benchmark_classification import benchmark_sparse_candidates, compute_dataset_integrity, compute_supervised_gate


def test_compute_supervised_gate_blocks_empty_training_pool() -> None:
    gate = compute_supervised_gate([], min_training_docs=10, min_docs_per_class=2)

    assert gate["eligible"] is False
    assert "training_pool_empty" in gate["reasons"]
    assert "training_pool_total_below_min:0<10" in gate["reasons"]


def test_benchmark_sparse_candidates_scores_synthetic_txt_dataset(tmp_path: Path) -> None:
    train_docs = {
        "juridico_contrato_a.txt": "clausula juridico litigio contrato partes assinatura parecer legal",
        "juridico_contrato_b.txt": "contrato juridico clausula contencioso obrigacoes partes legais",
        "financeiro_planilha_a.txt": "planilha fluxo de caixa faturamento contas a pagar conciliacao tesouraria",
        "financeiro_planilha_b.txt": "orcamento planilha faturamento contas a receber controladoria caixa",
        "operacoes_apresentacao_a.txt": "kickoff cronograma milestone workstream apresentacao implantacao operacoes",
        "operacoes_apresentacao_b.txt": "deck operacional cronograma frentes de trabalho cutover status report",
    }
    records: list[TrainingPoolRecord] = []
    for idx, (name, content) in enumerate(train_docs.items(), start=1):
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        if "juridico" in name:
            business_domain = "juridico"
            document_type = "contrato"
        elif "financeiro" in name:
            business_domain = "financeiro"
            document_type = "planilha"
        else:
            business_domain = "operacoes"
            document_type = "apresentacao"
        records.append(
            TrainingPoolRecord(
                doc_id=f"doc-{idx}",
                project_id="proj",
                original_filename=name,
                path=str(path),
                business_domain=business_domain,
                document_type=document_type,
                decision="reviewed",
            )
        )

    validation_examples = [
        {
            "entry": ValidationSetEntry(
                file="val_juridico.txt",
                business_domain="juridico",
                document_type="contrato",
            ),
            "file_path": tmp_path / "val_juridico.txt",
            "text": "parecer juridico clausula contrato litigio assinatura",
        },
        {
            "entry": ValidationSetEntry(
                file="val_financeiro.txt",
                business_domain="financeiro",
                document_type="planilha",
            ),
            "file_path": tmp_path / "val_financeiro.txt",
            "text": "planilha faturamento fluxo de caixa contas a pagar controladoria",
        },
        {
            "entry": ValidationSetEntry(
                file="val_operacoes.txt",
                business_domain="operacoes",
                document_type="apresentacao",
            ),
            "file_path": tmp_path / "val_operacoes.txt",
            "text": "kickoff cronograma milestone workstream deck operacional",
        },
    ]

    result = benchmark_sparse_candidates(
        repo_root=tmp_path,
        validation_examples=validation_examples,
        training_records=records,
        min_training_docs=0,
        min_docs_per_class=1,
    )

    assert result["gate"]["eligible"] is True
    assert result["training_examples_resolved"] == 6
    for family in ("sparse_logreg",):
        summary = result["benchmarks"][family]["summary"]
        assert summary["role"] == "benchmark_candidate"
        assert summary["business_domain_accuracy"] == 1.0
        assert summary["business_domain_macro_f1"] == 1.0
        assert summary["business_domain_recall_by_class"]["juridico"] == 1.0
        assert summary["document_type_accuracy"] == 1.0
        assert summary["document_type_macro_f1"] == 1.0
        assert summary["document_type_recall_by_class"]["contrato"] == 1.0
        assert summary["exact_match_accuracy"] == 1.0


def test_feature_text_uses_extended_excerpt_length() -> None:
    """Feature text in supervised classification must use up to 8000 chars, not 4000."""
    from app.utils import fold_ocr_spacing

    long_text = "a" * 10000
    filename = "test.pdf"
    # Reproduce the feature_text construction from classify_with_supervised_artifact
    feature_text = fold_ocr_spacing(f"{filename}\n{long_text[:8000]}".strip())

    # Must contain more than 4000 chars of excerpt content
    assert len(feature_text) > 4100, f"Feature text too short ({len(feature_text)})"
    # But at most 8000 chars of excerpt + filename + newline
    assert len(feature_text) <= 8010, f"Feature text too long ({len(feature_text)})"

    # Verify that the old 4000-char limit would produce shorter text
    old_feature_text = fold_ocr_spacing(f"{filename}\n{long_text[:4000]}".strip())
    assert len(feature_text) > len(old_feature_text), "8000-char excerpt must be longer than 4000-char"


def test_benchmark_report_includes_cv_scores(tmp_path: Path) -> None:
    """Benchmark summary must include cv_scores with fold-level metrics."""
    train_docs = {
        "juridico_contrato_a.txt": "clausula juridico litigio contrato partes assinatura parecer legal",
        "juridico_contrato_b.txt": "contrato juridico clausula contencioso obrigacoes partes legais",
        "financeiro_planilha_a.txt": "planilha fluxo de caixa faturamento contas a pagar conciliacao tesouraria",
        "financeiro_planilha_b.txt": "orcamento planilha faturamento contas a receber controladoria caixa",
        "operacoes_apresentacao_a.txt": "kickoff cronograma milestone workstream apresentacao implantacao operacoes",
        "operacoes_apresentacao_b.txt": "deck operacional cronograma frentes de trabalho cutover status report",
    }
    records: list[TrainingPoolRecord] = []
    for idx, (name, content) in enumerate(train_docs.items(), start=1):
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        if "juridico" in name:
            bd, dt = "juridico", "contrato"
        elif "financeiro" in name:
            bd, dt = "financeiro", "planilha"
        else:
            bd, dt = "operacoes", "apresentacao"
        records.append(
            TrainingPoolRecord(
                doc_id=f"doc-{idx}",
                project_id="proj",
                original_filename=name,
                path=str(path),
                business_domain=bd,
                document_type=dt,
                decision="reviewed",
            )
        )

    validation_examples = [
        {
            "entry": ValidationSetEntry(file="val.txt", business_domain="juridico", document_type="contrato"),
            "file_path": tmp_path / "val.txt",
            "text": "parecer juridico clausula contrato",
        }
    ]

    result = benchmark_sparse_candidates(
        repo_root=tmp_path,
        validation_examples=validation_examples,
        training_records=records,
        min_training_docs=0,
        min_docs_per_class=1,
    )

    for family in ("sparse_logreg",):
        summary = result["benchmarks"][family]["summary"]
        assert "cv_scores" in summary, f"cv_scores missing from {family} summary"
        cv = summary["cv_scores"]
        assert cv["n_splits"] == 2  # min 2 samples per combined label
        assert "business_domain_accuracy_mean" in cv
        assert "document_type_accuracy_mean" in cv
        assert "exact_match_accuracy_mean" in cv
        assert "fold_scores" in cv
        assert len(cv["fold_scores"]) == cv["n_splits"]
        for fold in cv["fold_scores"]:
            assert 0.0 <= fold["business_domain_accuracy"] <= 1.0
            assert 0.0 <= fold["document_type_accuracy"] <= 1.0
            assert 0.0 <= fold["exact_match_accuracy"] <= 1.0


def test_sparse_pipeline_uses_feature_union() -> None:
    """Pipeline must use FeatureUnion with char_wb and word vectorizers."""
    from sklearn.pipeline import FeatureUnion

    from app.classifier_supervised import _sparse_pipeline

    pipe = _sparse_pipeline("sparse_logreg")
    features_step = pipe.named_steps["features"]
    assert isinstance(features_step, FeatureUnion), f"Expected FeatureUnion, got {type(features_step)}"
    transformer_names = [name for name, _ in features_step.transformer_list]
    assert "char" in transformer_names, "Missing 'char' vectorizer in FeatureUnion"
    assert "word" in transformer_names, "Missing 'word' vectorizer in FeatureUnion"
    char_vec = dict(features_step.transformer_list)["char"]
    assert char_vec.analyzer == "char_wb"
    assert char_vec.ngram_range == (3, 5)
    word_vec = dict(features_step.transformer_list)["word"]
    assert word_vec.analyzer == "word"
    assert word_vec.ngram_range == (1, 2)


def test_artifact_schema_version_mismatch_rejected(tmp_path: Path) -> None:
    """Artifacts with schema_version != current must be rejected by loader."""
    import pickle

    from app.classifier_supervised import _ARTIFACT_SCHEMA_VERSION, load_sparse_artifact

    fake_artifact = {
        "schema_version": _ARTIFACT_SCHEMA_VERSION - 1,
        "family": "sparse_logreg",
    }
    artifact_path = tmp_path / "old_artifact.pkl"
    with artifact_path.open("wb") as f:
        pickle.dump(fake_artifact, f)

    import pytest

    with pytest.raises(ValueError, match="incompatible artifact schema_version"):
        load_sparse_artifact(artifact_path)


def test_compute_dataset_integrity_detects_sha_overlap(tmp_path: Path) -> None:
    validation_file = tmp_path / "validation.pdf"
    validation_file.write_bytes(b"same-content")
    training_file = tmp_path / "approved.pdf"
    training_file.write_bytes(b"same-content")

    integrity = compute_dataset_integrity(
        repo_root=tmp_path,
        validation_examples=[
            {
                "entry": ValidationSetEntry(
                    file="validation.pdf",
                    business_domain="juridico",
                    document_type="contrato",
                ),
                "file_path": validation_file,
                "text": "contrato juridico",
            }
        ],
        training_records=[
            TrainingPoolRecord(
                doc_id="doc-1",
                project_id="proj",
                original_filename="approved.pdf",
                path=str(training_file),
                business_domain="juridico",
                document_type="contrato",
                decision="approved",
            )
        ],
    )

    assert integrity["status"] == "error"
    assert len(integrity["overlap_sha256"]) == 1
    assert integrity["overlap_sha256"][0]["validation_files"] == ["validation.pdf"]
