from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.classifier_cycle import (  # noqa: E402
    benchmark_sparse_candidates,
    compute_dataset_integrity,
    evaluate_classifier_cycle,
)
from app.classifier_supervised import (  # noqa: E402
    SPARSE_MIN_DOCS_PER_CLASS as _SPARSE_MIN_DOCS_PER_CLASS,
    SPARSE_MIN_TRAINING_DOCS as _SPARSE_MIN_TRAINING_DOCS,
    compute_supervised_gate,
)


def _render_text(benchmarks: dict[str, Any]) -> str:
    lines: list[str] = []
    for mode, payload in benchmarks.items():
        summary = payload["summary"]
        compact_summary = {
            key: summary[key]
            for key in (
                "mode",
                "role",
                "total_labeled",
                "business_domain_accuracy",
                "business_domain_macro_f1",
                "document_type_accuracy",
                "document_type_macro_f1",
                "exact_match_accuracy",
                "skipped",
                "skip_reason",
                "training_pool_records",
                "validation_records",
                "vectorizer",
            )
            if key in summary
        }
        lines.append(json.dumps(compact_summary, ensure_ascii=False))
        for row in payload["results"]:
            lines.append(
                f"{row['file']}: domain={row['predicted_business_domain']} ({'ok' if row['business_domain_ok'] else 'miss'}) "
                f"type={row['predicted_document_type']} ({'ok' if row['document_type_ok'] else 'miss'})"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark oficial do classificador sobre o dataset operacional configurado em CLASSIFIER_DATASETS_ROOT."
    )
    parser.add_argument(
        "--mode",
        choices=["bootstrap", "sparse_logreg", "sparse_linear_svc", "all"],
        default="bootstrap",
        help="bootstrap é o classificador operacional atual; sparse_* avalia candidatos supervisionados no validation_set usando training_pool.",
    )
    parser.add_argument(
        "--profile",
        default="config/templates/default.json",
        help="Profile/template JSON usado na classificação",
    )
    parser.add_argument(
        "--min-training-docs",
        type=int,
        default=_SPARSE_MIN_TRAINING_DOCS,
        help="Mínimo de documentos rotulados no training_pool para considerar benchmark supervisionado",
    )
    parser.add_argument(
        "--min-docs-per-class",
        type=int,
        default=_SPARSE_MIN_DOCS_PER_CLASS,
        help="Mínimo por classe em business_domain e document_type para benchmark supervisionado",
    )
    parser.add_argument("--json", action="store_true", help="Emite saída JSON em vez de texto")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    cycle_payload = evaluate_classifier_cycle(
        repo_root=repo_root,
        profile_path=(repo_root / args.profile).resolve(),
        min_training_docs=args.min_training_docs,
        min_docs_per_class=args.min_docs_per_class,
    )

    payload = {
        "operational_classifier_mode": cycle_payload["operational_classifier_mode"],
        "dataset_integrity": cycle_payload["dataset_integrity"],
        "dataset_manifest": cycle_payload.get("dataset_manifest"),
        "gates": cycle_payload["gates"],
        "training_pool_records_jsonl": cycle_payload.get("training_pool_records_jsonl"),
        "training_pool_records_resolved": cycle_payload.get("training_pool_records_resolved"),
        "training_pool_records": cycle_payload["training_pool_records"],
        "training_examples_skipped_count": cycle_payload.get("training_examples_skipped_count", 0),
        "benchmarks": {},
    }
    if "training_examples_skipped" in cycle_payload:
        payload["training_examples_skipped"] = cycle_payload["training_examples_skipped"]
    if (cycle_payload.get("dataset_integrity") or {}).get("status") == "error":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    all_benchmarks = cycle_payload["benchmarks"]
    payload["benchmarks"] = all_benchmarks if args.mode == "all" else {args.mode: all_benchmarks[args.mode]}

    if args.json or args.mode in {"all", "sparse_logreg", "sparse_linear_svc"}:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_render_text(payload["benchmarks"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
