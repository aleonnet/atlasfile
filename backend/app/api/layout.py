from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..layout_service import apply_layout_migration, compute_plan_id, plan_layout_migration
from ..profile_schema_v2 import ProjectProfileV2
from ..profile_store import ensure_profile, load_profile, save_profile
from ..project_profile import list_project_roots

router = APIRouter(tags=["layout"])

ConflictStrategy = Literal["rename_with_suffix", "skip", "overwrite"]


class LayoutPlanRequest(BaseModel):
    profile: dict | ProjectProfileV2
    strategy: ConflictStrategy = "rename_with_suffix"
    cleanup_empty_dirs: bool = False


class LayoutApplyRequest(BaseModel):
    profile: dict | ProjectProfileV2
    plan_id: str
    confirm: bool = False
    strategy: ConflictStrategy = "rename_with_suffix"
    cleanup_empty_dirs: bool = False
    if_match_version: int | None = None
    updated_by: str | None = None


def _resolve_project_root(project_ref: str) -> Path:
    candidate = Path(settings.projects_root) / project_ref
    if candidate.exists():
        return candidate
    for proj in list_project_roots(Path(settings.projects_root)):
        try:
            profile = load_profile(proj)
            if profile.project_id == project_ref:
                return proj
        except Exception:
            continue
    raise HTTPException(status_code=404, detail=f"Projeto nao encontrado: {project_ref}")


def _normalize_folder_rows(rows: list[dict] | None, *, key_field: str) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    for row in rows or []:
        key = str(row.get(key_field) or "").strip()
        folder = str(row.get("folder") or "").strip()
        if key:
            normalized.append((key, folder))
    return normalized


def _normalize_new_profile(
    raw: dict | ProjectProfileV2,
    *,
    current: ProjectProfileV2,
    project_root: Path,
    relax_cross_validate: bool = False,
) -> ProjectProfileV2:
    payload = raw.model_dump(mode="json") if isinstance(raw, ProjectProfileV2) else dict(raw)
    payload["project_id"] = current.project_id
    payload["project_label"] = payload.get("project_label") or current.project_label
    payload["project_root"] = str(project_root)
    try:
        return ProjectProfileV2.model_validate(payload)
    except Exception:
        if not relax_cross_validate:
            raise
        # Auto-sync: remove routing rules and domains that no longer exist in
        # layout.business_domain_folders so folder-removal simulations stay valid.
        relaxed = dict(payload)
        business_domain_folder_keys = {
            bf.get("business_domain")
            for bf in (relaxed.get("layout") or {}).get("business_domain_folders", [])
        }
        cls = dict(relaxed.get("classification") or {})
        cls["business_domains"] = [
            bd for bd in cls.get("business_domains", []) if bd.get("key") in business_domain_folder_keys
        ]
        cls["routing_rules"] = [
            rr for rr in cls.get("routing_rules", [])
            if not rr.get("route_to") or rr.get("route_to") in business_domain_folder_keys
        ]
        relaxed["classification"] = cls
        return ProjectProfileV2.model_validate(relaxed)


def _layout_only_target_profile(
    raw: dict | ProjectProfileV2,
    *,
    current: ProjectProfileV2,
    project_root: Path,
) -> ProjectProfileV2:
    payload = raw.model_dump(mode="json") if isinstance(raw, ProjectProfileV2) else dict(raw)
    payload["project_id"] = current.project_id
    payload["project_label"] = payload.get("project_label") or current.project_label
    payload["project_root"] = str(project_root)
    layout_payload = dict(payload.get("layout") or current.layout.model_dump(mode="json"))
    layout = type(current.layout).model_validate(layout_payload)
    return current.model_copy(
        update={
            "project_label": payload["project_label"],
            "project_root": str(project_root),
            "layout": layout,
        },
        deep=True,
    )


@router.post("/api/projects/{project_ref}/layout/plan")
def post_layout_plan(project_ref: str, req: LayoutPlanRequest):
    project_root = _resolve_project_root(project_ref)
    current, _ = ensure_profile(project_root=project_root, project_id=project_root.name, project_label=project_root.name)
    try:
        target = _normalize_new_profile(req.profile, current=current, project_root=project_root, relax_cross_validate=True)
    except Exception:
        # Planning only needs the target layout; keep the current validated
        # classification/naming/indexing blocks when the incoming payload is
        # temporarily inconsistent during folder-removal simulations.
        target = _layout_only_target_profile(req.profile, current=current, project_root=project_root)
    plan = plan_layout_migration(
        old_profile=current,
        new_profile=target,
        strategy=req.strategy,
        cleanup_empty_dirs=req.cleanup_empty_dirs,
    )
    plan_id = compute_plan_id(plan)
    return {
        "plan_id": plan_id,
        "summary": {"moves": plan.moves, "conflicts": plan.conflicts, "mkdirs": plan.mkdirs, "renames": plan.renames, "ops": len(plan.ops)},
        "plan": plan.to_dict(),
    }


@router.post("/api/projects/{project_ref}/layout/apply")
def post_layout_apply(project_ref: str, req: LayoutApplyRequest):
    if not req.confirm:
        raise HTTPException(status_code=400, detail="confirm=true é obrigatório para apply")

    project_root = _resolve_project_root(project_ref)
    current = load_profile(project_root)
    target = _normalize_new_profile(req.profile, current=current, project_root=project_root, relax_cross_validate=True)
    plan = plan_layout_migration(
        old_profile=current,
        new_profile=target,
        strategy=req.strategy,
        cleanup_empty_dirs=req.cleanup_empty_dirs,
    )
    expected_plan_id = compute_plan_id(plan)
    if expected_plan_id != req.plan_id:
        raise HTTPException(status_code=409, detail="plan_id inválido para o estado atual do projeto")

    apply_summary = apply_layout_migration(plan, dry_run=False)
    if apply_summary.get("errors", 0) > 0:
        raise HTTPException(status_code=500, detail={"message": "layout apply concluiu com erros", "summary": apply_summary})

    if_match = req.if_match_version if req.if_match_version is not None else current.version
    saved = save_profile(
        project_root=project_root,
        profile=target,
        if_match_version=if_match,
        updated_by=req.updated_by or "layout:apply",
    )

    return {
        "ok": True,
        "plan_id": expected_plan_id,
        "apply": apply_summary,
        "profile_version": saved.version,
    }
