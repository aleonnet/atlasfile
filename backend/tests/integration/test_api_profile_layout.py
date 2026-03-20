"""Integration tests for profile/layout API endpoints."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def _setup_project(tmp_root: Path, project_name: str = "proj1") -> Path:
    project_root = tmp_root / project_name
    project_root.mkdir(parents=True, exist_ok=True)
    return project_root


def _patch_projects_root(tmp_root: Path):
    return patch("app.api.profile.settings.projects_root", str(tmp_root))


def _patch_layout_projects_root(tmp_root: Path):
    return patch("app.api.layout.settings.projects_root", str(tmp_root))


def _both_patches(tmp_root: Path):
    """Context manager stacking both project-root patches."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(_patch_projects_root(tmp_root))
    stack.enter_context(_patch_layout_projects_root(tmp_root))
    return stack


def test_profile_get_validate_put_history(client: TestClient, tmp_path: Path) -> None:
    project_root = _setup_project(tmp_path, "proj_profile")
    with _patch_projects_root(tmp_path), _patch_layout_projects_root(tmp_path):
        get_resp = client.get(f"/api/projects/{project_root.name}/profile")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        profile = get_data["profile"]
        assert profile["project_id"] == project_root.name
        assert get_data["version"] == 1
        assert get_resp.headers.get("etag")

        validate_resp = client.post(
            f"/api/projects/{project_root.name}/profile/validate",
            json={"profile": profile},
        )
        assert validate_resp.status_code == 200
        assert validate_resp.json()["valid"] is True

        profile["project_label"] = "Projeto Atualizado"
        put_resp = client.put(
            f"/api/projects/{project_root.name}/profile",
            json={"profile": profile, "if_match_version": get_data["version"], "updated_by": "tests"},
        )
        assert put_resp.status_code == 200
        put_data = put_resp.json()
        assert put_data["profile"]["project_label"] == "Projeto Atualizado"
        assert put_data["version"] == 2
        assert put_data["etag"]

        noop_resp = client.put(
            f"/api/projects/{project_root.name}/profile",
            json={"profile": put_data["profile"], "if_match_version": put_data["version"], "updated_by": "tests-noop"},
        )
        assert noop_resp.status_code == 200
        noop_data = noop_resp.json()
        assert noop_data["version"] == 2

        stale_resp = client.put(
            f"/api/projects/{project_root.name}/profile",
            json={"profile": profile, "if_match_version": 1, "updated_by": "tests-stale"},
        )
        assert stale_resp.status_code == 409

        history_resp = client.get(f"/api/projects/{project_root.name}/profile/history")
        assert history_resp.status_code == 200
        history_data = history_resp.json()
        assert "entries" in history_data
        assert len(history_data["entries"]) >= 2


def test_layout_plan_and_apply_moves_files(client: TestClient, tmp_path: Path) -> None:
    project_root = _setup_project(tmp_path, "proj_layout")
    with _patch_projects_root(tmp_path), _patch_layout_projects_root(tmp_path):
        get_resp = client.get(f"/api/projects/{project_root.name}/profile")
        assert get_resp.status_code == 200
        data = get_resp.json()
        profile = data["profile"]
        version = int(data["version"])

        business_domain = profile["classification"]["business_domains"][0]["key"]
        old_folder = next(
            item["folder"]
            for item in profile["layout"]["business_domain_folders"]
            if item["business_domain"] == business_domain
        )
        old_file = project_root / profile["layout"]["areas_root"] / old_folder / "doc.txt"
        old_file.parent.mkdir(parents=True, exist_ok=True)
        old_file.write_text("conteudo", encoding="utf-8")

        target_folder = f"99_{old_folder}"
        for area in profile["layout"]["business_domain_folders"]:
            if area["business_domain"] == business_domain:
                area["folder"] = target_folder
                break

        plan_resp = client.post(
            f"/api/projects/{project_root.name}/layout/plan",
            json={"profile": profile, "strategy": "rename_with_suffix", "cleanup_empty_dirs": True},
        )
        assert plan_resp.status_code == 200
        plan_data = plan_resp.json()
        assert plan_data["summary"]["ops"] > 0
        # Same business_domain with different folder → rename_dir (not moves)
        assert plan_data["summary"]["renames"] >= 1

        no_confirm_resp = client.post(
            f"/api/projects/{project_root.name}/layout/apply",
            json={
                "profile": profile,
                "plan_id": plan_data["plan_id"],
                "confirm": False,
                "strategy": "rename_with_suffix",
                "cleanup_empty_dirs": True,
                "if_match_version": version,
            },
        )
        assert no_confirm_resp.status_code == 400

        apply_resp = client.post(
            f"/api/projects/{project_root.name}/layout/apply",
            json={
                "profile": profile,
                "plan_id": plan_data["plan_id"],
                "confirm": True,
                "strategy": "rename_with_suffix",
                "cleanup_empty_dirs": True,
                "if_match_version": version,
                "updated_by": "tests-layout",
            },
        )
        assert apply_resp.status_code == 200
        apply_data = apply_resp.json()
        assert apply_data["ok"] is True
        assert apply_data["apply"]["errors"] == 0
        assert int(apply_data["profile_version"]) == version + 1

        moved_file = project_root / profile["layout"]["areas_root"] / target_folder / "doc.txt"
        assert moved_file.exists()
        assert not old_file.exists()


