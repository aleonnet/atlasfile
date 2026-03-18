from __future__ import annotations

from unittest.mock import Mock

from app.config import settings
from app.opensearch_client import ensure_index


def test_ensure_index_updates_dynamic_settings_for_existing_index() -> None:
    client = Mock()
    client.indices.exists.return_value = True

    ensure_index(client)

    client.indices.put_settings.assert_called_once_with(
        index=settings.opensearch_index,
        body={
            "index": {
                "number_of_replicas": 0,
                "highlight.max_analyzed_offset": 10_000_000,
                "mapping.nested_objects.limit": settings.opensearch_nested_objects_limit,
            }
        },
    )
    client.indices.put_mapping.assert_called_once()
    client.indices.create.assert_not_called()


def test_ensure_index_sets_nested_object_limit_on_create() -> None:
    client = Mock()
    client.indices.exists.return_value = False

    ensure_index(client)

    client.indices.create.assert_called_once()
    _, kwargs = client.indices.create.call_args
    assert kwargs["index"] == settings.opensearch_index
    assert kwargs["body"]["settings"]["index"]["mapping.nested_objects.limit"] == settings.opensearch_nested_objects_limit
