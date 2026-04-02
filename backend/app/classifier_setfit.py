from __future__ import annotations

import json
import math
import multiprocessing
import os
import tempfile
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

from .classification_bootstrap import extract_entities
from .topics import match_topics
from .utils import fold_ocr_spacing, utc_now_iso

# Lazy-import sentinel: torch and setfit are heavy (~800 MB RSS).
# They must NEVER be imported at module level so that the API process
# stays lean while training runs in isolated subprocesses.
# Only inference (predict / load) needs them in the parent process.
_SETFIT_IMPORT_ERROR: str | None = None

try:
    from importlib.util import find_spec

    if find_spec("setfit") is None:
        _SETFIT_IMPORT_ERROR = "No module named 'setfit'"
except (ImportError, ModuleNotFoundError) as exc:
    _SETFIT_IMPORT_ERROR = str(exc)


def _load_setfit_model(path: str) -> Any:
    """Lazy-import SetFitModel and load from *path*."""
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    import torch

    torch.set_num_threads(2)

    from setfit import SetFitModel

    return SetFitModel.from_pretrained(path)

SETFIT_MODEL_FAMILIES = ("setfit",)
SETFIT_MIN_TRAINING_DOCS = 32
SETFIT_MIN_DOCS_PER_CLASS = 2
# 4 samples/class with ModernBERT: ~33 steps × 22s/step = ~12 min on CPU.
# Paper (Tunstall 2022) shows 8/class optimal, but ModernBERT is 5x slower per step.
SETFIT_SAMPLES_PER_CLASS = 4
# ModernBERT: 8192 tokens (vs 128 do MiniLM). Resolve o bottleneck de contexto para documentos longos.
# Source: https://moshewasserblat.medium.com/new-results-on-setfit-modernbert-for-text-classification-with-few-shot-training-53c154df7c0e
SETFIT_BASE_MODEL = "nomic-ai/modernbert-embed-base"
_TOP_K = 3
_ARTIFACT_SCHEMA_VERSION = 3


def setfit_import_error() -> str | None:
    return _SETFIT_IMPORT_ERROR


def compute_setfit_gate(
    records: list[Any],
    *,
    min_training_docs: int = SETFIT_MIN_TRAINING_DOCS,
    min_docs_per_class: int = SETFIT_MIN_DOCS_PER_CLASS,
) -> dict[str, Any]:
    """Graduated gate: classes with <2 samples are excluded, not blocking.

    Same logic as compute_supervised_gate — see docstring there.
    """
    business_domain_counts = Counter(
        str(record.business_domain).strip()
        for record in records
        if str(getattr(record, "business_domain", "")).strip()
    )
    document_type_counts = Counter(
        str(record.document_type).strip()
        for record in records
        if str(getattr(record, "document_type", "")).strip()
    )

    bd_eligible = {k: v for k, v in business_domain_counts.items() if v >= 2}
    dt_eligible = {k: v for k, v in document_type_counts.items() if v >= 2}
    bd_excluded = {k: v for k, v in business_domain_counts.items() if v < 2}
    dt_excluded = {k: v for k, v in document_type_counts.items() if v < 2}
    bd_low = {k: v for k, v in bd_eligible.items() if v < min_docs_per_class}
    dt_low = {k: v for k, v in dt_eligible.items() if v < min_docs_per_class}

    reasons: list[str] = []
    warnings: list[str] = []

    if _SETFIT_IMPORT_ERROR:
        reasons.append(f"setfit_unavailable:{_SETFIT_IMPORT_ERROR}")
    if not records:
        reasons.append("training_pool_empty")
    if len(records) < min_training_docs:
        reasons.append(f"training_pool_total_below_min:{len(records)}<{min_training_docs}")
    if len(bd_eligible) < 2:
        reasons.append(f"business_domain_eligible_classes_below_min:{len(bd_eligible)}<2")
    if len(dt_eligible) < 2:
        reasons.append(f"document_type_eligible_classes_below_min:{len(dt_eligible)}<2")

    if bd_excluded:
        warnings.append(f"business_domain_excluded_low_support:{dict(sorted(bd_excluded.items()))}")
    if dt_excluded:
        warnings.append(f"document_type_excluded_low_support:{dict(sorted(dt_excluded.items()))}")
    if bd_low:
        warnings.append(f"business_domain_low_support:{dict(sorted(bd_low.items()))}")
    if dt_low:
        warnings.append(f"document_type_low_support:{dict(sorted(dt_low.items()))}")

    return {
        "eligible": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "min_training_docs": min_training_docs,
        "min_docs_per_class": min_docs_per_class,
        "total_records": len(records),
        "business_domain_counts": dict(sorted(business_domain_counts.items())),
        "document_type_counts": dict(sorted(document_type_counts.items())),
        "excluded_classes": {
            "business_domain": dict(sorted(bd_excluded.items())),
            "document_type": dict(sorted(dt_excluded.items())),
        },
    }


