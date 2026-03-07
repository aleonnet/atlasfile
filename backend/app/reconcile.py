from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from opensearchpy import OpenSearch
from opensearchpy.exceptions import TransportError

from .config import settings
from .indexer import index_document, read_text_excerpt
from .opensearch_client import ensure_index
from .profile_runtime import area_folder_map, areas_root_rel, para_scan_roots, triage_paths
from .project_profile import load_project_profile
from .utils import (
    DEFAULT_CANONICAL_PATTERN,
    extract_original_name_from_canonical,
    normalize_text,
    sanitize_token,
    sha256_file,
)

_VERSION_TAIL_RE = re.compile(r"__v(\d{2})(\.\w+)$")


def _is_ignored_file(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _parse_index_rows(index_path: Path) -> list[dict[str, str]]:
    if not index_path.exists():
        return []
    rows: list[dict[str, str]] = []
    for raw in index_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not raw.startswith("| ") or raw.startswith("|---"):
            continue
        cols = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cols) < 8:
            continue
        if cols[0] == "doc_id":
            continue
        row = {
            "doc_id": cols[0],
            "project_id": cols[1],
            "area": cols[2],
            "original_filename": cols[3],
            "canonical_filename": cols[4],
            "decision": cols[5],
            "confidence": cols[6],
            "path": cols[7],
            "naming_pattern": cols[8] if len(cols) > 8 else "",
        }
        rows.append(row)
    return rows


def _infer_area_from_layout_path(work_file: Path, project_root: Path, profile: dict[str, Any], scan_root: Path | None = None) -> str:
    base = scan_root if scan_root is not None else (project_root / areas_root_rel(profile))
    try:
        rel = work_file.relative_to(base)
    except ValueError:
        return "unclassified"
    first = rel.parts[0] if rel.parts else ""
    folder_to_area = {folder: area for area, folder in area_folder_map(profile).items()}
    if first in folder_to_area:
        return folder_to_area[first]
    if "_" in first:
        return first.split("_", 1)[1]
    return "unclassified"


def _try_migrate_old_format(f: Path, profile: dict[str, Any]) -> Path | None:
    """Rename a file from old canonical format (with area segment) to new format.

    Old: ``YYYYMMDD__proj__area__title__vNN.ext``
    New: ``YYYYMMDD__proj__title__vNN.ext``

    Returns the new Path if renamed, ``None`` otherwise.
    """
    tail = _VERSION_TAIL_RE.search(f.name)
    if not tail:
        return None

    prefix = f.name[: tail.start()]
    parts = prefix.split("__")

    # Old format produces exactly 4 segments (sanitize_token never yields __)
    if len(parts) != 4:
        return None

    date_part, proj_part, candidate_area, title_part = parts
    if not (len(date_part) == 8 and date_part.isdigit()):
        return None

    area_keys: set[str] = set()
    for wa in (profile.get("classification") or {}).get("work_areas", []):
        k = wa.get("key", "")
        if k:
            area_keys.add(sanitize_token(k))
    for af in (profile.get("layout") or {}).get("area_folders", []):
        k = af.get("area_key", "")
        if k:
            area_keys.add(sanitize_token(k))
    area_keys.add("unclassified")

    if candidate_area not in area_keys:
        return None

    version_suffix = tail.group(0)
    new_name = f"{date_part}__{proj_part}__{title_part}{version_suffix}"
    new_path = f.parent / new_name
    if new_path.exists():
        logger.warning("Migration skip: %s -> %s (destination exists)", f.name, new_name)
        return None

    f.rename(new_path)
    logger.info("Migration: renamed %s -> %s", f.name, new_name)
    return new_path


def _triage_rows(project_root: Path, project_id: str, profile: dict[str, Any]) -> list[dict[str, str]]:
    naming = profile.get("naming") or {}
    current_pattern = naming.get("canonical_pattern", DEFAULT_CANONICAL_PATTERN)
    out: list[dict[str, str]] = []
    triage = triage_paths(profile)
    for state, rel in (("pending", triage["pending"]), ("rejected", triage["rejected"])):
        state_dir = project_root / rel
        if not state_dir.exists():
            continue
        for meta in sorted(state_dir.glob("*.json"), key=lambda p: p.name):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                continue
            decision = str(data.get("decision") or ("triage_pending" if state == "pending" else state))
            out.append(
                {
                    "doc_id": str(data.get("doc_id") or uuid.uuid4()),
                    "project_id": str(data.get("project_id") or project_id),
                    "area": str(data.get("suggested_area") or data.get("area_key") or "unclassified"),
                    "original_filename": str(data.get("original_filename") or data.get("filename") or ""),
                    "canonical_filename": str(data.get("canonical_filename") or ""),
                    "decision": decision,
                    "confidence": f"{float(data.get('confidence_score') or 0.0):.2f}",
                    "path": str(data.get("source_path") or ""),
                    "naming_pattern": str(data.get("naming_pattern") or current_pattern),
                }
            )
    return out


