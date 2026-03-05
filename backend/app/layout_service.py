from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .profile_schema_v2 import ProjectProfileV2

MigrationOpType = Literal["mkdir", "move", "skip", "conflict", "rmdir_empty", "rename_dir"]
ConflictStrategy = Literal["rename_with_suffix", "skip", "overwrite"]

SYSTEM_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", ".gitkeep"}


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
    renames: int
    strategy: ConflictStrategy
    cleanup_empty_dirs: bool

    def to_dict(self) -> dict:
        return {
            "project_root": self.project_root,
            "from_areas_root": self.from_areas_root,
            "to_areas_root": self.to_areas_root,
            "ops": [asdict(op) for op in self.ops],
            "conflicts": self.conflicts,
            "moves": self.moves,
            "mkdirs": self.mkdirs,
            "renames": self.renames,
            "strategy": self.strategy,
            "cleanup_empty_dirs": self.cleanup_empty_dirs,
        }


def compute_plan_id(plan: MigrationPlan) -> str:
    payload = json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _safe_join(project_root: Path, rel: str) -> Path:
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


def _is_system_file(p: Path) -> bool:
    return p.name.startswith(".") or p.name in SYSTEM_FILES


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
    return [p for p in root.rglob("*") if p.is_file() and not _is_system_file(p)]


def _iter_dirs_bottom_up(root: Path) -> list[Path]:
    if not root.exists():
        return []
    dirs = [p for p in root.rglob("*") if p.is_dir()]
    dirs.sort(key=lambda p: len(p.parts), reverse=True)
    return dirs


def _resolve_conflict_dst(dst: Path, *, strategy: ConflictStrategy) -> tuple[str, Path, dict | None]:
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
    parts = rel_under_old_areas_root.parts
    if not parts:
        return (None, rel_under_old_areas_root)

    first = parts[0]
    for af in old_profile.layout.area_folders:
        if af.folder.strip("/").rstrip("/") == first:
            tail = Path(*parts[1:]) if len(parts) > 1 else Path()
            return (af.area_key, tail)
    return (None, rel_under_old_areas_root)


def _dir_has_remaining_content(d: Path, moved_sources: set[Path]) -> bool:
    """True if dir has real (non-system) files that aren't being moved."""
    for f in d.rglob("*"):
        if f.is_file() and not _is_system_file(f) and f.resolve() not in moved_sources:
            return True
    return False


def _detect_renames(
    old_profile: ProjectProfileV2,
    new_profile: ProjectProfileV2,
    project_root: Path,
) -> dict[str, tuple[Path, Path]]:
    """Detect area_folders with same area_key but different folder name.
    Returns {area_key: (old_dir, new_dir)} for dirs eligible for rename."""
    old_map = {af.area_key: af.folder for af in old_profile.layout.area_folders}
    renames: dict[str, tuple[Path, Path]] = {}
    for af in new_profile.layout.area_folders:
        old_folder = old_map.get(af.area_key)
        if old_folder and old_folder != af.folder:
            old_dir = _safe_join(project_root, f"{old_profile.layout.areas_root}/{old_folder}")
            new_dir = _safe_join(project_root, f"{new_profile.layout.areas_root}/{af.folder}")
            if old_dir.exists() and not new_dir.exists():
                renames[af.area_key] = (old_dir, new_dir)
    return renames


