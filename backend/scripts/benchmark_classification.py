from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.classification_bootstrap import classify_bootstrap
from app.document_extractor import extract_document_content
from app.evaluation_dataset import (
    TrainingPoolRecord,
    ValidationSetEntry,
    load_training_pool_records,
    load_validation_set,
    resolve_validation_file,
)
from app.ingestion import classify
from app.profile_schema_v2 import ProjectProfileV2
from app.project_profile import profile_v2_to_runtime
from app.utils import fold_ocr_spacing, normalize_text, sha256_file

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.svm import LinearSVC

    _SKLEARN_IMPORT_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover - covered indirectly in gate output
    TfidfVectorizer = None  # type: ignore[assignment]
    LogisticRegression = None  # type: ignore[assignment]
    Pipeline = None  # type: ignore[assignment]
    LinearSVC = None  # type: ignore[assignment]
    _SKLEARN_IMPORT_ERROR = str(exc)


_MAX_EXTRACT_CHARS = 50_000
_SPARSE_MIN_TRAINING_DOCS = 100
_SPARSE_MIN_DOCS_PER_CLASS = 5
_SPARSE_MODEL_FAMILIES = ("sparse_logreg", "sparse_linear_svc")


def _mode_role(mode: str) -> str:
    if mode == "bootstrap":
        return "operational_baseline"
    if mode == "baseline":
        return "legacy_reference"
    return "benchmark_candidate"


def _normalized_file_key(value: str) -> str:
    return normalize_text(Path(value).name)


def _classification_metrics(
    rows: list[dict[str, Any]],
    *,
    expected_key: str,
    predicted_key: str,
) -> dict[str, Any]:
    expected_values = [str(row.get(expected_key) or "") for row in rows]
    predicted_values = [str(row.get(predicted_key) or "") for row in rows]
    labels = sorted(set(expected_values) | set(predicted_values))
    if not labels:
        return {
            "macro_f1": 0.0,
            "recall_by_class": {},
            "confusion_matrix": {},
        }

    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for expected, predicted in zip(expected_values, predicted_values, strict=True):
        confusion[expected][predicted] += 1

    recall_by_class: dict[str, float] = {}
    f1_scores: list[float] = []
    for label in labels:
        tp = sum(
            1
            for expected, predicted in zip(expected_values, predicted_values, strict=True)
            if expected == label and predicted == label
        )
        fn = sum(
            1
            for expected, predicted in zip(expected_values, predicted_values, strict=True)
            if expected == label and predicted != label
        )
        fp = sum(
            1
            for expected, predicted in zip(expected_values, predicted_values, strict=True)
            if expected != label and predicted == label
        )
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        recall_by_class[label] = round(recall, 4)
        f1_scores.append(f1)

    confusion_matrix = {
        expected: {predicted: count for predicted, count in sorted(predictions.items())}
        for expected, predictions in sorted(confusion.items())
    }
    return {
        "macro_f1": round(sum(f1_scores) / len(labels), 4),
        "recall_by_class": recall_by_class,
        "confusion_matrix": confusion_matrix,
    }


