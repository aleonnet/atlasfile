"""Conflitos de rótulo por SHA256 — leitura e resolução via UI.

Fonte: ``label_reconciliation.jsonl`` gerado por ``scripts/reconcile_labels.py``
(detecção + proposta do LLM). Aqui vive o lado do produto: listar pendências e
aplicar a arbitragem humana nas fontes (validation_set/training_pool) e nos
derivados existentes (corpus.jsonl, splits/*.jsonl) por SHA — sem depender dos
scripts de dataset, que não são empacotados na imagem.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evaluation_dataset import (
    classifier_datasets_root,
    load_training_pool_records,
    load_validation_set,
    save_validation_set,
    training_pool_records_path,
    validation_set_files_dir,
)
from .utils import sha256_file, utc_now_iso


def reconciliation_path() -> Path:
    return classifier_datasets_root() / "label_reconciliation.jsonl"


def load_reconciliation() -> list[dict[str, Any]]:
    path = reconciliation_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def save_reconciliation(entries: list[dict[str, Any]]) -> None:
    with reconciliation_path().open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def list_pending_conflicts() -> list[dict[str, Any]]:
    return [e for e in load_reconciliation() if e.get("labeled_by") == "pending_human"]


def _update_jsonl_labels_by_sha(path: Path, sha: str, business_domain: str, document_type: str) -> int:
    """Atualiza bd/dt por sha256 em um jsonl derivado (corpus/splits), se existir."""
    if not path.exists():
        return 0
    changed = 0
    lines_out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("sha256") == sha and (
            record.get("business_domain") != business_domain or record.get("document_type") != document_type
        ):
            record["business_domain"] = business_domain
            record["document_type"] = document_type
            changed += 1
        lines_out.append(json.dumps(record, ensure_ascii=False))
    if changed:
        path.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    return changed


def resolve_conflict(sha256: str, business_domain: str, document_type: str) -> dict[str, Any]:
    """Aplica a arbitragem humana de um conflito: marca a resolução no
    reconciliation e propaga o rótulo canônico para fontes e derivados.

    Retorna um resumo do que foi atualizado. Levanta KeyError se o sha não
    estiver pendente.
    """
    entries = load_reconciliation()
    target = next((e for e in entries if e.get("sha256") == sha256), None)
    if target is None or target.get("labeled_by") != "pending_human":
        raise KeyError(f"Conflito pendente não encontrado: {sha256}")

    proposal = target.get("llm_proposal") or {}
    matches_llm = (
        proposal.get("business_domain") == business_domain
        and proposal.get("document_type") == document_type
    )
    target["canonical_business_domain"] = business_domain
    target["canonical_document_type"] = document_type
    target["labeled_by"] = "human_confirmed_llm" if matches_llm else "human"
    target["resolved_at"] = utc_now_iso()
    save_reconciliation(entries)

    # Fontes: validation_set
    updated_validation = 0
    files_dir = validation_set_files_dir()
    validation_entries = load_validation_set()
    for entry in validation_entries:
        path = files_dir / entry.file
        if not path.exists() or sha256_file(path) != sha256:
            continue
        if (entry.business_domain, entry.document_type) != (business_domain, document_type):
            entry.business_domain = business_domain
            entry.document_type = document_type
            entry.notes = (entry.notes + " | reconciled:ui").strip(" |")
            updated_validation += 1
    if updated_validation:
        save_validation_set(validation_entries)

    # Fontes: training_pool
    updated_training = 0
    records = load_training_pool_records()
    for record in records:
        if record.sha256 != sha256:
            continue
        if (record.business_domain, record.document_type) != (business_domain, document_type):
            record.business_domain = business_domain
            record.document_type = document_type
            record.notes = (record.notes + " | reconciled:ui").strip(" |")
            updated_training += 1
    if updated_training:
        with training_pool_records_path().open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(record.model_dump_json() + "\n")

    # Derivados existentes (corpus + splits) — coerência sem rebuild
    ds_root = classifier_datasets_root()
    updated_derived = _update_jsonl_labels_by_sha(ds_root / "corpus.jsonl", sha256, business_domain, document_type)
    for split in ("train", "validation", "test"):
        updated_derived += _update_jsonl_labels_by_sha(
            ds_root / "splits" / f"{split}.jsonl", sha256, business_domain, document_type
        )

    return {
        "sha256": sha256,
        "business_domain": business_domain,
        "document_type": document_type,
        "labeled_by": target["labeled_by"],
        "updated_validation": updated_validation,
        "updated_training": updated_training,
        "updated_derived": updated_derived,
    }
