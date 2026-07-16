from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.reconcile import cleanup_orphan_projects


def _make_agg_response(project_ids: list[str]) -> dict:
    return {
        "aggregations": {
            "project_ids": {
                "buckets": [{"key": pid, "doc_count": 5} for pid in project_ids]
            }
        }
    }


def test_cleanup_no_orphans() -> None:
    client = MagicMock()
    client.search.return_value = _make_agg_response(["proj_a", "proj_b"])

    result = cleanup_orphan_projects(
        client,
        valid_project_ids={"proj_a", "proj_b"},
        valid_project_roots=[Path("/projects/proj_a"), Path("/projects/proj_b")],
    )

    assert result["orphan_projects_found"] == 0
    assert result["orphan_docs_deleted"] == 0
    client.delete_by_query.assert_not_called()


def test_cleanup_removes_orphan_project() -> None:
    client = MagicMock()
    client.search.return_value = _make_agg_response(["proj_a", "proj_b"])
    client.delete_by_query.return_value = {"deleted": 3}

    result = cleanup_orphan_projects(
        client,
        valid_project_ids={"proj_a"},
        valid_project_roots=[Path("/projects/proj_a")],
    )

    assert result["orphan_projects_found"] == 1
    assert result["orphan_docs_deleted"] == 3
    # 2 chamadas por órfão: índice principal + índice de chunk vectors
    assert client.delete_by_query.call_count == 2
    indexes_called = [call.kwargs.get("index") for call in client.delete_by_query.call_args_list]
    assert indexes_called == ["atlasfile_documents", "atlasfile_chunk_vectors"]
    for call in client.delete_by_query.call_args_list:
        assert call.kwargs["body"]["query"]["term"]["project_id"] == "proj_b"


def test_cleanup_multiple_orphans() -> None:
    client = MagicMock()
    client.search.return_value = _make_agg_response(["proj_a", "proj_b", "proj_c"])
    client.delete_by_query.return_value = {"deleted": 2}

    result = cleanup_orphan_projects(
        client,
        valid_project_ids={"proj_a"},
        valid_project_roots=[Path("/projects/proj_a")],
    )

    assert result["orphan_projects_found"] == 2
    assert result["orphan_docs_deleted"] == 4
    # 2 órfãos x (índice principal + índice de chunk vectors)
    assert client.delete_by_query.call_count == 4


def test_cleanup_empty_index() -> None:
    client = MagicMock()
    client.search.return_value = _make_agg_response([])

    result = cleanup_orphan_projects(
        client,
        valid_project_ids={"proj_a"},
        valid_project_roots=[Path("/projects/proj_a")],
    )

    assert result["orphan_projects_found"] == 0
    assert result["orphan_docs_deleted"] == 0
    client.delete_by_query.assert_not_called()


def test_cleanup_accented_project_not_orphaned() -> None:
    """Accented indexed project_id should match its normalized valid counterpart."""
    client = MagicMock()
    client.search.return_value = _make_agg_response(["Kaidô", "proj_b"])

    result = cleanup_orphan_projects(
        client,
        valid_project_ids={"kaido", "proj_b"},
        valid_project_roots=[Path("/projects/kaido"), Path("/projects/proj_b")],
    )

    assert result["orphan_projects_found"] == 0
    assert result["orphan_docs_deleted"] == 0
    client.delete_by_query.assert_not_called()


def test_cleanup_delete_by_query_failure() -> None:
    client = MagicMock()
    client.search.return_value = _make_agg_response(["proj_a", "orphan_1", "orphan_2"])

    call_count = 0

    def _side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"deleted": 5}
        raise Exception("OpenSearch error")

    client.delete_by_query.side_effect = _side_effect

    result = cleanup_orphan_projects(
        client,
        valid_project_ids={"proj_a"},
        valid_project_roots=[Path("/projects/proj_a")],
    )

    assert result["orphan_projects_found"] == 2
    assert result["orphan_docs_deleted"] == 5