def _stratified_sample(
    texts: list[str],
    labels: list[str],
    max_per_class: int = SETFIT_SAMPLES_PER_CLASS,
) -> tuple[list[str], list[str]]:
    """Stratified sampling for the contrastive body-tuning phase.

    SetFit's contrastive learning is designed for 8-16 examples per class
    (Tunstall et al., 2022).  This keeps the pair count manageable —
    C(n,2) grows quadratically — while the classification head is later
    trained on ALL data.
    """
    import random
    from collections import defaultdict

    by_class: dict[str, list[str]] = defaultdict(list)
    for text, label in zip(texts, labels):
        by_class[label].append(text)
    out_texts: list[str] = []
    out_labels: list[str] = []
    for label in sorted(by_class):
        class_texts = by_class[label]
        if len(class_texts) > max_per_class:
            class_texts = random.sample(class_texts, max_per_class)
        out_texts.extend(class_texts)
        out_labels.extend([label] * len(class_texts))
    return out_texts, out_labels


def _subprocess_worker(
    sample_texts: list[str],
    sample_labels: list[str],
    all_texts: list[str],
    all_labels: list[str],
    output_dir: str,
    base_model: str,
    num_epochs: int,
    batch_size: int,
    error_file: str,
) -> None:
    """Train a complete SetFit model (body + head) in an isolated process.

    Phase 1 — Contrastive body tuning on a stratified *sample* (few-shot).
    Phase 2 — Sklearn head on *all* data (forward-only encode, trivial).

    Everything happens here so the parent process never loads torch
    during training.  The OS reclaims all memory when this exits.
    """
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    try:
        import gc

        import torch

        torch.set_num_threads(2)

        from datasets import Dataset
        from setfit import SetFitModel as _SFModel
        from setfit import Trainer as _SFTrainer
        from setfit import TrainingArguments as _SFArgs

        # --- Phase 1: contrastive body tuning (few-shot sample) ---
        # Truncate texts for contrastive pairs to limit memory.
        # Body tuning learns from semantic patterns, not full documents.
        # Full text is used in Phase 2 (encode for head training).
        _CONTRASTIVE_MAX_CHARS = 1000
        truncated_samples = [t[:_CONTRASTIVE_MAX_CHARS] for t in sample_texts]
        model = _SFModel.from_pretrained(base_model)
        train_dataset = Dataset.from_dict({"text": truncated_samples, "label": sample_labels})
        args = _SFArgs(
            num_epochs=num_epochs,
            batch_size=batch_size,
            sampling_strategy="undersampling",
            show_progress_bar=False,
            output_dir=output_dir,
            save_strategy="no",
            logging_dir=str(Path(output_dir) / "_logs"),
        )
        trainer = _SFTrainer(model=model, train_dataset=train_dataset, args=args)
        trainer.train_embeddings(truncated_samples, sample_labels, args=args)

        # Free training state (optimizer, gradients, pairs)
        del trainer, train_dataset, args
        gc.collect()

        # --- Phase 2: sklearn head on ALL data ---
        # Truncate to 2000 chars (~500 tokens) for encode: head training is
        # classification over embeddings, not sequence modelling — full context
        # is not needed and causes OOM on CPU/MPS (23 GiB+ attention buffer).
        _HEAD_ENCODE_MAX_CHARS = 2000
        encode_texts = [t[:_HEAD_ENCODE_MAX_CHARS] for t in all_texts]
        model.model_body.eval()
        with torch.no_grad():
            embeddings = model.model_body.encode(
                encode_texts, batch_size=8, show_progress_bar=False,
            )
        model.model_head.fit(embeddings, all_labels)
        if model.labels is None and model.multi_target_strategy is None:
            try:
                classes = model.model_head.classes_
                if classes.dtype.char == "U":
                    model.labels = classes.tolist()
            except Exception:
                pass

        model.save_pretrained(output_dir)
    except Exception:
        Path(error_file).write_text(traceback.format_exc(), encoding="utf-8")


