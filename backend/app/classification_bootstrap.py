from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .topics import match_topics
from .utils import fold_ocr_spacing

_WORD_CACHE: dict[str, re.Pattern[str]] = {}

_CNPJ_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
_EMAIL_RE = re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")
_CONTRACT_RE = re.compile(r"\b(?:(?:ct|cw)\s?\d{6,}|contrato\s*(?:n[ºo.]?\s*)?\d{4,})\b", re.IGNORECASE)
_MONEY_RE = re.compile(r"\b(?:r\$\s*)?\d{1,3}(?:\.\d{3})*(?:,\d{2})\b", re.IGNORECASE)

_DOC_TYPE_EXTENSION_BONUS = 0.08
_DOC_TYPE_ALIAS_BASE_CONFIDENCE = 0.35
_DOC_TYPE_ALIAS_CONFIDENCE_SCALE = 0.6
# Teto do caminho de ALIAS: abaixo de auto_route_min (0.85) — frequência de
# alias no corpo nunca auto-roteia sozinha; auto-route de tipo exige regra
# estrutural (cabeçalho) ou extensão característica. Régua: 12 arquivos reais
# do validation set, zero auto-route com tipo errado (plano v0.39.0).
_DOC_TYPE_CONFIDENCE_CAP = 0.84
_DOC_TYPE_BEST_EFFORT_CONFIDENCE = 0.25

_DOMAIN_FILENAME_HIT_WEIGHT = 3
_DOMAIN_TEXT_HIT_WEIGHT = 2
_DOMAIN_ENTITY_HIT_WEIGHT = 2
_DOMAIN_DOCUMENT_TYPE_HIT_WEIGHT = 2
_DOMAIN_CONFIDENCE_CAP = 0.92
_DOMAIN_BEST_EFFORT_CONFIDENCE = 0.05


def _classification_config(profile: dict[str, Any]) -> dict[str, Any]:
    config = dict(profile.get("classification") or {})
    required = ["business_domains", "document_types"]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"classification config is missing required key(s): {missing}")
    return config


def _business_domains(profile: dict[str, Any]) -> list[dict[str, Any]]:
    domains = list(_classification_config(profile).get("business_domains") or [])
    if not domains:
        raise ValueError("classification.business_domains must not be empty")
    return domains


def _document_types(profile: dict[str, Any]) -> list[dict[str, Any]]:
    document_types = list(_classification_config(profile).get("document_types") or [])
    if not document_types:
        raise ValueError("classification.document_types must not be empty")
    return document_types


def _document_types_by_key(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("key") or "").strip(): row
        for row in _document_types(profile)
        if str(row.get("key") or "").strip()
    }


