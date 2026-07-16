from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch

from .area_resolver import resolve_classification_path
from .bootstrap import ensure_project_structure
from .config import settings
from .classifier_runtime import classify_with_operational_mode
from .indexer import index_document, index_document_chunks_embeddings, read_text_excerpt
from .profile_runtime import areas_root_rel, triage_paths
from .triage import save_pending_metadata
from .utils import (
    DEFAULT_CANONICAL_PATTERN,
    build_canonical_filename,
    fs_safe,
    sanitize_token,
    sha256_file,
    utc_now_iso,
)

import logging as _logging
import time as _time

_ingestion_logger = _logging.getLogger(__name__)

def _persist_classification_usage(
    doc_id: str,
    filename: str,
    project_id: str,
    provider: str,
    model: str,
    usage: dict[str, Any],
) -> None:
    """Persist a classification LLM usage record to OpenSearch."""
    try:
        from .opensearch_client import get_client
        client = get_client()
        idx = settings.opensearch_classification_usage_index
        doc = {
            "doc_id": doc_id,
            "filename": filename,
            "project_id": project_id,
            "provider": provider,
            "model": model,
            "timestamp": int(_time.time() * 1000),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_input_tokens": int(usage.get("cache_read_input_tokens") or 0),
            "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens") or 0),
            "estimated_cost_usd": float(usage.get("estimated_cost_usd") or 0),
        }
        client.index(index=idx, body=doc)
    except Exception:
        _ingestion_logger.exception("Failed to persist classification usage")


def _llm_policy(profile: dict[str, Any]) -> dict[str, Any]:
    policy = dict(profile.get("llm_policy") or {})
    classification_policy = ((profile.get("classification") or {}).get("llm_policy") or {})
    for k, v in classification_policy.items():
        policy.setdefault(k, v)
    policy.setdefault("enabled", False)
    policy.setdefault("mode", "tag_only")
    policy.setdefault("allow_override_fields", ["document_type", "tags", "confidence", "topics"])
    guardrails = dict(policy.get("override_guardrails") or {})
    guardrails.setdefault("business_domain_override_only_if_rule_confidence_below", 0.65)
    guardrails.setdefault("require_explanation", True)
    guardrails.setdefault("max_business_domain_changes", 1)
    policy["override_guardrails"] = guardrails
    return policy


