"""Persist training/pipeline LLM usage to OpenSearch.

Follows the same pattern as _persist_classification_usage in ingestion.py.
Used by backend/scripts/ to record costs from label_corpus_llm, run_augmentation, etc.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from app.config import settings
from app.usage_costs import estimate_usage_cost

logger = logging.getLogger(__name__)


def generate_run_id() -> str:
    """Generate a unique run ID for a training/pipeline execution."""
    return str(uuid4())


def persist_training_usage(
    *,
    script_name: str,
    run_id: str,
    provider: str,
    model: str,
    usage: dict[str, Any],
    records_processed: int = 0,
    error_count: int = 0,
) -> None:
    """Persist a training/pipeline LLM usage record to OpenSearch.

    Never raises — wraps all errors to avoid crashing the calling script.
    """
    try:
        from app.opensearch_client import get_client

        client = get_client()
        idx = settings.opensearch_training_usage_index

        cost = estimate_usage_cost(usage, provider, model)

        doc = {
            "script_name": script_name,
            "run_id": run_id,
            "provider": provider,
            "model": model,
            "timestamp": int(time.time() * 1000),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_input_tokens": int(usage.get("cache_read_input_tokens") or 0),
            "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens") or 0),
            "estimated_cost_usd": cost,
            "records_processed": records_processed,
            "error_count": error_count,
        }
        client.index(index=idx, body=doc)
    except Exception:
        logger.exception("Failed to persist training usage for %s", script_name)
