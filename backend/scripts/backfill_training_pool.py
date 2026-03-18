from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation_dataset import (
    TrainingPoolRecord,
    load_training_pool_records,
    load_validation_set,
    resolve_validation_file,
    save_training_pool_records,
)
from app.project_profile import load_project_profile
from app.triage import triage_resolved_dir
from app.utils import sha256_file, utc_now_iso


def _validation_sha_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for entry in load_validation_set():
        if not entry.is_labeled():
            continue
        file_path = resolve_validation_file(entry.file)
        if not file_path.exists():
            continue
        digest = sha256_file(file_path)
        index.setdefault(digest, []).append(entry.file)
    return index


def _fallback_project_file_path(project_root: Path, data: dict[str, Any]) -> Path | None:
    canonical_filename = str(data.get("canonical_filename") or "").strip()
    business_domain = str(data.get("business_domain") or data.get("area_key") or "").strip()
    document_type = str(data.get("document_type") or "").strip()
    if not canonical_filename or not business_domain or not document_type:
        return None
    candidate = project_root / "02_AREAS" / business_domain / document_type / canonical_filename
    return candidate if candidate.exists() else None


def _resolve_record_file_path(project_root: Path, data: dict[str, Any]) -> Path | None:
    direct_candidates = [
        str(data.get("final_path") or "").strip(),
        str(data.get("path") or "").strip(),
    ]
    for candidate_value in direct_candidates:
        if not candidate_value:
            continue
        candidate = Path(candidate_value)
        if candidate.exists():
            return candidate
    return _fallback_project_file_path(project_root, data)


def collect_training_pool_records_from_resolved(project_root: Path) -> tuple[list[TrainingPoolRecord], list[dict[str, Any]]]:
    profile = load_project_profile(project_root)
    project_id = str(profile.get("project_id") or project_root.name).strip() or project_root.name
    records: list[TrainingPoolRecord] = []
    skipped: list[dict[str, Any]] = []
    validation_by_sha = _validation_sha_index()

    for meta_path in sorted(triage_resolved_dir(project_root).glob("*.json"), key=lambda path: path.name):
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        decision = str(data.get("decision") or "").strip()
        if decision not in {"approved", "corrected"}:
            skipped.append({"metadata": str(meta_path), "reason": f"unsupported_decision:{decision or 'empty'}"})
            continue

        final_path = _resolve_record_file_path(project_root, data)
        if final_path is None:
            skipped.append({"metadata": str(meta_path), "reason": "missing_final_path"})
            continue
        final_sha = sha256_file(final_path)
        if final_sha in validation_by_sha:
            skipped.append(
                {
                    "metadata": str(meta_path),
                    "reason": "overlap_with_validation_set",
                    "validation_files": sorted(validation_by_sha[final_sha]),
                }
            )
            continue

        business_domain = str(data.get("business_domain") or data.get("area_key") or "").strip()
        document_type = str(data.get("document_type") or "").strip()
        if not business_domain or not document_type:
            skipped.append({"metadata": str(meta_path), "reason": "missing_business_domain_or_document_type"})
            continue

        doc_id = str(data.get("doc_id") or meta_path.stem).strip() or meta_path.stem
        note = str(data.get("decision_note") or "").strip()
        note_prefix = "backfill_resolved_triage"
        notes = note_prefix if not note else f"{note_prefix}: {note}"
        records.append(
            TrainingPoolRecord(
                doc_id=doc_id,
                project_id=project_id,
                original_filename=str(data.get("original_filename") or final_path.name),
                path=str(final_path),
                business_domain=business_domain,
                document_type=document_type,
                decision=decision,
                reviewed_at=str(data.get("processed_at") or utc_now_iso()),
                topics=list(data.get("topics", []) or []),
                entities=list(data.get("entities", []) or []),
                notes=notes,
            )
        )

    return records, skipped


def merge_training_pool_records(
    existing: list[TrainingPoolRecord],
    incoming: list[TrainingPoolRecord],
    *,
    replace_project_ids: set[str] | None = None,
) -> list[TrainingPoolRecord]:
    replace_project_ids = replace_project_ids or set()
    merged: dict[tuple[str, str], TrainingPoolRecord] = {
        (record.project_id, record.doc_id): record
        for record in existing
        if record.project_id not in replace_project_ids
    }
    for record in incoming:
        merged[(record.project_id, record.doc_id)] = record
    return sorted(
        merged.values(),
        key=lambda record: (record.project_id, record.reviewed_at, record.doc_id),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera/atualiza config/training_pool/records.jsonl a partir de _TRIAGE_REVIEW/resolved de um projeto."
    )
    parser.add_argument("project_root", help="Caminho absoluto ou relativo do projeto AtlasFile")
    parser.add_argument(
        "--replace-project-records",
        action="store_true",
        help="Remove registros existentes do mesmo project_id antes de gravar o backfill",
    )
    parser.add_argument("--dry-run", action="store_true", help="Só mostra o resumo; não grava records.jsonl")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    records, skipped = collect_training_pool_records_from_resolved(project_root)
    existing = load_training_pool_records()
    project_ids = {record.project_id for record in records}
    merged = merge_training_pool_records(
        existing,
        records,
        replace_project_ids=project_ids if args.replace_project_records else set(),
    )

    payload = {
        "project_root": str(project_root),
        "project_ids": sorted(project_ids),
        "incoming_records": len(records),
        "skipped_records": skipped,
        "existing_records": len(existing),
        "result_records": len(merged),
        "dry_run": args.dry_run,
    }
    if not args.dry_run:
        save_training_pool_records(merged)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
