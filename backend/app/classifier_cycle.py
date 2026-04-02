from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from .classification_bootstrap import classify_bootstrap
from .classifier_registry import (
    DEFAULT_CLASSIFIER_MODE,
    SUPPORTED_CLASSIFIER_MODES,
    ClassifierRegistry,
    ClassifierSummary,
    classifier_model_path,
    load_classifier_registry,
    load_classifier_report,
    save_classifier_registry,
    save_classifier_report,
    summary_from_benchmark,
)
from .classifier_setfit import (
    SETFIT_MIN_DOCS_PER_CLASS,
    SETFIT_MIN_TRAINING_DOCS,
    compute_setfit_gate,
    fit_setfit_artifact,
    predict_labels_from_setfit_artifact,
    save_setfit_artifact,
    setfit_import_error,
)
from .classifier_supervised import (
    SPARSE_MODEL_FAMILIES,
    SPARSE_MIN_DOCS_PER_CLASS,
    SPARSE_MIN_TRAINING_DOCS,
    compute_supervised_gate,
    fit_sparse_artifact,
    predict_labels_from_artifact,
    save_sparse_artifact,
    sklearn_import_error,
)
from .document_extractor import extract_document_content
from .evaluation_dataset import (
    TrainingPoolRecord,
    ValidationSetEntry,
    classifier_datasets_root,
    load_split_as_training_records,
    load_split_as_validation_entries,
    load_training_pool_records,
    load_validation_set,
    resolve_corpus_validation_file,
    resolve_validation_file,
    splits_available,
    training_pool_records_path,
    validation_set_expected_path,
)
from .profile_schema_v2 import ProjectProfileV2
from .project_profile import profile_v2_to_runtime
from .utils import fold_ocr_spacing, normalize_text, sha256_file, utc_now_iso

_MAX_EXTRACT_CHARS = 20_000

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
        validation_digest = str(example.get("sha256") or sha256_file(file_path))
        validation_by_sha[validation_digest].append(entry.file)
        validation_by_name[_normalized_file_key(entry.file)].append(entry.file)

    overlap_sha256: list[dict[str, Any]] = []
    name_collisions: list[dict[str, Any]] = []
    unresolved_training_paths: list[dict[str, Any]] = []
    for record in training_records:
        if record.synthetic_text:
            continue
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

        training_sha = str(record.sha256 or sha256_file(path))
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
    parts = [original_name or file_path.name, extracted.text_excerpt]
    return fold_ocr_spacing("\n".join(part for part in parts if part).strip())


def load_validation_examples(entries: list[ValidationSetEntry]) -> list[dict[str, Any]]:
    use_corpus = splits_available()
    examples: list[dict[str, Any]] = []
    for entry in entries:
        file_path = (
            resolve_corpus_validation_file(entry.file)
            if use_corpus
            else resolve_validation_file(entry.file)
        )
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
        dataset_candidate = (classifier_datasets_root() / path).resolve()
        if dataset_candidate.exists() or (path.parts and path.parts[0] == "training_pool"):
            return dataset_candidate
        path = (repo_root / path).resolve()
    return path


def load_training_examples(repo_root: Path, records: list[TrainingPoolRecord]) -> tuple[list[dict[str, Any]], list[str]]:
    examples: list[dict[str, Any]] = []
    skipped: list[str] = []
    for record in records:
        if record.synthetic_text:
            examples.append(
                {
                    "record": record,
                    "file_path": None,
                    "sha256": "",
                    "text": record.synthetic_text,
                }
            )
            continue
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
                "sha256": str(record.sha256 or sha256_file(path)),
                "text": text,
            }
        )
    return examples, skipped


