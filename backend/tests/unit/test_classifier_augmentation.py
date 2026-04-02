from __future__ import annotations

from app.classifier_augmentation import (
    analyze_training_gaps,
    build_synthetic_prompt,
    build_synthetic_record,
    compute_augmentation_plan,
)
from app.evaluation_dataset import TrainingPoolRecord


def _make_record(business_domain: str, document_type: str) -> TrainingPoolRecord:
    return TrainingPoolRecord(
        doc_id="doc-1",
        project_id="proj",
        original_filename="file.pdf",
        path="/tmp/file.pdf",
        business_domain=business_domain,
        document_type=document_type,
        decision="approved",
    )


def _make_profile(domains: list[str], doc_types: list[str]) -> dict:
    return {
        "classification": {
            "business_domains": [
                {"key": d, "label": d.title(), "aliases": [d], "primary_scope": f"Scope {d}", "subfunction_topics": []}
                for d in domains
            ],
            "document_types": [
                {"key": t, "label": t.title(), "aliases": [t]}
                for t in doc_types
            ],
        }
    }


def test_analyze_training_gaps_detects_missing_classes() -> None:
    records = [_make_record("juridico", "contrato")] * 10
    profile = _make_profile(["juridico", "financeiro"], ["contrato", "planilha"])

    gaps = analyze_training_gaps(training_records=records, profile=profile, min_per_class=8)

    assert gaps["total_records"] == 10
    assert len(gaps["domain_gaps"]) == 1
    assert gaps["domain_gaps"][0]["business_domain"] == "financeiro"
    assert gaps["domain_gaps"][0]["deficit"] == 8
    assert len(gaps["doc_type_gaps"]) == 1
    assert gaps["doc_type_gaps"][0]["document_type"] == "planilha"
    assert gaps["doc_type_gaps"][0]["deficit"] == 8


def test_analyze_training_gaps_no_gaps_when_balanced() -> None:
    records = (
        [_make_record("juridico", "contrato")] * 10
        + [_make_record("financeiro", "planilha")] * 10
    )
    profile = _make_profile(["juridico", "financeiro"], ["contrato", "planilha"])

    gaps = analyze_training_gaps(training_records=records, profile=profile, min_per_class=8)

    assert gaps["domain_gaps"] == []
    assert gaps["doc_type_gaps"] == []


def test_compute_augmentation_plan_covers_gaps() -> None:
    records = [_make_record("juridico", "contrato")] * 10
    profile = _make_profile(["juridico", "financeiro"], ["contrato", "planilha"])
    gaps = analyze_training_gaps(training_records=records, profile=profile, min_per_class=8)

    plan = compute_augmentation_plan(
        gaps=gaps,
        profile=profile,
        min_synthetic_per_class=8,
        max_synthetic_per_class=20,
    )

    assert len(plan) > 0
    domains_in_plan = {item["business_domain"] for item in plan}
    doc_types_in_plan = {item["document_type"] for item in plan}
    assert "financeiro" in domains_in_plan
    assert "planilha" in doc_types_in_plan
    for item in plan:
        assert item["count"] > 0
        assert item["count"] <= 20


def test_build_synthetic_prompt_includes_key_info() -> None:
    prompt = build_synthetic_prompt(
        business_domain="financeiro",
        document_type="planilha",
        domain_aliases=["contabilidade", "tesouraria"],
        domain_scope="FP&A, controladoria, tesouraria",
        domain_topics=["fluxo_caixa", "orcamento"],
        doc_type_aliases=["xlsx", "csv"],
    )

    assert "financeiro" in prompt
    assert "planilha" in prompt
    assert "contabilidade" in prompt
    assert "tesouraria" in prompt
    assert "FP&A" in prompt
    assert "fluxo_caixa" in prompt
    assert "xlsx" in prompt
    assert "pt-BR" in prompt


def test_build_synthetic_record_schema() -> None:
    record = build_synthetic_record(
        business_domain="financeiro",
        document_type="planilha",
        synthetic_text="Relatório de fluxo de caixa mensal...",
    )

    assert record.business_domain == "financeiro"
    assert record.document_type == "planilha"
    assert record.decision == "llm_synthetic"
    assert record.synthetic_text == "Relatório de fluxo de caixa mensal..."
    assert record.path == ""
    assert record.doc_id
    assert "synthetic_" in record.original_filename


def test_synthetic_records_used_in_load_training_examples(tmp_path: Path) -> None:
    """Synthetic records with synthetic_text should be loaded without file access."""
    from pathlib import Path

    from app.classifier_cycle import load_training_examples

    synthetic_record = TrainingPoolRecord(
        doc_id="synth-1",
        project_id="llm_augmentation",
        original_filename="synthetic_financeiro_planilha.txt",
        path="",
        business_domain="financeiro",
        document_type="planilha",
        decision="llm_synthetic",
        synthetic_text="planilha fluxo de caixa faturamento contas a pagar",
    )
    real_record = TrainingPoolRecord(
        doc_id="real-1",
        project_id="proj",
        original_filename="missing_file.pdf",
        path="/nonexistent/path/missing_file.pdf",
        business_domain="juridico",
        document_type="contrato",
        decision="approved",
    )

    examples, skipped = load_training_examples(tmp_path, [synthetic_record, real_record])

    assert len(examples) == 1
    assert examples[0]["record"].doc_id == "synth-1"
    assert examples[0]["text"] == "planilha fluxo de caixa faturamento contas a pagar"
    assert examples[0]["file_path"] is None
    assert len(skipped) == 1
    assert "missing_file" in skipped[0]


def test_synthetic_records_roundtrip_jsonl(tmp_path: Path) -> None:
    """Synthetic records survive save/load to JSONL."""
    from pathlib import Path

    from app.evaluation_dataset import save_training_pool_records

    import json

    records = [
        build_synthetic_record(
            business_domain="financeiro",
            document_type="planilha",
            synthetic_text="dados financeiros simulados",
        ),
        TrainingPoolRecord(
            doc_id="real-1",
            project_id="proj",
            original_filename="real.pdf",
            path="training_pool/files/real.pdf",
            business_domain="juridico",
            document_type="contrato",
            decision="approved",
        ),
    ]

    jsonl_path = tmp_path / "records.jsonl"
    payload = "\n".join(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) for r in records)
    jsonl_path.write_text(payload + "\n", encoding="utf-8")

    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    loaded = [TrainingPoolRecord.model_validate_json(line) for line in lines if line.strip()]

    assert len(loaded) == 2
    assert loaded[0].decision == "llm_synthetic"
    assert loaded[0].synthetic_text == "dados financeiros simulados"
    assert loaded[1].decision == "approved"
    assert loaded[1].synthetic_text == ""
