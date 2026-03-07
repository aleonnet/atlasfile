from __future__ import annotations

import asyncio
import json
import math
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch

from .area_resolver import resolve_area_path
from .bootstrap import ensure_project_structure
from .config import settings
from .indexer import index_document, read_text_excerpt
from .profile_runtime import areas_root_rel, triage_paths
from .triage import save_pending_metadata
from .utils import (
    DEFAULT_CANONICAL_PATTERN,
    build_canonical_filename,
    fs_safe,
    normalize_text,
    sanitize_token,
    sha256_file,
    utc_now_iso,
)

_wb_cache: dict[str, re.Pattern[str]] = {}


def _match_normalize(text: str) -> str:
    """Replace underscores/hyphens with spaces so \b works on separated tokens."""
    return text.replace("_", " ").replace("-", " ")


def _wb_pattern(token: str) -> re.Pattern[str]:
    """Compiled word-boundary pattern, cached. Token is already match-normalized."""
    pat = _wb_cache.get(token)
    if pat is None:
        pat = re.compile(rf"\b{re.escape(token)}\b")
        _wb_cache[token] = pat
    return pat


def _score_area(area: dict[str, Any], text: str) -> float:
    aliases = [_match_normalize(normalize_text(a)) for a in area.get("aliases", [])]
    if not aliases:
        return 0.0
    mtext = _match_normalize(text)
    hits = sum(1 for alias in aliases if _wb_pattern(alias).search(mtext))
    return min(1.0, hits / max(1.0, math.sqrt(len(aliases))))


def classify(
    *,
    profile: dict[str, Any],
    source_path: Path,
    text_excerpt: str,
) -> dict[str, Any]:
    fname = normalize_text(source_path.name)
    path_text = normalize_text(str(source_path))
    full_text = f"{fname} {path_text} {normalize_text(text_excerpt)}"

    # 1) explicit routing rules (word-boundary matching)
    mpath = _match_normalize(path_text)
    mfname = _match_normalize(fname)
    for rule in profile.get("routing_rules", []):
        for token in rule.get("when_path_contains", []):
            if _wb_pattern(_match_normalize(normalize_text(token))).search(mpath):
                return {
                    "area_key": rule["route_to"],
                    "confidence": float(rule.get("confidence", 0.9)),
                    "reason": f"path_contains:{token}",
                    "top_candidates": [],
                }
        for token in rule.get("when_filename_contains", []):
            if _wb_pattern(_match_normalize(normalize_text(token))).search(mfname):
                return {
                    "area_key": rule["route_to"],
                    "confidence": float(rule.get("confidence", 0.9)),
                    "reason": f"filename_contains:{token}",
                    "top_candidates": [],
                }

    # 2) score by aliases (rule + assistive fallback)
    candidates: list[tuple[str, float]] = []
    for area in profile.get("work_areas", []):
        area_key = area.get("key")
        if not area_key:
            continue
        score = _score_area(area, full_text)
        candidates.append((area_key, score))
    candidates.sort(key=lambda x: x[1], reverse=True)

    if not candidates:
        return {"area_key": None, "confidence": 0.0, "reason": "no_candidates", "top_candidates": []}

    best_key, best_score = candidates[0]
    top_candidates = [{"area_key": key, "score": round(score, 4)} for key, score in candidates[:3]]
    return {
        "area_key": best_key,
        "confidence": float(best_score),
        "reason": "alias_scoring",
        "top_candidates": top_candidates,
    }