def build_dataset_manifest(
    *,
    profile_path: Path,
    validation_examples: list[dict[str, Any]],
    training_records: list[TrainingPoolRecord],
    resolved_training_examples: list[dict[str, Any]] | None = None,
    skipped_training_examples: list[str] | None = None,
) -> dict[str, Any]:
    expected_path = validation_set_expected_path()
    records_path = training_pool_records_path()
    resolved_examples = resolved_training_examples or []
    skipped = skipped_training_examples or []
    return {
        "datasets_root": str(classifier_datasets_root()),
        "profile_path": str(profile_path),
        "validation_set": {
            "expected_path": str(expected_path),
            "expected_sha256": sha256_file(expected_path) if expected_path.exists() else "",
            "labeled_records": len(validation_examples),
            "files": [
                {
                    "file": example["entry"].file,
                    "path": str(example["file_path"]),
                    "sha256": str(example.get("sha256") or sha256_file(example["file_path"])),
                }
                for example in validation_examples
            ],
        },
        "training_pool": {
            "records_path": str(records_path),
            "records_sha256": sha256_file(records_path) if records_path.exists() else "",
            "jsonl_records": len(training_records),
            "resolved_examples": len(resolved_examples),
            "skipped_examples": len(skipped),
            "files": [
                {
                    "doc_id": example["record"].doc_id,
                    "project_id": example["record"].project_id,
                    "original_filename": example["record"].original_filename,
                    "path": str(example["file_path"]),
                    "source_path": str(example["record"].source_path or ""),
                    "sha256": str(example.get("sha256") or example["record"].sha256 or ""),
                }
                for example in resolved_examples
            ],
        },
    }