def test_plan_rename_folder_uses_rename_dir(client: TestClient, tmp_path: Path) -> None:
    """Renaming a business_domain folder should produce a rename_dir op (not moves)."""
    project_root = _setup_project(tmp_path, "proj_rename")
    with _both_patches(tmp_path):
        profile = client.get(f"/api/projects/{project_root.name}/profile").json()["profile"]

        business_domain = profile["classification"]["business_domains"][0]["key"]
        old_folder = next(
            a["folder"]
            for a in profile["layout"]["business_domain_folders"]
            if a["business_domain"] == business_domain
        )
        area_dir = project_root / profile["layout"]["areas_root"] / old_folder
        area_dir.mkdir(parents=True, exist_ok=True)
        (area_dir / "a.pdf").write_bytes(b"pdf")
        (area_dir / "b.docx").write_bytes(b"docx")
        sub = area_dir / "sub"
        sub.mkdir()
        (sub / "c.txt").write_text("hi")

        new_folder = "renamed_folder"
        for a in profile["layout"]["business_domain_folders"]:
            if a["business_domain"] == business_domain:
                a["folder"] = new_folder

        resp = client.post(
            f"/api/projects/{project_root.name}/layout/plan",
            json={"profile": profile, "strategy": "rename_with_suffix", "cleanup_empty_dirs": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["renames"] == 1
        assert data["summary"]["moves"] == 0
        rename_ops = [op for op in data["plan"]["ops"] if op["op"] == "rename_dir"]
        assert len(rename_ops) == 1
        assert old_folder in rename_ops[0]["src"]
        assert new_folder in rename_ops[0]["dst"]


def test_plan_remove_folder_with_content_shows_conflicts(client: TestClient, tmp_path: Path) -> None:
    """Removing a business_domain folder that has files should show conflicts."""
    project_root = _setup_project(tmp_path, "proj_del_content")
    with _both_patches(tmp_path):
        profile = client.get(f"/api/projects/{project_root.name}/profile").json()["profile"]

        business_domain = profile["classification"]["business_domains"][0]["key"]
        old_folder = next(
            a["folder"]
            for a in profile["layout"]["business_domain_folders"]
            if a["business_domain"] == business_domain
        )
        area_dir = project_root / profile["layout"]["areas_root"] / old_folder
        area_dir.mkdir(parents=True, exist_ok=True)
        (area_dir / "important.pdf").write_bytes(b"data")

        profile["layout"]["business_domain_folders"] = [
            a
            for a in profile["layout"]["business_domain_folders"]
            if a["business_domain"] != business_domain
        ]

        resp = client.post(
            f"/api/projects/{project_root.name}/layout/plan",
            json={"profile": profile, "strategy": "rename_with_suffix", "cleanup_empty_dirs": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["conflicts"] >= 1
        conflict_ops = [op for op in data["plan"]["ops"] if op["op"] == "conflict"]
        assert len(conflict_ops) >= 1
        assert any("no new folder" in op["reason"] for op in conflict_ops)


def test_plan_remove_empty_folder_with_cleanup(client: TestClient, tmp_path: Path) -> None:
    """Removing a business_domain folder that is empty + cleanup_empty_dirs should produce rmdir_empty ops."""
    project_root = _setup_project(tmp_path, "proj_del_empty")
    with _both_patches(tmp_path):
        profile = client.get(f"/api/projects/{project_root.name}/profile").json()["profile"]

        business_domain = profile["classification"]["business_domains"][0]["key"]
        old_folder = next(
            a["folder"]
            for a in profile["layout"]["business_domain_folders"]
            if a["business_domain"] == business_domain
        )
        area_dir = project_root / profile["layout"]["areas_root"] / old_folder
        area_dir.mkdir(parents=True, exist_ok=True)

        profile["layout"]["business_domain_folders"] = [
            a
            for a in profile["layout"]["business_domain_folders"]
            if a["business_domain"] != business_domain
        ]

        resp = client.post(
            f"/api/projects/{project_root.name}/layout/plan",
            json={"profile": profile, "strategy": "rename_with_suffix", "cleanup_empty_dirs": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        rmdir_ops = [op for op in data["plan"]["ops"] if op["op"] == "rmdir_empty"]
        assert len(rmdir_ops) >= 1
        assert any(old_folder in op["src"] for op in rmdir_ops)


def test_validate_returns_errors_for_invalid_profile(client: TestClient, tmp_path: Path) -> None:
    """Validate endpoint should return {valid: false, errors: [...]} instead of crashing."""
    project_root = _setup_project(tmp_path, "proj_validate_err")
    with _patch_projects_root(tmp_path):
        profile = client.get(f"/api/projects/{project_root.name}/profile").json()["profile"]

        profile["layout"]["business_domain_folders"] = []

        resp = client.post(
            f"/api/projects/{project_root.name}/profile/validate",
            json={"profile": profile},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) >= 1

