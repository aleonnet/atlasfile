from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Any

from opensearchpy import OpenSearch

from ..bootstrap import ensure_project_structure
from ..project_profile import load_project_profile
from ..projects_root import projects_root_health
from ..reconcile import cleanup_orphan_projects, rebuild_search_index, reconcile_project_index, sync_search_index_for_project
from ..utils import utc_now_iso


def count_rows_to_process(valid_projects: list[tuple[Path, str]]) -> int:
    from ..reconcile import _is_ignored_file, _parse_index_rows

    total = 0
    for project_root, _ in valid_projects:
        for row in _parse_index_rows(project_root / "_INDEX.md"):
            if row["decision"] not in {"auto", "approved", "corrected"}:
                continue
            p = Path(row["path"])
            if not p.exists() or not p.is_file():
                continue
            if _is_ignored_file(p):
                continue
            total += 1
    return total


def run_reconcile(
    *,
    project_roots: list[Path],
    reindex_search: bool,
    reindex_mode: str,
    status: dict[str, Any],
    lock: Lock,
    os_client: OpenSearch,
    cleanup_orphans: bool = True,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    started_ts = time.time()
    with lock:
        status["running"] = True
        status["phase"] = "search_index" if reindex_search else "reconcile_index"
        status["progress_current"] = 0
        status["progress_total"] = 0
        status["progress_file"] = None
        status["progress_project"] = None
        status["progress_skipped"] = 0
        status["progress_file_pct"] = 0
        status["last_failure_message"] = None
        status["last_failed_doc_id"] = None

        project_reports: list[dict[str, Any]] = []
        valid_roots: list[Path] = []
        valid_projects: list[tuple[Path, str]] = []
        skipped: list[dict[str, str]] = []
        for root in project_roots:
            try:
                profile = load_project_profile(root)
            except Exception as exc:
                skipped.append({"project_root": str(root), "reason": str(exc)})
                continue
            ensure_project_structure(root, profile)
            project_reports.append(reconcile_project_index(root, profile))
            valid_roots.append(root)
            valid_projects.append((root, str(profile.get("project_id", root.name))))

        progress_total = count_rows_to_process(valid_projects) if reindex_search else 0
        status["progress_total"] = progress_total

        search_report = {"indexed_docs": 0, "deleted_docs": 0, "skipped_docs": 0}
        if reindex_search:
            if reindex_mode == "incremental":
                indexed_docs = 0
                deleted_docs = 0
                skipped_docs = 0
                failed_docs = 0
                for root, project_id in valid_projects:
                    status["progress_project"] = project_id
                    report = sync_search_index_for_project(os_client, root, project_id, progress=status)
                    indexed_docs += int(report.get("indexed_docs", 0))
                    deleted_docs += int(report.get("deleted_docs", 0))
                    skipped_docs += int(report.get("skipped_docs", 0))
                    failed_docs += int(report.get("failed_docs", 0))
                search_report = {
                    "indexed_docs": indexed_docs,
                    "deleted_docs": deleted_docs,
                    "skipped_docs": skipped_docs,
                    "failed_docs": failed_docs,
                }
            else:
                search_report = rebuild_search_index(
                    os_client,
                    valid_roots,
                    project_ids=valid_projects,
                    progress=status,
                )

        orphan_report = {"orphan_projects_found": 0, "orphan_docs_deleted": 0}
        # Limpeza de órfãos: liberada com a raiz SAUDÁVEL (mesmo vazia — instância
        # recomeçada limpa o índice antigo); pulada com a raiz indisponível (mount
        # quebrado não pode custar o índice inteiro).
        if reindex_search and cleanup_orphans:
            root_health = projects_root_health()
            if root_health["ok"]:
                valid_ids = {pid for _, pid in valid_projects}
                valid_roots = [r for r, _ in valid_projects]
                orphan_report = cleanup_orphan_projects(os_client, valid_ids, valid_roots)
            else:
                orphan_report["skipped_reason"] = root_health.get("error") or "projects_root_unavailable" 

        finished_at = utc_now_iso()
        duration_seconds = round(time.time() - started_ts, 3)
        summary = {
            "project_count": len(project_reports),
            "skipped_count": len(skipped),
            "rows_written": sum(int(r.get("rows_written", 0)) for r in project_reports),
            "added_rows": sum(int(r.get("added_rows", 0)) for r in project_reports),
            "removed_rows": sum(int(r.get("removed_rows", 0)) for r in project_reports),
            "adjustments_applied": sum(int(r.get("adjustments_applied", 0)) for r in project_reports),
            "indexed_docs": int(search_report.get("indexed_docs", 0)),
            "skipped_docs": int(search_report.get("skipped_docs", 0)),
            "failed_docs": int(search_report.get("failed_docs", 0)),
            "orphan_projects_found": orphan_report.get("orphan_projects_found", 0),
            "orphan_docs_deleted": orphan_report.get("orphan_docs_deleted", 0),
        }
        report = {
            "projects": project_reports,
            "skipped_projects": skipped,
            "search": search_report,
            "orphan_cleanup": orphan_report,
            "summary": summary,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration_seconds,
        }
        status.update(
            {
                "last_run_started_at": started_at,
                "last_run_finished_at": finished_at,
                "duration_seconds": duration_seconds,
                "summary": summary,
                "running": False,
                "phase": "idle",
                "progress_current": status.get("progress_current", 0),
                "progress_total": status.get("progress_total", 0),
                "progress_file": None,
                "progress_project": None,
                "progress_skipped": status.get("progress_skipped", 0),
            }
        )
        return report

