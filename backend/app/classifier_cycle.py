from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from .classification_bootstrap import classify_bootstrap
from .classifier_registry import (
    DEFAULT_CLASSIFIER_MODE,
    ClassifierRegistry,
    ClassifierSummary,
    classifier_model_path,
    load_classifier_registry,
    save_classifier_registry,
    save_classifier_report,
    summary_from_benchmark,
)
from .classifier_supervised import (
    SPARSE_MODEL_FAMILIES,
    SPARSE_MIN_DOCS_PER_CLASS,
    SPARSE_MIN_TRAINING_DOCS,
    compute_supervised_gate,
    fit_sparse_artifact,
    predict_labels_from_artifact,
    save_sparse_artifact,
)
from .document_extractor import extract_document_content
from .evaluation_dataset import (
    TrainingPoolRecord,
    ValidationSetEntry,
    load_training_pool_records,
    load_validation_set,
    resolve_validation_file,
)
from .profile_schema_v2 import ProjectProfileV2
from .project_profile import profile_v2_to_runtime
from .utils import fold_ocr_spacing, normalize_text, sha256_file, utc_now_iso

_MAX_EXTRACT_CHARS = 50_000

ProgressCallback = Callable[[dict[str, Any]], None]


def _emit_progress(progress_callback: ProgressCallback | None, **payload: Any) -> None:
    if progress_callback:
        progress_callback(payload)


def mode_role(mode: str) -> str:
    if mode == "bootstrap":
        return "operational_baseline"
    return "benchmark_candidate"


def _normalized_file_key(value: str) -> str:
    return normalize_text(Path(value).name)


