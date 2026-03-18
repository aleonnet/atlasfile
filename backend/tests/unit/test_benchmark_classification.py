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
    for family in ("sparse_logreg", "sparse_linear_svc"):
        summary = result["benchmarks"][family]["summary"]
        assert summary["role"] == "benchmark_candidate"
        assert summary["business_domain_accuracy"] == 1.0
        assert summary["business_domain_macro_f1"] == 1.0
        assert summary["business_domain_recall_by_class"]["juridico"] == 1.0
        assert summary["document_type_accuracy"] == 1.0
        assert summary["document_type_macro_f1"] == 1.0
        assert summary["document_type_recall_by_class"]["contrato"] == 1.0
        assert summary["exact_match_accuracy"] == 1.0


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