def benchmark_llm_candidate(
    *,
    profile: dict[str, Any],
    validation_examples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Benchmark LLM classification against validation set.

    Calls OpenAI API directly (no MCP dependency). Each document gets
    full text extraction (up to 20000 chars) matching the ingestion path.
    Skips gracefully if API key is not configured.
    """
    import os
    import time

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {
            "summary": {
                "mode": "llm",
                "role": mode_role("llm"),
                "skipped": True,
                "skip_reason": ["llm_api_key_not_configured"],
                "total_labeled": len(validation_examples),
            },
            "results": [],
        }

    from .indexer import read_text_excerpt
    from .orchestrator import _build_project_context
    from .prompts import get_system_prompt_classify

    try:
        from openai import OpenAI
    except ImportError:
        return {
            "summary": {
                "mode": "llm",
                "role": mode_role("llm"),
                "skipped": True,
                "skip_reason": ["openai_not_installed"],
                "total_labeled": len(validation_examples),
            },
            "results": [],
        }

    client = OpenAI(api_key=api_key)
    system_prompt = get_system_prompt_classify()
    project_context = _build_project_context(profile)
    context_block = f"\n\n{project_context}\n\n" if project_context else "\n\n"

    provider, model = "openai", os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o-mini")

    results: list[dict[str, Any]] = []
    for example in validation_examples:
        entry = example["entry"]
        file_path = example["file_path"]

        # Extract text like ingestion does (20000 chars, not the 8000 feature text)
        try:
            text_excerpt = read_text_excerpt(Path(file_path), limit=20_000)
        except Exception:
            text_excerpt = example.get("text", "")

        user_content = (
            f"Documento: {entry.file}{context_block}Trecho:\n{text_excerpt}\n\n"
            f"Responda em JSON com os campos: business_domain, document_type, confidence, explanation."
        )

        predicted_domain = ""
        predicted_type = ""
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=300,
            )
            raw = resp.choices[0].message.content or "{}"
            parsed = json.loads(raw)
            predicted_domain = str(parsed.get("business_domain", "")).strip()
            predicted_type = str(parsed.get("document_type", "")).strip()
        except Exception:
            pass

        time.sleep(0.15)

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
        "summary": summarize_predictions(
            "llm",
            results,
            extra_summary={"provider": provider, "model": model},
        ),
        "results": results,
    }


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


def _cross_validate_sparse(
    *,
    family: str,
    texts: list[str],
    business_domains: list[str],
    document_types: list[str],
    n_splits: int = 5,
) -> dict[str, Any] | None:
    """Run stratified k-fold CV on training data. Returns None if sklearn unavailable or data insufficient."""
    if sklearn_import_error():
        return None
    from sklearn.model_selection import StratifiedKFold

    combined_labels = [f"{d}|{t}" for d, t in zip(business_domains, document_types, strict=True)]
    label_counts = Counter(combined_labels)
    min_count = min(label_counts.values()) if label_counts else 0
    effective_splits = min(n_splits, min_count) if min_count >= 2 else 0
    if effective_splits < 2:
        return None

    skf = StratifiedKFold(n_splits=effective_splits, shuffle=True, random_state=42)
    fold_domain_acc: list[float] = []
    fold_doctype_acc: list[float] = []
    fold_exact_acc: list[float] = []

    for train_idx, test_idx in skf.split(texts, combined_labels):
        fold_train_texts = [texts[i] for i in train_idx]
        fold_train_domains = [business_domains[i] for i in train_idx]
        fold_train_types = [document_types[i] for i in train_idx]
        fold_test_texts = [texts[i] for i in test_idx]
        fold_test_domains = [business_domains[i] for i in test_idx]
        fold_test_types = [document_types[i] for i in test_idx]

        artifact = fit_sparse_artifact(
            family=family,
            train_texts=fold_train_texts,
            train_business_domains=fold_train_domains,
            train_document_types=fold_train_types,
            training_pool_records=len(fold_train_texts),
        )
        domain_ok = 0
        doctype_ok = 0
        exact_ok = 0
        for text, expected_domain, expected_type in zip(
            fold_test_texts, fold_test_domains, fold_test_types, strict=True
        ):
            predictions = predict_labels_from_artifact(artifact, text)
            pred_domain = str(predictions["business_domain"]["label"])
            pred_type = str(predictions["document_type"]["label"])
            d_ok = pred_domain == expected_domain
            t_ok = pred_type == expected_type
            domain_ok += int(d_ok)
            doctype_ok += int(t_ok)
            exact_ok += int(d_ok and t_ok)

        n = len(fold_test_texts)
        fold_domain_acc.append(domain_ok / n)
        fold_doctype_acc.append(doctype_ok / n)
        fold_exact_acc.append(exact_ok / n)

    def _mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        m = sum(values) / len(values)
        return round((sum((v - m) ** 2 for v in values) / (len(values) - 1)) ** 0.5, 4)

    return {
        "n_splits": effective_splits,
        "business_domain_accuracy_mean": _mean(fold_domain_acc),
        "business_domain_accuracy_std": _std(fold_domain_acc),
        "document_type_accuracy_mean": _mean(fold_doctype_acc),
        "document_type_accuracy_std": _std(fold_doctype_acc),
        "exact_match_accuracy_mean": _mean(fold_exact_acc),
        "exact_match_accuracy_std": _std(fold_exact_acc),
        "fold_scores": [
            {
                "business_domain_accuracy": round(d, 4),
                "document_type_accuracy": round(t, 4),
                "exact_match_accuracy": round(e, 4),
            }
            for d, t, e in zip(fold_domain_acc, fold_doctype_acc, fold_exact_acc, strict=True)
        ],
    }


def benchmark_sparse_candidates(
    *,
    repo_root: Path,
    validation_examples: list[dict[str, Any]],
    training_records: list[TrainingPoolRecord],
    min_training_docs: int = SPARSE_MIN_TRAINING_DOCS,
    min_docs_per_class: int = SPARSE_MIN_DOCS_PER_CLASS,
    include_artifacts: bool = False,
    enabled_families: list[str] | None = None,
    progress_callback: ProgressCallback | None = None,
    progress_step: int = 0,
    progress_total: int = 0,
    partial_benchmarks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    families = enabled_families if enabled_families is not None else list(SPARSE_MODEL_FAMILIES)
    gate = compute_supervised_gate(
        training_records,
        min_training_docs=min_training_docs,
        min_docs_per_class=min_docs_per_class,
    )
    output: dict[str, Any] = {"gate": gate, "benchmarks": {}, "training_examples_resolved": 0}
    if not gate["eligible"]:
        for family in families:
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
    output["training_examples_resolved"] = len(training_examples)
    output["resolved_training_examples"] = [
        {
            "record": example["record"],
            "file_path": example["file_path"],
            "sha256": example["sha256"],
            "text": example["text"],
        }
        for example in training_examples
    ]
    if skipped:
        gate = compute_supervised_gate(
            [example["record"] for example in training_examples],
            min_training_docs=min_training_docs,
            min_docs_per_class=min_docs_per_class,
        )
        output["gate"] = gate
        output["training_examples_skipped"] = skipped
        if not gate["eligible"]:
            for family in families:
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

    for family in families:
        progress_step += 1
        _emit_progress(progress_callback, phase=f"benchmark:{family}", progress_current=progress_step, progress_total=progress_total)
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

        extra = {
            "training_pool_records": len(training_examples),
            "validation_records": len(validation_examples),
            "vectorizer": "tfidf_char_wb_3_5__word_1_2",
        }
        cv_scores = _cross_validate_sparse(
            family=family,
            texts=train_texts,
            business_domains=train_business_domains,
            document_types=train_document_types,
        )
        if cv_scores is not None:
            extra["cv_scores"] = cv_scores

        summary = summarize_predictions(family, results, extra_summary=extra)
        output["benchmarks"][family] = {
            "summary": summary,
            "results": results,
        }
        if partial_benchmarks is not None:
            partial_benchmarks[family] = {"summary": summary}
            _emit_progress(progress_callback, benchmarks=partial_benchmarks)
    return output


def benchmark_setfit_candidate(
    *,
    repo_root: Path,
    validation_examples: list[dict[str, Any]],
    training_records: list[TrainingPoolRecord],
    training_examples: list[dict[str, Any]] | None = None,
    min_training_docs: int = SETFIT_MIN_TRAINING_DOCS,
    min_docs_per_class: int = SETFIT_MIN_DOCS_PER_CLASS,
    include_artifacts: bool = False,
) -> dict[str, Any]:
    gate = compute_setfit_gate(
        training_records,
        min_training_docs=min_training_docs,
        min_docs_per_class=min_docs_per_class,
    )
    output: dict[str, Any] = {"gate": gate, "benchmarks": {}, "training_examples_resolved": 0}
    if not gate["eligible"]:
        output["benchmarks"]["setfit"] = {
            "summary": {
                "mode": "setfit",
                "role": mode_role("setfit"),
                "skipped": True,
                "skip_reason": gate["reasons"],
                "total_labeled": len(validation_examples),
            },
            "results": [],
        }
        return output

    if training_examples is None:
        training_examples, skipped = load_training_examples(repo_root, training_records)
    else:
        skipped = []
    output["training_examples_resolved"] = len(training_examples)

    if skipped:
        gate = compute_setfit_gate(
            [example["record"] for example in training_examples],
            min_training_docs=min_training_docs,
            min_docs_per_class=min_docs_per_class,
        )
        output["gate"] = gate
        if not gate["eligible"]:
            output["benchmarks"]["setfit"] = {
                "summary": {
                    "mode": "setfit",
                    "role": mode_role("setfit"),
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

    artifact = fit_setfit_artifact(
        train_texts=train_texts,
        train_business_domains=train_business_domains,
        train_document_types=train_document_types,
        training_pool_records=len(training_examples),
    )
    if include_artifacts:
        output["artifacts"] = {"setfit": artifact}

    results: list[dict[str, Any]] = []
    for example in validation_examples:
        entry = example["entry"]
        predictions = predict_labels_from_setfit_artifact(artifact, example["text"])
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

    output["benchmarks"]["setfit"] = {
        "summary": summarize_predictions(
            "setfit",
            results,
            extra_summary={
                "training_pool_records": len(training_examples),
                "validation_records": len(validation_examples),
                "vectorizer": "setfit_paraphrase_multilingual",
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
    benchmark_enabled_modes: list[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    _enabled_modes = set(benchmark_enabled_modes) if benchmark_enabled_modes else set(SUPPORTED_CLASSIFIER_MODES)
    sparse_enabled = bool(_enabled_modes & set(SPARSE_MODEL_FAMILIES))
    setfit_enabled = "setfit" in _enabled_modes
    llm_enabled = "llm" in _enabled_modes
    bootstrap_enabled = "bootstrap" in _enabled_modes
    needs_supervised_data = sparse_enabled or setfit_enabled

    # Dynamic step count: 1 per enabled model. No separate loading/persist/promote phases.
    _step = 0
    _total_steps = 0
    if bootstrap_enabled:
        _total_steps += 1
    enabled_sparse_families = [f for f in SPARSE_MODEL_FAMILIES if f in _enabled_modes]
    _total_steps += len(enabled_sparse_families)
    if setfit_enabled:
        _total_steps += 1
    if llm_enabled:
        _total_steps += 1
    if _total_steps == 0:
        _total_steps = 1  # safety fallback

    profile = load_profile_runtime(profile_path)
    use_corpus = splits_available()
    if use_corpus:
        labeled_entries = [e for e in load_split_as_validation_entries("validation") if e.is_labeled()]
    else:
        labeled_entries = [entry for entry in load_validation_set() if entry.is_labeled()]
    if not labeled_entries:
        raise ValueError("Validation set has no labeled entries.")

    validation_examples = load_validation_examples(labeled_entries)

    if needs_supervised_data:
        training_records = load_split_as_training_records("train") if use_corpus else load_training_pool_records()
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
                "dataset_manifest": build_dataset_manifest(
                    profile_path=profile_path,
                    validation_examples=validation_examples,
                    training_records=training_records,
                ),
                "gates": {
                    "supervised": compute_supervised_gate(
                        training_records,
                        min_training_docs=min_training_docs,
                        min_docs_per_class=min_docs_per_class,
                    )
                },
                "training_pool_records_jsonl": len(training_records),
                "training_pool_records_resolved": 0,
                "training_pool_records": len(training_records),
                "training_examples_skipped_count": 0,
                "benchmarks": {},
            }
    else:
        training_records = []
        dataset_integrity = {"status": "ok", "skipped": True, "reason": "no_supervised_modes_enabled"}

    _partial_benchmarks: dict[str, Any] = {}

    bootstrap: dict[str, Any] = {}
    if bootstrap_enabled:
        _step += 1
        _emit_progress(progress_callback, phase="baseline:bootstrap", progress_current=_step, progress_total=_total_steps)
        bootstrap = evaluate_bootstrap(profile=profile, validation_examples=validation_examples)
        _partial_benchmarks["bootstrap"] = {"summary": bootstrap["summary"]}
        _emit_progress(progress_callback, benchmarks=_partial_benchmarks)
    else:
        bootstrap = {
            "summary": {
                "mode": "bootstrap",
                "role": mode_role("bootstrap"),
                "skipped": True,
                "skip_reason": ["disabled_by_user"],
                "total_labeled": len(validation_examples),
            },
            "results": [],
        }

    if sparse_enabled:
        supervised = benchmark_sparse_candidates(
            repo_root=repo_root,
            validation_examples=validation_examples,
            training_records=training_records,
            min_training_docs=min_training_docs,
            min_docs_per_class=min_docs_per_class,
            include_artifacts=include_artifacts,
            enabled_families=enabled_sparse_families,
            progress_callback=progress_callback,
            progress_step=_step,
            progress_total=_total_steps,
            partial_benchmarks=_partial_benchmarks,
        )
        _step += len(enabled_sparse_families)
        # Add skipped entries for disabled sparse families
        for family in SPARSE_MODEL_FAMILIES:
            if family not in enabled_sparse_families and family not in supervised.get("benchmarks", {}):
                supervised.setdefault("benchmarks", {})[family] = {
                    "summary": {
                        "mode": family,
                        "role": mode_role(family),
                        "skipped": True,
                        "skip_reason": ["disabled_by_user"],
                        "total_labeled": len(validation_examples),
                    },
                    "results": [],
                }
    else:
        supervised = {
            "gate": {"eligible": False, "reasons": ["disabled_by_user"]},
            "benchmarks": {
                family: {
                    "summary": {
                        "mode": family,
                        "role": mode_role(family),
                        "skipped": True,
                        "skip_reason": ["disabled_by_user"],
                        "total_labeled": len(validation_examples),
                    },
                    "results": [],
                }
                for family in SPARSE_MODEL_FAMILIES
            },
        }
    resolved_training_examples = list(supervised.pop("resolved_training_examples", []))
    skipped_training_examples = list(supervised.get("training_examples_skipped", []) or [])

    setfit_result: dict[str, Any] = {"gate": {"eligible": False, "reasons": []}, "benchmarks": {}}
    if setfit_enabled:
        _step += 1
        _emit_progress(progress_callback, phase="benchmark:setfit", progress_current=_step, progress_total=_total_steps)
        if not setfit_import_error():
            setfit_result = benchmark_setfit_candidate(
                repo_root=repo_root,
                validation_examples=validation_examples,
                training_records=training_records,
                training_examples=resolved_training_examples or None,
                include_artifacts=include_artifacts,
            )
        else:
            setfit_result["benchmarks"]["setfit"] = {
                "summary": {
                    "mode": "setfit",
                    "role": mode_role("setfit"),
                    "skipped": True,
                    "skip_reason": [f"setfit_unavailable:{setfit_import_error()}"],
                    "total_labeled": len(validation_examples),
                },
                "results": [],
            }
        setfit_summary = (setfit_result.get("benchmarks", {}).get("setfit", {}) or {}).get("summary")
        if setfit_summary:
            _partial_benchmarks["setfit"] = {"summary": setfit_summary}
            _emit_progress(progress_callback, benchmarks=_partial_benchmarks)
    else:
        setfit_result["benchmarks"]["setfit"] = {
            "summary": {
                "mode": "setfit",
                "role": mode_role("setfit"),
                "skipped": True,
                "skip_reason": ["disabled_by_user"],
                "total_labeled": len(validation_examples),
            },
            "results": [],
        }

    llm_result: dict[str, Any] = {}
    if llm_enabled:
        _step += 1
        _emit_progress(progress_callback, phase="benchmark:llm", progress_current=_step, progress_total=_total_steps)
        llm_result = benchmark_llm_candidate(profile=profile, validation_examples=validation_examples)
        llm_summary = llm_result.get("summary")
        if llm_summary:
            _partial_benchmarks["llm"] = {"summary": llm_summary}
            _emit_progress(progress_callback, benchmarks=_partial_benchmarks)
    else:
        llm_result = {
            "summary": {
                "mode": "llm",
                "role": mode_role("llm"),
                "skipped": True,
                "skip_reason": ["disabled_by_user"],
                "total_labeled": len(validation_examples),
            },
            "results": [],
        }

    benchmarks: dict[str, Any] = {
        "bootstrap": bootstrap,
        **supervised["benchmarks"],
        **setfit_result["benchmarks"],
        "llm": llm_result,
    }
    dataset_manifest = build_dataset_manifest(
        profile_path=profile_path,
        validation_examples=validation_examples,
        training_records=training_records,
        resolved_training_examples=resolved_training_examples,
        skipped_training_examples=skipped_training_examples,
    )
    payload = {
        "generated_at": utc_now_iso(),
        "operational_classifier_mode": DEFAULT_CLASSIFIER_MODE,
        "dataset_integrity": dataset_integrity,
        "dataset_manifest": dataset_manifest,
        "gates": {
            "supervised": supervised["gate"],
            "setfit": setfit_result["gate"],
        },
        "training_pool_records_jsonl": len(training_records),
        "training_pool_records_resolved": int(supervised.get("training_examples_resolved") or 0),
        "training_pool_records": len(training_records),
        "training_examples_skipped_count": len(skipped_training_examples),
        "benchmarks": benchmarks,
    }
    if "training_examples_skipped" in supervised:
        payload["training_examples_skipped"] = supervised["training_examples_skipped"]
    all_artifacts: dict[str, Any] = {}
    if include_artifacts:
        all_artifacts.update(supervised.get("artifacts", {}))
        all_artifacts.update(setfit_result.get("artifacts", {}))
        payload["artifacts"] = all_artifacts
    return payload


def run_classifier_cycle(
    *,
    profile_path: str | Path = "config/templates/default.json",
    min_training_docs: int = SPARSE_MIN_TRAINING_DOCS,
    min_docs_per_class: int = SPARSE_MIN_DOCS_PER_CLASS,
    benchmark_enabled_modes: list[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[2]
    profile_path_obj = (repo / profile_path).resolve() if not Path(profile_path).is_absolute() else Path(profile_path)
    registry = load_classifier_registry()
    report: dict[str, Any] | None = None
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
            benchmark_enabled_modes=benchmark_enabled_modes,
            progress_callback=progress_callback,
        )
        if (report.get("dataset_integrity") or {}).get("status") == "error":
            registry.latest_dataset_manifest = report.get("dataset_manifest")
            raise ValueError("dataset_integrity_error")
        # Herdar métricas do ciclo anterior para modos pulados
        _prev_report = load_classifier_report(registry.latest_report_id) if registry.latest_report_id else None
        if _prev_report:
            _prev_benchmarks = _prev_report.get("benchmarks") or {}
            for _mode, _bench in (report.get("benchmarks") or {}).items():
                _summary = _bench.get("summary") or {}
                if _summary.get("skipped") and _mode in _prev_benchmarks:
                    _prev_summary = (_prev_benchmarks[_mode].get("summary") or {})
                    if not _prev_summary.get("skipped"):
                        for _field in (
                            "business_domain_accuracy",
                            "business_domain_macro_f1",
                            "document_type_accuracy",
                            "document_type_macro_f1",
                            "exact_match_accuracy",
                        ):
                            if _field in _prev_summary:
                                _summary[_field] = _prev_summary[_field]
                        _summary["inherited_from_report_id"] = registry.latest_report_id
        artifacts = dict(report.pop("artifacts", {}) or {})
        for family, artifact in artifacts.items():
            if family == "setfit":
                save_setfit_artifact(classifier_model_path(family), artifact)
            else:
                save_sparse_artifact(classifier_model_path(family), artifact)
        champion_mode, champion_summary = choose_champion_mode(
            registry=registry,
            benchmarks=report["benchmarks"],
            training_pool_records=int(
                report.get("training_pool_records_resolved") or report.get("training_pool_records") or 0
            ),
        )
        report["champion"] = {
            "mode": champion_mode,
            "summary": champion_summary.model_dump(mode="json"),
            "promotion_policy": registry.promotion_policy,
        }
        report["operational_classifier_mode"] = champion_mode
        all_families = list(SPARSE_MODEL_FAMILIES) + ["setfit"]
        report["model_artifacts"] = {
            family: {"path": str(classifier_model_path(family))}
            for family in all_families
            if (
                (classifier_model_path(family) / "metadata.json").exists()
                if family == "setfit"
                else classifier_model_path(family).exists()
            )
        }
        report_id = save_classifier_report(report)

        registry.champion_mode = champion_mode
        registry.champion_report_id = report_id
        registry.latest_report_id = report_id
        registry.champion_summary = champion_summary
        registry.latest_dataset_manifest = report.get("dataset_manifest")
        registry.champion_dataset_manifest = report.get("dataset_manifest")
        registry.latest_cycle_status = "succeeded"
        registry.latest_cycle_finished_at = utc_now_iso()
        save_classifier_registry(registry)

        report["report_id"] = report_id
        return report
    except Exception as exc:
        if report and report.get("dataset_manifest"):
            registry.latest_dataset_manifest = report.get("dataset_manifest")
        registry.latest_cycle_status = "failed"
        registry.latest_cycle_finished_at = utc_now_iso()
        registry.latest_cycle_error = str(exc)
        save_classifier_registry(registry)
        raise