def _llm_policy(profile: dict[str, Any]) -> dict[str, Any]:
    policy = dict(profile.get("llm_policy") or {})
    classification_policy = ((profile.get("classification") or {}).get("llm_policy") or {})
    for k, v in classification_policy.items():
        policy.setdefault(k, v)
    policy.setdefault("enabled", False)
    policy.setdefault("mode", "tag_only")
    policy.setdefault("allow_override_fields", ["document_type", "tags", "confidence", "topics"])
    guardrails = dict(policy.get("override_guardrails") or {})
    guardrails.setdefault("area_override_only_if_rule_confidence_below", 0.65)
    guardrails.setdefault("require_explanation", True)
    guardrails.setdefault("max_area_changes", 1)
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
    area_keys = {str(a.get("key") or "").strip() for a in profile.get("work_areas", [])}
    force_triage_pending = False

    rule_conf = float(classification.get("confidence") or 0.0)
    llm_conf = float(llm_result.get("confidence") or 0.0)
    raw_llm_area = str(llm_result.get("area_key") or "").strip() or None
    explanation = str(llm_result.get("explanation") or "").strip()

    # Preserve rule-based results before any mutation
    classification["_rule_area_key"] = classification.get("area_key")
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

    # Preserve the raw LLM area even if it doesn't exist in current areas
    llm_area = raw_llm_area
    if raw_llm_area and raw_llm_area not in area_keys:
        classification["llm_proposed_area"] = raw_llm_area
        llm_area = None

    current_area = str(classification.get("area_key") or "").strip() or None
    if not llm_area or llm_area == current_area:
        return classification, force_triage_pending

    if mode == "review":
        classification["reason"] = "llm_review_divergence"
        force_triage_pending = True
        return classification, force_triage_pending

    if mode == "full_override":
        guardrails = dict(policy.get("override_guardrails") or {})
        threshold = float(guardrails.get("area_override_only_if_rule_confidence_below") or 0.65)
        require_explanation = bool(guardrails.get("require_explanation", True))
        max_area_changes = int(guardrails.get("max_area_changes", 1) or 1)
        can_override = (
            max_area_changes > 0
            and rule_conf < threshold
            and llm_conf >= rule_conf
            and (not require_explanation or bool(explanation))
        )
        if can_override:
            classification["area_key"] = llm_area
            classification["reason"] = "llm_full_override"
            return classification, force_triage_pending

        classification["reason"] = "llm_override_guardrail_blocked"
        force_triage_pending = True
        return classification, force_triage_pending

    return classification, force_triage_pending


def _append_index_md(project_root: Path, row: dict[str, Any]) -> None:
    index_path = project_root / "_INDEX.md"
    if not index_path.exists():
        index_path.write_text(
            "# _INDEX\n\n"
            "| doc_id | project_id | area | original_filename | canonical_filename | decision | confidence | path | naming_pattern |\n"
            "|---|---|---|---|---|---|---:|---|---|\n",
            encoding="utf-8",
        )

    existing_lines = index_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    row_key = (
        str(row.get("project_id", "")).strip(),
        str(row.get("path", "")).strip(),
        str(row.get("decision", "")).strip(),
        str(row.get("sha256", "")).strip(),
        str(row.get("canonical_filename", "")).strip(),
    )
    for raw in existing_lines:
        if not raw.startswith("| ") or raw.startswith("|---"):
            continue
        cols = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cols) < 8:
            continue
        existing_key = (
            cols[1],  # project_id
            cols[7],  # path
            cols[5],  # decision
            "",  # sha256 not present in markdown row
            cols[4],  # canonical_filename
        )
        if row_key[:3] == existing_key[:3] and row_key[4] == existing_key[4]:
            return

    np = row.get("naming_pattern", "")
    line = (
        f"| {row['doc_id']} | {row['project_id']} | {row.get('area_key', '')} | "
        f"{row['original_filename']} | {row['canonical_filename']} | {row['decision']} | "
        f"{row['confidence_score']:.2f} | {row['path']} | {np} |\n"
    )
    with index_path.open("a", encoding="utf-8") as f:
        f.write(line)


