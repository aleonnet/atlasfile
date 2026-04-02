#!/usr/bin/env python3
"""Inject training pool records from files already copied to training_pool/files/.

Usage:
    python -m scripts.inject_training_records \
        --business-domain juridico \
        --document-type contrato \
        --decision manual_inject \
        --project-id default \
        FILE [FILE ...]

Each FILE must already exist in training_pool/files/.  The script:
1. Computes SHA256 of the file
2. Checks for overlap with the validation set (aborts on collision)
3. Checks for duplicate SHA256 in existing records (skips)
4. Appends a TrainingPoolRecord to records.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation_dataset import (
    TrainingPoolRecord,
    append_training_pool_record,
    dataset_relative_path,
    load_training_pool_records,
    training_pool_files_dir,
    validation_sha_index,
)
from app.utils import sha256_file, utc_now_iso


def inject(
    filenames: list[str],
    *,
    business_domain: str,
    document_type: str,
    decision: str = "manual_inject",
    project_id: str = "default",
    dry_run: bool = False,
) -> tuple[int, int]:
    """Inject records and return (injected, skipped) counts."""
    files_dir = training_pool_files_dir()
    existing_records = load_training_pool_records()
    existing_sha = {r.sha256 for r in existing_records if r.sha256}
    val_sha = set(validation_sha_index().keys())

    injected = 0
    skipped = 0
    for filename in filenames:
        path = files_dir / filename
        if not path.exists():
            print(f"SKIP (not found): {filename}", file=sys.stderr)
            skipped += 1
            continue

        sha = sha256_file(path)

        if sha in val_sha:
            msg = f"ABORT: {filename} overlaps with validation set (SHA256={sha[:12]}...)"
            print(msg, file=sys.stderr)
            raise SystemExit(1)

        if sha in existing_sha:
            print(f"SKIP (duplicate SHA256): {filename}")
            skipped += 1
            continue

        doc_id = f"inject_{sha[:12]}"
        record = TrainingPoolRecord(
            doc_id=doc_id,
            project_id=project_id,
            original_filename=filename,
            path=dataset_relative_path(path),
            source_path=str(path),
            business_domain=business_domain,
            document_type=document_type,
            decision=decision,
            sha256=sha,
            reviewed_at=utc_now_iso(),
        )

        if dry_run:
            print(f"DRY-RUN: {filename} -> {business_domain}/{document_type} ({sha[:12]})")
        else:
            append_training_pool_record(record)
            existing_sha.add(sha)
            print(f"INJECTED: {filename} -> {business_domain}/{document_type}")
        injected += 1

    return injected, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject training pool records")
    parser.add_argument("files", nargs="+", help="Filenames in training_pool/files/")
    parser.add_argument("--business-domain", required=True)
    parser.add_argument("--document-type", required=True)
    parser.add_argument("--decision", default="manual_inject")
    parser.add_argument("--project-id", default="default")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    injected, skipped = inject(
        args.files,
        business_domain=args.business_domain,
        document_type=args.document_type,
        decision=args.decision,
        project_id=args.project_id,
        dry_run=args.dry_run,
    )
    print(f"\nDone: {injected} injected, {skipped} skipped")


if __name__ == "__main__":
    main()