def compute_dataset_integrity(
    *,
    repo_root: Path,
    validation_examples: list[dict[str, Any]],
    training_records: list[TrainingPoolRecord],
) -> dict[str, Any]:
    validation_by_sha: dict[str, list[str]] = defaultdict(list)
    validation_by_name: dict[str, list[str]] = defaultdict(list)
    for example in validation_examples:
        entry = example["entry"]
        file_path = Path(example["file_path"])
        validation_by_sha[sha256_file(file_path)].append(entry.file)
        validation_by_name[_normalized_file_key(entry.file)].append(entry.file)

    overlap_sha256: list[dict[str, Any]] = []
    name_collisions: list[dict[str, Any]] = []
    unresolved_training_paths: list[dict[str, Any]] = []
    for record in training_records:
        path = _resolve_training_path(repo_root, record)
        normalized_name = _normalized_file_key(record.original_filename or path.name)
        matching_validation_names = sorted(validation_by_name.get(normalized_name, []))
        if not path.exists():
            unresolved_training_paths.append(
                {
                    "project_id": record.project_id,
                    "original_filename": record.original_filename,
                    "path": str(path),
                }
            )
            if matching_validation_names:
                name_collisions.append(
                    {
                        "project_id": record.project_id,
                        "original_filename": record.original_filename,
                        "validation_files": matching_validation_names,
                    }
                )
            continue

        training_sha = sha256_file(path)
        overlapping_validation_files = sorted(validation_by_sha.get(training_sha, []))
        if overlapping_validation_files:
            overlap_sha256.append(
                {
                    "project_id": record.project_id,
                    "original_filename": record.original_filename,
                    "path": str(path),
                    "validation_files": overlapping_validation_files,
                    "sha256": training_sha,
                }
            )
            continue
        if matching_validation_names:
            name_collisions.append(
                {
                    "project_id": record.project_id,
                    "original_filename": record.original_filename,
                    "validation_files": matching_validation_names,
                }
            )

    status = "error" if overlap_sha256 else "warning" if (name_collisions or unresolved_training_paths) else "ok"
    return {
        "status": status,
        "validation_files": len(validation_examples),
        "training_records": len(training_records),
        "overlap_sha256": overlap_sha256,
        "name_collisions": name_collisions,
        "unresolved_training_paths": unresolved_training_paths,
    }