def _find_latest_version(
    *,
    project_root: Path,
    profile: dict[str, Any],
    project_id: str,
    area_key: str,
    title_token: str,
    suffix: str,
) -> int:
    latest = 0
    proj_tok = sanitize_token(project_id)
    area_tok = sanitize_token(area_key)
    title_sanitized = sanitize_token(title_token)
    title_safe = fs_safe(title_token).lower()

    # Old format token: __{proj}__{area}__{sanitized_title}__v
    old_token = f"__{proj_tok}__{area_tok}__{title_sanitized}__v"
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
            "area_key": original.get("area_key") or original.get("suggested_area") or "unclassified",
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
    classification = classify(profile=profile, source_path=inbox_file, text_excerpt=text_excerpt)

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

    classification, force_triage_pending = _apply_llm_policy(
        profile=profile,
        classification=classification,
        llm_result=llm_result,
    )

    auto_route_min = float(profile.get("confidence_thresholds", {}).get("auto_route_min", 0.85))
    triage_min = float(profile.get("confidence_thresholds", {}).get("triage_min", 0.5))
    confidence = float(classification["confidence"])
    area_key = classification.get("area_key")

    if area_key:
        area_path = resolve_area_path(
            project_root=project_root,
            profile=profile,
            area_key=area_key,
            create_if_missing=True,
        ) or areas_root_rel(profile)
    else:
        area_path = areas_root_rel(profile)

    ingested_at = utc_now_iso()

    next_version = _find_latest_version(
        project_root=project_root,
        profile=profile,
        project_id=project_id,
        area_key=area_key or "unclassified",
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
            "area": area_key or "unclassified",
            "original_name": inbox_file.stem,
            "document_type": classification.get("document_type", ""),
        },
        original_suffix=inbox_file.suffix or ".bin",
        version=next_version,
    )

    if confidence >= auto_route_min and area_key and not force_triage_pending:
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
            "suggested_area": area_key,
            "suggested_path": area_path,
            "confidence_score": confidence,
            "reason": classification.get("reason", "triage_pending"),
            "top_candidates": classification["top_candidates"],
            "source_path": str(dest_file),
            "metadata_path": "",
            "original_filename": inbox_file.name,
            "canonical_filename": canonical_filename,
            "sha256": sha,
            "ingested_at": ingested_at,
            "naming_pattern": canonical_pattern,
        }
        if classification.get("_rule_area_key"):
            meta["rule_area_key"] = classification["_rule_area_key"]
            meta["rule_confidence"] = classification.get("_rule_confidence", 0)
        if classification.get("llm_explanation"):
            meta["llm_explanation"] = classification["llm_explanation"]
        if classification.get("llm_proposed_area"):
            meta["llm_proposed_area"] = classification["llm_proposed_area"]
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
            "suggested_area": None,
            "suggested_path": None,
            "confidence_score": confidence,
            "reason": "below_triage_min",
            "top_candidates": classification.get("top_candidates", []),
            "source_path": str(dest_file),
            "metadata_path": "",
            "original_filename": inbox_file.name,
            "canonical_filename": canonical_filename,
            "sha256": sha,
            "ingested_at": ingested_at,
            "naming_pattern": canonical_pattern,
        }
        if classification.get("_rule_area_key"):
            meta["rule_area_key"] = classification["_rule_area_key"]
            meta["rule_confidence"] = classification.get("_rule_confidence", 0)
        if classification.get("llm_explanation"):
            meta["llm_explanation"] = classification["llm_explanation"]
        if classification.get("llm_proposed_area"):
            meta["llm_proposed_area"] = classification["llm_proposed_area"]
        meta_path = save_pending_metadata(project_root, doc_id, meta)
        meta["metadata_path"] = str(meta_path)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    tags = [area_key or "unclassified"]
    if classification.get("suggested_tags"):
        tags = list(set(tags + classification["suggested_tags"]))
    if confidence < auto_route_min or (llm_result and (llm_result.get("confidence") or 0) < auto_route_min):
        if "REVIEW_REQUIRED" not in tags:
            tags.append("REVIEW_REQUIRED")
    payload = {
        "doc_id": doc_id,
        "project_id": project_id,
        "area_key": area_key or "unclassified",
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
        "sha256": sha,
        "tags": tags,
        "naming_pattern": canonical_pattern,
    }
    if classification.get("document_type"):
        payload["document_type"] = classification["document_type"]
    if classification.get("suggested_topics"):
        payload["topics"] = list(classification.get("suggested_topics") or [])
        payload["topics_source"] = "llm_policy"
    if confidence < auto_route_min or (llm_result and (llm_result.get("confidence") or 0) < auto_route_min):
        payload["review_status"] = "needs_review"

    # LLM visibility fields
    if classification.get("_rule_area_key"):
        payload["rule_area_key"] = classification["_rule_area_key"]
        payload["rule_confidence"] = classification.get("_rule_confidence", 0)
    if classification.get("llm_explanation"):
        payload["llm_explanation"] = classification["llm_explanation"]
    if classification.get("llm_proposed_area"):
        payload["llm_proposed_area"] = classification["llm_proposed_area"]
    payload["classification_reason"] = classification.get("reason", "")

    if decision == "auto":
        index_document(client, payload, profile=profile)

    _append_index_md(project_root, payload)
    return payload