def _apply_llm_policy(
    *,
    profile: dict[str, Any],
    classification: dict[str, Any],
    llm_result: dict[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    if not llm_result:
        return classification, False

    policy = _llm_policy(profile)
    mode = str(policy.get("mode") or "tag_only")
    allow = {str(x).strip() for x in (policy.get("allow_override_fields") or [])}
    business_domain_keys = {
        str(domain.get("key") or "").strip()
        for domain in (profile.get("business_domains") or [])
    }
    force_triage_pending = False

    rule_conf = float(classification.get("confidence") or 0.0)
    llm_conf = float(llm_result.get("confidence") or 0.0)
    raw_llm_business_domain = str(llm_result.get("business_domain") or "").strip() or None
    explanation = str(llm_result.get("explanation") or "").strip()

    # Preserve rule-based results before any mutation
    classification["_rule_business_domain"] = classification.get("business_domain")
    classification["_rule_confidence"] = rule_conf

    # Always preserve explanation
    if explanation:
        classification["llm_explanation"] = explanation

    if "confidence" in allow and llm_conf > 0:
        classification["confidence"] = llm_conf
    if "tags" in allow and llm_result.get("tags"):
        classification["suggested_tags"] = list(llm_result.get("tags") or [])
    if "document_type" in allow and llm_result.get("document_type"):
        classification["document_type"] = llm_result.get("document_type")
    if "topics" in allow and llm_result.get("topics"):
        classification["suggested_topics"] = [str(t).strip() for t in (llm_result.get("topics") or []) if str(t).strip()]

    # Preserve the raw LLM business_domain even if it doesn't exist in the current profile.
    llm_business_domain = raw_llm_business_domain
    if raw_llm_business_domain and raw_llm_business_domain not in business_domain_keys:
        classification["llm_proposed_business_domain"] = raw_llm_business_domain
        llm_business_domain = None

    current_business_domain = str(classification.get("business_domain") or "").strip() or None
    if not llm_business_domain or llm_business_domain == current_business_domain:
        return classification, force_triage_pending

    if mode == "review":
        classification["reason"] = "llm_review_divergence"
        force_triage_pending = True
        return classification, force_triage_pending

    if mode == "full_override":
        guardrails = dict(policy.get("override_guardrails") or {})
        threshold = float(guardrails.get("business_domain_override_only_if_rule_confidence_below") or 0.65)
        require_explanation = bool(guardrails.get("require_explanation", True))
        max_business_domain_changes = int(guardrails.get("max_business_domain_changes", 1) or 1)
        can_override = (
            max_business_domain_changes > 0
            and rule_conf < threshold
            and llm_conf >= rule_conf
            and (not require_explanation or bool(explanation))
        )
        if can_override:
            classification["business_domain"] = llm_business_domain
            classification["reason"] = "llm_full_override"
            return classification, force_triage_pending

        classification["reason"] = "llm_override_guardrail_blocked"
        force_triage_pending = True
        return classification, force_triage_pending

    return classification, force_triage_pending


def _append_index_md(project_root: Path, row: dict[str, Any]) -> None:
    index_path = project_root / "_INDEX.md"
    header = (
        "# _INDEX\n\n"
        "| doc_id | project_id | business_domain | original_filename | canonical_filename | decision | confidence | path | naming_pattern |\n"
        "|---|---|---|---|---|---|---:|---|---|\n"
    )
    existing_lines = (
        index_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if index_path.exists()
        else []
    )
    doc_id = str(row.get("doc_id", "")).strip()
    kept_data_lines: list[str] = []
    for raw in existing_lines:
        if not raw.startswith("| ") or raw.startswith("|---"):
            continue
        cols = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cols) < 8 or cols[0] == "doc_id":
            continue
        if doc_id and cols[0] == doc_id:
            continue
        kept_data_lines.append(raw.strip())
    np = row.get("naming_pattern", "")
    kept_data_lines.append(
        f"| {row['doc_id']} | {row['project_id']} | {row.get('business_domain', '')} | "
        f"{row['original_filename']} | {row['canonical_filename']} | {row['decision']} | "
        f"{row['confidence_score']:.2f} | {row['path']} | {np} |"
    )
    body = ("\n".join(kept_data_lines) + "\n") if kept_data_lines else ""
    index_path.write_text(header + body, encoding="utf-8")


def _find_latest_version(
    *,
    project_root: Path,
    profile: dict[str, Any],
    project_id: str,
    business_domain: str,
    title_token: str,
    suffix: str,
) -> int:
    latest = 0
    proj_tok = sanitize_token(project_id)
    business_domain_tok = sanitize_token(business_domain)
    title_sanitized = sanitize_token(title_token)
    title_safe = fs_safe(title_token).lower()

    # Legacy format token: __{proj}__{area}__{sanitized_title}__v
    old_token = f"__{proj_tok}__{business_domain_tok}__{title_sanitized}__v"
    # New format token (default pattern, no area): __{proj}__{fs_safe_title}__v
    new_token = f"__{proj_tok}__{title_safe}__v"

    version_re = re.compile(r"__v(\d+)" + re.escape(suffix.lower()) + r"$")

    def _scan_text(text: str) -> None:
        nonlocal latest
        low = text.lower()
        if old_token not in low and new_token not in low:
            return
        m = version_re.search(low)
        if m:
            latest = max(latest, int(m.group(1)))

    work_root = project_root / areas_root_rel(profile)
    if work_root.exists():
        for f in work_root.rglob(f"*{suffix.lower()}"):
            if f.is_file():
                _scan_text(f.name)

    index_path = project_root / "_INDEX.md"
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            _scan_text(line)
    return latest


def _find_original_in_triage(project_root: Path, profile: dict[str, Any], sha256: str) -> dict[str, Any] | None:
    """Return metadata of the first existing document matching sha256 in triage dirs."""
    triage = triage_paths(profile)
    for rel in (triage["pending"], triage["resolved"], triage["rejected"]):
        d = project_root / rel
        if not d.exists():
            continue
        for meta in d.glob("*.json"):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("sha256") == sha256:
                return data
    return None


def _find_original_in_search_index(client: OpenSearch, project_id: str, sha256: str) -> dict[str, Any] | None:
    """Return the _source of the first indexed document matching sha256."""
    query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"project_id": project_id}},
                    {"term": {"sha256": sha256}},
                ]
            }
        },
        "size": 1,
        "track_total_hits": False,
    }
    try:
        result = client.search(index=settings.opensearch_index, body=query)
        hits = result.get("hits", {}).get("hits", [])
        if hits:
            return hits[0].get("_source", {})
    except Exception:
        pass
    return None


