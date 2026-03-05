from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .profile_v2 import ProjectProfileV2


# -----------------------------
# Migration plan model
# -----------------------------

MigrationOpType = Literal["mkdir", "move", "skip", "conflict", "rmdir_empty"]


@dataclass
class MigrationOp:
    op: MigrationOpType
    src: str | None = None
    dst: str | None = None
    reason: str = ""
    detail: dict | None = None


@dataclass
class MigrationPlan:
    project_root: str
    from_areas_root: str
    to_areas_root: str
    ops: list[MigrationOp]
    conflicts: int
    moves: int
    mkdirs: int


# -----------------------------
# Helpers
# -----------------------------

def _safe_join(project_root: Path, rel: str) -> Path:
    """Join and ensure the result stays within project_root."""
    rel = (rel or "").lstrip("/").strip()
    p = (project_root / rel).resolve()
    root = project_root.resolve()
    if root not in p.parents and p != root:
        raise ValueError(f"Path escapes project_root: {rel}")
    return p


def _is_under(p: Path, parent: Path) -> bool:
    try:
        p.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _reserved_roots(profile: ProjectProfileV2) -> list[Path]:
    pr = Path(profile.project_root).resolve()
    return [
        _safe_join(pr, profile.paths.inbox),
        _safe_join(pr, profile.paths.triage.pending),
        _safe_join(pr, profile.paths.triage.resolved),
        _safe_join(pr, profile.paths.triage.rejected),
    ]


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file():
            out.append(p)
    return out


def _iter_dirs_bottom_up(root: Path) -> list[Path]:
    if not root.exists():
        return []
    dirs = [p for p in root.rglob("*") if p.is_dir()]
    dirs.sort(key=lambda p: len(p.parts), reverse=True)
    return dirs


def _resolve_conflict_dst(dst: Path, *, strategy: Literal["rename_with_suffix", "skip", "overwrite"]) -> tuple[str, Path, dict | None]:
    """Return (op_type, final_dst, detail) for an existing destination."""
    if strategy == "skip":
        return ("skip", dst, None)
    if strategy == "overwrite":
        return ("move", dst, {"overwrite": True})

    base = dst.with_suffix("")
    ext = dst.suffix
    n = 1
    candidate = Path(str(base) + f"__migrated{n}" + ext)
    while candidate.exists():
        n += 1
        candidate = Path(str(base) + f"__migrated{n}" + ext)
    return ("move", candidate, {"renamed": True})


def _old_area_prefix(old_profile: ProjectProfileV2, rel_under_old_areas_root: Path) -> tuple[str | None, Path]:
    """
    Given a file path relative to old areas_root, identify which area folder it belongs to.

    Returns (area_key, tail_path_under_area_folder).
    If no area folder matches, returns (None, rel_under_old_areas_root).
    """
    # Match the first path segment against old_profile.layout.area_folders[*].folder
    parts = rel_under_old_areas_root.parts
    if not parts:
        return (None, rel_under_old_areas_root)

    first = parts[0]
    for af in old_profile.layout.area_folders:
        if af.folder.strip("/").rstrip("/") == first:
            tail = Path(*parts[1:]) if len(parts) > 1 else Path()
            return (af.area_key, tail)
    return (None, rel_under_old_areas_root)


# -----------------------------
# Plan
# -----------------------------