def _train_in_subprocess(
    sample_texts: list[str],
    sample_labels: list[str],
    all_texts: list[str],
    all_labels: list[str],
    output_dir: str,
    *,
    base_model: str = SETFIT_BASE_MODEL,
    num_epochs: int = 1,
    batch_size: int = 4,
    timeout: int = 1800,
) -> None:
    """Train a complete SetFit model in a child process.

    The child does body tuning (contrastive, on sample) then head
    training (sklearn, on all data), saves the model, and exits.
    Raises RuntimeError if the child crashes or times out.
    """
    error_file = str(Path(output_dir).parent / f"{Path(output_dir).name}_error.txt")
    ctx = multiprocessing.get_context("spawn")
    process = ctx.Process(
        target=_subprocess_worker,
        args=(
            sample_texts,
            sample_labels,
            all_texts,
            all_labels,
            output_dir,
            base_model,
            num_epochs,
            batch_size,
            error_file,
        ),
    )
    process.start()
    process.join(timeout=timeout)

    if process.is_alive():
        process.kill()
        process.join(timeout=10)
        raise RuntimeError(
            f"SetFit training subprocess timed out after {timeout}s"
        )

    error_path = Path(error_file)
    if error_path.exists():
        error_text = error_path.read_text(encoding="utf-8")
        error_path.unlink(missing_ok=True)
        raise RuntimeError(f"SetFit training subprocess failed:\n{error_text}")

    if process.exitcode != 0:
        raise RuntimeError(
            f"SetFit training subprocess exited with code {process.exitcode} "
            f"(likely OOM or signal {abs(process.exitcode or 0)})"
        )


def fit_setfit_artifact(
    *,
    train_texts: list[str],
    train_business_domains: list[str],
    train_document_types: list[str],
    training_pool_records: int,
    base_model: str = SETFIT_BASE_MODEL,
    samples_per_class: int = SETFIT_SAMPLES_PER_CLASS,
) -> dict[str, Any]:
    if _SETFIT_IMPORT_ERROR:
        raise RuntimeError(_SETFIT_IMPORT_ERROR)

    tmp_root = tempfile.mkdtemp(prefix="setfit_train_")
    domain_dir = str(Path(tmp_root) / "business_domain")
    doctype_dir = str(Path(tmp_root) / "document_type")

    # Each subprocess trains body (sample) + head (all data) + saves.
    # The parent NEVER loads torch during training — zero memory overlap.

    domain_sample_texts, domain_sample_labels = _stratified_sample(
        train_texts, train_business_domains, max_per_class=samples_per_class,
    )
    _train_in_subprocess(
        domain_sample_texts, domain_sample_labels,
        train_texts, train_business_domains,
        domain_dir, base_model=base_model,
    )

    doctype_sample_texts, doctype_sample_labels = _stratified_sample(
        train_texts, train_document_types, max_per_class=samples_per_class,
    )
    _train_in_subprocess(
        doctype_sample_texts, doctype_sample_labels,
        train_texts, train_document_types,
        doctype_dir, base_model=base_model,
    )

    # Load completed models only after all subprocesses are done
    domain_model = _load_setfit_model(domain_dir)
    doctype_model = _load_setfit_model(doctype_dir)

    return {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "family": "setfit",
        "trained_at": utc_now_iso(),
        "base_model": base_model,
        "training_pool_records": int(training_pool_records),
        "business_domain_model": domain_model,
        "document_type_model": doctype_model,
    }