def _load_profile(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.setdefault("project_id", "validation_set")
    raw.setdefault("project_label", "Validation Set")
    raw.setdefault("project_root", str(path.parent.parent))
    profile = ProjectProfileV2.model_validate(raw)
    return profile_v2_to_runtime(profile, Path(profile.project_root))


def _load_legacy_map(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    return {str(key): str(value) for key, value in (raw or {}).items()}


def _extract_feature_text(file_path: Path, *, original_name: str | None = None) -> str:
    extracted = extract_document_content(file_path, max_chars=_MAX_EXTRACT_CHARS)
    parts = [original_name or file_path.name, extracted.text_excerpt[:4000]]
    return fold_ocr_spacing("\n".join(part for part in parts if part).strip())


def _load_validation_examples(entries: list[ValidationSetEntry]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for entry in entries:
        file_path = resolve_validation_file(entry.file)
        if not file_path.exists():
            raise SystemExit(f"Validation file not found: {entry.file}")
        examples.append(
            {
                "entry": entry,
                "file_path": file_path,
                "text": _extract_feature_text(file_path, original_name=entry.file),
            }
        )
    return examples


def _resolve_training_path(repo_root: Path, record: TrainingPoolRecord) -> Path:
    path = Path(record.path).expanduser()
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def _load_training_examples(repo_root: Path, records: list[TrainingPoolRecord]) -> tuple[list[dict[str, Any]], list[str]]:
    examples: list[dict[str, Any]] = []
    skipped: list[str] = []
    for record in records:
        path = _resolve_training_path(repo_root, record)
        if not path.exists():
            skipped.append(f"missing_file:{record.original_filename}")
            continue
        try:
            text = _extract_feature_text(path, original_name=record.original_filename)
        except Exception as exc:  # pragma: no cover - exercised only on malformed real files
            skipped.append(f"extract_error:{record.original_filename}:{exc}")
            continue
        examples.append(
            {
                "record": record,
                "file_path": path,
                "text": text,
            }
        )
    return examples, skipped


def _baseline_predict(profile: dict[str, Any], file_path: Path, excerpt: str, legacy_map: dict[str, str]) -> tuple[str, str]:
    result = classify(profile=profile, source_path=file_path, text_excerpt=excerpt)
    area_key = str(result.get("area_key") or "").strip()
    predicted_domain = legacy_map.get(area_key, area_key)
    predicted_type = str(result.get("document_type") or "").strip()
    return predicted_domain, predicted_type


def _bootstrap_predict(profile: dict[str, Any], file_path: Path, excerpt: str) -> tuple[str, str]:
    result = classify_bootstrap(profile=profile, source_path=file_path, text_excerpt=excerpt)
    return (
        str(result.get("business_domain") or result.get("area_key") or "").strip(),
        str(result.get("document_type") or "").strip(),
    )


def _summarize_predictions(mode: str, results: list[dict[str, Any]], *, extra_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    total = len(results)
    business_domain_metrics = _classification_metrics(
        results,
        expected_key="expected_business_domain",
        predicted_key="predicted_business_domain",
    )
    document_type_metrics = _classification_metrics(
        results,
        expected_key="expected_document_type",
        predicted_key="predicted_document_type",
    )
    summary = {
        "mode": mode,
        "role": _mode_role(mode),
        "total_labeled": total,
        "business_domain_accuracy": round(sum(1 for row in results if row["business_domain_ok"]) / total, 4) if total else 0.0,
        "business_domain_macro_f1": business_domain_metrics["macro_f1"],
        "business_domain_recall_by_class": business_domain_metrics["recall_by_class"],
        "business_domain_confusion_matrix": business_domain_metrics["confusion_matrix"],
        "document_type_accuracy": round(sum(1 for row in results if row["document_type_ok"]) / total, 4) if total else 0.0,
        "document_type_macro_f1": document_type_metrics["macro_f1"],
        "document_type_recall_by_class": document_type_metrics["recall_by_class"],
        "document_type_confusion_matrix": document_type_metrics["confusion_matrix"],
        "exact_match_accuracy": round(sum(1 for row in results if row["exact_ok"]) / total, 4) if total else 0.0,
    }
    if extra_summary:
        summary.update(extra_summary)
    return summary


def _evaluate_rule_mode(
    mode: str,
    *,
    profile: dict[str, Any],
    validation_examples: list[dict[str, Any]],
    legacy_map: dict[str, str],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for example in validation_examples:
        entry = example["entry"]
        file_path = example["file_path"]
        excerpt = example["text"]
        if mode == "baseline":
            predicted_domain, predicted_type = _baseline_predict(profile, file_path, excerpt, legacy_map)
        else:
            predicted_domain, predicted_type = _bootstrap_predict(profile, file_path, excerpt)
        results.append(
            {
                "file": entry.file,
                "expected_business_domain": entry.business_domain,
                "predicted_business_domain": predicted_domain,
                "expected_document_type": entry.document_type,
                "predicted_document_type": predicted_type,
                "business_domain_ok": predicted_domain == entry.business_domain,
                "document_type_ok": predicted_type == entry.document_type,
                "exact_ok": predicted_domain == entry.business_domain and predicted_type == entry.document_type,
            }
        )
    return {
        "summary": _summarize_predictions(mode, results, extra_summary={"legacy_area_map_entries": len(legacy_map)} if mode == "baseline" else None),
        "results": results,
    }


def compute_supervised_gate(
    records: list[TrainingPoolRecord],
    *,
    min_training_docs: int = _SPARSE_MIN_TRAINING_DOCS,
    min_docs_per_class: int = _SPARSE_MIN_DOCS_PER_CLASS,
) -> dict[str, Any]:
    business_domain_counts = Counter(record.business_domain for record in records if record.business_domain.strip())
    document_type_counts = Counter(record.document_type for record in records if record.document_type.strip())
    reasons: list[str] = []
    if _SKLEARN_IMPORT_ERROR:
        reasons.append(f"sklearn_unavailable:{_SKLEARN_IMPORT_ERROR}")
    if not records:
        reasons.append("training_pool_empty")
    if len(records) < min_training_docs:
        reasons.append(f"training_pool_total_below_min:{len(records)}<{min_training_docs}")
    if len(business_domain_counts) < 2:
        reasons.append("business_domain_classes_below_min:2")
    if len(document_type_counts) < 2:
        reasons.append("document_type_classes_below_min:2")
    if business_domain_counts and min(business_domain_counts.values()) < min_docs_per_class:
        reasons.append(
            f"business_domain_min_support_below_min:{min(business_domain_counts.values())}<{min_docs_per_class}"
        )
    if document_type_counts and min(document_type_counts.values()) < min_docs_per_class:
        reasons.append(
            f"document_type_min_support_below_min:{min(document_type_counts.values())}<{min_docs_per_class}"
        )
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "min_training_docs": min_training_docs,
        "min_docs_per_class": min_docs_per_class,
        "total_records": len(records),
        "business_domain_counts": dict(sorted(business_domain_counts.items())),
        "document_type_counts": dict(sorted(document_type_counts.items())),
    }


def _sparse_pipeline(family: str) -> Pipeline:
    if _SKLEARN_IMPORT_ERROR:
        raise RuntimeError(_SKLEARN_IMPORT_ERROR)
    classifier: Any
    if family == "sparse_logreg":
        classifier = LogisticRegression(max_iter=3000, class_weight="balanced")
    elif family == "sparse_linear_svc":
        classifier = LinearSVC(class_weight="balanced")
    else:  # pragma: no cover - protected by CLI choices and tests
        raise ValueError(f"unsupported supervised family: {family}")
    return Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    lowercase=True,
                    strip_accents="unicode",
                    sublinear_tf=True,
                ),
            ),
            ("classifier", classifier),
        ]
    )