def _document_type_lexicon(profile: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for row in _document_types(profile):
        key = str(row.get("key") or "").strip()
        folder = str(row.get("folder") or "").strip()
        values = [key, key.replace("_", " "), folder]
        tokens.update(_normalized_aliases(values))
    return tokens


def _entity_catalog(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return list(_classification_config(profile).get("entity_catalog") or [])


def _word_pattern(token: str) -> re.Pattern[str]:
    cached = _WORD_CACHE.get(token)
    if cached is None:
        cached = re.compile(rf"(^|[^a-z0-9]){re.escape(token)}([^a-z0-9]|$)")
        _WORD_CACHE[token] = cached
    return cached


def _match_score(aliases: list[str], text: str) -> float:
    if not aliases:
        return 0.0
    hits = 0
    normalized_text = fold_ocr_spacing(text)
    for alias in aliases:
        alias_norm = fold_ocr_spacing(alias)
        if not alias_norm:
            continue
        if _word_pattern(alias_norm).search(normalized_text):
            hits += 1
    if hits <= 0:
        return 0.0
    return min(1.0, hits / max(1.0, math.sqrt(len(aliases))))


def _contains_alias(text_norm: str, alias: str) -> bool:
    alias_norm = fold_ocr_spacing(alias)
    if not alias_norm:
        return False
    return bool(_word_pattern(alias_norm).search(text_norm))


def _normalized_aliases(values: list[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        item = fold_ocr_spacing(value)
        if item:
            normalized.add(item)
    return normalized


def _alias_hits(aliases: list[str], text_norm: str) -> set[str]:
    hits: set[str] = set()
    if not text_norm:
        return hits
    for alias in aliases:
        alias_norm = fold_ocr_spacing(alias)
        if alias_norm and _word_pattern(alias_norm).search(text_norm):
            hits.add(alias_norm)
    return hits


def _alias_specificity(hits: set[str]) -> int:
    return sum(max(1, len(hit.split())) for hit in hits)


def _extensions_match(ext: str, configured_extensions: list[str]) -> bool:
    return ext in {str(item).lower() for item in configured_extensions if str(item).strip()}


def _rule_matches_text(text_norm: str, ext: str, rule: dict[str, Any]) -> bool:
    allowed_extensions = [str(item).lower() for item in (rule.get("extensions") or []) if str(item).strip()]
    if allowed_extensions and ext not in allowed_extensions:
        return False

    # head_chars: regra de cabeçalho só enxerga a abertura do documento —
    # menção profunda no corpo não é título. Ausente = texto inteiro (compat).
    head_chars = rule.get("head_chars")
    if head_chars:
        try:
            text_norm = text_norm[: int(head_chars)]
        except (TypeError, ValueError):
            pass

    any_of = [str(item).strip() for item in (rule.get("any_of") or []) if str(item).strip()]
    if any_of and not any(_contains_alias(text_norm, token) for token in any_of):
        return False

    all_of = [str(item).strip() for item in (rule.get("all_of") or []) if str(item).strip()]
    if all_of and not all(_contains_alias(text_norm, token) for token in all_of):
        return False

    with_any_of = [str(item).strip() for item in (rule.get("with_any_of") or []) if str(item).strip()]
    if with_any_of and not any(_contains_alias(text_norm, token) for token in with_any_of):
        return False

    exclude_any_of = [str(item).strip() for item in (rule.get("exclude_any_of") or []) if str(item).strip()]
    if exclude_any_of and any(_contains_alias(text_norm, token) for token in exclude_any_of):
        return False

    return True


def _sorted_document_type_scores(profile: dict[str, Any], scores: dict[str, float]) -> list[tuple[str, float]]:
    by_key = _document_types_by_key(profile)
    return sorted(
        scores.items(),
        key=lambda item: (
            -item[1],
            int(by_key.get(item[0], {}).get("fallback_priority") or 100),
            item[0],
        ),
    )


def detect_document_type(*, profile: dict[str, Any], source_path: Path, text_excerpt: str) -> dict[str, Any]:
    ext = (source_path.suffix or "").lower()
    filename_text = fold_ocr_spacing(source_path.name)
    excerpt_head = fold_ocr_spacing(text_excerpt[:4000])
    combined = f"{filename_text}\n{excerpt_head}".strip()
    document_types = _document_types(profile)

    extension_scores: dict[str, float] = {}
    for row in document_types:
        key = str(row.get("key") or "").strip()
        extension_confidence = {
            str(item).lower(): float(value)
            for item, value in (row.get("extension_confidence_by_extension") or {}).items()
            if str(item).strip()
        }
        if key and ext in extension_confidence:
            extension_scores[key] = extension_confidence[ext]
    if extension_scores:
        ranked = _sorted_document_type_scores(profile, extension_scores)
        best_key, best_score = ranked[0]
        return {
            "document_type": best_key,
            "document_type_confidence": round(best_score, 4),
            "document_type_reason": "extension",
            "top_document_type_candidates": [
                {"document_type": key, "score": round(score, 4)}
                for key, score in ranked[:3]
            ],
        }

    structural_scores: dict[str, tuple[float, str]] = {}
    for row in document_types:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        for rule in row.get("detection_rules") or []:
            if not _rule_matches_text(combined, ext, rule):
                continue
            confidence = float(rule.get("confidence") or 0.0)
            reason = str(rule.get("reason") or "structural_header")
            current = structural_scores.get(key)
            if current is None or confidence > current[0]:
                structural_scores[key] = (confidence, reason)
    if structural_scores:
        ranked = sorted(
            structural_scores.items(),
            key=lambda item: (
                -item[1][0],
                int(_document_types_by_key(profile).get(item[0], {}).get("fallback_priority") or 100),
                item[0],
            ),
        )
        best_key, (best_score, best_reason) = ranked[0]
        return {
            "document_type": best_key,
            "document_type_confidence": round(best_score, 4),
            "document_type_reason": best_reason,
            "top_document_type_candidates": [
                {"document_type": key, "score": round(score_reason[0], 4)}
                for key, score_reason in ranked[:3]
            ],
        }

    candidate_scores: dict[str, float] = {}
    for row in document_types:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        aliases = [key] + [str(alias).strip() for alias in (row.get("aliases") or []) if str(alias).strip()]
        score = _match_score(aliases, combined)
        if _extensions_match(ext, list(row.get("extensions") or [])):
            score = min(1.0, score + _DOC_TYPE_EXTENSION_BONUS)
        candidate_scores[key] = round(score, 4)

    ranked_candidates = _sorted_document_type_scores(profile, candidate_scores)
    if ranked_candidates and ranked_candidates[0][1] > 0:
        best_key, best_score = ranked_candidates[0]
        confidence = min(
            _DOC_TYPE_CONFIDENCE_CAP,
            _DOC_TYPE_ALIAS_BASE_CONFIDENCE + best_score * _DOC_TYPE_ALIAS_CONFIDENCE_SCALE,
        )
        return {
            "document_type": best_key,
            "document_type_confidence": round(confidence, 4),
            "document_type_reason": "alias_structure",
            "top_document_type_candidates": [
                {"document_type": key, "score": score}
                for key, score in ranked_candidates[:3]
            ],
        }

    fallback_pool = [
        row for row in document_types
        if _extensions_match(ext, [str(item) for item in (row.get("extensions") or [])])
    ] or document_types
    fallback_pool = sorted(
        fallback_pool,
        key=lambda row: (
            int(row.get("fallback_priority") or 100),
            str(row.get("key") or ""),
        ),
    )
    fallback_key = str(fallback_pool[0].get("key") or "").strip()
    return {
        "document_type": fallback_key,
        "document_type_confidence": round(_DOC_TYPE_BEST_EFFORT_CONFIDENCE, 4),
        "document_type_reason": "best_effort_config",
        "top_document_type_candidates": [{"document_type": fallback_key, "score": round(_DOC_TYPE_BEST_EFFORT_CONFIDENCE, 4)}],
    }


def extract_entities(*, profile: dict[str, Any], source_path: Path, text_excerpt: str) -> list[dict[str, str]]:
    text = fold_ocr_spacing(f"{source_path.name}\n{text_excerpt}")
    entities: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _append(entity_type: str, value: str) -> None:
        key = (entity_type, value)
        if not value or key in seen:
            return
        seen.add(key)
        entities.append({"type": entity_type, "value": value})

    for match in _CNPJ_RE.findall(text_excerpt):
        _append("cnpj", match)
    for match in _EMAIL_RE.findall(text_excerpt):
        _append("email", match)
    for match in _CONTRACT_RE.findall(text_excerpt):
        _append("contrato", match.strip())
    for match in _MONEY_RE.findall(text_excerpt):
        _append("valor", match.strip())

    for row in _entity_catalog(profile):
        entity_type = str(row.get("type") or "entity").strip() or "entity"
        value = str(row.get("value") or "").strip()
        aliases = [value] + [str(alias).strip() for alias in (row.get("aliases") or []) if str(alias).strip()]
        if any(_word_pattern(fold_ocr_spacing(alias)).search(text) for alias in aliases if alias):
            _append(entity_type, value)

    return entities


def _fallback_business_domain(
    *,
    domains: list[dict[str, Any]],
    document_type_tokens: set[str],
) -> str:
    for domain in domains:
        key = str(domain.get("key") or "").strip()
        aliases = _normalized_aliases([key] + [str(alias).strip() for alias in (domain.get("aliases") or []) if str(alias).strip()])
        if aliases & document_type_tokens:
            return key
    return str(domains[0].get("key") or "").strip()


def _domain_confidence(best_score: int, second_score: int) -> float:
    if best_score <= 0:
        return _DOMAIN_BEST_EFFORT_CONFIDENCE
    margin = max(0, best_score - second_score)
    confidence = 0.18 + min(best_score, 7) * 0.08 + min(margin, 3) * 0.06
    return round(min(_DOMAIN_CONFIDENCE_CAP, confidence), 4)


def classify_business_domain(
    *,
    profile: dict[str, Any],
    source_path: Path,
    text_excerpt: str,
    document_type: str,
    entities: list[dict[str, str]],
) -> dict[str, Any]:
    text = fold_ocr_spacing(text_excerpt[:4000])
    filename_text = fold_ocr_spacing(source_path.stem)
    entity_text = fold_ocr_spacing("\n".join(entity.get("value", "") for entity in entities))
    domains = _business_domains(profile)
    document_type_row = _document_types_by_key(profile).get(document_type, {})
    document_type_tokens = _normalized_aliases(
        [document_type] + [str(alias).strip() for alias in (document_type_row.get("aliases") or []) if str(alias).strip()]
    )
    domain_keys = [str(domain.get("key") or "").strip() for domain in domains if str(domain.get("key") or "").strip()]
    document_type_lexicon = _document_type_lexicon(profile)
    if not domain_keys:
        raise ValueError("classification.business_domains must not be empty")

    candidates: list[tuple[str, int, int, int, int, int, int]] = []
    for key in domain_keys:
        domain = next(domain for domain in domains if str(domain.get("key") or "").strip() == key)
        aliases = [key]
        aliases.extend(
            alias
            for alias in (str(alias).strip() for alias in (domain.get("aliases") or []))
            if alias and fold_ocr_spacing(alias) not in document_type_lexicon
        )
        alias_set = _normalized_aliases(aliases)
        filename_hit_set = _alias_hits(aliases, filename_text)
        text_hit_set = _alias_hits(aliases, text)
        entity_hit_set = _alias_hits(aliases, entity_text)
        filename_hits = len(filename_hit_set)
        text_hits = len(text_hit_set)
        entity_hits = len(entity_hit_set)
        document_type_hits = len(alias_set & document_type_tokens)
        specificity = (
            _alias_specificity(filename_hit_set) * _DOMAIN_FILENAME_HIT_WEIGHT
            + _alias_specificity(text_hit_set) * _DOMAIN_TEXT_HIT_WEIGHT
            + _alias_specificity(entity_hit_set) * _DOMAIN_ENTITY_HIT_WEIGHT
        )
        score = (
            filename_hits * _DOMAIN_FILENAME_HIT_WEIGHT
            + text_hits * _DOMAIN_TEXT_HIT_WEIGHT
            + entity_hits * _DOMAIN_ENTITY_HIT_WEIGHT
            + document_type_hits * _DOMAIN_DOCUMENT_TYPE_HIT_WEIGHT
        )
        candidates.append((key, score, specificity, filename_hits, text_hits, document_type_hits, entity_hits))

    candidates.sort(key=lambda item: (-item[1], -item[2], -item[4], -item[3], -item[5], -item[6], item[0]))
    best_key, best_score, _, _, _, _, _ = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else 0
    if best_score <= 0:
        fallback_key = _fallback_business_domain(domains=domains, document_type_tokens=document_type_tokens)
        return {
            "business_domain": fallback_key,
            "business_domain_confidence": round(_DOMAIN_BEST_EFFORT_CONFIDENCE, 4),
            "business_domain_reason": "alias_best_effort",
            "top_business_domain_candidates": [{"business_domain": fallback_key, "score": round(_DOMAIN_BEST_EFFORT_CONFIDENCE, 4)}],
        }

    return {
        "business_domain": best_key,
        "business_domain_confidence": _domain_confidence(best_score, second_score),
        "business_domain_reason": "bootstrap_aliases",
        "top_business_domain_candidates": [
            {"business_domain": key, "score": score}
            for key, score, _, _, _, _, _ in candidates[:3]
        ],
    }


def classify_bootstrap(
    *,
    profile: dict[str, Any],
    source_path: Path,
    text_excerpt: str,
) -> dict[str, Any]:
    doc_type_result = detect_document_type(profile=profile, source_path=source_path, text_excerpt=text_excerpt)
    entities = extract_entities(profile=profile, source_path=source_path, text_excerpt=text_excerpt)
    domain_result = classify_business_domain(
        profile=profile,
        source_path=source_path,
        text_excerpt=text_excerpt,
        document_type=str(doc_type_result["document_type"]),
        entities=entities,
    )
    topics_input = "\n".join(part for part in [source_path.name, text_excerpt] if part)
    topics, topics_source = match_topics(
        text=topics_input,
        business_domain=str(domain_result.get("business_domain") or "").strip() or None,
        profile=profile,
    )
    confidence = round(
        min(
            float(doc_type_result.get("document_type_confidence") or 0.0),
            float(domain_result.get("business_domain_confidence") or 0.0),
        ),
        4,
    )
    business_domain = str(domain_result["business_domain"])
    return {
        "business_domain": business_domain,
        "document_type": str(doc_type_result["document_type"]),
        "document_type_confidence": float(doc_type_result.get("document_type_confidence") or 0.0),
        "business_domain_confidence": float(domain_result.get("business_domain_confidence") or 0.0),
        "confidence": confidence,
        "reason": f"{domain_result.get('business_domain_reason')}|{doc_type_result.get('document_type_reason')}",
        "top_candidates": [
            {"business_domain": row["business_domain"], "score": row["score"]}
            for row in domain_result.get("top_business_domain_candidates", [])
        ],
        "top_document_type_candidates": doc_type_result.get("top_document_type_candidates", []),
        "entities": entities,
        "topics": topics,
        "topics_source": topics_source,
    }
