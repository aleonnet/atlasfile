from __future__ import annotations

import asyncio
import json
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
from .triage import save_pending_metadata
from .utils import build_canonical_filename, normalize_text, sanitize_token, sha256_file, utc_now_iso


def _score_area(area: dict[str, Any], text: str) -> float:
    aliases = [normalize_text(a) for a in area.get("aliases", [])]
    if not aliases:
        return 0.0
    hits = sum(1 for alias in aliases if alias in text)
    return hits / len(aliases)


def classify(
    *,
    profile: dict[str, Any],
    source_path: Path,
    text_excerpt: str,
) -> dict[str, Any]:
    fname = normalize_text(source_path.name)
    path_text = normalize_text(str(source_path))
    full_text = f"{fname} {path_text} {normalize_text(text_excerpt)}"

    # 1) explicit routing rules
    for rule in profile.get("routing_rules", []):
        for token in rule.get("when_path_contains", []):
            if normalize_text(token) in path_text:
                return {
                    "area_key": rule["route_to"],
                    "confidence": float(rule.get("confidence", 0.9)),
                    "reason": f"path_contains:{token}",
                    "top_candidates": [],
                }
        for token in rule.get("when_filename_contains", []):
            if normalize_text(token) in fname:
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


def _append_index_md(project_root: Path, row: dict[str, Any]) -> None:
    index_path = project_root / "_INDEX.md"
    if not index_path.exists():
        index_path.write_text(
            "# _INDEX\n\n"
            "| doc_id | project_id | area | original_filename | canonical_filename | decision | confidence | path |\n"
            "|---|---|---|---|---|---|---:|---|\n",
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
        # Prevent repeated rows for the same record/path/decision.
        if row_key[:3] == existing_key[:3] and row_key[4] == existing_key[4]:
            return

    line = (
        f"| {row['doc_id']} | {row['project_id']} | {row.get('area_key', '')} | "
        f"{row['original_filename']} | {row['canonical_filename']} | {row['decision']} | "
        f"{row['confidence_score']:.2f} | {row['path']} |\n"
    )
    with index_path.open("a", encoding="utf-8") as f:
        f.write(line)


def _find_latest_version(
    *,
    project_root: Path,
    project_id: str,
    area_key: str,
    title_token: str,
    suffix: str,
) -> int:
    latest = 0
    token = (
        f"__{sanitize_token(project_id)}__{sanitize_token(area_key)}__"
        f"{sanitize_token(title_token)}__v"
    )
    version_re = re.compile(r"__v(\d+)" + re.escape(suffix.lower()) + r"$")

    # inspect existing work files
    work_root = project_root / "_WORK"
    if work_root.exists():
        for f in work_root.rglob(f"*{suffix.lower()}"):
            if not f.is_file():
                continue
            name = f.name.lower()
            if token not in name:
                continue
            m = version_re.search(name)
            if m:
                latest = max(latest, int(m.group(1)))

    # inspect index history
    index_path = project_root / "_INDEX.md"
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if token not in line.lower():
                continue
            m = version_re.search(line.lower())
            if m:
                latest = max(latest, int(m.group(1)))
    return latest


def _sha_exists_in_triage(project_root: Path, sha256: str) -> bool:
    triage_root = project_root / "_TRIAGE_REVIEW"
    if not triage_root.exists():
        return False
    for state in ("pending", "resolved", "rejected"):
        d = triage_root / state
        if not d.exists():
            continue
        for meta in d.glob("*.json"):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("sha256") == sha256:
                return True
    return False


def _sha_exists_in_search_index(client: OpenSearch, project_id: str, sha256: str) -> bool:
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
        return len(result.get("hits", {}).get("hits", [])) > 0
    except Exception:
        return False


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
    doc_id = str(uuid.uuid4())
    text_excerpt = read_text_excerpt(inbox_file)
    classification = classify(profile=profile, source_path=inbox_file, text_excerpt=text_excerpt)

    llm_result: dict[str, Any] | None = None
    if getattr(settings, "classification_llm_enabled", False):
        try:
            from .orchestrator import classify_with_llm
            llm_result = asyncio.run(classify_with_llm(doc_id, text_excerpt, inbox_file.name))
        except Exception:
            llm_result = None
    if llm_result and (llm_result.get("confidence") or 0) > 0:
        classification["confidence"] = llm_result.get("confidence", classification.get("confidence", 0))
        if llm_result.get("tags"):
            classification["suggested_tags"] = llm_result["tags"]
        if llm_result.get("document_type"):
            classification["document_type"] = llm_result["document_type"]

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
        ) or "_WORK"
    else:
        area_path = "_WORK"

    sha = sha256_file(inbox_file)
    ingested_at = utc_now_iso()

    # Dedup by project + sha256.
    if _sha_exists_in_triage(project_root, sha) or _sha_exists_in_search_index(client, project_id, sha):
        dup_doc_id = str(uuid.uuid4())
        rejected_dir = project_root / "_TRIAGE_REVIEW" / "rejected"
        rejected_dir.mkdir(parents=True, exist_ok=True)
        target_name = inbox_file.name
        target_path = rejected_dir / target_name
        if target_path.exists():
            target_path = rejected_dir / f"{inbox_file.stem}__dup_{dup_doc_id[:8]}{inbox_file.suffix}"
        shutil.move(str(inbox_file), str(target_path))

        meta = {
            "doc_id": dup_doc_id,
            "filename": target_path.name,
            "project_id": project_id,
            "suggested_area": classification.get("area_key"),
            "suggested_path": None,
            "confidence_score": float(classification.get("confidence", 0.0)),
            "reason": "duplicate_sha256",
            "top_candidates": classification.get("top_candidates", []),
            "source_path": str(target_path),
            "metadata_path": str(rejected_dir / f"{dup_doc_id}.json"),
            "original_filename": inbox_file.name,
            "canonical_filename": "",
            "sha256": sha,
            "ingested_at": ingested_at,
            "decision": "duplicate",
        }
        (rejected_dir / f"{dup_doc_id}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        payload = {
            "doc_id": dup_doc_id,
            "project_id": project_id,
            "area_key": classification.get("area_key") or "unclassified",
            "title": inbox_file.stem,
            "content": text_excerpt,
            "original_filename": inbox_file.name,
            "canonical_filename": "",
            "path": str(target_path),
            "source_channel": "",
            "source_ref": "",
            "sender": "",
            "received_at": None,
            "ingested_at": ingested_at,
            "processed_at": utc_now_iso(),
            "decision": "duplicate",
            "confidence_score": float(classification.get("confidence", 0.0)),
            "sha256": sha,
            "tags": [classification.get("area_key") or "unclassified"],
        }
        _append_index_md(project_root, payload)
        return payload

    next_version = _find_latest_version(
        project_root=project_root,
        project_id=project_id,
        area_key=area_key or "unclassified",
        title_token=inbox_file.stem,
        suffix=(inbox_file.suffix or ".bin"),
    ) + 1

    canonical_filename = build_canonical_filename(
        project_id=project_id,
        area_key=area_key or "unclassified",
        short_title=inbox_file.stem,
        original_suffix=inbox_file.suffix or ".bin",
        version=next_version,
    )

    if confidence >= auto_route_min and area_key:
        dest_dir = project_root / area_path
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / canonical_filename
        shutil.move(str(inbox_file), str(dest_file))
        decision = "auto"
        path_for_index = str(dest_file)
    elif confidence >= triage_min:
        dest_dir = project_root / "_TRIAGE_REVIEW" / "pending"
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
            "reason": classification["reason"],
            "top_candidates": classification["top_candidates"],
            "source_path": str(dest_file),
            "metadata_path": "",
            "original_filename": inbox_file.name,
            "canonical_filename": canonical_filename,
            "sha256": sha,
            "ingested_at": ingested_at,
        }
        meta_path = save_pending_metadata(project_root, doc_id, meta)
        meta["metadata_path"] = str(meta_path)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        dest_dir = project_root / "_TRIAGE_REVIEW" / "pending"
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
        }
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
    }
    if classification.get("document_type"):
        payload["document_type"] = classification["document_type"]
    if confidence < auto_route_min or (llm_result and (llm_result.get("confidence") or 0) < auto_route_min):
        payload["review_status"] = "needs_review"

    if decision == "auto":
        index_document(client, payload)

    _append_index_md(project_root, payload)
    return payload
