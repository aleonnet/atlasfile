#!/usr/bin/env python3
"""Partition corpus.jsonl into stratified train/validation/test splits (70/15/15).

Reads corpus.jsonl, stratifies by (business_domain, document_type) combined,
generates train.jsonl, validation.jsonl, test.jsonl in datasets/splits/.

Usage:
    PROJECTS_ROOT=/path/to/projects python -m scripts.build_splits [--dry-run] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation_dataset import classifier_datasets_root


def build_splits(*, seed: int = 42, dry_run: bool = False) -> dict:
    """Build stratified 70/15/15 splits from corpus.jsonl."""
    from sklearn.model_selection import StratifiedShuffleSplit

    ds_root = classifier_datasets_root()
    corpus_path = ds_root / "corpus.jsonl"
    splits_dir = ds_root / "splits"

    if not corpus_path.exists():
        print("ERROR: corpus.jsonl not found. Run build_corpus.py first.", file=sys.stderr)
        sys.exit(1)

    entries = [json.loads(l) for l in corpus_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    # Filter labeled only
    labeled = [e for e in entries if e.get("business_domain") and e.get("document_type")]
    unlabeled = len(entries) - len(labeled)

    # Stratification key = combined (domain, type)
    strat_keys = [f"{e['business_domain']}|{e['document_type']}" for e in labeled]

    # Check minimum: classes with only 1 sample can't be split
    key_counts = Counter(strat_keys)
    singleton_keys = {k for k, v in key_counts.items() if v == 1}
    singletons = [e for e, k in zip(labeled, strat_keys) if k in singleton_keys]
    splittable = [(e, k) for e, k in zip(labeled, strat_keys) if k not in singleton_keys]

    if not splittable:
        print("ERROR: Not enough data for stratified split.", file=sys.stderr)
        sys.exit(1)

    splittable_entries = [e for e, _ in splittable]
    splittable_keys = [k for _, k in splittable]

    # First split: 70% train, 30% holdout
    sss1 = StratifiedShuffleSplit(n_splits=1, test_size=0.30, random_state=seed)
    train_idx, holdout_idx = next(sss1.split(splittable_entries, splittable_keys))

    holdout_entries = [splittable_entries[i] for i in holdout_idx]
    holdout_keys = [splittable_keys[i] for i in holdout_idx]

    # Second split: holdout → 50/50 → val 15%, test 15%
    # Some holdout classes may have only 1 sample — force them to validation
    holdout_key_counts = Counter(holdout_keys)
    holdout_singletons_idx = [i for i, k in enumerate(holdout_keys) if holdout_key_counts[k] == 1]
    holdout_splittable_idx = [i for i, k in enumerate(holdout_keys) if holdout_key_counts[k] > 1]

    if holdout_splittable_idx:
        h_entries = [holdout_entries[i] for i in holdout_splittable_idx]
        h_keys = [holdout_keys[i] for i in holdout_splittable_idx]
        sss2 = StratifiedShuffleSplit(n_splits=1, test_size=0.50, random_state=seed)
        val_idx2, test_idx2 = next(sss2.split(h_entries, h_keys))
        val_entries = [h_entries[i] for i in val_idx2]
        test_entries = [h_entries[i] for i in test_idx2]
    else:
        val_entries = []
        test_entries = []

    # Add holdout singletons to validation (better to evaluate than to test)
    for i in holdout_singletons_idx:
        val_entries.append(holdout_entries[i])

    train_entries = [splittable_entries[i] for i in train_idx]

    # Add corpus-level singletons to training (can't evaluate with 1 sample)
    train_entries.extend(singletons)

    # Verify zero overlap
    train_ids = {e["doc_id"] for e in train_entries}
    val_ids = {e["doc_id"] for e in val_entries}
    test_ids = {e["doc_id"] for e in test_entries}
    assert not (train_ids & val_ids), "Train/val overlap!"
    assert not (train_ids & test_ids), "Train/test overlap!"
    assert not (val_ids & test_ids), "Val/test overlap!"
    assert len(train_ids) + len(val_ids) + len(test_ids) == len(labeled), "Missing documents!"

    # Write splits
    if not dry_run:
        splits_dir.mkdir(parents=True, exist_ok=True)
        for name, split_entries in [("train", train_entries), ("validation", val_entries), ("test", test_entries)]:
            path = splits_dir / f"{name}.jsonl"
            with path.open("w", encoding="utf-8") as f:
                for entry in split_entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Stats
    def dist(entries):
        bd = Counter(e["business_domain"] for e in entries)
        dt = Counter(e["document_type"] for e in entries)
        return {"domains": dict(sorted(bd.items())), "types": dict(sorted(dt.items()))}

    report = {
        "seed": seed,
        "total_labeled": len(labeled),
        "unlabeled_excluded": unlabeled,
        "singletons_to_train": len(singletons),
        "train": {"count": len(train_entries), "pct": round(len(train_entries) / len(labeled) * 100, 1), **dist(train_entries)},
        "validation": {"count": len(val_entries), "pct": round(len(val_entries) / len(labeled) * 100, 1), **dist(val_entries)},
        "test": {"count": len(test_entries), "pct": round(len(test_entries) / len(labeled) * 100, 1), **dist(test_entries)},
        "zero_overlap": True,
    }

    if not dry_run:
        (splits_dir / "split_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build stratified splits from corpus")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report = build_splits(seed=args.seed, dry_run=args.dry_run)
    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}Splits built:")
    print(f"  Train:      {report['train']['count']} ({report['train']['pct']}%)")
    print(f"  Validation: {report['validation']['count']} ({report['validation']['pct']}%)")
    print(f"  Test:       {report['test']['count']} ({report['test']['pct']}%)")
    print(f"  Singletons → train: {report['singletons_to_train']}")
    print(f"  Zero overlap: {report['zero_overlap']}")

    print(f"\nValidation domains: {report['validation']['domains']}")
    print(f"Validation types:   {report['validation']['types']}")


if __name__ == "__main__":
    main()