def classification_metrics(
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


def summarize_predictions(
    mode: str,
    results: list[dict[str, Any]],
    *,
    extra_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = len(results)
    business_domain_metrics = classification_metrics(
        results,
        expected_key="expected_business_domain",
        predicted_key="predicted_business_domain",
    )
    document_type_metrics = classification_metrics(
        results,
        expected_key="expected_document_type",
        predicted_key="predicted_document_type",
    )
    summary = {
        "mode": mode,
        "role": mode_role(mode),
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
        path = resolve_training_path(repo_root, record)
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


def load_profile_runtime(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.setdefault("project_id", "validation_set")
    raw.setdefault("project_label", "Validation Set")
    raw.setdefault("project_root", str(path.parent.parent))
    profile = ProjectProfileV2.model_validate(raw)
    return profile_v2_to_runtime(profile, Path(profile.project_root))


def extract_feature_text(file_path: Path, *, original_name: str | None = None) -> str:
    extracted = extract_document_content(file_path, max_chars=_MAX_EXTRACT_CHARS)
    parts = [original_name or file_path.name, extracted.text_excerpt[:4000]]
    return fold_ocr_spacing("\n".join(part for part in parts if part).strip())


def load_validation_examples(entries: list[ValidationSetEntry]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for entry in entries:
        file_path = resolve_validation_file(entry.file)
        if not file_path.exists():
            raise ValueError(f"Validation file not found: {entry.file}")
        examples.append(
            {
                "entry": entry,
                "file_path": file_path,
                "text": extract_feature_text(file_path, original_name=entry.file),
            }
        )
    return examples


def resolve_training_path(repo_root: Path, record: TrainingPoolRecord) -> Path:
    path = Path(record.path).expanduser()
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def load_training_examples(repo_root: Path, records: list[TrainingPoolRecord]) -> tuple[list[dict[str, Any]], list[str]]:
    examples: list[dict[str, Any]] = []
    skipped: list[str] = []
    for record in records:
        path = resolve_training_path(repo_root, record)
        if not path.exists():
            skipped.append(f"missing_file:{record.original_filename}")
            continue
        try:
            text = extract_feature_text(path, original_name=record.original_filename)
        except Exception as exc:  # pragma: no cover - only exercised with malformed real files
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


def evaluate_bootstrap(
    *,
    profile: dict[str, Any],
    validation_examples: list[dict[str, Any]],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for example in validation_examples:
        entry = example["entry"]
        file_path = example["file_path"]
        excerpt = example["text"]
        predicted = classify_bootstrap(profile=profile, source_path=file_path, text_excerpt=excerpt)
        predicted_domain = str(predicted.get("business_domain") or "").strip()
        predicted_type = str(predicted.get("document_type") or "").strip()
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
    return {"summary": summarize_predictions("bootstrap", results), "results": results}


def benchmark_sparse_candidates(
    *,
    repo_root: Path,
    validation_examples: list[dict[str, Any]],
    training_records: list[TrainingPoolRecord],
    min_training_docs: int = SPARSE_MIN_TRAINING_DOCS,
    min_docs_per_class: int = SPARSE_MIN_DOCS_PER_CLASS,
    include_artifacts: bool = False,
) -> dict[str, Any]:
    gate = compute_supervised_gate(
        training_records,
        min_training_docs=min_training_docs,
        min_docs_per_class=min_docs_per_class,
    )
    output: dict[str, Any] = {"gate": gate, "benchmarks": {}}
    if not gate["eligible"]:
        for family in SPARSE_MODEL_FAMILIES:
            output["benchmarks"][family] = {
                "summary": {
                    "mode": family,
                    "role": mode_role(family),
                    "skipped": True,
                    "skip_reason": gate["reasons"],
                    "total_labeled": len(validation_examples),
                },
                "results": [],
            }
        return output

    training_examples, skipped = load_training_examples(repo_root, training_records)
    if skipped:
        gate = compute_supervised_gate(
            [example["record"] for example in training_examples],
            min_training_docs=min_training_docs,
            min_docs_per_class=min_docs_per_class,
        )
        output["gate"] = gate
        output["training_examples_skipped"] = skipped
        if not gate["eligible"]:
            for family in SPARSE_MODEL_FAMILIES:
                output["benchmarks"][family] = {
                    "summary": {
                        "mode": family,
                        "role": mode_role(family),
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

    if include_artifacts:
        output["artifacts"] = {}

    for family in SPARSE_MODEL_FAMILIES:
        artifact = fit_sparse_artifact(
            family=family,
            train_texts=train_texts,
            train_business_domains=train_business_domains,
            train_document_types=train_document_types,
            training_pool_records=len(training_examples),
        )
        if include_artifacts:
            output["artifacts"][family] = artifact

        results: list[dict[str, Any]] = []
        for example in validation_examples:
            entry = example["entry"]
            predictions = predict_labels_from_artifact(artifact, example["text"])
            predicted_domain = str(predictions["business_domain"]["label"])
            predicted_type = str(predictions["document_type"]["label"])
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

        output["benchmarks"][family] = {
            "summary": summarize_predictions(
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


def _summary_threshold_ok(summary: ClassifierSummary, registry: ClassifierRegistry) -> bool:
    gates = registry.promotion_gates
    return (
        not summary.skipped
        and summary.business_domain_accuracy >= gates.min_business_domain_accuracy
        and summary.document_type_accuracy >= gates.min_document_type_accuracy
        and summary.exact_match_accuracy >= gates.min_exact_match_accuracy
    )


def _summary_rank(summary: ClassifierSummary) -> tuple[float, float, float]:
    return (
        summary.exact_match_accuracy,
        summary.business_domain_accuracy,
        summary.document_type_accuracy,
    )


def choose_champion_mode(
    *,
    registry: ClassifierRegistry,
    benchmarks: dict[str, Any],
    training_pool_records: int,
) -> tuple[str, ClassifierSummary]:
    current_champion = registry.champion_mode if registry.champion_mode in benchmarks else DEFAULT_CLASSIFIER_MODE
    summaries: dict[str, ClassifierSummary] = {}
    for mode, payload in benchmarks.items():
        summary = summary_from_benchmark(
            mode,
            payload.get("summary") or {},
            training_pool_records=training_pool_records,
        )
        if _summary_threshold_ok(summary, registry):
            summaries[mode] = summary

    bootstrap_summary = summaries.get("bootstrap")
    if not summaries:
        if registry.champion_summary:
            return registry.champion_mode, registry.champion_summary
        fallback = summary_from_benchmark(
            "bootstrap",
            (benchmarks.get("bootstrap") or {}).get("summary") or {},
            training_pool_records=training_pool_records,
        )
        return "bootstrap", fallback

    best_mode, best_summary = sorted(
        summaries.items(),
        key=lambda item: (
            -_summary_rank(item[1])[0],
            -_summary_rank(item[1])[1],
            -_summary_rank(item[1])[2],
            item[0] != current_champion if registry.promotion_gates.prefer_current_champion_on_tie else False,
            item[0],
        ),
    )[0]

    if best_summary.skipped and bootstrap_summary:
        return "bootstrap", bootstrap_summary
    return best_mode, best_summary


def evaluate_classifier_cycle(
    *,
    repo_root: Path,
    profile_path: Path,
    min_training_docs: int = SPARSE_MIN_TRAINING_DOCS,
    min_docs_per_class: int = SPARSE_MIN_DOCS_PER_CLASS,
    include_artifacts: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    _emit_progress(progress_callback, phase="loading_datasets", progress_current=1, progress_total=5)
    profile = load_profile_runtime(profile_path)
    labeled_entries = [entry for entry in load_validation_set() if entry.is_labeled()]
    if not labeled_entries:
        raise ValueError("Validation set has no labeled entries.")

    validation_examples = load_validation_examples(labeled_entries)
    training_records = load_training_pool_records()
    dataset_integrity = compute_dataset_integrity(
        repo_root=repo_root,
        validation_examples=validation_examples,
        training_records=training_records,
    )
    if dataset_integrity["status"] == "error":
        return {
            "generated_at": utc_now_iso(),
            "operational_classifier_mode": DEFAULT_CLASSIFIER_MODE,
            "dataset_integrity": dataset_integrity,
            "gates": {
                "supervised": compute_supervised_gate(
                    training_records,
                    min_training_docs=min_training_docs,
                    min_docs_per_class=min_docs_per_class,
                )
            },
            "training_pool_records": len(training_records),
            "benchmarks": {},
        }

    _emit_progress(progress_callback, phase="benchmark_bootstrap", progress_current=2, progress_total=5)
    bootstrap = evaluate_bootstrap(profile=profile, validation_examples=validation_examples)
    _emit_progress(progress_callback, phase="benchmark_supervised", progress_current=3, progress_total=5)
    supervised = benchmark_sparse_candidates(
        repo_root=repo_root,
        validation_examples=validation_examples,
        training_records=training_records,
        min_training_docs=min_training_docs,
        min_docs_per_class=min_docs_per_class,
        include_artifacts=include_artifacts,
    )
    benchmarks: dict[str, Any] = {
        "bootstrap": bootstrap,
        **supervised["benchmarks"],
    }
    payload = {
        "generated_at": utc_now_iso(),
        "operational_classifier_mode": DEFAULT_CLASSIFIER_MODE,
        "dataset_integrity": dataset_integrity,
        "gates": {"supervised": supervised["gate"]},
        "training_pool_records": len(training_records),
        "benchmarks": benchmarks,
    }
    if "training_examples_skipped" in supervised:
        payload["training_examples_skipped"] = supervised["training_examples_skipped"]
    if include_artifacts:
        payload["artifacts"] = supervised.get("artifacts", {})
    return payload


def run_classifier_cycle(
    *,
    profile_path: str | Path = "config/templates/default.json",
    min_training_docs: int = SPARSE_MIN_TRAINING_DOCS,
    min_docs_per_class: int = SPARSE_MIN_DOCS_PER_CLASS,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[2]
    profile_path_obj = (repo / profile_path).resolve() if not Path(profile_path).is_absolute() else Path(profile_path)
    registry = load_classifier_registry()
    registry.latest_cycle_status = "running"
    registry.latest_cycle_started_at = utc_now_iso()
    registry.latest_cycle_finished_at = None
    registry.latest_cycle_error = None
    save_classifier_registry(registry)

    try:
        report = evaluate_classifier_cycle(
            repo_root=repo,
            profile_path=profile_path_obj,
            min_training_docs=min_training_docs,
            min_docs_per_class=min_docs_per_class,
            include_artifacts=True,
            progress_callback=progress_callback,
        )
        if (report.get("dataset_integrity") or {}).get("status") == "error":
            raise ValueError("dataset_integrity_error")
        artifacts = dict(report.pop("artifacts", {}) or {})
        _emit_progress(progress_callback, phase="persisting_artifacts", progress_current=4, progress_total=5)
        for family, artifact in artifacts.items():
            save_sparse_artifact(classifier_model_path(family), artifact)

        _emit_progress(progress_callback, phase="promoting_champion", progress_current=5, progress_total=5)
        champion_mode, champion_summary = choose_champion_mode(
            registry=registry,
            benchmarks=report["benchmarks"],
            training_pool_records=int(report.get("training_pool_records") or 0),
        )
        report["champion"] = {
            "mode": champion_mode,
            "summary": champion_summary.model_dump(mode="json"),
            "promotion_policy": registry.promotion_policy,
        }
        report["operational_classifier_mode"] = champion_mode
        report["model_artifacts"] = {
            family: {"path": str(classifier_model_path(family))}
            for family in SPARSE_MODEL_FAMILIES
            if classifier_model_path(family).exists()
        }
        report_id = save_classifier_report(report)

        registry.champion_mode = champion_mode
        registry.champion_report_id = report_id
        registry.latest_report_id = report_id
        registry.champion_summary = champion_summary
        registry.latest_cycle_status = "succeeded"
        registry.latest_cycle_finished_at = utc_now_iso()
        save_classifier_registry(registry)

        report["report_id"] = report_id
        return report
    except Exception as exc:
        registry.latest_cycle_status = "failed"
        registry.latest_cycle_finished_at = utc_now_iso()
        registry.latest_cycle_error = str(exc)
        save_classifier_registry(registry)
        raise
