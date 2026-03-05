from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

from ..config import settings
from ..profile_schema_v2 import ProfilePutRequest, ProjectProfileV2
from ..profile_store import compute_profile_etag, ensure_profile, list_profile_history, load_profile, save_profile
from ..project_profile import list_project_roots

router = APIRouter(tags=["profile"])


class ProfileValidateRequest(BaseModel):
    profile: dict[str, Any] | ProjectProfileV2


def _resolve_project_root(project_ref: str) -> Path:
    candidate = Path(settings.projects_root) / project_ref
    if candidate.exists():
        return candidate

    for proj in list_project_roots(Path(settings.projects_root)):
        try:
            p = load_profile(proj)
            if p.project_id == project_ref:
                return proj
        except Exception:
            continue
    raise HTTPException(status_code=404, detail=f"Projeto nao encontrado: {project_ref}")


def _normalize_profile_for_project(profile: ProjectProfileV2, *, project_root: Path) -> ProjectProfileV2:
    model = profile.model_copy(deep=True)
    if not model.project_id:
        model.project_id = project_root.name
    model.project_root = str(project_root)
    return model


@router.get("/api/projects/{project_ref}/profile")
def get_profile(project_ref: str, response: Response):
    project_root = _resolve_project_root(project_ref)
    profile, _ = ensure_profile(project_root=project_root, project_id=project_root.name, project_label=project_root.name)
    etag = compute_profile_etag(profile)
    response.headers["ETag"] = etag
    return {"profile": profile.model_dump(mode="json"), "etag": etag, "version": profile.version}


@router.put("/api/projects/{project_ref}/profile")
def put_profile(project_ref: str, payload: ProfilePutRequest):
    project_root = _resolve_project_root(project_ref)
    model = _normalize_profile_for_project(payload.profile, project_root=project_root)
    try:
        saved = save_profile(
            project_root=project_root,
            profile=model,
            if_match_version=payload.if_match_version,
            updated_by=payload.updated_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    etag = compute_profile_etag(saved)
    return {"profile": saved.model_dump(mode="json"), "version": saved.version, "etag": etag}


@router.post("/api/projects/{project_ref}/profile/validate")
def validate_profile(project_ref: str, payload: ProfileValidateRequest):
    project_root = _resolve_project_root(project_ref)
    raw = payload.profile.model_dump(mode="json") if isinstance(payload.profile, ProjectProfileV2) else dict(payload.profile)
    raw["project_root"] = str(project_root)
    if not raw.get("project_id"):
        raw["project_id"] = project_root.name
    try:
        model = ProjectProfileV2.model_validate(raw)
        return {"valid": True, "profile": model.model_dump(mode="json")}
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)]}


@router.get("/api/projects/{project_ref}/profile/history")
def get_profile_history(project_ref: str, if_none_match: str | None = Header(default=None)):
    project_root = _resolve_project_root(project_ref)
    entries = list_profile_history(project_root)
    etag = compute_profile_etag({"entries": entries})
    if if_none_match and if_none_match == etag:
        return Response(status_code=304)
    return {"entries": entries, "etag": etag}

