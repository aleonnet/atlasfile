from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.classifier_setfit import (
    _ARTIFACT_SCHEMA_VERSION,
    SETFIT_MIN_DOCS_PER_CLASS,
    SETFIT_MIN_TRAINING_DOCS,
    SETFIT_SAMPLES_PER_CLASS,
    _stratified_sample,
    compute_setfit_gate,
    setfit_import_error,
)


class _FakeRecord:
    def __init__(self, business_domain: str, document_type: str) -> None:
        self.business_domain = business_domain
        self.document_type = document_type


def test_compute_setfit_gate_blocks_insufficient_data() -> None:
    records = [_FakeRecord("juridico", "contrato")] * 5
    gate = compute_setfit_gate(records, min_training_docs=32, min_docs_per_class=8)

    assert gate["eligible"] is False
    assert any("training_pool_total_below_min" in r for r in gate["reasons"])


def test_compute_setfit_gate_blocks_single_class() -> None:
    records = [_FakeRecord("juridico", "contrato")] * 50
    gate = compute_setfit_gate(records, min_training_docs=32, min_docs_per_class=8)

    assert gate["eligible"] is False
    assert any("eligible_classes_below_min" in r for r in gate["reasons"])


def test_compute_setfit_gate_accepts_sufficient_data() -> None:
    records = (
        [_FakeRecord("juridico", "contrato")] * 20
        + [_FakeRecord("financeiro", "planilha")] * 20
    )
    gate = compute_setfit_gate(records, min_training_docs=32, min_docs_per_class=8)

    assert gate["eligible"] is True
    assert gate["reasons"] == []
    assert gate["total_records"] == 40


@pytest.mark.skipif(setfit_import_error() is not None, reason="setfit not installed")
def test_fit_and_predict_setfit_synthetic() -> None:
    from app.classifier_setfit import fit_setfit_artifact, predict_labels_from_setfit_artifact

    texts = (
        ["clausula juridico litigio contrato partes assinatura parecer legal"] * 10
        + ["planilha fluxo de caixa faturamento contas a pagar conciliacao tesouraria"] * 10
    )
    domains = ["juridico"] * 10 + ["financeiro"] * 10
    types = ["contrato"] * 10 + ["planilha"] * 10

    artifact = fit_setfit_artifact(
        train_texts=texts,
        train_business_domains=domains,
        train_document_types=types,
        training_pool_records=20,
    )

    assert artifact["schema_version"] == _ARTIFACT_SCHEMA_VERSION
    assert artifact["family"] == "setfit"

    result = predict_labels_from_setfit_artifact(
        artifact, "clausula juridico contrato parecer legal"
    )
    assert result["family"] == "setfit"
    assert result["business_domain"]["label"] == "juridico"
    assert result["document_type"]["label"] == "contrato"
    assert 0.0 <= result["business_domain"]["confidence"] <= 1.0


@pytest.mark.skipif(setfit_import_error() is not None, reason="setfit not installed")
def test_save_load_setfit_artifact_roundtrip(tmp_path: Path) -> None:
    from app.classifier_setfit import (
        fit_setfit_artifact,
        load_setfit_artifact,
        predict_labels_from_setfit_artifact,
        save_setfit_artifact,
    )

    texts = (
        ["clausula juridico contrato parecer"] * 10
        + ["planilha faturamento contas caixa"] * 10
    )
    domains = ["juridico"] * 10 + ["financeiro"] * 10
    types = ["contrato"] * 10 + ["planilha"] * 10

    artifact = fit_setfit_artifact(
        train_texts=texts,
        train_business_domains=domains,
        train_document_types=types,
        training_pool_records=20,
    )

    artifact_dir = tmp_path / "setfit_model"
    save_setfit_artifact(artifact_dir, artifact)

    assert (artifact_dir / "metadata.json").exists()
    assert (artifact_dir / "business_domain").is_dir()
    assert (artifact_dir / "document_type").is_dir()

    loaded = load_setfit_artifact(artifact_dir)
    assert loaded["schema_version"] == _ARTIFACT_SCHEMA_VERSION
    assert loaded["family"] == "setfit"

    result = predict_labels_from_setfit_artifact(
        loaded, "clausula juridico contrato"
    )
    assert result["business_domain"]["label"] == "juridico"