def benchmark_sparse_candidates(
    *,
    repo_root: Path,
    validation_examples: list[dict[str, Any]],
    training_records: list[TrainingPoolRecord],
    min_training_docs: int = _SPARSE_MIN_TRAINING_DOCS,
    min_docs_per_class: int = _SPARSE_MIN_DOCS_PER_CLASS,
) -> dict[str, Any]:
    gate = compute_supervised_gate(
        training_records,
        min_training_docs=min_training_docs,
        min_docs_per_class=min_docs_per_class,
    )
    output: dict[str, Any] = {"gate": gate, "benchmarks": {}}
    if not gate["eligible"]:
        for family in _SPARSE_MODEL_FAMILIES:
            output["benchmarks"][family] = {
                "summary": {
                    "mode": family,
                    "role": _mode_role(family),
                    "skipped": True,
                    "skip_reason": gate["reasons"],
                    "total_labeled": len(validation_examples),
                },
                "results": [],
            }
        return output

    training_examples, skipped = _load_training_examples(repo_root, training_records)
    if skipped:
        gate = compute_supervised_gate(
            [example["record"] for example in training_examples],
            min_training_docs=min_training_docs,
            min_docs_per_class=min_docs_per_class,
        )
        output["gate"] = gate
        output["training_examples_skipped"] = skipped
        if not gate["eligible"]:
            for family in _SPARSE_MODEL_FAMILIES:
                output["benchmarks"][family] = {
                    "summary": {
                        "mode": family,
                        "role": _mode_role(family),
                        "skipped": True,
                        "skip_reason": gate["reasons"],
                        "total_labeled": len(validation_examples),
                    },
                    "results": [],
                }
            return output

    train_texts = [example["text"] for example in training_examples]
    train_business_domains = [example["record"].business_domain for example in training_examples]
    train_document_types = [example["record"].document_type for example in training_examples]
    validation_texts = [example["text"] for example in validation_examples]

    for family in _SPARSE_MODEL_FAMILIES:
        domain_model = _sparse_pipeline(family)
        type_model = _sparse_pipeline(family)
        domain_model.fit(train_texts, train_business_domains)
        type_model.fit(train_texts, train_document_types)
        predicted_domains = domain_model.predict(validation_texts)
        predicted_types = type_model.predict(validation_texts)

        results: list[dict[str, Any]] = []
        for example, predicted_domain, predicted_type in zip(
            validation_examples,
            predicted_domains,
            predicted_types,
            strict=True,
        ):
            entry = example["entry"]
            results.append(
                {
                    "file": entry.file,
                    "expected_business_domain": entry.business_domain,
                    "predicted_business_domain": str(predicted_domain),
                    "expected_document_type": entry.document_type,
                    "predicted_document_type": str(predicted_type),
                    "business_domain_ok": str(predicted_domain) == entry.business_domain,
                    "document_type_ok": str(predicted_type) == entry.document_type,
                    "exact_ok": str(predicted_domain) == entry.business_domain and str(predicted_type) == entry.document_type,
                }
            )
        output["benchmarks"][family] = {
            "summary": _summarize_predictions(
                family,
                results,
                extra_summary={
                    "training_pool_records": len(training_examples),
                    "validation_records": len(validation_examples),
                    "vectorizer": "tfidf_char_wb_3_5",
                },
            ),
            "results": results,
        }
    return output


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
                "legacy_area_map_entries",
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
    parser = argparse.ArgumentParser(description="Benchmark sobre config/validation_set/expected.json com gates explícitos.")
    parser.add_argument(
        "--mode",
        choices=["baseline", "bootstrap", "sparse_logreg", "sparse_linear_svc", "all"],
        default="bootstrap",
        help="baseline usa o classificador legado como referência; bootstrap é o baseline operacional atual; sparse_* avalia candidatos supervisionados no validation_set usando training_pool.",
    )
    parser.add_argument(
        "--profile",
        default="config/templates/default.json",
        help="Profile/template JSON usado na classificação",
    )
    parser.add_argument(
        "--legacy-area-map",
        default="config/validation_set/legacy_area_to_business_domain.json",
        help="Mapeamento opcional area_key legado -> business_domain para benchmark baseline",
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
    profile = _load_profile((repo_root / args.profile).resolve())
    legacy_map = _load_legacy_map((repo_root / args.legacy_area_map).resolve())
    labeled_entries = [entry for entry in load_validation_set() if entry.is_labeled()]
    if not labeled_entries:
        raise SystemExit("Validation set has no labeled entries.")

    validation_examples = _load_validation_examples(labeled_entries)
    training_records = load_training_pool_records()
    dataset_integrity = compute_dataset_integrity(
        repo_root=repo_root,
        validation_examples=validation_examples,
        training_records=training_records,
    )
    if dataset_integrity["status"] == "error":
        print(
            json.dumps(
                {
                    "operational_classifier_mode": "bootstrap",
                    "dataset_integrity": dataset_integrity,
                    "training_pool_records": len(training_records),
                    "benchmarks": {},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    supervised = benchmark_sparse_candidates(
        repo_root=repo_root,
        validation_examples=validation_examples,
        training_records=training_records,
        min_training_docs=args.min_training_docs,
        min_docs_per_class=args.min_docs_per_class,
    )

    benchmarks: dict[str, Any] = {}
    if args.mode in {"baseline", "all"}:
        benchmarks["baseline"] = _evaluate_rule_mode(
            "baseline",
            profile=profile,
            validation_examples=validation_examples,
            legacy_map=legacy_map,
        )
    if args.mode in {"bootstrap", "all"}:
        benchmarks["bootstrap"] = _evaluate_rule_mode(
            "bootstrap",
            profile=profile,
            validation_examples=validation_examples,
            legacy_map=legacy_map,
        )
    if args.mode in _SPARSE_MODEL_FAMILIES:
        benchmarks[args.mode] = supervised["benchmarks"][args.mode]
    elif args.mode == "all":
        benchmarks.update(supervised["benchmarks"])

    payload = {
        "operational_classifier_mode": "bootstrap",
        "dataset_integrity": dataset_integrity,
        "gates": {"supervised": supervised["gate"]},
        "training_pool_records": len(training_records),
        "benchmarks": benchmarks,
    }
    if "training_examples_skipped" in supervised:
        payload["training_examples_skipped"] = supervised["training_examples_skipped"]

    if args.json or args.mode in {"all", "sparse_logreg", "sparse_linear_svc"}:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_render_text(benchmarks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
