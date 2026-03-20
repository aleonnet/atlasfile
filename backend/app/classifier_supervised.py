from __future__ import annotations

import math
import pickle
from collections import Counter
from pathlib import Path
from typing import Any

from .classification_bootstrap import extract_entities
from .topics import match_topics
from .utils import fold_ocr_spacing, utc_now_iso

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.svm import LinearSVC

    _SKLEARN_IMPORT_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover - covered indirectly in integration flows
    TfidfVectorizer = None  # type: ignore[assignment]
    LogisticRegression = None  # type: ignore[assignment]
    Pipeline = None  # type: ignore[assignment]
    LinearSVC = None  # type: ignore[assignment]
    _SKLEARN_IMPORT_ERROR = str(exc)


SPARSE_MODEL_FAMILIES = ("sparse_logreg", "sparse_linear_svc")
SPARSE_MIN_TRAINING_DOCS = 100
SPARSE_MIN_DOCS_PER_CLASS = 5
_TOP_K = 3


def sklearn_import_error() -> str | None:
    return _SKLEARN_IMPORT_ERROR


def compute_supervised_gate(
    records: list[Any],
    *,
    min_training_docs: int = SPARSE_MIN_TRAINING_DOCS,
    min_docs_per_class: int = SPARSE_MIN_DOCS_PER_CLASS,
) -> dict[str, Any]:
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
    else:  # pragma: no cover - protected by callers/tests
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


def fit_sparse_artifact(
    *,
    family: str,
    train_texts: list[str],
    train_business_domains: list[str],
    train_document_types: list[str],
    training_pool_records: int,
) -> dict[str, Any]:
    if family not in SPARSE_MODEL_FAMILIES:
        raise ValueError(f"unsupported supervised family: {family}")
    domain_model = _sparse_pipeline(family)
    document_type_model = _sparse_pipeline(family)
    domain_model.fit(train_texts, train_business_domains)
    document_type_model.fit(train_texts, train_document_types)
    return {
        "schema_version": 1,
        "family": family,
        "trained_at": utc_now_iso(),
        "vectorizer": "tfidf_char_wb_3_5",
        "training_pool_records": int(training_pool_records),
        "business_domain_model": domain_model,
        "document_type_model": document_type_model,
    }


def save_sparse_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(artifact, handle)


def load_sparse_artifact(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("invalid supervised artifact payload")
    family = str(payload.get("family") or "").strip()
    if family not in SPARSE_MODEL_FAMILIES:
        raise ValueError(f"unsupported supervised artifact family: {family}")
    return payload


def _softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    max_value = max(values)
    exps = [math.exp(value - max_value) for value in values]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


def _classifier_classes(model: Pipeline) -> list[str]:
    classifier = model.named_steps["classifier"]
    return [str(value) for value in getattr(classifier, "classes_", [])]


def _raw_class_scores(model: Pipeline, text: str) -> list[float]:
    classifier = model.named_steps["classifier"]
    scores = classifier.decision_function(model.named_steps["tfidf"].transform([text]))
    raw = scores[0] if getattr(scores, "ndim", 1) > 1 else scores
    if isinstance(raw, (int, float)):
        margin = float(raw)
        return [-margin, margin]
    return [float(value) for value in raw]


def _predict_with_scores(model: Pipeline, text: str) -> dict[str, Any]:
    classes = _classifier_classes(model)
    if not classes:
        raise ValueError("supervised model has no classes")
    if len(classes) == 1:
        return {
            "label": classes[0],
            "confidence": 1.0,
            "top_candidates": [{"label": classes[0], "score": 1.0}],
        }

    classifier = model.named_steps["classifier"]
    if hasattr(classifier, "predict_proba"):
        probabilities = classifier.predict_proba(model.named_steps["tfidf"].transform([text]))[0]
        scores = [float(value) for value in probabilities]
    else:
        raw_scores = _raw_class_scores(model, text)
        if len(raw_scores) == 1 and len(classes) == 2:
            margin = raw_scores[0]
            raw_scores = [-margin, margin]
        scores = _softmax(raw_scores)

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


def classify_with_supervised_artifact(
    *,
    artifact: dict[str, Any],
    profile: dict[str, Any],
    source_path: Path,
    text_excerpt: str,
) -> dict[str, Any]:
    family = str(artifact.get("family") or "").strip()
    if family not in SPARSE_MODEL_FAMILIES:
        raise ValueError(f"unsupported supervised artifact family: {family}")

    feature_text = fold_ocr_spacing(f"{source_path.name}\n{text_excerpt[:4000]}".strip())
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
        "reason": f"supervised:{family}",
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
        "classifier_mode": family,
    }


def predict_labels_from_artifact(artifact: dict[str, Any], text: str) -> dict[str, Any]:
    family = str(artifact.get("family") or "").strip()
    if family not in SPARSE_MODEL_FAMILIES:
        raise ValueError(f"unsupported supervised artifact family: {family}")
    domain_prediction = _predict_with_scores(artifact["business_domain_model"], text)
    document_type_prediction = _predict_with_scores(artifact["document_type_model"], text)
    return {
        "family": family,
        "business_domain": domain_prediction,
        "document_type": document_type_prediction,
    }