@pytest.mark.skipif(setfit_import_error() is not None, reason="setfit not installed")
def test_classify_with_setfit_returns_expected_schema(tmp_path: Path) -> None:
    from app.classifier_setfit import classify_with_setfit_artifact, fit_setfit_artifact

    texts = (
        ["clausula juridico contrato parecer"] * 10
        + ["planilha faturamento contas caixa"] * 10
    )
    domains = ["juridico"] * 10 + ["financeiro"] * 10
    types = ["contrato"] * 10 + ["planilha"] * 10

    artifact = fit_setfit_artifact(
        train_texts=texts,
        train_business_domains=domains,
        train_document_types=types,
        training_pool_records=20,
    )

    profile_path = Path(__file__).resolve().parents[3] / "config" / "templates" / "default.json"
    raw = json.loads(profile_path.read_text(encoding="utf-8"))
    raw["project_id"] = "test"
    raw["project_label"] = "Test"
    raw["project_root"] = str(tmp_path)
    from app.profile_schema_v2 import ProjectProfileV2
    from app.project_profile import profile_v2_to_runtime
    profile = profile_v2_to_runtime(ProjectProfileV2.model_validate(raw), tmp_path)

    result = classify_with_setfit_artifact(
        artifact=artifact,
        profile=profile,
        source_path=Path("contrato_servicos.pdf"),
        text_excerpt="clausula juridico contrato parecer legal",
    )

    assert result["business_domain"] in ("juridico", "financeiro")
    assert result["document_type"] in ("contrato", "planilha")
    assert "confidence" in result
    assert "top_candidates" in result
    assert "top_document_type_candidates" in result
    assert "entities" in result
    assert "topics" in result
    assert result["classifier_mode"] == "setfit"
    assert result["reason"] == "supervised:setfit"


def test_stratified_sample_caps_per_class() -> None:
    texts = [f"text_{i}" for i in range(50)]
    labels = ["A"] * 30 + ["B"] * 20
    sampled_texts, sampled_labels = _stratified_sample(texts, labels, max_per_class=10)
    from collections import Counter

    counts = Counter(sampled_labels)
    assert counts["A"] == 10
    assert counts["B"] == 10
    assert len(sampled_texts) == 20


def test_stratified_sample_preserves_small_classes() -> None:
    texts = ["t1", "t2", "t3", "t4", "t5"]
    labels = ["A", "A", "A", "B", "B"]
    sampled_texts, sampled_labels = _stratified_sample(texts, labels, max_per_class=10)
    from collections import Counter

    counts = Counter(sampled_labels)
    assert counts["A"] == 3
    assert counts["B"] == 2
    assert len(sampled_texts) == 5


@pytest.mark.skipif(setfit_import_error() is not None, reason="setfit not installed")
def test_fit_uses_all_data_for_head() -> None:
    """Head must be trained on ALL data, not just the contrastive sample."""
    from app.classifier_setfit import fit_setfit_artifact

    all_domains = sorted({"juridico", "financeiro", "fiscal", "ti"})
    texts: list[str] = []
    domains: list[str] = []
    types: list[str] = []
    for domain in all_domains:
        texts.extend([f"texto {domain} exemplo {i}" for i in range(10)])
        domains.extend([domain] * 10)
        types.extend(["contrato"] * 5 + ["planilha"] * 5)

    artifact = fit_setfit_artifact(
        train_texts=texts,
        train_business_domains=domains,
        train_document_types=types,
        training_pool_records=len(texts),
        samples_per_class=4,
    )

    head_classes = sorted(artifact["business_domain_model"].model_head.classes_.tolist())
    assert head_classes == all_domains, (
        f"Head must see all {len(all_domains)} classes, got {head_classes}"
    )


def test_setfit_artifact_schema_version_mismatch_rejected(tmp_path: Path) -> None:
    """Artifacts with wrong schema_version must be rejected."""
    if setfit_import_error():
        pytest.skip("setfit not installed")

    from app.classifier_setfit import load_setfit_artifact

    artifact_dir = tmp_path / "bad_setfit"
    artifact_dir.mkdir()
    (artifact_dir / "metadata.json").write_text(
        json.dumps({"schema_version": 999, "family": "setfit"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="incompatible setfit artifact schema_version"):
        load_setfit_artifact(artifact_dir)