def save_setfit_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": artifact["schema_version"],
        "family": artifact["family"],
        "trained_at": artifact["trained_at"],
        "base_model": artifact["base_model"],
        "training_pool_records": artifact["training_pool_records"],
    }
    (path / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifact["business_domain_model"].save_pretrained(str(path / "business_domain"))
    artifact["document_type_model"].save_pretrained(str(path / "document_type"))


def load_setfit_artifact(path: Path) -> dict[str, Any]:
    if _SETFIT_IMPORT_ERROR:
        raise RuntimeError(_SETFIT_IMPORT_ERROR)
    metadata_path = path / "metadata.json"
    if not metadata_path.exists():
        raise ValueError(f"setfit artifact metadata not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    schema_version = int(metadata.get("schema_version") or 0)
    if schema_version != _ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"incompatible setfit artifact schema_version: {schema_version} "
            f"(expected {_ARTIFACT_SCHEMA_VERSION})"
        )
    family = str(metadata.get("family") or "").strip()
    if family != "setfit":
        raise ValueError(f"unexpected setfit artifact family: {family}")
    domain_model = _load_setfit_model(str(path / "business_domain"))
    document_type_model = _load_setfit_model(str(path / "document_type"))
    return {
        **metadata,
        "business_domain_model": domain_model,
        "document_type_model": document_type_model,
    }


def _softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    max_value = max(values)
    exps = [math.exp(value - max_value) for value in values]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


def _predict_with_scores(model: Any, text: str) -> dict[str, Any]:
    proba = model.predict_proba([text])
    scores_row = proba[0]
    classes = [str(c) for c in model.model_head.classes_]
    if not classes:
        raise ValueError("setfit model has no classes")
    scores = [float(s) for s in scores_row]
    ranked = sorted(
        zip(classes, scores, strict=True),
        key=lambda item: (-item[1], item[0]),
    )
    best_label, best_score = ranked[0]
    return {
        "label": best_label,
        "confidence": round(float(best_score), 4),
        "top_candidates": [
            {"label": label, "score": round(float(score), 4)}
            for label, score in ranked[:_TOP_K]
        ],
    }


def classify_with_setfit_artifact(
    *,
    artifact: dict[str, Any],
    profile: dict[str, Any],
    source_path: Path,
    text_excerpt: str,
) -> dict[str, Any]:
    family = str(artifact.get("family") or "").strip()
    if family != "setfit":
        raise ValueError(f"unexpected setfit artifact family: {family}")

    # ModernBERT: max_seq_length=8192 tokens. Use up to 8000 chars to leverage full context.
    # Source: https://huggingface.co/nomic-ai/modernbert-embed-base
    feature_text = fold_ocr_spacing(f"{source_path.name}\n{text_excerpt[:8000]}".strip())
    domain_prediction = _predict_with_scores(artifact["business_domain_model"], feature_text)
    document_type_prediction = _predict_with_scores(artifact["document_type_model"], feature_text)
    entities = extract_entities(profile=profile, source_path=source_path, text_excerpt=text_excerpt)
    topics_input = "\n".join(part for part in [source_path.name, text_excerpt] if part)
    topics, topics_source = match_topics(
        text=topics_input,
        business_domain=str(domain_prediction["label"]).strip() or None,
        profile=profile,
    )
    business_domain = str(domain_prediction["label"]).strip()
    document_type = str(document_type_prediction["label"]).strip()
    return {
        "business_domain": business_domain,
        "document_type": document_type,
        "business_domain_confidence": float(domain_prediction["confidence"]),
        "document_type_confidence": float(document_type_prediction["confidence"]),
        "confidence": round(
            min(
                float(domain_prediction["confidence"]),
                float(document_type_prediction["confidence"]),
            ),
            4,
        ),
        "reason": "supervised:setfit",
        "top_candidates": [
            {
                "business_domain": row["label"],
                "score": row["score"],
            }
            for row in domain_prediction["top_candidates"]
        ],
        "top_document_type_candidates": [
            {
                "document_type": row["label"],
                "score": row["score"],
            }
            for row in document_type_prediction["top_candidates"]
        ],
        "entities": entities,
        "topics": topics,
        "topics_source": topics_source,
        "classifier_mode": "setfit",
    }


def predict_labels_from_setfit_artifact(artifact: dict[str, Any], text: str) -> dict[str, Any]:
    family = str(artifact.get("family") or "").strip()
    if family != "setfit":
        raise ValueError(f"unexpected setfit artifact family: {family}")
    # Truncate to match _HEAD_ENCODE_MAX_CHARS used in training — same embedding space.
    text = text[:2000]
    domain_prediction = _predict_with_scores(artifact["business_domain_model"], text)
    document_type_prediction = _predict_with_scores(artifact["document_type_model"], text)
    return {
        "family": family,
        "business_domain": domain_prediction,
        "document_type": document_type_prediction,
    }