def plan_layout_migration(
    *,
    old_profile: ProjectProfileV2,
    new_profile: ProjectProfileV2,
    strategy: ConflictStrategy = "rename_with_suffix",
    cleanup_empty_dirs: bool = False,
) -> MigrationPlan:
    if old_profile.project_id != new_profile.project_id:
        raise ValueError("Profiles must be for the same project_id")

    project_root = Path(old_profile.project_root).resolve()
    old_areas_root = _safe_join(project_root, old_profile.layout.areas_root)
    new_areas_root = _safe_join(project_root, new_profile.layout.areas_root)
    reserved = _reserved_roots(old_profile) + _reserved_roots(new_profile)

    ops: list[MigrationOp] = []
    mkdirs = 0
    renames = 0

    if not new_areas_root.exists():
        ops.append(MigrationOp(op="mkdir", dst=str(new_areas_root), reason="create new areas_root"))
        mkdirs += 1

    # Detect folder renames (same area_key, different folder name, old exists, new doesn't)
    dir_renames = _detect_renames(old_profile, new_profile, project_root)
    renamed_old_dirs: set[Path] = set()

    for area_key, (old_dir, new_dir) in dir_renames.items():
        ops.append(MigrationOp(
            op="rename_dir", src=str(old_dir), dst=str(new_dir),
            reason=f"rename area folder {area_key}",
        ))
        renamed_old_dirs.add(old_dir.resolve())
        renames += 1

    # mkdir only for truly new folders (not covered by rename)
    for af in new_profile.layout.area_folders:
        if af.area_key in dir_renames:
            continue
        dst_dir = _safe_join(project_root, f"{new_profile.layout.areas_root}/{af.folder}")
        if not dst_dir.exists():
            ops.append(MigrationOp(op="mkdir", dst=str(dst_dir), reason=f"create area folder {af.area_key}"))
            mkdirs += 1

    conflicts = 0
    moves = 0
    moved_sources: set[Path] = set()

    for src in _iter_files(old_areas_root):
        # Files under renamed dirs are handled by the rename_dir op
        if any(_is_under(src, rd) for rd in renamed_old_dirs):
            continue

        if any(_is_under(src, r) for r in reserved):
            ops.append(MigrationOp(op="skip", src=str(src), reason="reserved root; not moving"))
            continue

        rel_under_old = src.relative_to(old_areas_root)
        area_key, tail = _old_area_prefix(old_profile, rel_under_old)
        if area_key:
            new_folder = new_profile.layout.folder_for_area(area_key)
            if not new_folder:
                ops.append(MigrationOp(op="conflict", src=str(src), reason=f"no new folder for area_key={area_key}"))
                conflicts += 1
                continue
            dst = _safe_join(project_root, f"{new_profile.layout.areas_root}/{new_folder}/{tail.as_posix()}")
        else:
            dst = new_areas_root / rel_under_old

        if src.resolve() == dst.resolve():
            continue

        if any(_is_under(dst, r) for r in reserved):
            ops.append(MigrationOp(op="conflict", src=str(src), dst=str(dst), reason="destination overlaps reserved root"))
            conflicts += 1
            continue

        if dst.exists():
            op_type, final_dst, detail = _resolve_conflict_dst(dst, strategy=strategy)
            if op_type == "skip":
                ops.append(MigrationOp(op="skip", src=str(src), dst=str(dst), reason="destination exists; skip"))
                continue
            ops.append(
                MigrationOp(
                    op="move",
                    src=str(src),
                    dst=str(final_dst),
                    reason="destination exists; handled by strategy",
                    detail=detail,
                )
            )
            moved_sources.add(src.resolve())
            moves += 1
            conflicts += 1
            continue

        ops.append(MigrationOp(op="move", src=str(src), dst=str(dst), reason="migrate to new layout"))
        moved_sources.add(src.resolve())
        moves += 1

    if cleanup_empty_dirs:
        new_layout_dirs: set[Path] = {new_areas_root.resolve()}
        for af in new_profile.layout.area_folders:
            d = _safe_join(project_root, f"{new_profile.layout.areas_root}/{af.folder}")
            new_layout_dirs.add(d.resolve())
        # Dirs handled by rename are also protected
        for _, new_dir in dir_renames.values():
            new_layout_dirs.add(new_dir.resolve())

        for d in _iter_dirs_bottom_up(old_areas_root):
            if any(_is_under(d, r) for r in reserved):
                continue
            if d.resolve() in new_layout_dirs:
                continue
            if d.resolve() in renamed_old_dirs:
                continue
            if not _dir_has_remaining_content(d, moved_sources):
                ops.append(MigrationOp(op="rmdir_empty", src=str(d), reason="cleanup empty dir"))

    return MigrationPlan(
        project_root=str(project_root),
        from_areas_root=str(old_areas_root),
        to_areas_root=str(new_areas_root),
        ops=ops,
        conflicts=conflicts,
        moves=moves,
        mkdirs=mkdirs,
        renames=renames,
        strategy=strategy,
        cleanup_empty_dirs=cleanup_empty_dirs,
    )


def apply_layout_migration(plan: MigrationPlan, *, dry_run: bool = True) -> dict:
    summary = {
        "dry_run": dry_run, "mkdir": 0, "move": 0, "skip": 0,
        "conflict": 0, "rmdir_empty": 0, "rename_dir": 0,
        "errors": 0, "error_items": [],
    }

    for op in plan.ops:
        summary[op.op] = summary.get(op.op, 0) + 1
        if dry_run:
            continue

        try:
            if op.op == "mkdir":
                assert op.dst
                Path(op.dst).mkdir(parents=True, exist_ok=True)
            elif op.op == "rename_dir":
                assert op.src and op.dst
                src_dir = Path(op.src)
                dst_dir = Path(op.dst)
                dst_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_dir), str(dst_dir))
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
                    for sf in d.iterdir():
                        if sf.is_file() and _is_system_file(sf):
                            sf.unlink()
                    try:
                        next(d.iterdir())
                    except StopIteration:
                        d.rmdir()
        except Exception as exc:
            summary["errors"] += 1
            summary["error_items"].append(
                {
                    "op": op.op,
                    "src": op.src,
                    "dst": op.dst,
                    "reason": op.reason,
                    "error": str(exc),
                }
            )

    return summary