def plan_layout_migration(
    *,
    old_profile: ProjectProfileV2,
    new_profile: ProjectProfileV2,
    strategy: Literal["rename_with_suffix", "skip", "overwrite"] = "rename_with_suffix",
    cleanup_empty_dirs: bool = False,
) -> MigrationPlan:
    """
    Plan how to migrate documents considering BOTH:
    1) areas_root change: old layout.areas_root -> new layout.areas_root
    2) area folder remap: old layout.area_folders[*].folder -> new layout.area_folders[*].folder per area_key

    Scope:
    - Only moves files currently under old layout.areas_root.
    - Does NOT touch inbox/triage roots.
    - For each file, identifies its old area folder (first segment under old areas_root).
      If matched to an area_key, remaps to new area's folder (same area_key) under new areas_root.
      If not matched, keeps the relative structure under new areas_root (best-effort).

    Conflict handling:
    - rename_with_suffix: dst becomes "<name>__migratedN.<ext>"
    - skip: create "skip" op
    - overwrite: create "move" op with overwrite=True detail (apply honors)

    cleanup_empty_dirs:
    - If True, appends rmdir_empty ops for directories under old areas_root that become empty.
      This is conservative: only attempts to remove dirs if empty at apply time.
    """
    if old_profile.project_id != new_profile.project_id:
        raise ValueError("Profiles must be for the same project_id")

    project_root = Path(old_profile.project_root).resolve()
    old_areas_root = _safe_join(project_root, old_profile.layout.areas_root)
    new_areas_root = _safe_join(project_root, new_profile.layout.areas_root)

    reserved = _reserved_roots(old_profile) + _reserved_roots(new_profile)

    ops: list[MigrationOp] = []
    mkdirs = 0

    # Ensure destination root exists (mkdir op)
    if not new_areas_root.exists():
        ops.append(MigrationOp(op="mkdir", dst=str(new_areas_root), reason="create new areas_root"))
        mkdirs += 1

    # Ensure each target area folder exists in new layout (mkdir ops)
    for af in new_profile.layout.area_folders:
        dst_dir = _safe_join(project_root, f"{new_profile.layout.areas_root}/{af.folder}")
        if not dst_dir.exists():
            ops.append(MigrationOp(op="mkdir", dst=str(dst_dir), reason=f"create area folder {af.area_key}"))
            mkdirs += 1

    conflicts = 0
    moves = 0

    for src in _iter_files(old_areas_root):
        if any(_is_under(src, r) for r in reserved):
            ops.append(MigrationOp(op="skip", src=str(src), reason="reserved root; not moving"))
            continue

        rel_under_old = src.relative_to(old_areas_root)

        # Try to identify the old area folder (first segment) and map to area_key
        area_key, tail = _old_area_prefix(old_profile, rel_under_old)

        if area_key:
            new_folder = new_profile.layout.folder_for_area(area_key)
            if not new_folder:
                ops.append(MigrationOp(op="conflict", src=str(src), reason=f"no new folder for area_key={area_key}"))
                conflicts += 1
                continue
            dst = _safe_join(project_root, f"{new_profile.layout.areas_root}/{new_folder}/{tail.as_posix()}")
        else:
            # Unknown/unmapped folder: keep relative structure (best-effort)
            dst = new_areas_root / rel_under_old

        if any(_is_under(dst, r) for r in reserved):
            ops.append(MigrationOp(op="conflict", src=str(src), dst=str(dst), reason="destination overlaps reserved root"))
            conflicts += 1
            continue

        if dst.exists():
            op_type, final_dst, detail = _resolve_conflict_dst(dst, strategy=strategy)
            if op_type == "skip":
                ops.append(MigrationOp(op="skip", src=str(src), dst=str(dst), reason="destination exists; skip"))
                continue
            ops.append(MigrationOp(op="move", src=str(src), dst=str(final_dst), reason="destination exists; handled by strategy", detail=detail))
            moves += 1
            conflicts += 1
            continue

        ops.append(MigrationOp(op="move", src=str(src), dst=str(dst), reason="migrate (areas_root and/or area_folders remap)"))
        moves += 1

    # Optional cleanup of now-empty dirs under old areas_root (safe attempt at apply time)
    if cleanup_empty_dirs:
        for d in _iter_dirs_bottom_up(old_areas_root):
            # Never attempt to remove reserved roots
            if any(_is_under(d, r) for r in reserved):
                continue
            ops.append(MigrationOp(op="rmdir_empty", src=str(d), reason="cleanup empty dir (best-effort)"))

    return MigrationPlan(
        project_root=str(project_root),
        from_areas_root=str(old_areas_root),
        to_areas_root=str(new_areas_root),
        ops=ops,
        conflicts=conflicts,
        moves=moves,
        mkdirs=mkdirs,
    )


# -----------------------------
# Apply
# -----------------------------

def apply_layout_migration(
    plan: MigrationPlan,
    *,
    dry_run: bool = True,
) -> dict:
    """
    Apply a MigrationPlan.

    IMPORTANT:
    - This function moves files and creates directories.
    - It does NOT rewrite your _INDEX.md or reindex. After apply, run your existing reconcile/sync.
    - rmdir_empty is best-effort and only removes directories if empty at apply time.

    Returns a summary dict.
    """
    summary = {"dry_run": dry_run, "mkdir": 0, "move": 0, "skip": 0, "conflict": 0, "rmdir_empty": 0, "errors": 0, "error_items": []}

    for op in plan.ops:
        summary[op.op] = summary.get(op.op, 0) + 1

        if dry_run:
            continue

        try:
            if op.op == "mkdir":
                assert op.dst
                Path(op.dst).mkdir(parents=True, exist_ok=True)

            elif op.op == "move":
                assert op.src and op.dst
                src = Path(op.src)
                dst = Path(op.dst)
                dst.parent.mkdir(parents=True, exist_ok=True)

                overwrite = bool((op.detail or {}).get("overwrite", False))
                if overwrite and dst.exists():
                    dst.unlink()

                shutil.move(str(src), str(dst))

            elif op.op == "rmdir_empty":
                assert op.src
                d = Path(op.src)
                if d.exists() and d.is_dir():
                    # only remove if empty
                    try:
                        next(d.iterdir())
                        # not empty
                    except StopIteration:
                        d.rmdir()

            # skip/conflict: no action
        except Exception as e:
            summary["errors"] += 1
            summary["error_items"].append(
                {
                    "op": op.op,
                    "src": op.src,
                    "dst": op.dst,
                    "reason": op.reason,
                    "error": str(e),
                }
            )

    return summary
