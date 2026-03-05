from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .models import TriageItem
from .profile_runtime import triage_paths
from .project_profile import load_project_profile
from .utils import utc_now_iso


def triage_base(project_root: Path) -> Path:
    profile = _safe_profile(project_root)
    pending = triage_paths(profile)["pending"]
    parts = Path(pending).parts
    if len(parts) <= 1:
        return project_root / "_TRIAGE_REVIEW"
    return project_root / Path(*parts[:-1])


def _safe_profile(project_root: Path) -> dict[str, Any]:
    try:
        return load_project_profile(project_root)
    except Exception:
        return {}


def triage_pending_dir(project_root: Path) -> Path:
    profile = _safe_profile(project_root)
    return project_root / triage_paths(profile)["pending"]


def triage_resolved_dir(project_root: Path) -> Path:
    profile = _safe_profile(project_root)
    return project_root / triage_paths(profile)["resolved"]


def triage_rejected_dir(project_root: Path) -> Path:
    profile = _safe_profile(project_root)
    return project_root / triage_paths(profile)["rejected"]


def ensure_triage_dirs(project_root: Path) -> None:
    triage_pending_dir(project_root).mkdir(parents=True, exist_ok=True)
    triage_resolved_dir(project_root).mkdir(parents=True, exist_ok=True)
    triage_rejected_dir(project_root).mkdir(parents=True, exist_ok=True)


def save_pending_metadata(project_root: Path, doc_id: str, metadata: dict[str, Any]) -> Path:
    ensure_triage_dirs(project_root)
    meta_path = triage_pending_dir(project_root) / f"{doc_id}.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path


def list_pending(project_root: Path) -> list[TriageItem]:
    ensure_triage_dirs(project_root)
    out: list[TriageItem] = []

    # Self-healing cleanup: if metadata points to a missing file, move metadata out of pending.
    rejected_dir = triage_rejected_dir(project_root)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    for json_file in sorted(triage_pending_dir(project_root).glob("*.json"), key=lambda p: p.name):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        source_path = Path(data.get("source_path", ""))
        if not source_path.exists():
            data["decision"] = "orphaned_missing_source"
            data["reason"] = "pending_metadata_without_file"
            data["processed_at"] = utc_now_iso()
            target_meta = rejected_dir / json_file.name
            if target_meta.exists():
                target_meta = rejected_dir / f"{json_file.stem}__orphan.json"
            shutil.move(str(json_file), str(target_meta))
            target_meta.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            continue
        out.append(TriageItem(**data))
    return out