def reconcile_project_index(project_root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    project_id = normalize_text(str(profile.get("project_id", project_root.name)))
    index_path = project_root / "_INDEX.md"

    existing_rows = _parse_index_rows(index_path)
    old_rows_set = {
        (
            row.get("doc_id", ""),
            row.get("project_id", ""),
            row.get("area", ""),
            row.get("original_filename", ""),
            row.get("canonical_filename", ""),
            row.get("decision", ""),
            row.get("confidence", ""),
            row.get("path", ""),
            row.get("naming_pattern", ""),
        )
        for row in existing_rows
    }
    existing_work_rows: dict[str, dict[str, str]] = {
        row["path"]: row for row in existing_rows if row.get("decision") in {"auto", "approved", "corrected"}
    }

    naming = profile.get("naming") or {}
    naming_pattern = naming.get("canonical_pattern", DEFAULT_CANONICAL_PATTERN)

    work_rows: list[dict[str, str]] = []
    # Scan all PARA roots (projects, areas, resources, archive)
    scan_entries = para_scan_roots(profile)
    seen_paths: set[str] = set()
    for folder_rel, category in scan_entries:
        scan_dir = project_root / folder_rel
        if not scan_dir.exists():
            continue
        for f in sorted(scan_dir.rglob("*"), key=lambda p: str(p).lower()):
            if not f.is_file():
                continue
            if _is_ignored_file(f.relative_to(project_root)):
                continue

            # Auto-migrate old canonical format -> new (remove area segment)
            old_path_str = str(f)
            new_path = _try_migrate_old_format(f, profile)
            if new_path is not None:
                f = new_path

            p = str(f)
            if p in seen_paths:
                continue
            seen_paths.add(p)
            prev = existing_work_rows.get(old_path_str) or existing_work_rows.get(p)

            # Reconstruct original_filename when no previous record exists
            orig_fn = (prev or {}).get("original_filename") or None
            # Use per-file pattern from previous index row when available
            row_pattern = (prev or {}).get("naming_pattern") or ""
            if not orig_fn:
                parse_pattern = row_pattern or naming_pattern
                extracted = extract_original_name_from_canonical(f.name, parse_pattern)
                if not extracted:
                    extracted = extract_original_name_from_canonical(
                        f.name, "{date}__{project}__{area}__{original_name}"
                    )
                if not extracted and parse_pattern != naming_pattern:
                    extracted = extract_original_name_from_canonical(f.name, naming_pattern)
                orig_fn = extracted or f.name

            # area_key: infer from subfolder for "areas" root; use PARA category otherwise
            if category == "areas":
                inferred_area = _infer_area_from_layout_path(f, project_root, profile, scan_root=scan_dir)
            else:
                inferred_area = category

            work_rows.append(
                {
                    "doc_id": (prev or {}).get("doc_id", str(uuid.uuid4())),
                    "project_id": project_id,
                    "area": (prev or {}).get("area", inferred_area),
                    "original_filename": orig_fn,
                    "canonical_filename": f.name,
                    "decision": (prev or {}).get("decision", "auto"),
                    "confidence": (prev or {}).get("confidence", "0.90"),
                    "path": p,
                    "naming_pattern": row_pattern or naming_pattern,
                }
            )

    triage_rows = _triage_rows(project_root, project_id, profile)

    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in work_rows + triage_rows:
        key = (row["doc_id"], row["path"], row["decision"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    rows.sort(key=lambda r: (r["path"], r["decision"], r["doc_id"]))
    new_rows_set = {
        (
            row.get("doc_id", ""),
            row.get("project_id", ""),
            row.get("area", ""),
            row.get("original_filename", ""),
            row.get("canonical_filename", ""),
            row.get("decision", ""),
            row.get("confidence", ""),
            row.get("path", ""),
            row.get("naming_pattern", ""),
        )
        for row in rows
    }
    added_rows = len(new_rows_set - old_rows_set)
    removed_rows = len(old_rows_set - new_rows_set)

    header = (
        "# _INDEX\n\n"
        "| doc_id | project_id | area | original_filename | canonical_filename | decision | confidence | path | naming_pattern |\n"
        "|---|---|---|---|---|---|---:|---|---|\n"
    )
    lines = [
        (
            f"| {r['doc_id']} | {r['project_id']} | {r['area']} | {r['original_filename']} | "
            f"{r['canonical_filename']} | {r['decision']} | {r['confidence']} | {r['path']} | {r.get('naming_pattern', '')} |"
        )
        for r in rows
    ]
    body = ("\n".join(lines) + "\n") if lines else ""
    index_path.write_text(header + body, encoding="utf-8")

    return {
        "project_id": project_id,
        "index_path": str(index_path),
        "rows_written": len(rows),
        "work_rows": len(work_rows),
        "triage_rows": len(triage_rows),
        "added_rows": added_rows,
        "removed_rows": removed_rows,
        "adjustments_applied": added_rows + removed_rows,
    }


def _build_doc_payload(row: dict[str, str], p: Path, current_sha: str) -> dict[str, Any]:
    return {
        "doc_id": row["doc_id"],
        "project_id": row["project_id"],
        "area_key": row["area"],
        "title": p.stem,
        "content": read_text_excerpt(p),
        "original_filename": row["original_filename"],
        "canonical_filename": row["canonical_filename"],
        "path": row["path"],
        "source_channel": "",
        "source_ref": "",
        "sender": "",
        "received_at": None,
        "ingested_at": None,
        "processed_at": None,
        "decision": row["decision"],
        "confidence_score": float(row["confidence"] or 0.0),
        "sha256": current_sha,
        "tags": [row["area"]] if row["area"] else [],
    }


def _project_scope_query(project_id: str, project_root: Path) -> dict[str, Any]:
    root_prefix = f"{str(project_root).rstrip('/')}/"
    return {
        "bool": {
            "should": [
                {"term": {"project_id": project_id}},
                {"prefix": {"path": root_prefix}},
            ],
            "minimum_should_match": 1,
        }
    }


def rebuild_search_index(
    client: OpenSearch,
    project_roots: list[Path],
    project_ids: list[tuple[Path, str]] | None = None,
    progress: dict[str, Any] | None = None,
) -> dict[str, int]:
    use_incremental = getattr(settings, "search_index_incremental_by_sha256", True)
    if not use_incremental:
        if client.indices.exists(index=settings.opensearch_index):
            client.indices.delete(index=settings.opensearch_index)
        ensure_index(client)
        indexed = 0
        for project_root in project_roots:
            try:
                profile = load_project_profile(project_root)
            except Exception:
                profile = {}
            for row in _parse_index_rows(project_root / "_INDEX.md"):
                if row["decision"] not in {"auto", "approved", "corrected"}:
                    continue
                p = Path(row["path"])
                if not p.exists() or not p.is_file():
                    continue
                if _is_ignored_file(p):
                    continue
                current_sha = sha256_file(p)
                payload = _build_doc_payload(row, p, current_sha)
                index_document(client, payload, refresh=False, profile=profile)
                indexed += 1
                if progress is not None:
                    progress["progress_current"] = progress.get("progress_current", 0) + 1
                    progress["progress_file"] = p.name
                    progress["progress_project"] = row["project_id"]
        return {"indexed_docs": indexed, "deleted_docs": 0, "skipped_docs": 0}

    ensure_index(client)
    indexed_total = 0
    skipped_total = 0
    failed_total = 0
    for project_root, project_id in project_ids or []:
        report = sync_search_index_for_project(client, project_root, project_id, progress=progress)
        indexed_total += report.get("indexed_docs", 0)
        skipped_total += report.get("skipped_docs", 0)
        failed_total += report.get("failed_docs", 0)
    return {
        "indexed_docs": indexed_total,
        "deleted_docs": 0,
        "skipped_docs": skipped_total,
        "failed_docs": failed_total,
    }


def cleanup_orphan_projects(
    client: OpenSearch,
    valid_project_ids: set[str],
    valid_project_roots: list[Path],
) -> dict[str, int]:
    """Remove OpenSearch docs belonging to projects that no longer exist on disk."""
    try:
        res = client.search(
            index=settings.opensearch_index,
            body={
                "size": 0,
                "aggs": {
                    "project_ids": {
                        "terms": {"field": "project_id", "size": 1000}
                    }
                },
            },
        )
    except Exception:
        logger.exception("Failed to query project_id aggregation for orphan cleanup")
        return {"orphan_projects_found": 0, "orphan_docs_deleted": 0}

    valid_path_prefixes = {f"{str(r).rstrip('/')}/" for r in valid_project_roots}
    buckets = res.get("aggregations", {}).get("project_ids", {}).get("buckets", [])
    indexed_ids = {b["key"] for b in buckets}

    # Normalize valid project IDs so accented/cased variants don't become orphans
    valid_normalized = {normalize_text(pid).replace(" ", "_") for pid in valid_project_ids}
    orphan_ids = {
        iid for iid in indexed_ids
        if normalize_text(iid).replace(" ", "_") not in valid_normalized
    }

    total_deleted = 0
    for orphan_id in orphan_ids:
        query: dict[str, Any] = {"term": {"project_id": orphan_id}}
        try:
            del_res = client.delete_by_query(
                index=settings.opensearch_index,
                body={"query": query},
                conflicts="proceed",
                refresh=False,
            )
            total_deleted += int(del_res.get("deleted", 0))
        except Exception:
            logger.exception("Failed to delete orphan docs for project_id=%s", orphan_id)

    if total_deleted > 0:
        try:
            client.indices.refresh(index=settings.opensearch_index)
        except Exception:
            pass

    return {"orphan_projects_found": len(orphan_ids), "orphan_docs_deleted": total_deleted}


def sync_search_index_for_project(
    client: OpenSearch,
    project_root: Path,
    project_id: str,
    progress: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Synchronize one project's search docs without dropping global index."""
    ensure_index(client)
    use_incremental = getattr(settings, "search_index_incremental_by_sha256", True)
    if profile is None:
        try:
            profile = load_project_profile(project_root)
        except Exception:
            profile = {}

    rows = [
        r
        for r in _parse_index_rows(project_root / "_INDEX.md")
        if r["decision"] in {"auto", "approved", "corrected"}
    ]
    rows = [r for r in rows if Path(r["path"]).exists() and Path(r["path"]).is_file()]
    rows = [r for r in rows if not _is_ignored_file(Path(r["path"]))]

    if not use_incremental:
        delete_result = client.delete_by_query(
            index=settings.opensearch_index,
            body={"query": _project_scope_query(project_id, project_root)},
            conflicts="proceed",
            refresh=True,
        )
        deleted_docs = int(delete_result.get("deleted", 0))
        indexed_docs = 0
        for row in rows:
            p = Path(row["path"])
            current_sha = sha256_file(p)
            payload = _build_doc_payload(row, p, current_sha)
            index_document(client, payload, refresh=False, profile=profile)
            indexed_docs += 1
            if progress is not None:
                progress["progress_current"] = progress.get("progress_current", 0) + 1
                progress["progress_file"] = p.name
                progress["progress_project"] = project_id
        client.indices.refresh(index=settings.opensearch_index)
        return {"indexed_docs": indexed_docs, "deleted_docs": deleted_docs, "skipped_docs": 0}

    want_doc_ids = {row["doc_id"] for row in rows}
    res = client.search(
        index=settings.opensearch_index,
        body={
            "query": _project_scope_query(project_id, project_root),
            "size": 10000,
            "_source": False,
        },
    )
    index_doc_ids = {hit["_id"] for hit in res.get("hits", {}).get("hits", [])}
    to_remove = index_doc_ids - want_doc_ids
    deleted_docs = 0
    for doc_id in to_remove:
        try:
            client.delete(index=settings.opensearch_index, id=doc_id, refresh=False)
            deleted_docs += 1
        except Exception:
            pass

    indexed_docs = 0
    skipped_docs = 0
    failed_docs = 0
    for row in rows:
        p = Path(row["path"])
        doc_id = row["doc_id"]
        if progress is not None:
            progress["progress_current"] = progress.get("progress_current", 0) + 1
            progress["progress_file"] = p.name
            progress["progress_project"] = project_id
            progress["progress_file_pct"] = 0
        current_sha = sha256_file(p)
        try:
            get_res = client.get(
                index=settings.opensearch_index, id=doc_id, _source=["sha256", "project_id"]
            )
            src = get_res.get("_source") or {}
            existing_sha = src.get("sha256") or ""
            existing_pid = src.get("project_id") or ""
            # Skip only when both content hash AND project_id match
            if existing_sha == current_sha and existing_pid == row["project_id"]:
                skipped_docs += 1
                if progress is not None:
                    progress["progress_skipped"] = progress.get("progress_skipped", 0) + 1
                    progress["progress_file_pct"] = 100
                continue
        except Exception:
            pass
        if progress is not None:
            progress["progress_file_pct"] = 50
        try:
            client.delete(index=settings.opensearch_index, id=doc_id, refresh=False)
        except Exception:
            pass
        try:
            payload = _build_doc_payload(row, p, current_sha)
            for attempt in range(3):
                try:
                    index_document(client, payload, refresh=False, profile=profile)
                    indexed_docs += 1
                    if progress is not None:
                        progress["progress_file_pct"] = 100
                    break
                except TransportError as e:
                    if getattr(e, "status_code", None) == 429 and attempt < 2:
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    raise
        except Exception:
            failed_docs += 1
            if progress is not None:
                progress["progress_file_pct"] = 100
            logger.exception(
                "Falha ao indexar documento no reconcile: doc_id=%s path=%s",
                doc_id,
                p,
            )
    client.indices.refresh(index=settings.opensearch_index)
    return {
        "indexed_docs": indexed_docs,
        "deleted_docs": deleted_docs,
        "skipped_docs": skipped_docs,
        "failed_docs": failed_docs,
    }
