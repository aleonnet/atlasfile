"""Testes do núcleo de reconciliação de rótulos (consenso + arbitragem)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location("reconcile_labels", _SCRIPTS_DIR / "reconcile_labels.py")
reconcile_labels = importlib.util.module_from_spec(_spec)
sys.modules["reconcile_labels"] = reconcile_labels  # dataclasses exigem o módulo registrado
_spec.loader.exec_module(reconcile_labels)

LabelObservation = reconcile_labels.LabelObservation
group_observations = reconcile_labels.group_observations
distinct_options = reconcile_labels.distinct_options
resolve_sha = reconcile_labels.resolve_sha
parse_human_resolutions = reconcile_labels.parse_human_resolutions


def _obs(sha: str, bd: str, dt: str, source: str = "training_pool", ref: str = "a.pdf", authoritative: bool = True):
    return LabelObservation(
        sha256=sha, business_domain=bd, document_type=dt, source=source, ref=ref, authoritative=authoritative
    )


def _no_llm(sha, group):
    raise AssertionError("LLM não deveria ser chamado em consenso")


def test_unanimidade_vira_consensus_sem_llm():
    group = [_obs("s1", "juridico", "edital"), _obs("s1", "juridico", "edital", source="validation_set", ref="b.docx")]
    res = resolve_sha("s1", group, _no_llm)
    assert res.labeled_by == "consensus"
    assert (res.canonical_business_domain, res.canonical_document_type) == ("juridico", "edital")


def test_observacional_nao_gera_conflito_contra_autoritativa():
    # project_tree diverge, mas a única fonte autoritativa decide sozinha
    group = [
        _obs("s2", "ti", "apresentacao"),
        _obs("s2", "financeiro", "apresentacao", source="project_tree", ref="v070/x.pptx", authoritative=False),
    ]
    res = resolve_sha("s2", group, _no_llm)
    assert res.labeled_by == "consensus"
    assert res.canonical_business_domain == "ti"


def test_conflito_resolvido_quando_llm_concorda_com_uma_fonte():
    group = [_obs("s3", "juridico", "edital"), _obs("s3", "societario", "edital", ref="outro.docx")]
    res = resolve_sha("s3", group, lambda sha, g: {"business_domain": "juridico", "document_type": "edital", "confidence": 0.9})
    assert res.labeled_by == "llm_consensus"
    assert res.canonical_business_domain == "juridico"


def test_llm_divergente_de_todas_vira_pending_human():
    group = [_obs("s4", "juridico", "edital"), _obs("s4", "societario", "edital", ref="outro.docx")]
    res = resolve_sha("s4", group, lambda sha, g: {"business_domain": "regulatorio", "document_type": "contrato"})
    assert res.labeled_by == "pending_human"
    assert res.canonical_business_domain == ""
    assert res.llm_proposal["business_domain"] == "regulatorio"


def test_somente_observacionais_conflitantes_vao_para_llm():
    group = [
        _obs("s5", "ti", "apresentacao", source="project_tree", ref="v080/x.pptx", authoritative=False),
        _obs("s5", "financeiro", "apresentacao", source="project_tree", ref="v070/x.pptx", authoritative=False),
    ]
    res = resolve_sha("s5", group, lambda sha, g: {"business_domain": "ti", "document_type": "apresentacao"})
    assert res.labeled_by == "llm_consensus"
    assert res.canonical_business_domain == "ti"


def test_group_observations_ignora_incompletos():
    grouped = group_observations([_obs("s6", "", "edital"), _obs("s6", "juridico", "edital")])
    assert len(grouped["s6"]) == 1


def test_parse_human_resolutions(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(
        "### sha `abc123def456` — `x.docx`\n- fontes: ...\n- resolution: juridico/edital\n",
        encoding="utf-8",
    )
    parsed = parse_human_resolutions(report)
    assert parsed == {"abc123def456": ("juridico", "edital")}


def test_dataset_integrity_reporta_label_conflicts(tmp_path):
    from app.classifier_cycle import compute_dataset_integrity
    from app.evaluation_dataset import TrainingPoolRecord

    f1 = tmp_path / "a.txt"
    f1.write_text("conteudo A", encoding="utf-8")
    records = [
        TrainingPoolRecord(
            doc_id="d1", project_id="p1", original_filename="a.txt", path=str(f1),
            business_domain="juridico", document_type="edital", decision="approved", sha256="sha-a",
        ),
        TrainingPoolRecord(
            doc_id="d2", project_id="p2", original_filename="a.txt", path=str(f1),
            business_domain="societario", document_type="edital", decision="approved", sha256="sha-a",
        ),
    ]
    result = compute_dataset_integrity(repo_root=tmp_path, validation_examples=[], training_records=records)
    assert result["status"] == "warning"
    assert len(result["label_conflicts"]) == 1
    conflict = result["label_conflicts"][0]
    assert conflict["sha256"] == "sha-a"
    assert any("juridico/edital" in labels for labels in conflict["labels"].values())
