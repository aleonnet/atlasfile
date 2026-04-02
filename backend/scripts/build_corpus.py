#!/usr/bin/env python3
"""Consolidate training_pool + validation_set into a single deduplicated corpus.

Reads all files from both dataset directories, deduplicates by SHA256,
cleans filenames, copies to corpus_files/, and generates corpus.jsonl.

Usage:
    PROJECTS_ROOT=/path/to/projects python -m scripts.build_corpus [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation_dataset import (
    classifier_datasets_root,
    training_pool_files_dir,
    training_pool_records_path,
    validation_set_expected_path,
    validation_set_files_dir,
)
from app.utils import sha256_file, utc_now_iso


def _strip_canonical_prefix(name: str) -> str:
    """Remove triage-flow canonical prefix: {hex}__YYYYMMDD__training_pool_*__name__v01.ext"""
    match = re.match(r"^[0-9a-f]{8,}__\d{8}__.*?__(.+?)(?:__v\d+)?(\.\w+)$", name)
    if match:
        return match.group(1) + match.group(2)
    return name


def _strip_injected_prefix(name: str) -> str:
    """Remove tp_, tp2_ prefixes from injected files."""
    if name.startswith("tp2_"):
        return name[4:]
    if name.startswith("tp_"):
        return name[3:]
    return name


def _strip_vdr_numbering(name: str) -> str:
    """Remove VDR hierarchical numbering like '1.15.2.52 [51]-10248820_' or '5.3.8.3.7 25474 '."""
    # Pattern: digits and dots at start, optional bracket block, optional long number + underscore
    cleaned = re.sub(r"^\d+(?:\.\d+)+ (?:\[\d+\]-?)?\d*_?", "", name)
    # Pattern: digits and dots at start + space + number + space
    cleaned = re.sub(r"^\d+(?:\.\d+)+ \d+ ", "", cleaned)
    # Pattern: just dots-numbers at start
    cleaned = re.sub(r"^\d+(?:\.\d+)+ ", "", cleaned)
    return cleaned if cleaned else name


def _fix_encoding(name: str) -> str:
    """Fix common encoding artifacts from OneDrive/Windows."""
    replacements = {
        "Ç╟O": "ÇÃO",
        "ç╟o": "ção",
        "╞o": "ão",
        "Σ": "õ",
        "╞": "ã",
        "╟": "Ã",
    }
    for bad, good in replacements.items():
        name = name.replace(bad, good)
    return name


def _normalize_filename(name: str) -> str:
    """Full filename normalization pipeline."""
    stem = Path(name).stem
    ext = Path(name).suffix.lower()

    stem = _fix_encoding(stem)
    stem = _strip_canonical_prefix(stem + ext).replace(ext, "")
    stem = _strip_injected_prefix(stem)
    stem = _strip_vdr_numbering(stem)

    # Remove accents
    nfkd = unicodedata.normalize("NFKD", stem)
    stem = "".join(c for c in nfkd if not unicodedata.combining(c))

    # Remove special chars, keep alphanumeric, spaces, hyphens, underscores
    stem = re.sub(r"[^\w\s\-]", "", stem)
    # Collapse whitespace to single underscore
    stem = re.sub(r"\s+", "_", stem.strip())
    # Collapse multiple underscores/hyphens
    stem = re.sub(r"[_\-]{2,}", "_", stem)
    # Lowercase
    stem = stem.lower().strip("_")
    # Truncate
    stem = stem[:100]

    return stem + ext if stem else "unnamed" + ext


def _load_existing_labels() -> dict[str, dict]:
    """Load labels from both records.jsonl and expected.json, keyed by SHA256."""
    labels: dict[str, dict] = {}

    # Training pool records
    tp_path = training_pool_records_path()
    if tp_path.exists():
        for line in tp_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            sha = record.get("sha256", "")
            if sha and sha not in labels:
                labels[sha] = {
                    "business_domain": record.get("business_domain", ""),
                    "document_type": record.get("document_type", ""),
                    "source": "training_pool",
                    "topics": record.get("topics", []),
                    "notes": record.get("notes", ""),
                    "original_filename": record.get("original_filename", ""),
                }

    # Validation set entries
    val_path = validation_set_expected_path()
    if val_path.exists():
        entries = json.loads(val_path.read_text(encoding="utf-8") or "[]")
        val_dir = validation_set_files_dir()
        for entry in entries:
            file_path = val_dir / entry["file"]
            if file_path.exists():
                sha = sha256_file(file_path)
                if sha not in labels:
                    labels[sha] = {
                        "business_domain": entry.get("business_domain", ""),
                        "document_type": entry.get("document_type", ""),
                        "source": "validation_set",
                        "topics": entry.get("topics", []),
                        "notes": entry.get("notes", ""),
                        "original_filename": entry["file"],
                    }
    return labels


def build_corpus(*, dry_run: bool = False) -> dict:
    """Build consolidated corpus from training_pool + validation_set."""
    ds_root = classifier_datasets_root()
    corpus_dir = ds_root / "corpus_files"
    corpus_jsonl = ds_root / "corpus.jsonl"
    metadata_dir = ds_root / "metadata"

    if not dry_run:
        corpus_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)

    # Collect all unique files by SHA256
    seen_sha: dict[str, tuple[Path, str]] = {}  # sha -> (first_path, original_name)
    all_files: list[tuple[Path, str]] = []  # (path, source_label)

    tp_dir = training_pool_files_dir()
    val_dir = validation_set_files_dir()

    for source_dir, source_label in [(tp_dir, "training_pool"), (val_dir, "validation_set")]:
        if not source_dir.exists():
            continue
        for f in sorted(source_dir.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            all_files.append((f, source_label))

    # Deduplicate
    existing_labels = _load_existing_labels()
    corpus_entries: list[dict] = []
    dedup_removed: list[dict] = []
    doc_counter = 0

    for file_path, source_label in all_files:
        sha = sha256_file(file_path)
        if sha in seen_sha:
            dedup_removed.append({
                "removed_file": file_path.name,
                "kept_file": seen_sha[sha][1],
                "sha256": sha,
                "source": source_label,
            })
            continue
        seen_sha[sha] = (file_path, file_path.name)
        doc_counter += 1

        clean_name = _normalize_filename(file_path.name)
        doc_id = f"doc_{doc_counter:04d}"
        corpus_filename = f"{doc_id}__{clean_name}"

        label_info = existing_labels.get(sha, {})

        entry = {
            "doc_id": doc_id,
            "original_filename": file_path.name,
            "clean_filename": clean_name,
            "corpus_file": corpus_filename,
            "sha256": sha,
            "business_domain": label_info.get("business_domain", ""),
            "document_type": label_info.get("document_type", ""),
            "source": source_label,
            "labeled_by": "pending_llm" if not label_info.get("business_domain") else "existing",
            "labeled_at": utc_now_iso() if label_info.get("business_domain") else "",
            "topics": label_info.get("topics", []),
            "notes": label_info.get("notes", ""),
        }
        corpus_entries.append(entry)

        if not dry_run:
            dest = corpus_dir / corpus_filename
            if not dest.exists():
                shutil.copy2(file_path, dest)

    # Write corpus.jsonl
    if not dry_run:
        with corpus_jsonl.open("w", encoding="utf-8") as f:
            for entry in corpus_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Write dedup report
    dedup_report = {
        "generated_at": utc_now_iso(),
        "total_files_scanned": len(all_files),
        "unique_documents": len(corpus_entries),
        "duplicates_removed": len(dedup_removed),
        "duplicates": dedup_removed,
    }
    if not dry_run:
        (metadata_dir / "dedup_report.json").write_text(
            json.dumps(dedup_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # Stats
    bd_counts = Counter(e["business_domain"] for e in corpus_entries if e["business_domain"])
    dt_counts = Counter(e["document_type"] for e in corpus_entries if e["document_type"])
    unlabeled = sum(1 for e in corpus_entries if not e["business_domain"] or not e["document_type"])

    stats = {
        "total_unique": len(corpus_entries),
        "labeled": len(corpus_entries) - unlabeled,
        "unlabeled": unlabeled,
        "duplicates_removed": len(dedup_removed),
        "business_domain_distribution": dict(sorted(bd_counts.items())),
        "document_type_distribution": dict(sorted(dt_counts.items())),
    }

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build consolidated corpus")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats = build_corpus(dry_run=args.dry_run)
    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}Corpus built:")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