def _build_unique_triage_pending_path(*, pending_dir: Path, original_name: str, doc_id: str) -> Path:
    # Prefixing doc_id prevents file overwrite when the same original filename is ingested again.
    base_name = f"{doc_id[:8]}__{original_name}"
    target = pending_dir / base_name
    if not target.exists():
        return target
    return pending_dir / f"{doc_id}__{original_name}"


def process_inbox_file(
    *,
    client: OpenSearch,
    project_root: Path,
    profile: dict[str, Any],
    inbox_file: Path,
) -> dict[str, Any]:
    ensure_project_structure(project_root, profile)

    project_id = profile["project_id"]
    sha = sha256_file(inbox_file)

    # ── Early dedup: SHA256 check before any classification/LLM work ──
    original_triage = _find_original_in_triage(project_root, profile, sha)
    original_index = _find_original_in_search_index(client, project_id, sha) if not original_triage else None
    original = original_triage or original_index

    if original:
        inbox_file.unlink()
        return {
            "doc_id": original.get("doc_id", ""),
            "project_id": project_id,
            "business_domain": (
                original.get("business_domain")
                or original.get("suggested_business_domain")
                or "unclassified"
            ),
            "title": original.get("title") or inbox_file.stem,
            "original_filename": inbox_file.name,
            "canonical_filename": original.get("canonical_filename", ""),
            "path": original.get("path") or original.get("source_path", ""),
            "decision": "duplicate",
            "confidence_score": float(original.get("confidence_score") or original.get("confidence", 0.0)),
            "sha256": sha,
            "tags": original.get("tags", []),
            "duplicate_of": original.get("doc_id", ""),
        }

    # ── Classification pipeline (only for non-duplicates) ──
    doc_id = str(uuid.uuid4())
    text_excerpt = read_text_excerpt(inbox_file)
    classification = classify_with_operational_mode(profile=profile, source_path=inbox_file, text_excerpt=text_excerpt)

    llm_result: dict[str, Any] | None = None
    policy = _llm_policy(profile)
    llm_enabled = bool(policy.get("enabled")) or bool(getattr(settings, "classification_llm_enabled", False))
    if llm_enabled:
        try:
            from .orchestrator import classify_with_llm

            provider_override = policy.get("provider") if policy.get("enabled") else None
            model_override = policy.get("model") if policy.get("enabled") else None
            llm_result = asyncio.run(
                classify_with_llm(
                    doc_id,
                    text_excerpt,
                    inbox_file.name,
                    provider_override=provider_override,
                    model_override=model_override,
                    profile=profile,
                )
            )
        except Exception:
            llm_result = None

    if llm_result and llm_result.get("usage"):
        _persist_classification_usage(
            doc_id=doc_id,
            filename=inbox_file.name,
            project_id=project_id,
            provider=llm_result.get("provider", ""),
            model=llm_result.get("model", ""),
            usage=llm_result["usage"],
        )

    classification, force_triage_pending = _apply_llm_policy(
        profile=profile,
        classification=classification,
        llm_result=llm_result,
    )

    auto_route_min = float(profile.get("confidence_thresholds", {}).get("auto_route_min", 0.85))
    triage_min = float(profile.get("confidence_thresholds", {}).get("triage_min", 0.5))
    confidence = float(classification["confidence"])
    business_domain = classification.get("business_domain")
    if not business_domain:
        raise ValueError("bootstrap classification did not return business_domain")
    document_type = str(classification.get("document_type") or "").strip()
    if not document_type:
        raise ValueError("bootstrap classification did not return document_type")

    area_path = resolve_classification_path(
        project_root=project_root,
        profile=profile,
        business_domain=str(business_domain),
        document_type=document_type,
        create_if_missing=True,
    )

    ingested_at = utc_now_iso()

    next_version = _find_latest_version(
        project_root=project_root,
        profile=profile,
        project_id=project_id,
        business_domain=business_domain or "unclassified",
        title_token=inbox_file.stem,
        suffix=(inbox_file.suffix or ".bin"),
    ) + 1

    naming = profile.get("naming") or {}
    canonical_pattern = naming.get("canonical_pattern", DEFAULT_CANONICAL_PATTERN)
    date_format = naming.get("date_format", "%Y%m%d")

    canonical_filename = build_canonical_filename(
        pattern=canonical_pattern,
        date_format=date_format,
        fields={
            "project": project_id,
            "business_domain": business_domain or "unclassified",
            "original_name": inbox_file.stem,
            "document_type": document_type,
        },
        original_suffix=inbox_file.suffix or ".bin",
        version=next_version,
    )

    if confidence >= auto_route_min and business_domain and not force_triage_pending:
        dest_dir = project_root / area_path
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / canonical_filename
        shutil.move(str(inbox_file), str(dest_file))
        decision = "auto"
        path_for_index = str(dest_file)
    elif confidence >= triage_min or force_triage_pending:
        triage = triage_paths(profile)
        dest_dir = project_root / triage["pending"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = _build_unique_triage_pending_path(
            pending_dir=dest_dir,
            original_name=inbox_file.name,
            doc_id=doc_id,
        )
        shutil.move(str(inbox_file), str(dest_file))
        decision = "triage_pending"
        path_for_index = str(dest_file)

        meta = {
            "doc_id": doc_id,
            "filename": dest_file.name,
            "project_id": project_id,
            "suggested_business_domain": business_domain,
            "suggested_path": area_path,
            "suggested_document_type": document_type,
            "confidence_score": confidence,
            "business_domain_confidence": float(classification.get("business_domain_confidence") or confidence),
            "document_type_confidence": float(classification.get("document_type_confidence") or 0.0),
            "reason": classification.get("reason", "triage_pending"),
            "top_candidates": classification["top_candidates"],
            "top_document_type_candidates": classification.get("top_document_type_candidates", []),
            "source_path": str(dest_file),
            "metadata_path": "",
            "original_filename": inbox_file.name,
            "canonical_filename": canonical_filename,
            "document_type": document_type,
            "topics": classification.get("topics", []),
            "entities": classification.get("entities", []),
            "sha256": sha,
            "ingested_at": ingested_at,
            "naming_pattern": canonical_pattern,
            "classifier_mode": classification.get("classifier_mode"),
            "classifier_requested_mode": classification.get("classifier_requested_mode"),
            "classifier_fallback_reason": classification.get("classifier_fallback_reason"),
        }
        if classification.get("_rule_business_domain"):
            meta["rule_business_domain"] = classification["_rule_business_domain"]
            meta["rule_confidence"] = classification.get("_rule_confidence", 0)
        if classification.get("llm_explanation"):
            meta["llm_explanation"] = classification["llm_explanation"]
        if classification.get("llm_proposed_business_domain"):
            meta["llm_proposed_business_domain"] = classification["llm_proposed_business_domain"]
        meta_path = save_pending_metadata(project_root, doc_id, meta)
        meta["metadata_path"] = str(meta_path)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        triage = triage_paths(profile)
        dest_dir = project_root / triage["pending"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = _build_unique_triage_pending_path(
            pending_dir=dest_dir,
            original_name=inbox_file.name,
            doc_id=doc_id,
        )
        shutil.move(str(inbox_file), str(dest_file))
        decision = "triage_pending"
        path_for_index = str(dest_file)
        meta = {
            "doc_id": doc_id,
            "filename": dest_file.name,
            "project_id": project_id,
            "suggested_business_domain": business_domain,
            "suggested_path": area_path,
            "suggested_document_type": document_type,
            "confidence_score": confidence,
            "business_domain_confidence": float(classification.get("business_domain_confidence") or confidence),
            "document_type_confidence": float(classification.get("document_type_confidence") or 0.0),
            "reason": "below_triage_min",
            "top_candidates": classification.get("top_candidates", []),
            "top_document_type_candidates": classification.get("top_document_type_candidates", []),
            "source_path": str(dest_file),
            "metadata_path": "",
            "original_filename": inbox_file.name,
            "canonical_filename": canonical_filename,
            "document_type": document_type,
            "topics": classification.get("topics", []),
            "entities": classification.get("entities", []),
            "sha256": sha,
            "ingested_at": ingested_at,
            "naming_pattern": canonical_pattern,
            "classifier_mode": classification.get("classifier_mode"),
            "classifier_requested_mode": classification.get("classifier_requested_mode"),
            "classifier_fallback_reason": classification.get("classifier_fallback_reason"),
        }
        if classification.get("_rule_business_domain"):
            meta["rule_business_domain"] = classification["_rule_business_domain"]
            meta["rule_confidence"] = classification.get("_rule_confidence", 0)
        if classification.get("llm_explanation"):
            meta["llm_explanation"] = classification["llm_explanation"]
        if classification.get("llm_proposed_business_domain"):
            meta["llm_proposed_business_domain"] = classification["llm_proposed_business_domain"]
        meta_path = save_pending_metadata(project_root, doc_id, meta)
        meta["metadata_path"] = str(meta_path)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    tags = [business_domain or "unclassified", document_type]
    if classification.get("suggested_tags"):
        tags = list(set(tags + classification["suggested_tags"]))
    if confidence < auto_route_min or (llm_result and (llm_result.get("confidence") or 0) < auto_route_min):
        if "REVIEW_REQUIRED" not in tags:
            tags.append("REVIEW_REQUIRED")
    payload = {
        "doc_id": doc_id,
        "project_id": project_id,
        "business_domain": business_domain or "unclassified",
        "title": inbox_file.stem,
        "content": text_excerpt,
        "original_filename": inbox_file.name,
        "canonical_filename": canonical_filename,
        "path": path_for_index,
        "source_channel": "",
        "source_ref": "",
        "sender": "",
        "received_at": None,
        "ingested_at": ingested_at,
        "processed_at": utc_now_iso(),
        "decision": decision,
        "confidence_score": confidence,
        "business_domain_confidence": float(classification.get("business_domain_confidence") or confidence),
        "document_type_confidence": float(classification.get("document_type_confidence") or 0.0),
        "sha256": sha,
        "tags": tags,
        "naming_pattern": canonical_pattern,
        "entities": classification.get("entities", []),
        "classifier_mode": classification.get("classifier_mode"),
        "classifier_requested_mode": classification.get("classifier_requested_mode"),
    }
    if classification.get("classifier_fallback_reason"):
        payload["classifier_fallback_reason"] = classification["classifier_fallback_reason"]
    payload["document_type"] = document_type
    if classification.get("suggested_topics"):
        payload["topics"] = list(classification.get("suggested_topics") or [])
        payload["topics_source"] = "llm_policy"
    elif classification.get("topics"):
        payload["topics"] = list(classification.get("topics") or [])
        payload["topics_source"] = classification.get("topics_source", "synonym_match")
    if confidence < auto_route_min or (llm_result and (llm_result.get("confidence") or 0) < auto_route_min):
        payload["review_status"] = "needs_review"

    # LLM visibility fields
    if classification.get("_rule_business_domain"):
        payload["rule_business_domain"] = classification["_rule_business_domain"]
        payload["rule_confidence"] = classification.get("_rule_confidence", 0)
    if classification.get("llm_explanation"):
        payload["llm_explanation"] = classification["llm_explanation"]
    if classification.get("llm_proposed_business_domain"):
        payload["llm_proposed_business_domain"] = classification["llm_proposed_business_domain"]
    payload["classification_reason"] = classification.get("reason", "")

    if decision == "auto":
        enriched = index_document(client, payload, profile=profile)
        index_document_chunks_embeddings(client, enriched)

    _append_index_md(project_root, payload)
    return payload
