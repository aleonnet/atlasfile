from __future__ import annotations

import asyncio
import html as html_module
import httpx
import json
import mimetypes
import unicodedata
import urllib.parse
import re
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File as FastAPIFile, Header, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .api.layout import router as layout_router
from .api.profile import router as profile_router
from .area_resolver import resolve_classification_path
from .bootstrap import ensure_project_structure
from .classifier_cycle import run_classifier_cycle
from .classifier_registry import (
    SUPPORTED_CLASSIFIER_MODES,
    classifier_report_path,
    list_classifier_reports,
    load_classifier_registry,
    load_classifier_report,
    save_classifier_registry,
)
from .classifier_runtime import resolve_classifier_mode
from .config import settings
from functools import partial

from .dataset_holdout import (
    backfill_validation_from_training_pool,
    dataset_readiness,
    route_labeled_document,
)
from .indexer import backfill_search_fields, index_document, read_text_excerpt
from .ingest_history import append_ingest_entry, load_ingest_history, update_history_item
from .ingestion import _append_index_md, process_inbox_file
from .models import (
    ChatRequest,
    ChatResponse,
    ChatSession,
    ChatSessionCreate,
    ChatSessionUpdate,
    ClassificationUsageByModel,
    ClassificationUsageSummary,
    ClassifyRequest,
    ClassifyResponse,
    ContextPressure,
    DocumentMetadataUpdate,
    DocumentMoveRequest,
    DocumentTagsUpdate,
    ListDocumentItem,
    ListDocumentsResponse,
    ModelOption,
    SearchHit,
    SearchResponse,
    SearchSuggestion,
    StatsBucket,
    StatsResponse,
    StoredChatMessage,
    SuggestResponse,
    TriageDecisionRequest,
    TurnUsage,
    UsageByDayEntry,
    UsageByModelEntry,
    UsageSessionItem,
    UsageSummaryResponse,
    UsageTotals,
    TrainingUsageByModel,
    TrainingUsageByScript,
    TrainingUsageSummary,
)
from opensearchpy.exceptions import NotFoundError as OSNotFoundError
from .auth import AuthContext, enforce_project_scope, require_auth
from .opensearch_client import ensure_chat_sessions_index, ensure_classification_usage_index, ensure_index, ensure_training_usage_index, get_client
from .search_hybrid import (
    build_chunk_filters,
    rerank_pairs,
    rrf_fuse,
    semantic_search,
    semantic_search_chunks,
)
from .project_profile import list_project_roots, load_project_profile
from .profile_runtime import inbox_rel
from .profile_schema_v2 import OperationalClassifierMode
from .profile_store import ensure_profile, load_profile, save_profile
from .template_store import (
    create_profile_from_template,
    delete_template as _delete_template,
    get_template as _get_template,
    list_templates as _list_templates,
    save_template as _save_template,
)
from .services.reconcile_service import count_rows_to_process, run_reconcile
from .triage import (
    ensure_triage_dirs,
    list_pending,
    triage_pending_dir,
    triage_rejected_dir,
    triage_resolved_dir,
)
from .llm_catalog import LLM_MODEL_CATALOG, catalog_refreshed_at, load_catalog
from .llm_catalog_refresh import (
    LITELLM_CATALOG_URL,
    get_catalog_source_url,
    refresh_catalog,
    set_catalog_source_url,
)
from .taxonomy_migration import (
    TaxonomyMigrationError,
    apply_taxonomy_migration,
    plan_taxonomy_migration,
    remove_taxonomy_entry,
)
from .spreadsheet_query import (
    SpreadsheetQueryError,
    get_schema as get_spreadsheet_schema,
    run_query as run_spreadsheet_query,
)
from .orchestrator import classify_with_llm, get_llm_config, run_chat_loop
from .usage_costs import get_cost_per_1m
from .utils import DEFAULT_CANONICAL_PATTERN, build_canonical_filename, fold_ocr_spacing, normalize_text, utc_now_iso
from .channels import ChannelManager, ChannelMessage
from .channels.telegram import TelegramChannel

import logging as _logging

_logger = _logging.getLogger(__name__)

os_client = get_client()
_reconcile_lock = threading.Lock()
_reconcile_stop = threading.Event()

channel_manager: ChannelManager | None = None

# Per-chat_id lock to serialize message processing (prevents race conditions)
_channel_locks: dict[str, asyncio.Lock] = {}
# Chat IDs that requested a forced new session via /novo
_forced_new_sessions: set[str] = set()
# Project scope explicitly selected for a channel chat (e.g. Telegram /projeto).
_channel_project_scopes: dict[str, str] = {}

# SSE event bus: notifies web clients when a session is modified externally
_session_events: dict[str, asyncio.Event] = {}


def _notify_session_update(session_id: str) -> None:
    """Signal that a session was modified (triggers SSE push to connected clients)."""
    ev = _session_events.get(session_id)
    if ev:
        ev.set()


def _get_session_event(session_id: str) -> asyncio.Event:
    """Get or create the asyncio.Event for a given session."""
    if session_id not in _session_events:
        _session_events[session_id] = asyncio.Event()
    return _session_events[session_id]


def _get_channel_lock(key: str) -> asyncio.Lock:
    if key not in _channel_locks:
        _channel_locks[key] = asyncio.Lock()
    return _channel_locks[key]


def _channel_scope_key(channel_id: str, chat_id: str) -> str:
    return f"{channel_id}:{chat_id}"


def _get_channel_project_scope(channel_id: str, chat_id: str) -> str | None:
    return _channel_project_scopes.get(_channel_scope_key(channel_id, chat_id))


def _set_channel_project_scope(channel_id: str, chat_id: str, project_id: str) -> None:
    scope = str(project_id or "").strip()
    key = _channel_scope_key(channel_id, chat_id)
    if scope:
        _channel_project_scopes[key] = scope
    else:
        _channel_project_scopes.pop(key, None)


def _clear_channel_project_scope(channel_id: str, chat_id: str) -> None:
    _channel_project_scopes.pop(_channel_scope_key(channel_id, chat_id), None)


def _find_active_channel_session(channel_id: str, chat_id: str) -> dict[str, Any] | None:
    """Find the most recent session for a channel+chat_id pair."""
    _idx = settings.opensearch_chat_sessions_index
    body: dict[str, Any] = {
        "query": {"bool": {"must": [
            {"term": {"channel": channel_id}},
            {"term": {"channel_chat_id": chat_id}},
        ]}},
        "sort": [{"updatedAt": {"order": "desc"}}],
        "size": 1,
    }
    try:
        resp = os_client.search(index=_idx, body=body)
        hits = resp.get("hits", {}).get("hits", [])
        if hits:
            doc = hits[0]["_source"]
            doc["id"] = hits[0]["_id"]
            return doc
    except Exception:
        _logger.exception("Error finding channel session")
    return None


def _session_timed_out(session: dict[str, Any], timeout_minutes: int) -> bool:
    updated = _parse_ts(session.get("updatedAt"))
    if not updated:
        return True
    age_ms = int(time.time() * 1000) - updated
    return age_ms > timeout_minutes * 60 * 1000


def _build_history_from_session(session: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract message history from a stored session."""
    msgs = session.get("messages") or []
    return [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in msgs if m.get("content")]


def _merge_usage(existing: dict[str, Any] | None, new_usage: dict[str, Any], provider_model_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge new turn usage into existing usage_totals and usage_by_model."""
    totals = dict(existing) if existing else {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0, "api_call_count": 0}
    for k in ("input_tokens", "output_tokens", "total_tokens", "api_call_count"):
        totals[k] = int(totals.get(k) or 0) + int(new_usage.get(k) or 0)
    totals["estimated_cost_usd"] = float(totals.get("estimated_cost_usd") or 0) + float(new_usage.get("estimated_cost_usd") or 0)
    for k in ("cache_read_input_tokens", "cache_creation_input_tokens", "cache_write_input_tokens"):
        if new_usage.get(k):
            totals[k] = int(totals.get(k) or 0) + int(new_usage[k])
    return totals


async def _handle_channel_message(msg: ChannelMessage) -> str:
    """Dispatch inbound channel message: manages session lifecycle (multi-turn, usage, history)."""
    lock_key = f"{msg.channel_id}:{msg.chat_id}"
    lock = _get_channel_lock(lock_key)

    async with lock:
        provider, model = get_llm_config("chat")
        provider_model_key = f"{provider}/{model}"
        now_ms = int(time.time() * 1000)
        timeout = settings.channel_session_timeout_minutes

        forced = msg.chat_id in _forced_new_sessions
        if forced:
            _forced_new_sessions.discard(msg.chat_id)

        session = None if forced else _find_active_channel_session(msg.channel_id, msg.chat_id)
        if session and _session_timed_out(session, timeout):
            session = None

        active_project_id = _get_channel_project_scope(msg.channel_id, msg.chat_id)
        session_project_id = str((session or {}).get("project_id") or "").strip()
        if not active_project_id and session_project_id:
            active_project_id = session_project_id
            _set_channel_project_scope(msg.channel_id, msg.chat_id, active_project_id)

        history = _build_history_from_session(session) if session else []
        history.append({"role": "user", "content": msg.text})

        result = await run_chat_loop(history, provider, model, project_id=active_project_id)
        content = result.get("content", "") if isinstance(result, dict) else str(result)
        usage = result.get("usage", {}) if isinstance(result, dict) else {}

        user_stored = {"role": "user", "content": msg.text, "timestamp": now_ms, "channel": msg.channel_id}
        assistant_stored = {"role": "assistant", "content": content, "timestamp": now_ms, "model": provider_model_key, "channel": msg.channel_id}

        _idx = settings.opensearch_chat_sessions_index
        if session:
            existing_msgs = session.get("messages") or []
            existing_msgs.extend([user_stored, assistant_stored])
            existing_totals = session.get("usage_totals")
            new_totals = _merge_usage(existing_totals, usage, provider_model_key)
            existing_by_model = session.get("usage_by_model") or {}
            model_totals = _merge_usage(existing_by_model.get(provider_model_key), usage, provider_model_key)
            existing_by_model[provider_model_key] = model_totals
            os_client.update(index=_idx, id=session["id"], body={"doc": {
                "messages": existing_msgs,
                "usage_totals": new_totals,
                "usage_by_model": existing_by_model,
                "updatedAt": now_ms,
                **({"project_id": active_project_id} if active_project_id else {}),
            }})
            _notify_session_update(session["id"])
        else:
            title = msg.text[:80] if msg.text else "Telegram"
            by_model = {provider_model_key: usage}
            doc = {
                "title": title,
                "messages": [user_stored, assistant_stored],
                "model": provider_model_key,
                "createdAt": now_ms,
                "updatedAt": now_ms,
                "channel": msg.channel_id,
                "channel_chat_id": msg.chat_id,
                "usage_totals": usage,
                "usage_by_model": by_model,
                **({"project_id": active_project_id} if active_project_id else {}),
            }
            session_id = str(uuid.uuid4())
            os_client.index(index=_idx, id=session_id, body=doc)
            _notify_session_update(session_id)

        return content


def _build_channel_config() -> dict[str, Any]:
    return {
        "telegram": {
            "enabled": settings.telegram_enabled,
            "bot_token": settings.telegram_bot_token,
        },
    }
_reconcile_status: dict[str, Any] = {
    "last_run_started_at": None,
    "last_run_finished_at": None,
    "duration_seconds": None,
    "summary": {
        "project_count": 0,
        "skipped_count": 0,
        "rows_written": 0,
        "added_rows": 0,
        "removed_rows": 0,
        "adjustments_applied": 0,
        "indexed_docs": 0,
        "skipped_docs": 0,
        "failed_docs": 0,
    },
    "running": False,
    "phase": "idle",
    "progress_current": 0,
    "progress_total": 0,
    "progress_file": None,
    "progress_project": None,
    "progress_skipped": 0,
    "progress_file_pct": 0,
}

_ingest_status: dict[str, Any] = {
    "last_run_started_at": None,
    "last_run_finished_at": None,
    "duration_seconds": None,
    "project_id": None,
    "running": False,
    "phase": "idle",
    "progress_current": 0,
    "progress_total": 0,
    "progress_file": None,
    "processed_count": 0,
    "failed_count": 0,
    "last_error": None,
}

_classifier_cycle_status: dict[str, Any] = {
    "last_run_started_at": None,
    "last_run_finished_at": None,
    "duration_seconds": None,
    "running": False,
    "phase": "idle",
    "progress_current": 0,
    "progress_total": 0,
    "report_id": None,
    "champion_mode": None,
    "last_error": None,
}

_ingest_status: dict[str, Any] = {
    "last_run_started_at": None,
    "last_run_finished_at": None,
    "duration_seconds": None,
    "project_id": None,
    "running": False,
    "phase": "idle",
    "progress_current": 0,
    "progress_total": 0,
    "progress_file": None,
    "processed_count": 0,
    "failed_count": 0,
    "last_error": None,
}

_classifier_cycle_status: dict[str, Any] = {
    "last_run_started_at": None,
    "last_run_finished_at": None,
    "duration_seconds": None,
    "running": False,
    "phase": "idle",
    "progress_current": 0,
    "progress_total": 0,
    "report_id": None,
    "champion_mode": None,
    "last_error": None,
}
_cycle_cancel_event = threading.Event()


def _backfill_channel_web(client) -> None:
    """One-time migration: set channel='web' on chat sessions that lack the field."""
    idx = settings.opensearch_chat_sessions_index
    try:
        client.update_by_query(
            index=idx,
            body={
                "query": {"bool": {"must_not": {"exists": {"field": "channel"}}}},
                "script": {"source": "ctx._source.channel = 'web'", "lang": "painless"},
            },
            refresh=True,
        )
    except Exception:
        _logger.debug("backfill_channel_web: skipped (index may not exist yet)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure OpenSearch index, optional auto-reconcile, and channels. Shutdown: stop channels and reconcile."""
    global channel_manager
    max_attempts = 30
    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            ensure_index(os_client)
            ensure_chat_sessions_index(os_client)
            ensure_classification_usage_index(os_client)
            ensure_training_usage_index(os_client)
            _backfill_channel_web(os_client)
            backfill_search_fields(os_client)
            _start_auto_reconcile_if_enabled()
            break
        except Exception as exc:  # pragma: no cover - startup resiliency
            last_error = exc
            time.sleep(2)
    else:
        if last_error:
            raise last_error

    if settings.channels_enabled:
        channel_manager = ChannelManager(on_message=_handle_channel_message)
        channel_manager.register(TelegramChannel(on_message=channel_manager.dispatch))
        try:
            await channel_manager.start_all(_build_channel_config())
            _logger.info("Channels started")
        except Exception:
            _logger.exception("Channel startup failed (non-fatal)")

    yield

    if channel_manager:
        await channel_manager.stop_all()
    _reconcile_stop.set()


def _cors_origins() -> list[str]:
    raw = (settings.allowed_origins or "").strip()
    if not raw:
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    return [o.strip() for o in raw.split(",") if o.strip()]


# Autenticação global: com api_auth_enabled=false (default) tudo passa com escopo
# irrestrito; /health e preflight CORS nunca exigem key (tratado dentro de require_auth).
app = FastAPI(title=settings.app_name, lifespan=lifespan, dependencies=[Depends(require_auth)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from .api.channels import router as channels_router

app.include_router(profile_router)
app.include_router(layout_router)
app.include_router(channels_router)

def _normalize_query_text(value: str) -> str:
    return fold_ocr_spacing(value)


def _strip_html_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "")


SNIPPET_TOTAL_MAX = settings.snippet_total_max


def _trim_highlight(snippet: str) -> str:
    """Trim snippet to SNIPPET_TOTAL_MAX plain-text chars, preserving ALL <em> tags within the window."""
    if not snippet:
        return snippet
    plain = _strip_html_tags(snippet)
    if len(plain) <= SNIPPET_TOTAL_MAX:
        return snippet

    em_mask = [False] * len(plain)
    plain_idx = 0
    in_em = False
    si = 0
    while si < len(snippet):
        if snippet[si] == "<":
            tag_end = snippet.find(">", si)
            if tag_end < 0:
                break
            tag = snippet[si : tag_end + 1].lower()
            if tag == "<em>":
                in_em = True
            elif tag == "</em>":
                in_em = False
            si = tag_end + 1
        else:
            if plain_idx < len(plain):
                em_mask[plain_idx] = in_em
                plain_idx += 1
            si += 1

    first_em = next((i for i, v in enumerate(em_mask) if v), None)
    if first_em is None:
        return plain[:SNIPPET_TOTAL_MAX].rstrip()

    ellipsis_reserve = 8
    budget = max(SNIPPET_TOTAL_MAX - ellipsis_reserve, SNIPPET_TOTAL_MAX // 2)
    half = budget // 2
    win_start = max(0, first_em - half)
    win_end = min(len(plain), win_start + budget)
    if win_end - win_start < budget:
        win_start = max(0, win_end - budget)

    prefix_ellipsis = win_start > 0
    suffix_ellipsis = win_end < len(plain)
    if prefix_ellipsis:
        sp = plain.find(" ", win_start)
        if 0 <= sp < win_start + 15:
            win_start = sp + 1
    if suffix_ellipsis:
        sp = plain.rfind(" ", max(win_start, win_end - 15), win_end)
        if sp > win_start:
            win_end = sp

    parts: list[str] = []
    cur_em = False
    for pos in range(win_start, win_end):
        if em_mask[pos] and not cur_em:
            parts.append("<em>")
            cur_em = True
        elif not em_mask[pos] and cur_em:
            parts.append("</em>")
            cur_em = False
        parts.append(plain[pos])
    if cur_em:
        parts.append("</em>")

    body = "".join(parts)
    if prefix_ellipsis:
        body = "... " + body
    if suffix_ellipsis:
        body = body.rstrip() + " ..."
    return body


def _tokenize_normalized(value: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _normalize_query_text(value)) if t]


def _normalized_stem(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return _normalize_query_text(Path(raw).stem)


def _field_exact_match_rank(query: str, value: str) -> int:
    query_norm = _normalize_query_text(query)
    value_norm = _normalize_query_text(value)
    if not query_norm or not value_norm:
        return 0
    if query_norm == value_norm:
        return 2
    stem_norm = _normalized_stem(value)
    if stem_norm and query_norm == stem_norm:
        return 1
    return 0


def _search_hit_sort_key(query: str, src: dict[str, Any], score: float, total_evidences: int) -> tuple[int, int, int, float, int]:
    return (
        _field_exact_match_rank(query, str(src.get("original_filename") or "")),
        _field_exact_match_rank(query, str(src.get("title") or "")),
        _field_exact_match_rank(query, str(src.get("canonical_filename") or "")),
        score,
        total_evidences,
    )


def _count_query_occurrences_in_text(text: str, query: str) -> int:
    query_tokens = _tokenize_normalized(query)
    text_tokens = _tokenize_normalized(text)
    if not query_tokens or not text_tokens:
        return 0
    q_len = len(query_tokens)
    if len(text_tokens) < q_len:
        return 0
    count = 0
    for i in range(len(text_tokens) - q_len + 1):
        if text_tokens[i : i + q_len] == query_tokens:
            count += 1
    return count


def _longest_contiguous_match_tokens(query_tokens: list[str], text_tokens: list[str]) -> int:
    if not query_tokens or not text_tokens:
        return 0
    best = 0
    q_len = len(query_tokens)
    t_len = len(text_tokens)
    # Contiguous token overlap (exact token sequence after normalization).
    for qi in range(q_len):
        for ti in range(t_len):
            if query_tokens[qi] != text_tokens[ti]:
                continue
            span = 0
            while qi + span < q_len and ti + span < t_len and query_tokens[qi + span] == text_tokens[ti + span]:
                span += 1
            if span > best:
                best = span
    return best


def _field_highlight_priority(field_name: str) -> int:
    if field_name.startswith("content_chunks"):
        return 0
    if field_name.startswith("content"):
        return 1
    if field_name.startswith("title"):
        return 2
    if field_name.startswith("original_filename"):
        return 3
    if field_name.startswith("canonical_filename"):
        return 4
    return 5


def _highlight_quality(snippet: str, query_tokens: list[str]) -> tuple[int, int, int]:
    plain = _strip_html_tags(snippet)
    snippet_tokens = _tokenize_normalized(plain)
    contiguous = _longest_contiguous_match_tokens(query_tokens, snippet_tokens)
    em_count = snippet.lower().count("<em>")
    # Higher contiguous coverage first, then total highlighted terms, then snippet length.
    return (contiguous, em_count, len(plain))


def _ordered_highlights(highlighted_by_field: dict[str, list[str]], query: str) -> list[str]:
    query_tokens = _tokenize_normalized(query)
    entries: list[tuple[int, tuple[int, int, int], str]] = []
    for field_name, snippets in highlighted_by_field.items():
        field_priority = _field_highlight_priority(field_name)
        for snippet in snippets:
            entries.append((field_priority, _highlight_quality(snippet, query_tokens), snippet))
    entries.sort(key=lambda item: (item[0], -item[1][0], -item[1][1], -item[1][2]))
    ordered = [snippet for _, _, snippet in entries]
    return list(dict.fromkeys(ordered))


def _highlights_with_full_phrase_first(ordered: list[str], query: str) -> list[str]:
    """Coloca primeiro os snippets que contêm a query inteira (mesmo critério da busca)."""
    if not query or not ordered:
        return ordered
    norm_q = _normalize_query_text(query)
    if not norm_q:
        return ordered
    trimmed = [_trim_highlight(s) for s in ordered]
    contains_full = [s for s in trimmed if norm_q in _normalize_query_text(_strip_html_tags(s))]
    others = [s for s in trimmed if s not in contains_full]
    return contains_full + others


def _field_to_location(field_name: str) -> str:
    if field_name.startswith("title"):
        return "title"
    if field_name.startswith("content_chunks"):
        return "content_chunk"
    if field_name.startswith("content"):
        return "content"
    if field_name.startswith("original_filename"):
        return "original_filename"
    if field_name.startswith("canonical_filename"):
        return "canonical_filename"
    return field_name


def _extract_chunk_markers(highlights: list[str]) -> list[str]:
    markers: set[str] = set()
    generic_pattern = re.compile(r"\[([^\]]+)\]")
    for snippet in highlights:
        clean_snippet = _strip_html_tags(snippet)
        for match in generic_pattern.finditer(clean_snippet):
            marker = re.sub(r"\s+", " ", match.group(1).strip()).lower()
            if marker:
                markers.add(marker)
    return sorted(markers)


def _extract_locations_from_chunk_text(chunk_text: str, query: str, limit: int = 3) -> list[str]:
    text = chunk_text or ""
    if not text:
        return []
    raw_tokens = [t for t in re.split(r"[^a-z0-9]+", _normalize_query_text(query)) if len(t) >= 2]
    stopwords = {"de", "da", "do", "das", "dos", "e", "a", "o", "na", "no", "em", "para", "com", "por", "um", "uma"}
    tokens = [t for t in raw_tokens if t not in stopwords]
    if not tokens:
        tokens = raw_tokens
    if not tokens:
        return []
    markers: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("[") or "]" not in line:
            continue
        marker = line[1 : line.index("]")].strip().lower()
        normalized_line = _normalize_query_text(line)
        if any(token in normalized_line for token in tokens):
            markers.append(marker)
        if len(markers) >= limit:
            break
    return sorted(set(markers))


def _parse_docx_location(loc: str) -> tuple[bool, int, int, int] | None:
    """Parse docx location string.
    Returns (estimated, page, paragraph, part).
    """
    m = re.match(
        r"(docx_page|docx_page_est):(\d+):paragraph:(\d+)(?::part:(\d+))?$",
        (loc or "").strip().lower(),
    )
    if not m:
        return None
    estimated = m.group(1) == "docx_page_est"
    page = int(m.group(2))
    paragraph = int(m.group(3))
    part = int(m.group(4) or 1)
    return (estimated, page, paragraph, part)


def _location_sort_key(value: str) -> tuple[int, str]:
    v = (value or "").strip().lower()
    parsed_docx = _parse_docx_location(v)
    if parsed_docx:
        estimated, page, paragraph, part = parsed_docx
        kind = 3 if not estimated else 4
        return (kind, f"{page:09d}:{paragraph:09d}:{part:09d}")
    if v.startswith("sheet "):
        return (0, v)
    if v.startswith("slide "):
        return (1, v)
    if v.startswith("page "):
        return (2, v)
    if v.startswith("section "):
        return (5, v)
    if v == "content_chunk":
        return (6, v)
    if v == "content":
        return (7, v)
    if v == "title":
        return (8, v)
    if v in {"original_filename", "canonical_filename"}:
        return (9, v)
    return (10, v)


def _evidence_location_sort_key(loc: str) -> tuple[int, int, int]:
    """Ordena evidências por tipo (page, slide, section, sheet), depois por número principal e ocorrência.
    Ex.: page:4:1, page:6:1, page:6:2, page:7:1.
    """
    loc = (loc or "").strip().lower()
    parsed_docx = _parse_docx_location(loc)
    if parsed_docx:
        estimated, page, paragraph, _part = parsed_docx
        return (2 if not estimated else 3, page, paragraph)

    # page:N(:M) ou slide:N(:M) ou section:N(:M)
    m = re.match(r"(page|slide|section):(\d+)(?::(\d+))?$", loc)
    if m:
        type_order = {"page": 0, "slide": 1, "section": 4}.get(m.group(1), 5)
        return (type_order, int(m.group(2)), int(m.group(3) or 1))
    # sheet ... row N ... (ordenar por row se existir)
    sheet_m = re.search(r"row\s+(\d+)", loc)
    if sheet_m:
        return (5, int(sheet_m.group(1)), 0)
    return (6, 0, 0)


def _prioritize_locations(values: list[str], max_items: int = 6) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        norm = re.sub(r"\s+", " ", _strip_html_tags(value).strip().lower())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        unique.append(norm)
    prioritized = sorted(unique, key=_location_sort_key)
    return prioritized[:max_items]


def _levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _autocomplete_confidence(query: str, *texts: str) -> float:
    q_norm = _normalize_query_text(query)
    if len(q_norm) < 2:
        return 0.0
    query_tokens = [t for t in re.split(r"[^a-z0-9]+", q_norm) if t]
    if not query_tokens:
        return 0.0
    words: list[str] = []
    for text in texts:
        words.extend([w for w in re.split(r"[^a-z0-9]+", _normalize_query_text(text)) if w])
    if not words:
        return 0.0

    per_token: list[float] = []
    for token in query_tokens:
        token_score = 0.0
        for word in words:
            if word == token:
                token_score = max(token_score, 1.0)
            elif abs(len(word) - len(token)) <= 1 and _levenshtein_distance(word, token) <= 1:
                token_score = max(token_score, 1.0)
            elif word.startswith(token):
                token_score = max(token_score, min(len(token) / max(len(word), 1), 0.99))
            else:
                dist = _levenshtein_distance(word, token)
                if dist <= 2:
                    token_score = max(token_score, max(0.3, 1 - (dist / max(len(word), len(token), 1))))
        per_token.append(min(token_score, 1.0))
    if not per_token:
        return 0.0
    return round(sum(per_token) / len(per_token), 3)


def _resolve_project_root(project_id: str) -> Path:
    candidate = Path(settings.projects_root) / project_id
    if candidate.exists():
        return candidate

    # accent+case+space/underscore canonical form for fuzzy comparison
    def _canonical(s: str) -> str:
        return normalize_text(s).replace(" ", "_")

    canonical_id = _canonical(project_id)
    for proj in list_project_roots(Path(settings.projects_root)):
        if _canonical(proj.name) == canonical_id:
            return proj
        try:
            profile = load_project_profile(proj)
            pid = str(profile.get("project_id") or "")
            if pid == project_id or _canonical(pid) == canonical_id:
                return proj
        except Exception:
            continue
    raise HTTPException(status_code=404, detail=f"Projeto nao encontrado: {project_id}")


def _project_scope_filter(project_ref: str) -> dict[str, Any]:
    """Build a resilient filter for project-scoped search.

    Supports current project_id plus path-prefix fallback to avoid empty results
    when legacy indexed docs still carry an older project_id.
    """
    ref = str(project_ref or "").strip()
    if not ref:
        return {"match_all": {}}

    aliases: set[str] = {ref}
    normalized_ref = normalize_text(ref)
    if normalized_ref and normalized_ref != ref:
        aliases.add(normalized_ref)
    # space<->underscore tolerance: "kaido teste" also matches "kaido_teste"
    for variant in (ref.replace(" ", "_"), ref.replace("_", " ")):
        if variant != ref:
            aliases.add(variant)
            norm_variant = normalize_text(variant)
            if norm_variant and norm_variant != variant:
                aliases.add(norm_variant)
    path_prefix: str | None = None
    try:
        project_root = _resolve_project_root(ref)
    except HTTPException:
        project_root = None

    if project_root is not None:
        aliases.add(project_root.name)
        root_str = str(project_root).rstrip("/")
        if root_str:
            path_prefix = f"{root_str}/"
        try:
            profile = load_project_profile(project_root)
            profile_project_id = str(profile.get("project_id") or "").strip()
            if profile_project_id:
                aliases.add(profile_project_id)
        except Exception:
            pass

    should: list[dict[str, Any]] = [{"term": {"project_id": alias}} for alias in sorted(a for a in aliases if a)]
    if path_prefix:
        should.append({"prefix": {"path": path_prefix}})
    if not should:
        return {"term": {"project_id": ref}}
    if len(should) == 1:
        return should[0]
    return {"bool": {"should": should, "minimum_should_match": 1}}


def _initialize_project_if_needed(project_root: Path) -> tuple[dict[str, Any], bool]:
    _, created = ensure_profile(project_root=project_root, project_id=project_root.name, project_label=project_root.name)
    profile = load_project_profile(project_root)
    ensure_project_structure(project_root, profile)
    return profile, created


def _count_rows_to_process(valid_projects: list[tuple[Path, str]]) -> int:
    return count_rows_to_process(valid_projects)


def _run_reconcile(
    project_roots: list[Path],
    *,
    reindex_search: bool,
    reindex_mode: str = "full",
    cleanup_orphans: bool = True,
) -> dict[str, Any]:
    return run_reconcile(
        project_roots=project_roots,
        reindex_search=reindex_search,
        reindex_mode=reindex_mode,
        status=_reconcile_status,
        lock=_reconcile_lock,
        os_client=os_client,
        cleanup_orphans=cleanup_orphans,
    )


def _start_auto_reconcile_if_enabled() -> None:
    interval = int(settings.auto_reconcile_interval_seconds or 0)
    if interval <= 0:
        return
    if _reconcile_stop.is_set():
        _reconcile_stop.clear()

    def loop() -> None:
        while not _reconcile_stop.wait(interval):
            try:
                roots = list_project_roots(Path(settings.projects_root))
                _run_reconcile(
                    roots,
                    reindex_search=bool(settings.auto_reconcile_reindex_search),
                )
            except Exception:
                _reconcile_status["running"] = False
                _reconcile_status["phase"] = "idle"
                continue

    thread = threading.Thread(target=loop, name="atlasfile-auto-reconcile", daemon=True)
    thread.start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/setup/status")
def setup_status(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    roots = list_project_roots(Path(settings.projects_root))
    initialized_count = 0
    for r in roots:
        try:
            load_project_profile(r)
            initialized_count += 1
        except Exception:
            pass
    return {
        "app_env": settings.app_env,
        "projects_root": settings.projects_root,
        "projects_host_root": settings.projects_host_root,
        "total_project_dirs": len(roots),
        "initialized_projects": initialized_count,
        "onboarding_suggested": initialized_count == 0,
    }


@app.get("/api/projects")
def get_projects(auth: AuthContext = Depends(require_auth)) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    for root in list_project_roots(Path(settings.projects_root)):
        project_id = root.name
        project_label = root.name
        initialized = False
        try:
            profile = load_project_profile(root)
            project_id = profile.get("project_id", root.name)
            project_label = profile.get("project_label", root.name)
            initialized = True
        except Exception:
            initialized = False
        if not (auth.can_access_project(project_id) or auth.can_access_project(root.name)):
            continue
        projects.append(
            {
                "project_id": project_id,
                "project_label": project_label,
                "root": str(root),
                "initialized": initialized,
            }
        )
    return projects


@app.post("/api/projects/{project_ref}/initialize")
def initialize_project(project_ref: str, template: str = Query("default"), auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    enforce_project_scope(auth, project_ref)
    project_root = Path(settings.projects_root) / project_ref
    project_root.mkdir(parents=True, exist_ok=True)
    _, created = ensure_profile(
        project_root=project_root,
        project_id=project_root.name,
        project_label=project_root.name,
        template_slug=template,
    )
    profile = load_project_profile(project_root)
    ensure_project_structure(project_root, profile)
    return {
        "status": "ok",
        "already_initialized": not created,
        "project": {
            "project_id": profile.get("project_id", project_root.name),
            "project_label": profile.get("project_label", project_root.name),
            "root": str(project_root),
            "initialized": True,
        },
    }


# ── Template CRUD ──

@app.get("/api/templates")
def api_list_templates(auth: AuthContext = Depends(require_auth)) -> list[dict[str, Any]]:
    return _list_templates()


@app.get("/api/templates/{slug}")
def api_get_template(slug: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    try:
        return _get_template(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Template não encontrado: {slug}")


@app.post("/api/templates")
def api_create_template(body: dict[str, Any], auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    from_profile = body.pop("from_profile", None)
    if from_profile:
        project_root = _resolve_project_root(from_profile)
        profile_data = load_project_profile(project_root)
        slug = body.get("slug") or body.get("template_meta", {}).get("slug") or from_profile.lower().replace(" ", "_")
        name = body.get("name") or body.get("template_meta", {}).get("name") or from_profile
        description = body.get("description") or body.get("template_meta", {}).get("description") or f"Template derivado de {from_profile}"
        profile_data.pop("version", None)
        profile_data.pop("updated_at", None)
        profile_data.pop("updated_by", None)
        profile_data["project_id"] = "__PROJECT_ID__"
        profile_data["project_label"] = "__PROJECT_LABEL__"
        profile_data["project_root"] = "__PROJECT_ROOT__"
        profile_data["template_meta"] = {"slug": slug, "name": name, "description": description}
        try:
            return _save_template(slug, profile_data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    slug = body.get("template_meta", {}).get("slug") or body.get("slug", "")
    if not slug:
        raise HTTPException(status_code=400, detail="slug obrigatório")
    try:
        return _save_template(slug, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/templates/{slug}")
def api_update_template(slug: str, body: dict[str, Any], auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    try:
        return _save_template(slug, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/templates/{slug}")
def api_delete_template(slug: str, auth: AuthContext = Depends(require_auth)) -> dict[str, str]:
    try:
        _delete_template(slug)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Template não encontrado: {slug}")
    return {"status": "ok"}


@app.get("/api/reconcile/status")
def get_reconcile_status(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    return dict(_reconcile_status)


async def _stream_reconcile_status() -> Any:
    """Generator for SSE: envia status a cada 0.25s ate running ser False."""
    while True:
        data = dict(_reconcile_status)
        yield f"data: {json.dumps(data)}\n\n"
        if not data.get("running"):
            break
        await asyncio.sleep(0.25)


@app.get("/api/reconcile/status/stream")
async def stream_reconcile_status(auth: AuthContext = Depends(require_auth)) -> StreamingResponse:
    """Server-Sent Events: stream do status de reconcile ate running === false."""
    return StreamingResponse(
        _stream_reconcile_status(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/ingest/status")
def get_ingest_status(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    return dict(_ingest_status)


async def _stream_ingest_status() -> Any:
    while True:
        data = dict(_ingest_status)
        yield f"data: {json.dumps(data)}\n\n"
        if not data.get("running"):
            break
        await asyncio.sleep(0.25)


@app.get("/api/ingest/status/stream")
async def stream_ingest_status(auth: AuthContext = Depends(require_auth)) -> StreamingResponse:
    return StreamingResponse(
        _stream_ingest_status(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _extract_classifier_report_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return None
    champion = report.get("champion") or {}
    summary = champion.get("summary")
    if isinstance(summary, dict):
        return summary
    operational_mode = str(report.get("operational_classifier_mode") or "").strip()
    if not operational_mode:
        return None
    return ((report.get("benchmarks") or {}).get(operational_mode) or {}).get("summary")


def _classifier_status_payload(project_id: str | None = None) -> dict[str, Any]:
    if project_id and project_id.strip():
        project_root = _resolve_project_root(project_id.strip())
        resolved = resolve_classifier_mode(load_project_profile(project_root))
        registry = resolved["registry"]
        override_mode = resolved["override_mode"]
        effective_mode = resolved["effective_mode"]
        latest_report = resolved["latest_report"]
    else:
        registry = load_classifier_registry()
        override_mode = None
        effective_mode = registry.champion_mode
        latest_report = load_classifier_report(registry.latest_report_id)

    return {
        "project_id": project_id,
        "available_modes": list(SUPPORTED_CLASSIFIER_MODES),
        "champion_mode": registry.champion_mode,
        "fallback_mode": registry.fallback_mode,
        "effective_mode": effective_mode,
        "override_mode": override_mode,
        "promotion_policy": registry.promotion_policy,
        "project_override_allowed": registry.project_override_allowed,
        "promotion_gates": registry.promotion_gates.model_dump(mode="json"),
        "latest_report_id": registry.latest_report_id,
        "champion_report_id": registry.champion_report_id,
        "champion_summary": registry.champion_summary.model_dump(mode="json") if registry.champion_summary else None,
        "latest_report_summary": _extract_classifier_report_summary(latest_report),
        "latest_cycle_status": registry.latest_cycle_status,
        "latest_cycle_started_at": registry.latest_cycle_started_at,
        "latest_cycle_finished_at": registry.latest_cycle_finished_at,
        "latest_cycle_error": registry.latest_cycle_error,
        "benchmark_enabled_modes": registry.benchmark_enabled_modes,
    }


def _run_classifier_cycle_background(
    min_training_docs: int,
    min_docs_per_class: int,
    benchmark_enabled_modes: list[str] | None = None,
    openai_api_key: str | None = None,
) -> None:
    _cycle_cancel_event.clear()
    started_at = time.time()

    def _progress(update: dict) -> None:
        if _cycle_cancel_event.is_set():
            raise InterruptedError("Cancelado pelo usuário")
        _classifier_cycle_status.update(update)

    try:
        report = run_classifier_cycle(
            min_training_docs=min_training_docs,
            min_docs_per_class=min_docs_per_class,
            benchmark_enabled_modes=benchmark_enabled_modes,
            progress_callback=_progress,
            openai_api_key=openai_api_key,
        )
        champion = (report.get("champion") or {}).get("mode")
        total = _classifier_cycle_status.get("progress_total") or 1
        _classifier_cycle_status.update(
            {
                "last_run_finished_at": utc_now_iso(),
                "duration_seconds": round(time.time() - started_at, 3),
                "running": False,
                "phase": "completed",
                "progress_current": total,
                "progress_total": total,
                "report_id": report.get("report_id"),
                "champion_mode": champion,
                "last_error": None,
            }
        )
    except InterruptedError:
        _classifier_cycle_status.update(
            {
                "last_run_finished_at": utc_now_iso(),
                "duration_seconds": round(time.time() - started_at, 3),
                "running": False,
                "phase": "cancelled",
                "last_error": "Cancelado pelo usuário",
            }
        )
    except Exception as exc:
        _classifier_cycle_status.update(
            {
                "last_run_finished_at": utc_now_iso(),
                "duration_seconds": round(time.time() - started_at, 3),
                "running": False,
                "phase": "failed",
                "last_error": str(exc),
            }
        )


@app.get("/api/classifier/status")
def get_classifier_status(project_id: str | None = Query(None, description="Projeto para calcular override efetivo"), auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    return _classifier_status_payload(project_id)


@app.get("/api/classifier/label-conflicts")
def get_label_conflicts(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Conflitos de rótulo pendentes de arbitragem humana (reconciliação por SHA)."""
    from app.label_conflicts import list_pending_conflicts

    items = list_pending_conflicts()
    return {"total": len(items), "items": items}


class LabelConflictResolution(BaseModel):
    business_domain: str
    document_type: str


class TaxonomyCreateRequest(BaseModel):
    kind: str  # document_type | business_domain
    key: str
    label: str = ""
    aliases: list[str] = []
    extensions: list[str] = []
    created_from: str = ""


class TaxonomyMigrateRequest(BaseModel):
    kind: str
    from_key: str
    to_key: str
    dry_run: bool = True
    remove_old: bool = True


def _taxonomy_project_context(project_id: str) -> tuple[Path, dict[str, Any]]:
    project_root = _resolve_project_root(project_id)
    profile = load_project_profile(project_root)
    return project_root, profile


@app.post("/api/taxonomy/migrate")
def migrate_taxonomy(request: TaxonomyMigrateRequest, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Migra uma key de taxonomia (origem → destino): dry_run conta tudo;
    apply move documentos (sem disparar o hold-out), reescreve datasets por
    rótulo, pendências de triagem, templates e profiles (origem vira alias)."""
    if _classifier_cycle_status.get("running"):
        raise HTTPException(status_code=409, detail="Aguarde o ciclo do classificador terminar")
    if _reconcile_status.get("running"):
        raise HTTPException(status_code=409, detail="Aguarde a reconciliação terminar")
    try:
        if request.dry_run:
            return plan_taxonomy_migration(
                kind=request.kind, from_key=request.from_key, to_key=request.to_key, os_client=os_client
            )
        return apply_taxonomy_migration(
            kind=request.kind,
            from_key=request.from_key,
            to_key=request.to_key,
            remove_old=request.remove_old,
            os_client=os_client,
            relocate=partial(_relocate_document, dataset_routing=False),
            load_project_context=_taxonomy_project_context,
        )
    except TaxonomyMigrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/taxonomy/{kind}/{key}")
def delete_taxonomy_entry(kind: str, key: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Remove a entrada dos templates e profiles — APENAS quando nenhum
    documento, dataset ou pendência de triagem ainda a usa (senão 409 com
    orientação para migrar antes)."""
    try:
        return remove_taxonomy_entry(kind=kind, key=key, os_client=os_client)
    except TaxonomyMigrationError as exc:
        code = 409 if "ainda é usada" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc))


@app.post("/api/taxonomy/create")
def create_taxonomy(request: TaxonomyCreateRequest, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Cria um document_type/business_domain no template default e propaga aos
    profiles dos projetos — usado quando uma sugestão aprovada usa taxonomia nova.
    Bootstrap e LLM reconhecem o novo tipo imediatamente (taxonomia em runtime)."""
    from app.taxonomy import create_taxonomy_entry

    try:
        result = create_taxonomy_entry(
            kind=request.kind,
            key=request.key,
            label=request.label,
            aliases=request.aliases,
            extensions=request.extensions,
            created_from=request.created_from,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", **result}


@app.get("/api/taxonomy")
def get_taxonomy(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Taxonomia vigente do template default (keys de domínios e tipos) — usada
    pela UI para validar sugestões antes de aplicar."""
    from app.template_store import get_template

    # get_template retorna {meta..., profile: raw} — a taxonomia vive no profile
    raw = get_template("default")["profile"]
    classification = raw.get("classification", {})
    return {
        "business_domains": [d.get("key") for d in classification.get("business_domains", []) if d.get("key")],
        "document_types": [t.get("key") for t in classification.get("document_types", []) if t.get("key")],
    }


@app.post("/api/classifier/label-conflicts/{sha256}/resolve")
def resolve_label_conflict(
    sha256: str, request: LabelConflictResolution, auth: AuthContext = Depends(require_auth)
) -> dict[str, Any]:
    """Aplica a arbitragem humana: rótulo canônico propagado a fontes e derivados."""
    from app.label_conflicts import resolve_conflict

    bd = request.business_domain.strip()
    dt = request.document_type.strip()
    if not bd or not dt:
        raise HTTPException(status_code=422, detail="business_domain e document_type são obrigatórios")
    try:
        result = resolve_conflict(sha256, bd, dt)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", **result}


@app.get("/api/classifier/report/latest")
def get_latest_classifier_report(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    registry = load_classifier_registry()
    report = load_classifier_report(registry.latest_report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Nenhum relatório de benchmark disponível")
    return report


@app.get("/api/classifier/reports")
def get_classifier_reports(limit: int = Query(10, ge=1, le=50), auth: AuthContext = Depends(require_auth)) -> list[dict[str, Any]]:
    reports = []
    for report in list_classifier_reports(limit=limit):
        reports.append(
            {
                "report_id": report.get("report_id"),
                "generated_at": report.get("generated_at") or report.get("saved_at"),
                "operational_classifier_mode": report.get("operational_classifier_mode"),
                "champion_mode": (report.get("champion") or {}).get("mode"),
                "champion_summary": _extract_classifier_report_summary(report),
            }
        )
    return reports


@app.delete("/api/classifier/reports/{report_id}")
def delete_classifier_report(report_id: str, auth: AuthContext = Depends(require_auth)) -> Response:
    registry = load_classifier_registry()
    if report_id == registry.champion_report_id:
        raise HTTPException(status_code=409, detail="Não é possível deletar o relatório campeão ativo")
    path = classifier_report_path(report_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Report {report_id!r} não encontrado")
    path.unlink()
    return Response(status_code=204)


@app.put("/api/classifier/override/{project_id}")
def set_classifier_override(project_id: str, body: dict[str, Any], auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    enforce_project_scope(auth, project_id)
    override_raw = str(body.get("override_mode") or "").strip()
    try:
        override_mode = OperationalClassifierMode(override_raw) if override_raw else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    project_root = _resolve_project_root(project_id)
    profile, _ = ensure_profile(project_root=project_root, project_id=project_id, project_label=project_root.name)
    profile.classification.operational.override_mode = override_mode
    save_profile(
        project_root=project_root,
        profile=profile,
        if_match_version=profile.version,
        updated_by="system:classifier_override",
    )
    return _classifier_status_payload(project_id)


@app.put("/api/classifier/benchmark-modes")
def set_benchmark_enabled_modes(body: dict[str, Any], auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    modes_raw = body.get("benchmark_enabled_modes")
    if not isinstance(modes_raw, list):
        raise HTTPException(status_code=400, detail="benchmark_enabled_modes must be a list")
    modes = [str(m).strip() for m in modes_raw if str(m).strip()]
    for mode in modes:
        if mode not in SUPPORTED_CLASSIFIER_MODES:
            raise HTTPException(status_code=400, detail=f"unsupported mode: {mode}")
    if not modes:
        raise HTTPException(status_code=400, detail="Pelo menos um modo deve estar habilitado")
    registry = load_classifier_registry()
    registry.benchmark_enabled_modes = modes
    save_classifier_registry(registry)
    return _classifier_status_payload()


@app.get("/api/classifier/cycle/status")
def get_classifier_cycle_status(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    return dict(_classifier_cycle_status)


async def _stream_classifier_cycle_status() -> Any:
    while True:
        data = dict(_classifier_cycle_status)
        yield f"data: {json.dumps(data)}\n\n"
        if not data.get("running"):
            break
        await asyncio.sleep(0.25)


@app.get("/api/classifier/cycle/status/stream")
async def stream_classifier_cycle_status(auth: AuthContext = Depends(require_auth)) -> StreamingResponse:
    return StreamingResponse(
        _stream_classifier_cycle_status(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/classifier/datasets/readiness")
def get_dataset_readiness(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Prontidão dos datasets (validação rotulada, treino, gate sparse) para a UI orientar o usuário."""
    return dataset_readiness()


@app.post("/api/classifier/datasets/backfill-validation")
def backfill_validation(
    dry_run: bool = Query(False),
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Reserva ~20% do training pool para o validation set (estratificado, idempotente)."""
    if _classifier_cycle_status.get("running"):
        raise HTTPException(status_code=409, detail="Aguarde o ciclo do classificador terminar")
    return backfill_validation_from_training_pool(dry_run=dry_run)


@app.post("/api/classifier/cycle")
def start_classifier_cycle(
    min_training_docs: int = Query(100, ge=0),
    min_docs_per_class: int = Query(5, ge=1),
    x_openai_api_key: str | None = Header(None, alias="X-OpenAI-API-Key"),
    auth: AuthContext = Depends(require_auth)
) -> JSONResponse:
    if _classifier_cycle_status.get("running"):
        raise HTTPException(status_code=409, detail="Classifier cycle already in progress")
    readiness = dataset_readiness()
    auto_backfill_moved = 0
    if readiness.get("cycle_ready") and readiness.get("validation", {}).get("labeled", 0) == 0:
        # Auto-cura: validação vazia mas o backfill resolve — executa sem pedir clique extra
        auto_backfill_moved = int(backfill_validation_from_training_pool().get("moved", 0))
        readiness = dataset_readiness()
    if not readiness.get("cycle_ready"):
        blockers = readiness.get("blockers") or []
        detail = blockers[0]["message"] if blockers else "Datasets do classificador ainda não estão prontos"
        raise HTTPException(status_code=422, detail=detail)
    registry = load_classifier_registry()
    enabled_modes = registry.benchmark_enabled_modes or ["bootstrap"]
    _classifier_cycle_status.update(
        {
            "last_run_started_at": utc_now_iso(),
            "last_run_finished_at": None,
            "duration_seconds": None,
            "running": True,
            "phase": "extracting",
            "progress_current": 0,
            "progress_total": len(enabled_modes),
            "report_id": None,
            "champion_mode": None,
            "last_error": None,
        }
    )
    thread = threading.Thread(
        target=_run_classifier_cycle_background,
        # Key do navegador transiente (benchmark llm); fallback: OPENAI_API_KEY do ambiente
        args=(min_training_docs, min_docs_per_class, registry.benchmark_enabled_modes, x_openai_api_key),
        name="atlasfile-classifier-cycle",
        daemon=True,
    )
    thread.start()
    return JSONResponse(
        status_code=202,
        content={
            "status": "started",
            "message": "Classifier cycle started",
            "auto_backfill_moved": auto_backfill_moved,
        },
    )


@app.delete("/api/classifier/cycle")
def cancel_classifier_cycle(auth: AuthContext = Depends(require_auth)) -> Response:
    if not _classifier_cycle_status.get("running"):
        raise HTTPException(status_code=409, detail="Nenhum ciclo em andamento")
    _cycle_cancel_event.set()
    return Response(status_code=202)


async def _stream_session_events(session_id: str) -> Any:
    """SSE generator: pushes session data whenever it's modified by another channel."""
    ev = _get_session_event(session_id)
    try:
        while True:
            try:
                await asyncio.wait_for(ev.wait(), timeout=25.0)
                ev.clear()
                try:
                    hit = os_client.get(index=_CHAT_SESSIONS_INDEX, id=session_id)
                    session = _session_doc_to_model(session_id, hit["_source"])
                    yield f"event: session_update\ndata: {session.model_dump_json()}\n\n"
                except Exception:
                    yield f"event: error\ndata: {{\"detail\":\"session not found\"}}\n\n"
                    break
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        _session_events.pop(session_id, None)


@app.get("/api/chat/sessions/{session_id}/events")
async def stream_session_events(session_id: str, auth: AuthContext = Depends(require_auth)) -> StreamingResponse:
    """SSE: stream real-time updates for a specific chat session."""
    return StreamingResponse(
        _stream_session_events(session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _run_reconcile_background(
    project_roots: list[Path], reindex_search: bool, reindex_mode: str, cleanup_orphans: bool = True,
) -> None:
    try:
        _run_reconcile(project_roots, reindex_search=reindex_search, reindex_mode=reindex_mode, cleanup_orphans=cleanup_orphans)
    except Exception:
        _reconcile_status["running"] = False
        _reconcile_status["phase"] = "idle"
        raise


@app.post("/api/reconcile/{project_id}")
def reconcile_project(project_id: str, reindex_search: bool = True, auth: AuthContext = Depends(require_auth)):
    enforce_project_scope(auth, project_id)
    if _reconcile_status.get("running"):
        raise HTTPException(status_code=409, detail="Reconcile already in progress")
    project_root = _resolve_project_root(project_id)
    thread = threading.Thread(
        target=_run_reconcile_background,
        args=([project_root], reindex_search, "incremental", False),
        name="atlasfile-reconcile-project",
        daemon=True,
    )
    thread.start()
    return JSONResponse(status_code=202, content={"status": "started", "message": "Reconcile started"})


@app.post("/api/reconcile")
def reconcile_all_projects(reindex_search: bool = True, auth: AuthContext = Depends(require_auth)):
    if _reconcile_status.get("running"):
        raise HTTPException(status_code=409, detail="Reconcile already in progress")
    roots = list_project_roots(Path(settings.projects_root))
    thread = threading.Thread(
        target=_run_reconcile_background,
        args=(roots, reindex_search, "incremental"),
        name="atlasfile-reconcile-all",
        daemon=True,
    )
    thread.start()
    return JSONResponse(status_code=202, content={"status": "started", "message": "Reconcile started"})


@app.post("/api/ingest/scan/{project_id}")
def scan_project_inbox(project_id: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    enforce_project_scope(auth, project_id)
    if _ingest_status.get("running"):
        raise HTTPException(status_code=409, detail="Ingest already in progress")
    project_root = _resolve_project_root(project_id)
    profile, _ = _initialize_project_if_needed(project_root)
    inbox = project_root / inbox_rel(profile)
    inbox.mkdir(parents=True, exist_ok=True)

    files = [
        f
        for f in sorted(inbox.iterdir(), key=lambda p: p.name.lower())
        if f.is_file() and not f.name.startswith(".")
    ]
    started_at = time.time()
    _ingest_status.update(
        {
            "last_run_started_at": utc_now_iso(),
            "last_run_finished_at": None,
            "duration_seconds": None,
            "project_id": project_id,
            "running": True,
            "phase": "processing",
            "progress_current": 0,
            "progress_total": len(files),
            "progress_file": None,
            "processed_count": 0,
            "failed_count": 0,
            "last_error": None,
        }
    )

    processed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    try:
        for idx, f in enumerate(files, start=1):
            _ingest_status["progress_file"] = f.name
            try:
                processed.append(
                    process_inbox_file(
                        client=os_client,
                        project_root=project_root,
                        profile=profile,
                        inbox_file=f,
                    )
                )
            except Exception as exc:
                failed.append({"filename": f.name, "path": str(f), "error": str(exc)})
            finally:
                _ingest_status["progress_current"] = idx
                _ingest_status["processed_count"] = len(processed)
                _ingest_status["failed_count"] = len(failed)
    except Exception as exc:
        _ingest_status["phase"] = "failed"
        _ingest_status["last_error"] = str(exc)
        raise
    finally:
        _ingest_status["running"] = False
        _ingest_status["progress_file"] = None
        _ingest_status["last_run_finished_at"] = utc_now_iso()
        _ingest_status["duration_seconds"] = round(time.time() - started_at, 3)
        if _ingest_status["phase"] != "failed":
            _ingest_status["phase"] = "completed"

    result = {
        "project_id": project_id,
        "processed_count": len(processed),
        "failed_count": len(failed),
        "items": processed,
        "errors": failed,
    }

    append_ingest_entry(project_root, scan_result=result)

    return result


@app.post("/api/ingest/upload/{project_id}")
async def upload_to_inbox(
    project_id: str,
    files: list[UploadFile] = FastAPIFile(...),
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    profile = load_project_profile(project_root)
    inbox = project_root / inbox_rel(profile)
    inbox.mkdir(parents=True, exist_ok=True)

    uploaded: list[dict[str, str]] = []
    for upload_file in files:
        original_name = upload_file.filename or "unnamed"
        dest = inbox / original_name
        if dest.exists():
            stem = Path(original_name).stem
            suffix = Path(original_name).suffix
            n = 2
            while dest.exists():
                dest = inbox / f"{stem}__{n}{suffix}"
                n += 1
        content = await upload_file.read()
        dest.write_bytes(content)
        uploaded.append({"filename": original_name, "saved_as": dest.name})

    return {"uploaded": uploaded}


@app.get("/api/ingest/inbox/{project_id}")
def list_inbox_files(project_id: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    profile = load_project_profile(project_root)
    inbox = project_root / inbox_rel(profile)
    if not inbox.exists():
        return {"files": []}
    files = [
        {"filename": f.name, "size": f.stat().st_size}
        for f in sorted(inbox.iterdir(), key=lambda p: p.name.lower())
        if f.is_file() and not f.name.startswith(".")
    ]
    return {"files": files}


@app.delete("/api/ingest/upload/{project_id}/{filename:path}")
def delete_inbox_file(project_id: str, filename: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    profile = load_project_profile(project_root)
    inbox = project_root / inbox_rel(profile)
    target = (inbox / filename).resolve()
    # Prevent path traversal
    if not str(target).startswith(str(inbox.resolve())):
        raise HTTPException(status_code=400, detail="Path invalido")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Arquivo nao encontrado na inbox: {filename}")
    target.unlink()
    return {"status": "ok", "deleted": filename}


@app.get("/api/ingest/history/{project_id}")
def get_ingest_history(project_id: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    entries = load_ingest_history(project_root)
    return {"project_id": project_id, "entries": entries}


@app.get("/api/files/download")
def download_file(
    path: str = Query(..., description="Caminho do arquivo dentro do projects root"),
    auth: AuthContext = Depends(require_auth),
) -> FileResponse:
    """Serve o arquivo para abrir no app associado à extensão (inline)."""
    base = Path(settings.projects_root).resolve()
    requested = Path(path).resolve()
    try:
        relative = requested.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Caminho fora do diretorio de projetos")
    # Escopo por projeto: o 1º segmento sob o projects root é a pasta do projeto.
    if relative.parts:
        enforce_project_scope(auth, relative.parts[0])
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    media_type, _ = mimetypes.guess_type(str(requested), strict=False)
    # Headers HTTP são latin-1: nomes acentuados vão via filename* (RFC 6266)
    # com fallback ASCII — filename= direto com UTF-8 estoura 500 no Starlette.
    ascii_name = unicodedata.normalize("NFKD", requested.name).encode("ascii", "ignore").decode() or "download"
    utf8_name = urllib.parse.quote(requested.name)
    return FileResponse(
        path=str(requested),
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"},
    )


def _resolve_spreadsheet_path(doc_id: str, auth: AuthContext) -> Path:
    """doc_id → arquivo físico da planilha, confinado ao projects root e ao escopo do auth."""
    try:
        hit = os_client.get(index=settings.opensearch_index, id=doc_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {doc_id}")
    src = hit.get("_source", {})
    enforce_project_scope(auth, str(src.get("project_id") or ""))
    path_str = str(src.get("path") or "")
    if not path_str:
        raise HTTPException(status_code=400, detail="Documento sem path registrado")
    base = Path(settings.projects_root).resolve()
    requested = Path(path_str).resolve()
    try:
        requested.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Caminho fora do diretorio de projetos")
    if not requested.is_file():
        raise HTTPException(status_code=404, detail=f"Arquivo nao encontrado no filesystem: {requested.name}")
    return requested


@app.get("/api/documents/{doc_id}/spreadsheet/schema")
def spreadsheet_schema_endpoint(doc_id: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Abas, colunas e amostra da planilha original — base para spreadsheet_query."""
    path = _resolve_spreadsheet_path(doc_id, auth)
    try:
        return get_spreadsheet_schema(path)
    except SpreadsheetQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class SpreadsheetQueryRequest(BaseModel):
    sql: str


@app.post("/api/documents/{doc_id}/spreadsheet/query")
def spreadsheet_query_endpoint(
    doc_id: str, body: SpreadsheetQueryRequest, auth: AuthContext = Depends(require_auth)
) -> dict[str, Any]:
    """Executa SELECT (DuckDB) sobre a planilha original — agregações exatas sem passar pelo contexto do LLM."""
    path = _resolve_spreadsheet_path(doc_id, auth)
    try:
        return run_spreadsheet_query(path, body.sql)
    except SpreadsheetQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _apply_get_document_limit(data: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Trunca content + content_chunks para não exceder max_chars. Adiciona _truncated, _message etc. quando houver corte."""
    content = data.get("content") or ""
    chunks = list(data.get("content_chunks") or [])
    total_chars = len(content) + sum(len((c.get("text") or "")) for c in chunks)
    if total_chars <= max_chars:
        return data
    out = {k: v for k, v in data.items() if k not in ("content", "content_chunks")}
    budget = max_chars
    if len(content) > budget:
        out["content"] = (content[: budget - 200] + "\n\n[... truncado ...]") if budget > 200 else content[:budget]
        budget = 0
    else:
        out["content"] = content
        budget -= len(content)
    returned: list[dict[str, Any]] = []
    for c in chunks:
        t = (c.get("text") or "")
        if budget <= 0:
            break
        if len(t) > budget:
            returned.append({"location": c.get("location"), "text": t[: budget - 100] + "\n[... truncado ...]"})
            budget = 0
        else:
            returned.append(c)
            budget -= len(t)
    out["content_chunks"] = returned
    out["_truncated"] = True
    out["_total_chunks"] = len(chunks)
    out["_returned_chunks"] = len(returned)
    out["_message"] = (
        f"Documento truncado por limite de tamanho (máx. {max_chars} caracteres). "
        f"Retornados os primeiros {len(returned)} de {len(chunks)} trechos. "
        "Use busca por termo (search_documents) para localizar trechos específicos."
    )
    return out


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Return document by id: metadata + content_chunks (location + text) and content excerpt. Resposta limitada a get_document_max_chars para caber no contexto do modelo; quando truncada, inclui _truncated e _message."""
    try:
        hit = os_client.get(index=settings.opensearch_index, id=doc_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {doc_id}")
    src = hit.get("_source", {})
    if not src:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {doc_id}")
    enforce_project_scope(auth, str(src.get("project_id") or ""))
    chunks = list(src.get("content_chunks") or [])
    content_from_chunks = "\n".join(c.get("text", "") for c in chunks)
    data = {
        "doc_id": src.get("doc_id"),
        "project_id": src.get("project_id"),
        "business_domain": src.get("business_domain"),
        "title": src.get("title"),
        "original_filename": src.get("original_filename"),
        "canonical_filename": src.get("canonical_filename"),
        "path": src.get("path"),
        "content": content_from_chunks,
        "content_chunks": chunks,
        "tags": src.get("tags", []),
        "document_type": src.get("document_type"),
        "correspondent": src.get("correspondent"),
        "review_status": src.get("review_status"),
        "content_type": src.get("content_type"),
        "ingested_at": src.get("ingested_at"),
        "processed_at": src.get("processed_at"),
    }
    return _apply_get_document_limit(data, settings.get_document_max_chars)


@app.get("/api/documents/{doc_id}/chunks")
def get_document_chunks(
    doc_id: str,
    locations: list[str] = Query(..., min_length=1),
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Return only the requested chunks of a document. locations are chunk identifiers (e.g. from search_documents match_locations or evidences[].location). Returns metadata and content_chunks with only those locations. Use after search to get full text of matched chunks without loading the full document."""
    try:
        hit = os_client.get(index=settings.opensearch_index, id=doc_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {doc_id}")
    src = hit.get("_source", {})
    if not src:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {doc_id}")
    enforce_project_scope(auth, str(src.get("project_id") or ""))
    all_chunks = list(src.get("content_chunks") or [])
    want = {loc.strip() for loc in locations if (loc or "").strip()}
    filtered = [c for c in all_chunks if (c.get("location") or "").strip() in want]
    return {
        "doc_id": src.get("doc_id"),
        "project_id": src.get("project_id"),
        "business_domain": src.get("business_domain"),
        "title": src.get("title"),
        "original_filename": src.get("original_filename"),
        "canonical_filename": src.get("canonical_filename"),
        "path": src.get("path"),
        "content_chunks": filtered,
        "tags": src.get("tags", []),
        "document_type": src.get("document_type"),
        "correspondent": src.get("correspondent"),
        "review_status": src.get("review_status"),
        "content_type": src.get("content_type"),
        "ingested_at": src.get("ingested_at"),
        "processed_at": src.get("processed_at"),
        "_requested_locations": len(locations),
        "_returned_chunks": len(filtered),
    }


@app.post("/api/documents/{doc_id}/tags")
def update_document_tags(doc_id: str, payload: DocumentTagsUpdate, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Add and/or remove tags for a document. Idempotent (no duplicate tags)."""
    try:
        hit = os_client.get(index=settings.opensearch_index, id=doc_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {doc_id}")
    src = hit["_source"]
    current_tags: list[str] = list(src.get("tags") or [])
    to_add = [t for t in (payload.add or []) if t and t.strip()]
    to_remove = set((payload.remove or []) if payload.remove else [])
    new_tags = [t for t in current_tags if t not in to_remove]
    for t in to_add:
        if t not in new_tags:
            new_tags.append(t)
    update_body: dict[str, Any] = {"doc": {"tags": new_tags}}
    os_client.update(index=settings.opensearch_index, id=doc_id, body=update_body, refresh=True)
    return {"status": "ok", "doc_id": doc_id, "tags": new_tags}


@app.patch("/api/documents/{doc_id}")
def update_document_metadata(doc_id: str, payload: DocumentMetadataUpdate, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Partial update: document_type, correspondent, business_domain, review_status."""
    try:
        os_client.get(index=settings.opensearch_index, id=doc_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {doc_id}")
    doc_updates: dict[str, Any] = {}
    if payload.document_type is not None:
        doc_updates["document_type"] = payload.document_type
    if payload.correspondent is not None:
        doc_updates["correspondent"] = payload.correspondent
    if payload.business_domain is not None:
        doc_updates["business_domain"] = payload.business_domain
    if payload.review_status is not None:
        doc_updates["review_status"] = payload.review_status
    if not doc_updates:
        return {"status": "ok", "doc_id": doc_id}
    os_client.update(index=settings.opensearch_index, id=doc_id, body={"doc": doc_updates}, refresh=True)
    return {"status": "ok", "doc_id": doc_id}


@app.post("/api/documents/{project_id}/{doc_id}/move")
def move_document(project_id: str, doc_id: str, request: DocumentMoveRequest, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    profile = load_project_profile(project_root)

    # Fetch current document from OpenSearch
    try:
        result = os_client.get(index=settings.opensearch_index, id=doc_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {doc_id}")

    source = result.get("_source", {})
    source_path_str = source.get("path", "")
    if not source_path_str:
        raise HTTPException(status_code=400, detail="Documento sem path registrado")

    source_path = Path(source_path_str)
    if not source_path.exists():
        raise HTTPException(status_code=400, detail=f"Arquivo nao encontrado no filesystem: {source_path}")

    old_business_domain = source.get("business_domain", "")
    old_document_type = source.get("document_type", "")
    original_filename = source.get("original_filename", source_path.name)

    try:
        indexed_payload = _relocate_document(
            project_root=project_root,
            profile=profile,
            project_id=project_id,
            doc_id=doc_id,
            source_path=source_path,
            target_business_domain=request.target_business_domain,
            target_document_type=request.target_document_type,
            original_filename=original_filename,
            decision="moved",
            existing_canonical_filename=source.get("canonical_filename"),
            ingested_at=source.get("ingested_at"),
            sha256=source.get("sha256", ""),
            extra_metadata={
                "confidence_score": source.get("confidence_score", 0.0),
                "entities": source.get("entities", []),
                "topics": source.get("topics", []),
                "naming_pattern": source.get("naming_pattern"),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    update_history_item(project_root, doc_id, {
        "business_domain": request.target_business_domain,
        "document_type": request.target_document_type,
        "decision": "moved",
    })

    return {
        "status": "ok",
        "doc_id": doc_id,
        "old_path": source_path_str,
        "new_path": indexed_payload["path"],
        "old_business_domain": old_business_domain,
        "new_business_domain": request.target_business_domain,
        "old_document_type": old_document_type,
        "new_document_type": request.target_document_type,
    }


@app.get("/api/tags")
def list_tags(project_id: str | None = Query(None, description="Filter by project"), auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Aggregate unique tag values from the index."""
    aggs: dict[str, Any] = {
        "tags": {
            "terms": {"field": "tags", "size": 500, "order": {"_key": "asc"}},
        }
    }
    query: dict[str, Any] = {"query": {"match_all": {}}}
    if project_id:
        query["query"] = {"bool": {"filter": [{"term": {"project_id": project_id}}]}}
    body = {"size": 0, "query": query["query"], "aggs": aggs}
    try:
        result = os_client.search(index=settings.opensearch_index, body=body)
    except OSNotFoundError:
        return {"tags": []}
    buckets = (result.get("aggregations") or {}).get("tags", {}).get("buckets") or []
    tags_list = [b["key"] for b in buckets if b.get("key")]
    return {"tags": tags_list}


@app.get("/api/stats", response_model=StatsResponse)
def get_stats(
    project_id: str | None = Query(None, description="Filter by project"),
    auth: AuthContext = Depends(require_auth),
) -> StatsResponse:
    """Aggregate document statistics: total count and breakdowns by doc_kind, business_domain, document_type, extension, tags."""
    enforce_project_scope(auth, project_id)
    query: dict[str, Any] = {"match_all": {}}
    if project_id:
        query = {"bool": {"filter": [_project_scope_filter(project_id)]}}
    elif not auth.unrestricted:
        query = {"bool": {"filter": [{"terms": {"project_id": list(auth.allowed_projects)}}]}}
    aggs: dict[str, Any] = {
        "by_doc_kind": {"terms": {"field": "doc_kind", "size": 20}},
        "by_business_domain": {"terms": {"field": "business_domain", "size": 50}},
        "by_document_type": {"terms": {"field": "document_type", "size": 50}},
        "by_extension": {"terms": {"field": "extension", "size": 30}},
        "by_tags": {"terms": {"field": "tags", "size": 100}},
        "by_project_id": {"terms": {"field": "project_id", "size": 100}},
    }
    body: dict[str, Any] = {"size": 0, "query": query, "aggs": aggs}
    _empty_stats = StatsResponse(
        project_id=project_id,
        total_documents=0,
        by_doc_kind=[],
        by_business_domain=[],
        by_document_type=[],
        by_extension=[],
        by_tags=[],
        by_project_id=[],
    )
    try:
        result = os_client.search(index=settings.opensearch_index, body=body)
    except OSNotFoundError:
        return _empty_stats
    total_hit = result.get("hits", {}).get("total", {})
    total_documents = total_hit["value"] if isinstance(total_hit, dict) else int(total_hit or 0)
    aggregations = result.get("aggregations") or {}

    def _buckets(name: str) -> list[StatsBucket]:
        return [StatsBucket(key=b["key"], count=b["doc_count"]) for b in (aggregations.get(name, {}).get("buckets") or []) if b.get("key")]

    return StatsResponse(
        project_id=project_id,
        total_documents=total_documents,
        by_doc_kind=_buckets("by_doc_kind"),
        by_business_domain=_buckets("by_business_domain"),
        by_document_type=_buckets("by_document_type"),
        by_extension=_buckets("by_extension"),
        by_tags=_buckets("by_tags"),
        by_project_id=_buckets("by_project_id"),
    )


@app.get("/api/models", response_model=list[ModelOption])
def get_models(auth: AuthContext = Depends(require_auth)) -> list[ModelOption]:
    """Return catalog of supported LLM models (builtin + cache remoto LiteLLM mesclados)."""
    return load_catalog()


@app.post("/api/models/refresh")
def refresh_models(
    dry_run: bool = Query(False),
    url: str | None = Query(None, description="Testar uma URL alternativa (só com dry_run)"),
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Atualiza o catálogo de modelos e preços a partir da fonte remota (chat + tool use only).
    dry_run=true valida a fonte (fetch + parse + contagens) sem persistir."""
    if url and not dry_run:
        raise HTTPException(status_code=400, detail="URL alternativa só é aceita com dry_run=true — salve-a antes")
    try:
        return refresh_catalog(dry_run=dry_run, url=url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao buscar o catálogo remoto: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/models/catalog-config")
def get_models_catalog_config(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Fonte do catálogo (URL efetiva + default) e data do último refresh."""
    return {
        "url": get_catalog_source_url(),
        "default_url": LITELLM_CATALOG_URL,
        "refreshed_at": catalog_refreshed_at(),
    }


class CatalogConfigRequest(BaseModel):
    url: str = ""


@app.put("/api/models/catalog-config")
def update_models_catalog_config(
    body: CatalogConfigRequest, auth: AuthContext = Depends(require_auth)
) -> dict[str, Any]:
    """Salva a URL da fonte do catálogo (vazia = voltar à default). Valida com dry-run antes."""
    candidate = body.url.strip()
    try:
        if candidate:
            refresh_catalog(dry_run=True, url=candidate)
        effective = set_catalog_source_url(candidate)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"URL inacessível: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"url": effective, "default_url": LITELLM_CATALOG_URL, "refreshed_at": catalog_refreshed_at()}


@app.get("/api/models/detail")
def get_models_detail(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Catálogo mesclado com preços por 1M tokens — para a aba Catálogo de modelos."""
    builtin_keys = {(m.provider, m.model) for m in LLM_MODEL_CATALOG}
    items: list[dict[str, Any]] = []
    for option in load_catalog():
        cost = get_cost_per_1m(option.provider, option.model)
        items.append(
            {
                **option.model_dump(),
                "input_cost_per_1m": cost[0] if cost else None,
                "output_cost_per_1m": cost[1] if cost else None,
                "cache_read_cost_per_1m": cost[2] if cost else None,
                "cache_write_cost_per_1m": cost[3] if cost else None,
                "cost_tracked": cost is not None,
                "source": "builtin" if (option.provider, option.model) in builtin_keys else "remote",
            }
        )
    return {"refreshed_at": catalog_refreshed_at(), "source_url": get_catalog_source_url(), "models": items}


class ModelValidateRequest(BaseModel):
    provider: str
    model: str


class KeyValidateRequest(BaseModel):
    provider: str


@app.post("/api/keys/validate")
def validate_provider_key(
    body: KeyValidateRequest,
    x_openai_api_key: str | None = Header(None, alias="X-OpenAI-API-Key"),
    x_anthropic_api_key: str | None = Header(None, alias="X-Anthropic-API-Key"),
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Checa se a key do provedor é válida (models.list); key transiente, nunca persistida.

    Key inválida é resultado esperado (valid=False), não erro — o wizard usa
    isto de forma não-impeditiva.
    """
    provider = body.provider.strip().lower()
    if provider == "openai":
        if not x_openai_api_key:
            raise HTTPException(status_code=400, detail="Informe a chave OpenAI no header X-OpenAI-API-Key")
        import openai as openai_sdk

        try:
            openai_sdk.OpenAI(api_key=x_openai_api_key).models.list()
            return {"valid": True, "detail": "Chave OpenAI válida"}
        except openai_sdk.AuthenticationError:
            return {"valid": False, "detail": "Chave OpenAI inválida"}
        except Exception as exc:  # rede/timeout — não confundir com key inválida
            raise HTTPException(status_code=502, detail=f"Falha ao consultar a OpenAI: {exc}")
    if provider == "anthropic":
        if not x_anthropic_api_key:
            raise HTTPException(status_code=400, detail="Informe a chave Anthropic no header X-Anthropic-API-Key")
        import anthropic as anthropic_sdk

        try:
            anthropic_sdk.Anthropic(api_key=x_anthropic_api_key).models.list()
            return {"valid": True, "detail": "Chave Anthropic válida"}
        except anthropic_sdk.AuthenticationError:
            return {"valid": False, "detail": "Chave Anthropic inválida"}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao consultar a Anthropic: {exc}")
    raise HTTPException(status_code=400, detail=f"Provedor não suportado: {provider}")


@app.post("/api/models/validate")
def validate_model(
    body: ModelValidateRequest,
    x_openai_api_key: str | None = Header(None, alias="X-OpenAI-API-Key"),
    x_anthropic_api_key: str | None = Header(None, alias="X-Anthropic-API-Key"),
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Confirma na API do provedor que o modelo existe (GET /v1/models/{id}); não persiste a key."""
    provider = body.provider.strip().lower()
    model = body.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="Informe o nome do modelo")
    if provider == "openai":
        if not x_openai_api_key:
            raise HTTPException(status_code=400, detail="Configure a chave OpenAI antes de validar")
        import openai as openai_sdk

        try:
            openai_sdk.OpenAI(api_key=x_openai_api_key).models.retrieve(model)
            return {"valid": True, "detail": f"Modelo '{model}' disponível na OpenAI"}
        except openai_sdk.NotFoundError:
            return {"valid": False, "detail": f"Modelo '{model}' não existe na OpenAI"}
        except openai_sdk.AuthenticationError:
            raise HTTPException(status_code=401, detail="Chave OpenAI inválida")
        except Exception as exc:  # rede/timeout — não confundir com inexistente
            raise HTTPException(status_code=502, detail=f"Falha ao consultar a OpenAI: {exc}")
    if provider == "anthropic":
        if not x_anthropic_api_key:
            raise HTTPException(status_code=400, detail="Configure a chave Anthropic antes de validar")
        import anthropic as anthropic_sdk

        try:
            anthropic_sdk.Anthropic(api_key=x_anthropic_api_key).models.retrieve(model)
            return {"valid": True, "detail": f"Modelo '{model}' disponível na Anthropic"}
        except anthropic_sdk.NotFoundError:
            return {"valid": False, "detail": f"Modelo '{model}' não existe na Anthropic"}
        except anthropic_sdk.AuthenticationError:
            raise HTTPException(status_code=401, detail="Chave Anthropic inválida")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao consultar a Anthropic: {exc}")
    raise HTTPException(status_code=400, detail=f"Provedor não suportado: {provider}")


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(
    body: ChatRequest,
    x_openai_api_key: str | None = Header(None, alias="X-OpenAI-API-Key"),
    x_anthropic_api_key: str | None = Header(None, alias="X-Anthropic-API-Key"),
    auth: AuthContext = Depends(require_auth),
) -> ChatResponse:
    """Send messages to the chat orchestrator (LLM + MCP tools)."""
    enforce_project_scope(auth, body.project_id)
    provider, model = get_llm_config("chat")
    if body.provider:
        provider = body.provider
    if body.model:
        model = body.model
    api_key = x_openai_api_key if provider == "openai" else (x_anthropic_api_key if provider == "anthropic" else None)
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    try:
        result = await run_chat_loop(
            messages,
            provider,
            model,
            api_key=api_key,
            enable_thinking=body.enable_thinking,
            project_id=body.project_id,
        )
        usage_raw = result.get("usage")
        usage = TurnUsage(**usage_raw) if isinstance(usage_raw, dict) else None
        cp_raw = result.get("context_pressure")
        cp = ContextPressure(**cp_raw) if isinstance(cp_raw, dict) else None
        return ChatResponse(content=result["content"], tool_calls_used=result.get("tool_calls_used", []), usage=usage, context_pressure=cp)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        err_msg = (str(e).strip() or type(e).__name__).replace("\n", " ")
        if any(
            x in err_msg.lower()
            for x in ("authentication", "api_key", "invalid api key", "incorrect api key", "no api key")
        ):
            raise HTTPException(
                status_code=503,
                detail="Chave de API do provedor não configurada ou inválida. Configure OPENAI_API_KEY ou ANTHROPIC_API_KEY no backend (ou informe na configuração do assistente).",
            ) from e
        raise HTTPException(status_code=503, detail=f"Erro no assistente: {err_msg}") from e


_CHAT_SESSIONS_INDEX = settings.opensearch_chat_sessions_index


def _parse_ts(v: Any) -> int:
    """Parse createdAt/updatedAt from OpenSearch (int ms, float, ISO string, or datetime)."""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, datetime):
        return int(v.timestamp() * 1000)
    if isinstance(v, str):
        try:
            return int(datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() * 1000)
        except (ValueError, TypeError):
            return 0
    return 0


def _parse_usage_by_model(raw: Any) -> dict[str, UsageTotals] | None:
    """Deserialize usage_by_model from OpenSearch doc (dict of model_key -> UsageTotals dict)."""
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, UsageTotals] = {}
    for k, v in raw.items():
        if isinstance(v, dict) and v:
            out[k] = UsageTotals(**v)
    return out or None


def _session_doc_to_model(doc_id: str, src: dict[str, Any]) -> ChatSession:
    ms = [
        StoredChatMessage(
            role=m.get("role", "user"),
            content=m.get("content", ""),
            timestamp=m.get("timestamp"),
            model=m.get("model"),
            channel=m.get("channel"),
        )
        for m in src.get("messages", [])
    ]
    ut = src.get("usage_totals")
    usage_totals = UsageTotals(**ut) if isinstance(ut, dict) and ut else None
    return ChatSession(
        id=doc_id,
        title=src.get("title", ""),
        messages=ms,
        model=src.get("model", ""),
        createdAt=_parse_ts(src.get("createdAt")),
        updatedAt=_parse_ts(src.get("updatedAt")),
        project_id=src.get("project_id") or None,
        usage_totals=usage_totals,
        usage_by_model=_parse_usage_by_model(src.get("usage_by_model")),
        channel=src.get("channel") or None,
        channel_chat_id=src.get("channel_chat_id"),
    )


@app.get("/api/chat/sessions", response_model=list[ChatSession])
def list_chat_sessions(
    q: str | None = Query(None, alias="q"),
    channel: str | None = Query(None, description="Filter by channel (web, telegram, ...)"),
    auth: AuthContext = Depends(require_auth)
) -> list[ChatSession]:
    """List chat sessions ordered by updatedAt desc; optional full-text filter on title."""
    body: dict[str, Any] = {"size": 500, "sort": [{"updatedAt": {"order": "desc"}}]}
    filters: list[dict[str, Any]] = []
    if q and q.strip():
        filters.append({"simple_query_string": {"query": q.strip(), "fields": ["title"], "default_operator": "and"}})
    if channel and channel.strip():
        filters.append({"term": {"channel": channel.strip()}})
    if filters:
        body["query"] = {"bool": {"must": filters}}
    else:
        body["query"] = {"match_all": {}}
    try:
        result = os_client.search(index=_CHAT_SESSIONS_INDEX, body=body)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao listar sessões: {e!s}") from e
    hits = (result.get("hits") or {}).get("hits") or []
    out: list[ChatSession] = []
    for hit in hits:
        doc_id = hit.get("_id", "")
        src = hit.get("_source", {})
        out.append(_session_doc_to_model(doc_id, src))
    return out


@app.get("/api/chat/sessions/{session_id}", response_model=ChatSession)
def get_chat_session(session_id: str, auth: AuthContext = Depends(require_auth)) -> ChatSession:
    """Return a single chat session by id."""
    try:
        hit = os_client.get(index=_CHAT_SESSIONS_INDEX, id=session_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    src = hit.get("_source", {})
    return _session_doc_to_model(session_id, src)


@app.post("/api/chat/sessions", response_model=ChatSession)
def create_chat_session(body: ChatSessionCreate, auth: AuthContext = Depends(require_auth)) -> ChatSession:
    """Create a new chat session (id generated in backend)."""
    now_ms = int(time.time() * 1000)
    doc_id = uuid.uuid4().hex
    doc: dict[str, Any] = {
        "title": body.title,
        "messages": [m.model_dump() for m in body.messages],
        "model": body.model,
        "createdAt": now_ms,
        "updatedAt": now_ms,
        "channel": body.channel,
    }
    if body.project_id is not None:
        doc["project_id"] = body.project_id
    if body.channel_chat_id is not None:
        doc["channel_chat_id"] = body.channel_chat_id
    if body.usage_totals is not None:
        doc["usage_totals"] = body.usage_totals.model_dump()
    if body.usage_by_model is not None:
        doc["usage_by_model"] = {k: v.model_dump() for k, v in body.usage_by_model.items()}
    os_client.index(index=_CHAT_SESSIONS_INDEX, id=doc_id, body=doc, refresh=True)
    return _session_doc_to_model(doc_id, doc)


async def _maybe_mirror_to_channel(
    session_src: dict[str, Any],
    appended: list,
    source_channel: str | None,
) -> None:
    """If mirror is enabled, send appended user + assistant messages to the session's origin channel."""
    ch = session_src.get("channel")
    chat_id = session_src.get("channel_chat_id")
    if not ch or not chat_id or ch == "web":
        return
    if source_channel and source_channel == ch:
        return
    mirror_setting = getattr(settings, f"{ch}_mirror_responses", False)
    if not mirror_setting:
        return
    if not channel_manager:
        return
    channel_obj = channel_manager.get_channel(ch)
    if not channel_obj or not channel_obj.is_running():
        return

    messages_to_send: list[str] = []
    for msg in appended:
        m = msg.model_dump() if hasattr(msg, "model_dump") else msg
        content = m.get("content")
        if not content:
            continue
        role = m.get("role", "")
        if role == "user":
            messages_to_send.append(f"🌐 via web:\n{content}")
        elif role == "assistant":
            messages_to_send.append(content)

    if not messages_to_send:
        return
    try:
        from app.chart_renderer import extract_chart_blocks, render_chart_png

        for text in messages_to_send:
            # Render chart blocks as images before sending
            chart_blocks = extract_chart_blocks(text)
            clean_text = text
            for chart_spec, original_block in chart_blocks:
                png_bytes = render_chart_png(chart_spec)
                if png_bytes and hasattr(channel_obj, "send_photo"):
                    await channel_obj.send_photo(chat_id, png_bytes, caption=chart_spec.get("title", ""))
                    clean_text = clean_text.replace(original_block, "")
            clean_text = clean_text.strip()
            if clean_text:
                await channel_obj.send_message(chat_id, clean_text)
    except Exception:
        _logger.warning("Mirror to %s/%s failed", ch, chat_id, exc_info=True)


@app.patch("/api/chat/sessions/{session_id}", response_model=ChatSession)
async def update_chat_session(session_id: str, body: ChatSessionUpdate, auth: AuthContext = Depends(require_auth)) -> ChatSession:
    """Update session. Supports append_messages (atomic) or messages (full replace)."""
    if body.messages is not None and body.append_messages is not None:
        raise HTTPException(status_code=400, detail="Envie 'messages' ou 'append_messages', não ambos")

    partial: dict[str, Any] = {"updatedAt": int(time.time() * 1000)}
    if body.title is not None:
        partial["title"] = body.title
    if body.project_id is not None:
        partial["project_id"] = body.project_id
    if body.usage_totals is not None:
        partial["usage_totals"] = body.usage_totals.model_dump()
    if body.usage_by_model is not None:
        partial["usage_by_model"] = {k: v.model_dump() for k, v in body.usage_by_model.items()}

    if body.messages is not None:
        partial["messages"] = [m.model_dump() for m in body.messages]

    # Atomic append: read current messages, concatenate, save
    if body.append_messages is not None:
        try:
            hit = os_client.get(index=_CHAT_SESSIONS_INDEX, id=session_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Sessão não encontrada")
        existing = hit["_source"].get("messages") or []
        existing.extend(m.model_dump() for m in body.append_messages)
        partial["messages"] = existing

    try:
        os_client.update(
            index=_CHAT_SESSIONS_INDEX,
            id=session_id,
            body={"doc": partial},
            refresh=True,
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    hit = os_client.get(index=_CHAT_SESSIONS_INDEX, id=session_id)
    session_src = hit["_source"]
    result = _session_doc_to_model(session_id, session_src)

    _notify_session_update(session_id)

    # Mirror: send assistant response to origin channel if enabled
    if body.append_messages:
        await _maybe_mirror_to_channel(session_src, body.append_messages, body.source_channel)

    return result


@app.delete("/api/chat/sessions/{session_id}", status_code=204)
def delete_chat_session(session_id: str, auth: AuthContext = Depends(require_auth)):
    """Delete a chat session. Returns 204 No Content."""
    try:
        os_client.delete(index=_CHAT_SESSIONS_INDEX, id=session_id, refresh=True)
    except Exception:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return None


def _split_provider_model(model_raw: str) -> tuple[str, str]:
    """Split stored 'provider/model' into (provider, bare_model) for cost lookup.

    Sessions store model as 'openai/gpt-4.1'; the cost config uses bare 'gpt-4.1'.
    Falls back to prefix-based inference when there's no slash.
    Ref.: OpenClaw resolveModelCostConfig (provider and model always separate).
    """
    s = (model_raw or "").strip()
    if "/" in s:
        provider, bare = s.split("/", 1)
        return (provider.lower(), bare)
    m = s.lower()
    if m.startswith("gpt"):
        return ("openai", s)
    if m.startswith("claude"):
        return ("anthropic", s)
    return ("openai", s)


@app.get("/api/usage/summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    project_id: str | None = Query(None, description="Filter by project_id; omit for all"),
    channel: str | None = Query(None, description="Filter by channel (web, telegram, ...)"),
    auth: AuthContext = Depends(require_auth)
) -> UsageSummaryResponse:
    """Aggregate usage from chat sessions in the given date range (by updatedAt)."""
    try:
        start_ts = int(datetime.strptime(start_date.strip(), "%Y-%m-%d").timestamp() * 1000)
        end_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d")
        end_ts = int((end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)).timestamp() * 1000)
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas devem ser YYYY-MM-DD")
    if start_ts > end_ts:
        raise HTTPException(status_code=400, detail="start_date deve ser anterior a end_date")
    body: dict[str, Any] = {
        "size": 10_000,
        "query": {"bool": {"must": [{"range": {"updatedAt": {"gte": start_ts, "lte": end_ts}}}]}},
        "sort": [{"updatedAt": {"order": "asc"}}],
    }
    if project_id and project_id.strip():
        body["query"]["bool"]["must"].append({"term": {"project_id": project_id.strip()}})
    if channel and channel.strip():
        body["query"]["bool"]["must"].append({"term": {"channel": channel.strip()}})
    try:
        result = os_client.search(index=_CHAT_SESSIONS_INDEX, body=body)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao agregar usage: {e!s}") from e
    hits = (result.get("hits") or {}).get("hits") or []
    total_tokens = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0
    total_cost = 0.0
    total_api_calls = 0
    by_model_raw: dict[str, dict[str, Any]] = {}
    by_day_raw: dict[str, dict[str, Any]] = {}
    def _accum_model(model_key: str, inp: int, out: int, cost: float) -> None:
        if model_key not in by_model_raw:
            by_model_raw[model_key] = {"input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0}
        by_model_raw[model_key]["input_tokens"] += inp
        by_model_raw[model_key]["output_tokens"] += out
        by_model_raw[model_key]["estimated_cost_usd"] += cost

    for hit in hits:
        src = hit.get("_source") or {}
        ut = src.get("usage_totals") or {}
        if not isinstance(ut, dict):
            continue
        inp = int(ut.get("input_tokens") or 0)
        outp = int(ut.get("output_tokens") or 0)
        cr = int(ut.get("cache_read_input_tokens") or 0)
        cw = int(ut.get("cache_creation_input_tokens") or ut.get("cache_write_input_tokens") or 0)
        tot = int(ut.get("total_tokens") or 0)
        cost = float(ut.get("estimated_cost_usd") or 0)
        total_tokens += tot
        total_input += inp
        total_output += outp
        total_cache_read += cr
        total_cache_write += cw
        total_cost += cost
        total_api_calls += int(ut.get("api_call_count") or 0)
        ubm = src.get("usage_by_model")
        if isinstance(ubm, dict) and ubm:
            for model_key, model_ut in ubm.items():
                if not isinstance(model_ut, dict):
                    continue
                _accum_model(
                    model_key,
                    int(model_ut.get("input_tokens") or 0),
                    int(model_ut.get("output_tokens") or 0),
                    float(model_ut.get("estimated_cost_usd") or 0),
                )
        else:
            # Fallback legado: sessoes sem usage_by_model atribuem ao model do doc
            model = (src.get("model") or "").strip() or "unknown"
            _accum_model(
                model,
                int(ut.get("input_tokens") or 0),
                int(ut.get("output_tokens") or 0),
                cost,
            )
        updated_at = src.get("updatedAt")
        if updated_at is not None:
            try:
                ts = int(updated_at) if isinstance(updated_at, (int, float)) else int(datetime.fromisoformat(str(updated_at).replace("Z", "+00:00")).timestamp() * 1000)
                day = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            except (ValueError, TypeError, OSError):
                day = ""
            if day:
                if day not in by_day_raw:
                    by_day_raw[day] = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
                by_day_raw[day]["input_tokens"] += inp
                by_day_raw[day]["output_tokens"] += outp
                by_day_raw[day]["cache_read_tokens"] += cr
                by_day_raw[day]["cache_write_tokens"] += cw
                by_day_raw[day]["total_tokens"] += tot
                by_day_raw[day]["estimated_cost_usd"] += cost
    by_model_list: list[UsageByModelEntry] = []
    for model, agg in by_model_raw.items():
        provider, bare_model = _split_provider_model(model)
        cost_per = get_cost_per_1m(provider, bare_model)
        input_cost = output_cost = 0.0
        if cost_per:
            input_cost = (agg["input_tokens"] / 1_000_000) * cost_per[0]
            output_cost = (agg["output_tokens"] / 1_000_000) * cost_per[1]
        by_model_list.append(
            UsageByModelEntry(
                model=model,
                input_tokens=agg["input_tokens"],
                output_tokens=agg["output_tokens"],
                input_cost_usd=round(input_cost, 6),
                output_cost_usd=round(output_cost, 6),
                total_tokens=agg["input_tokens"] + agg["output_tokens"],
                estimated_cost_usd=round(agg["estimated_cost_usd"], 6),
                cost_tracked=cost_per is not None,
            )
        )
    by_model_list.sort(key=lambda x: (-x.estimated_cost_usd, x.model))
    by_day_list = [
        UsageByDayEntry(
            date=d,
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
            cache_read_tokens=v["cache_read_tokens"],
            cache_write_tokens=v["cache_write_tokens"],
            total_tokens=v["total_tokens"],
            estimated_cost_usd=round(v["estimated_cost_usd"], 6),
        )
        for d, v in sorted(by_day_raw.items())
    ]
    return UsageSummaryResponse(
        total_tokens=total_tokens,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cache_read_tokens=total_cache_read,
        total_cache_write_tokens=total_cache_write,
        estimated_cost_usd=round(total_cost, 6),
        session_count=len(hits),
        total_api_calls=total_api_calls,
        by_model=by_model_list,
        by_day=by_day_list,
    )


@app.get("/api/usage/sessions", response_model=list[UsageSessionItem])
def get_usage_sessions(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    project_id: str | None = Query(None, description="Filter by project_id; omit for all"),
    channel: str | None = Query(None, description="Filter by channel (web, telegram, ...)"),
    limit: int = Query(100, ge=1, le=500),
    auth: AuthContext = Depends(require_auth)
) -> list[UsageSessionItem]:
    """List chat sessions with usage in the date range, ordered by updatedAt desc."""
    try:
        start_ts = int(datetime.strptime(start_date.strip(), "%Y-%m-%d").timestamp() * 1000)
        end_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d")
        end_ts = int((end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)).timestamp() * 1000)
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas devem ser YYYY-MM-DD")
    if start_ts > end_ts:
        raise HTTPException(status_code=400, detail="start_date deve ser anterior a end_date")
    body: dict[str, Any] = {
        "size": limit,
        "query": {"bool": {"must": [{"range": {"updatedAt": {"gte": start_ts, "lte": end_ts}}}]}},
        "sort": [{"updatedAt": {"order": "desc"}}],
    }
    if project_id and project_id.strip():
        body["query"]["bool"]["must"].append({"term": {"project_id": project_id.strip()}})
    if channel and channel.strip():
        body["query"]["bool"]["must"].append({"term": {"channel": channel.strip()}})
    try:
        result = os_client.search(index=_CHAT_SESSIONS_INDEX, body=body)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao listar sessões de usage: {e!s}") from e
    hits = (result.get("hits") or {}).get("hits") or []
    out: list[UsageSessionItem] = []
    for hit in hits:
        doc_id = hit.get("_id", "")
        src = hit.get("_source") or {}
        ut = src.get("usage_totals")
        usage_totals = UsageTotals(**ut) if isinstance(ut, dict) and ut else None
        updated_at = src.get("updatedAt")
        ts_ms = _parse_ts(updated_at) if updated_at is not None else 0
        out.append(
            UsageSessionItem(
                id=doc_id,
                title=src.get("title", ""),
                project_id=src.get("project_id") or None,
                model=src.get("model", ""),
                updatedAt=ts_ms,
                usage_totals=usage_totals,
                usage_by_model=_parse_usage_by_model(src.get("usage_by_model")),
                channel=src.get("channel") or None,
            )
        )
    return out


@app.post("/api/classify", response_model=ClassifyResponse)
async def api_classify(
    body: ClassifyRequest,
    x_openai_api_key: str | None = Header(None, alias="X-OpenAI-API-Key"),
    x_anthropic_api_key: str | None = Header(None, alias="X-Anthropic-API-Key"),
    auth: AuthContext = Depends(require_auth)
) -> ClassifyResponse:
    """Classify a document excerpt via LLM (submit_classification tool). Request may override provider/model."""
    if body.provider and body.model:
        provider, model = body.provider.strip().lower(), body.model.strip()
        provider_override, model_override = provider, model
    else:
        provider, model = get_llm_config("classification")
        provider_override, model_override = None, None
    api_key = x_openai_api_key if provider == "openai" else (x_anthropic_api_key if provider == "anthropic" else None)
    result = await classify_with_llm(
        body.doc_id, body.text_excerpt, body.filename or "",
        api_key=api_key,
        provider_override=provider_override,
        model_override=model_override,
    )
    usage_raw = result.pop("usage", None)
    result.pop("provider", None)
    result.pop("model", None)
    usage = TurnUsage(**usage_raw) if isinstance(usage_raw, dict) and usage_raw else None
    return ClassifyResponse(**result, usage=usage)


_CLASSIFICATION_USAGE_INDEX = settings.opensearch_classification_usage_index


@app.get("/api/usage/classification", response_model=ClassificationUsageSummary)
def get_classification_usage(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    project_id: str | None = Query(None, description="Filter by project_id; omit for all"),
    auth: AuthContext = Depends(require_auth)
) -> ClassificationUsageSummary:
    """Aggregate classification LLM usage in the given date range."""
    try:
        start_ts = int(datetime.strptime(start_date.strip(), "%Y-%m-%d").timestamp() * 1000)
        end_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d")
        end_ts = int((end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)).timestamp() * 1000)
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas devem ser YYYY-MM-DD")

    filters: list[dict[str, Any]] = [{"range": {"timestamp": {"gte": start_ts, "lte": end_ts}}}]
    if project_id and project_id.strip():
        filters.append({"term": {"project_id": project_id.strip()}})

    body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"must": filters}},
        "aggs": {
            "total_calls": {"value_count": {"field": "timestamp"}},
            "total_input": {"sum": {"field": "input_tokens"}},
            "total_output": {"sum": {"field": "output_tokens"}},
            "total_cost": {"sum": {"field": "estimated_cost_usd"}},
            "by_model": {
                "terms": {"field": "model", "size": 50},
                "aggs": {
                    "input_tokens": {"sum": {"field": "input_tokens"}},
                    "output_tokens": {"sum": {"field": "output_tokens"}},
                    "cost": {"sum": {"field": "estimated_cost_usd"}},
                },
            },
            "by_day": {
                "date_histogram": {"field": "timestamp", "calendar_interval": "day", "format": "yyyy-MM-dd"},
                "aggs": {
                    "input_tokens": {"sum": {"field": "input_tokens"}},
                    "output_tokens": {"sum": {"field": "output_tokens"}},
                    "cache_read": {"sum": {"field": "cache_read_input_tokens"}},
                    "cache_write": {"sum": {"field": "cache_creation_input_tokens"}},
                    "cost": {"sum": {"field": "estimated_cost_usd"}},
                },
            },
        },
    }
    try:
        result = os_client.search(index=_CLASSIFICATION_USAGE_INDEX, body=body)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao agregar usage de classificação: {e!s}") from e

    aggs = result.get("aggregations") or {}
    by_model_list: list[ClassificationUsageByModel] = []
    for bucket in (aggs.get("by_model", {}).get("buckets") or []):
        by_model_list.append(ClassificationUsageByModel(
            model=bucket["key"],
            call_count=bucket["doc_count"],
            input_tokens=int(bucket.get("input_tokens", {}).get("value") or 0),
            output_tokens=int(bucket.get("output_tokens", {}).get("value") or 0),
            estimated_cost_usd=round(float(bucket.get("cost", {}).get("value") or 0), 6),
        ))

    by_day_list: list[UsageByDayEntry] = []
    for bucket in (aggs.get("by_day", {}).get("buckets") or []):
        inp = int(bucket.get("input_tokens", {}).get("value") or 0)
        outp = int(bucket.get("output_tokens", {}).get("value") or 0)
        cr = int(bucket.get("cache_read", {}).get("value") or 0)
        cw = int(bucket.get("cache_write", {}).get("value") or 0)
        by_day_list.append(UsageByDayEntry(
            date=bucket.get("key_as_string", ""),
            input_tokens=inp,
            output_tokens=outp,
            cache_read_tokens=cr,
            cache_write_tokens=cw,
            total_tokens=inp + outp,
            estimated_cost_usd=round(float(bucket.get("cost", {}).get("value") or 0), 6),
        ))

    return ClassificationUsageSummary(
        total_calls=int(aggs.get("total_calls", {}).get("value") or 0),
        total_input_tokens=int(aggs.get("total_input", {}).get("value") or 0),
        total_output_tokens=int(aggs.get("total_output", {}).get("value") or 0),
        estimated_cost_usd=round(float(aggs.get("total_cost", {}).get("value") or 0), 6),
        by_model=by_model_list,
        by_day=by_day_list,
    )


_TRAINING_USAGE_INDEX = settings.opensearch_training_usage_index


@app.get("/api/usage/training", response_model=TrainingUsageSummary)
def get_training_usage(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    project_id: str | None = Query(None, description="Filter by project_id; omit for all"),
    auth: AuthContext = Depends(require_auth)
) -> TrainingUsageSummary:
    """Aggregate training/pipeline LLM usage in the given date range."""
    try:
        start_ts = int(datetime.strptime(start_date.strip(), "%Y-%m-%d").timestamp() * 1000)
        end_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d")
        end_ts = int((end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)).timestamp() * 1000)
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas devem ser YYYY-MM-DD")

    filters: list[dict[str, Any]] = [{"range": {"timestamp": {"gte": start_ts, "lte": end_ts}}}]

    body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"must": filters}},
        "aggs": {
            "total_calls": {"value_count": {"field": "timestamp"}},
            "total_api_calls": {"sum": {"field": "records_processed"}},
            "total_input": {"sum": {"field": "input_tokens"}},
            "total_output": {"sum": {"field": "output_tokens"}},
            "total_cost": {"sum": {"field": "estimated_cost_usd"}},
            "by_model": {
                "terms": {"field": "model", "size": 50},
                "aggs": {
                    "input_tokens": {"sum": {"field": "input_tokens"}},
                    "output_tokens": {"sum": {"field": "output_tokens"}},
                    "cost": {"sum": {"field": "estimated_cost_usd"}},
                    "api_calls": {"sum": {"field": "records_processed"}},
                },
            },
            "by_script": {
                "terms": {"field": "script_name", "size": 50},
                "aggs": {
                    "input_tokens": {"sum": {"field": "input_tokens"}},
                    "output_tokens": {"sum": {"field": "output_tokens"}},
                    "cost": {"sum": {"field": "estimated_cost_usd"}},
                    "api_calls": {"sum": {"field": "records_processed"}},
                },
            },
            "by_day": {
                "date_histogram": {"field": "timestamp", "calendar_interval": "day", "format": "yyyy-MM-dd"},
                "aggs": {
                    "input_tokens": {"sum": {"field": "input_tokens"}},
                    "output_tokens": {"sum": {"field": "output_tokens"}},
                    "cache_read": {"sum": {"field": "cache_read_input_tokens"}},
                    "cache_write": {"sum": {"field": "cache_creation_input_tokens"}},
                    "cost": {"sum": {"field": "estimated_cost_usd"}},
                },
            },
        },
    }
    try:
        result = os_client.search(index=_TRAINING_USAGE_INDEX, body=body)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao agregar usage de treinamento: {e!s}") from e

    aggs = result.get("aggregations") or {}
    by_model_list: list[TrainingUsageByModel] = []
    for bucket in (aggs.get("by_model", {}).get("buckets") or []):
        by_model_list.append(TrainingUsageByModel(
            model=bucket["key"],
            call_count=bucket["doc_count"],
            api_call_count=int(bucket.get("api_calls", {}).get("value") or 0),
            input_tokens=int(bucket.get("input_tokens", {}).get("value") or 0),
            output_tokens=int(bucket.get("output_tokens", {}).get("value") or 0),
            estimated_cost_usd=round(float(bucket.get("cost", {}).get("value") or 0), 6),
        ))

    by_script_list: list[TrainingUsageByScript] = []
    for bucket in (aggs.get("by_script", {}).get("buckets") or []):
        by_script_list.append(TrainingUsageByScript(
            script_name=bucket["key"],
            call_count=bucket["doc_count"],
            api_call_count=int(bucket.get("api_calls", {}).get("value") or 0),
            input_tokens=int(bucket.get("input_tokens", {}).get("value") or 0),
            output_tokens=int(bucket.get("output_tokens", {}).get("value") or 0),
            estimated_cost_usd=round(float(bucket.get("cost", {}).get("value") or 0), 6),
        ))

    by_day_list: list[UsageByDayEntry] = []
    for bucket in (aggs.get("by_day", {}).get("buckets") or []):
        inp = int(bucket.get("input_tokens", {}).get("value") or 0)
        outp = int(bucket.get("output_tokens", {}).get("value") or 0)
        cr = int(bucket.get("cache_read", {}).get("value") or 0)
        cw = int(bucket.get("cache_write", {}).get("value") or 0)
        by_day_list.append(UsageByDayEntry(
            date=bucket.get("key_as_string", ""),
            input_tokens=inp,
            output_tokens=outp,
            cache_read_tokens=cr,
            cache_write_tokens=cw,
            total_tokens=inp + outp,
            estimated_cost_usd=round(float(bucket.get("cost", {}).get("value") or 0), 6),
        ))

    return TrainingUsageSummary(
        total_calls=int(aggs.get("total_calls", {}).get("value") or 0),
        total_api_calls=int(aggs.get("total_api_calls", {}).get("value") or 0),
        total_input_tokens=int(aggs.get("total_input", {}).get("value") or 0),
        total_output_tokens=int(aggs.get("total_output", {}).get("value") or 0),
        estimated_cost_usd=round(float(aggs.get("total_cost", {}).get("value") or 0), 6),
        by_model=by_model_list,
        by_script=by_script_list,
        by_day=by_day_list,
    )


@app.get("/api/triage/{project_id}")
def get_triage(project_id: str, auth: AuthContext = Depends(require_auth)) -> list[dict[str, Any]]:
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    ensure_triage_dirs(project_root)
    return [item.model_dump() for item in list_pending(project_root)]


def _ensure_business_domain_in_profile(
    project_root: Path,
    profile: dict[str, Any],
    business_domain: str,
) -> dict[str, Any]:
    """Validate that a business domain exists in the profile."""
    del project_root
    business_domains = profile.get("classification", {}).get("business_domains", [])
    existing_keys = {
        str(domain.get("key", "")).strip()
        for domain in business_domains
    }
    if business_domain not in existing_keys:
        raise ValueError(f"business_domain not configured in profile: {business_domain}")
    return profile


def _ensure_document_type_in_profile(project_root: Path, profile: dict[str, Any], document_type: str) -> dict[str, Any]:
    del project_root
    document_types = profile.get("classification", {}).get("document_types", [])
    existing_keys = {str(item.get("key", "")).strip() for item in document_types}
    if document_type not in existing_keys:
        raise ValueError(f"document_type not configured in profile: {document_type}")
    return profile


def _extract_canonical_version(canonical_filename: str) -> int:
    match = re.search(r"__v(\d+)(?:\.[^.]+)$", str(canonical_filename or "").strip())
    return int(match.group(1)) if match else 1


def _ingested_date_token(ingested_at: Any, date_format: str) -> str | None:
    raw = str(ingested_at or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime(date_format)
    except ValueError:
        return None


# Fases reais da decisão de triagem em andamento (uma por vez, claim atômico
# garante). A UI consome via GET /api/triage/decision-status para mostrar a
# etapa verdadeira (mover, extrair, indexar...) em vez de rótulo genérico.
_decision_status: dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "doc_id": None,
    "project_id": None,
    "filename": None,
    "action": None,
    "started_at": None,
}


def _set_decision_phase(phase: str) -> None:
    if _decision_status.get("running"):
        _decision_status["phase"] = phase


@app.get("/api/triage/decision-status")
def get_triage_decision_status(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    return dict(_decision_status)


def _relocate_document(
    *,
    project_root: Path,
    profile: dict[str, Any],
    project_id: str,
    doc_id: str,
    source_path: Path,
    target_business_domain: str,
    target_document_type: str,
    original_filename: str,
    decision: str,
    existing_canonical_filename: str | None = None,
    ingested_at: str | None = None,
    sha256: str = "",
    extra_metadata: dict[str, Any] | None = None,
    note: str = "",
    dataset_routing: bool = True,
) -> dict[str, Any]:
    """Move arquivo para 02_AREAS/{bd}/{dt}, reindexar, e append training pool.

    dataset_routing=False (migração de taxonomia em massa): pula o hold-out —
    moves em lote NÃO são decisões humanas novas; os datasets são reescritos
    por rótulo antigo separadamente (taxonomy_migration.rewrite_dataset_labels).
    Returns the indexed payload dict with training_pool_status.
    """
    profile = _ensure_business_domain_in_profile(project_root, profile, target_business_domain)
    profile = _ensure_document_type_in_profile(project_root, profile, target_document_type)
    classification_path = resolve_classification_path(
        project_root=project_root,
        profile=profile,
        business_domain=target_business_domain,
        document_type=target_document_type,
        create_if_missing=True,
    )

    naming = profile.get("naming") or {}
    canonical_pattern = str(
        (extra_metadata or {}).get("naming_pattern")
        or naming.get("canonical_pattern", DEFAULT_CANONICAL_PATTERN)
    )
    date_format = str(naming.get("date_format", "%Y%m%d"))
    original_path = Path(original_filename)
    canonical_filename = (existing_canonical_filename or "").strip()
    preserved_version = _extract_canonical_version(canonical_filename)
    preserved_date = _ingested_date_token(ingested_at, date_format)
    if decision in ("corrected", "moved") or not canonical_filename:
        canonical_filename = build_canonical_filename(
            pattern=canonical_pattern,
            date_format=date_format,
            fields={
                "project": project_id,
                "business_domain": target_business_domain,
                "original_name": original_path.stem,
                "document_type": target_document_type,
            },
            original_suffix=original_path.suffix or source_path.suffix or ".bin",
            version=preserved_version,
            date_override=preserved_date,
        )

    dest_dir = project_root / classification_path
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / canonical_filename
    _set_decision_phase("movendo_arquivo")
    shutil.move(str(source_path), str(dest_path))

    _set_decision_phase("extraindo_conteudo")
    extracted_content = read_text_excerpt(dest_path)
    indexed_payload: dict[str, Any] = {
        "doc_id": doc_id,
        "project_id": project_id,
        "business_domain": target_business_domain,
        "title": source_path.stem,
        "content": extracted_content,
        "original_filename": original_filename,
        "canonical_filename": canonical_filename,
        "path": str(dest_path),
        "source_channel": (extra_metadata or {}).get("source_channel", ""),
        "source_ref": (extra_metadata or {}).get("source_ref", ""),
        "sender": (extra_metadata or {}).get("sender", ""),
        "received_at": (extra_metadata or {}).get("received_at"),
        "ingested_at": ingested_at,
        "processed_at": utc_now_iso(),
        "decision": decision,
        "confidence_score": float((extra_metadata or {}).get("confidence_score", 0.0)),
        "sha256": sha256,
        "tags": [target_business_domain, target_document_type],
        "document_type": target_document_type,
        "entities": (extra_metadata or {}).get("entities", []),
        "naming_pattern": canonical_pattern,
    }
    _set_decision_phase("indexando")
    index_document(os_client, indexed_payload, profile=profile)
    _append_index_md(project_root, indexed_payload)

    if dataset_routing:
        # Datasets do classificador: decisão humana roteia treino OU validação
        # (hold-out determinístico + regra semente + warm-up — ver dataset_holdout.py)
        _set_decision_phase("atualizando_datasets")
        dataset_result = route_labeled_document(
            source_path=dest_path,
            doc_id=doc_id,
            project_id=project_id,
            original_filename=original_filename,
            business_domain=target_business_domain,
            document_type=target_document_type,
            decision=decision,
            topics=list((extra_metadata or {}).get("topics", []) or []),
            entities=list((extra_metadata or {}).get("entities", []) or []),
            notes=note,
        )
        indexed_payload.update(dataset_result)
    return indexed_payload


@app.get("/api/triage/{project_id}/rejected")
def list_rejected_triage(project_id: str, auth: AuthContext = Depends(require_auth)) -> list[dict[str, Any]]:
    """Documentos rejeitados (e registros órfãos) — visibilidade e ações de restaurar/excluir."""
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    rejected_dir = triage_rejected_dir(project_root)
    items: list[dict[str, Any]] = []
    if rejected_dir.exists():
        for meta_path in rejected_dir.glob("*.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            file_path = Path(str(data.get("source_path") or data.get("path") or ""))
            items.append({
                "doc_id": meta_path.stem,
                "original_filename": data.get("original_filename") or data.get("filename") or "",
                "decision": data.get("decision") or "rejected",
                "decision_note": data.get("decision_note") or data.get("reason") or "",
                "processed_at": data.get("processed_at") or "",
                "suggested_business_domain": data.get("suggested_business_domain") or "",
                "suggested_document_type": data.get("suggested_document_type") or "",
                "file_exists": file_path.is_file(),
            })
    items.sort(key=lambda i: i["processed_at"], reverse=True)
    return items


@app.post("/api/triage/{project_id}/{doc_id}/restore")
def restore_rejected_triage(project_id: str, doc_id: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Devolve um rejeitado à fila de triagem (arquivo volta ao pending, meta recriado)."""
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    rejected_dir = triage_rejected_dir(project_root)
    meta_path = rejected_dir / f"{doc_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail=f"Rejeitado nao encontrado: {doc_id}")
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    file_path = Path(str(data.get("source_path") or data.get("path") or ""))
    if not file_path.is_file():
        raise HTTPException(
            status_code=400,
            detail="Registro sem arquivo físico (órfão) — use excluir para limpar o registro",
        )
    original_filename = str(data.get("original_filename") or file_path.name)
    pending_dir = triage_pending_dir(project_root)
    pending_dir.mkdir(parents=True, exist_ok=True)
    pending_file = pending_dir / f"{doc_id[:8]}__{original_filename}"
    shutil.move(str(file_path), str(pending_file))
    data["decision"] = "triage_pending"
    data["decision_note"] = ""
    data["source_path"] = str(pending_file)
    data["path"] = str(pending_file)
    data["filename"] = pending_file.name
    data["restored_at"] = utc_now_iso()
    (pending_dir / f"{doc_id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_path.unlink(missing_ok=True)
    update_history_item(project_root, doc_id, {"decision": "triage_pending"})
    return {"status": "ok", "action": "restored", "doc_id": doc_id}


@app.delete("/api/triage/{project_id}/{doc_id}/rejected")
def delete_rejected_triage(project_id: str, doc_id: str, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    """Exclui definitivamente um rejeitado (arquivo + registro)."""
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    meta_path = triage_rejected_dir(project_root) / f"{doc_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail=f"Rejeitado nao encontrado: {doc_id}")
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    file_path = Path(str(data.get("source_path") or data.get("path") or ""))
    # segurança: só apaga arquivo DENTRO da pasta rejected
    if file_path.is_file() and file_path.parent == triage_rejected_dir(project_root):
        file_path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    update_history_item(project_root, doc_id, {"decision": "deleted"})
    return {"status": "ok", "action": "deleted", "doc_id": doc_id}


@app.post("/api/triage/{project_id}/{doc_id}/decision")
def decide_triage(project_id: str, doc_id: str, request: TriageDecisionRequest, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    enforce_project_scope(auth, project_id)
    project_root = _resolve_project_root(project_id)
    profile = load_project_profile(project_root)
    ensure_project_structure(project_root, profile)

    pending_dir = triage_pending_dir(project_root)
    original_meta = pending_dir / f"{doc_id}.json"
    # Claim atômico do pending: o fluxo de aprovação move o arquivo cedo e só
    # apagava o meta no final — uma decisão concorrente (duplo clique, retry)
    # nessa janela via "pending sem arquivo" e fabricava um órfão fantasma.
    # O rename garante exclusividade; a concorrente recebe 409 amigável.
    pending_meta = pending_dir / f"{doc_id}.json.processing"
    try:
        original_meta.rename(pending_meta)
    except FileNotFoundError:
        if pending_meta.exists():
            raise HTTPException(status_code=409, detail="Decisão já em andamento para este documento")
        if (triage_resolved_dir(project_root) / f"{doc_id}.json").exists() or (
            triage_rejected_dir(project_root) / f"{doc_id}.json"
        ).exists():
            raise HTTPException(status_code=409, detail="Este documento já foi decidido")
        raise HTTPException(status_code=404, detail=f"Triage item nao encontrado: {doc_id}")

    _decision_status.update({
        "running": True,
        "phase": "preparando",
        "doc_id": doc_id,
        "project_id": project_id,
        "filename": None,
        "action": request.action,
        "started_at": utc_now_iso(),
    })
    try:
        meta_preview = json.loads(pending_meta.read_text(encoding="utf-8"))
        _decision_status["filename"] = str(meta_preview.get("original_filename") or "")
    except Exception:
        pass
    try:
        return _process_claimed_triage_decision(
            project_root=project_root,
            profile=profile,
            project_id=project_id,
            doc_id=doc_id,
            request=request,
            pending_meta=pending_meta,
        )
    except BaseException:
        # Falha de validação/processamento: o item volta à fila (o sucesso apaga o claim)
        if pending_meta.exists():
            try:
                pending_meta.rename(original_meta)
            except OSError:
                pass
        raise
    finally:
        _decision_status.update({"running": False, "phase": "idle"})


def _process_claimed_triage_decision(
    *,
    project_root: Path,
    profile: dict[str, Any],
    project_id: str,
    doc_id: str,
    request: TriageDecisionRequest,
    pending_meta: Path,
) -> dict[str, Any]:
    data = json.loads(pending_meta.read_text(encoding="utf-8"))
    source_path = Path(data["source_path"])
    if not source_path.exists():
        data["decision"] = "orphaned_missing_source"
        data["reason"] = "pending_metadata_without_file"
        data["processed_at"] = utc_now_iso()
        pending_meta.unlink(missing_ok=True)
        (triage_rejected_dir(project_root) / f"{doc_id}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"status": "ok", "action": "orphaned_cleanup", "doc_id": doc_id}

    action = request.action.lower().strip()
    if action not in {"approve", "correct", "reject"}:
        raise HTTPException(status_code=400, detail="Acao invalida. Use approve, correct ou reject.")

    if action == "reject":
        _set_decision_phase("movendo_arquivo")
        rejected_dir = triage_rejected_dir(project_root)
        original_filename = str(data.get("original_filename") or source_path.name)
        original_path = Path(original_filename)
        dest = rejected_dir / original_filename
        if dest.exists():
            dest = rejected_dir / f"{original_path.stem}__rejected_{doc_id[:8]}{original_path.suffix}"
        shutil.move(str(source_path), str(dest))
        data["decision"] = "rejected"
        data["decision_note"] = request.note or ""
        data["processed_at"] = utc_now_iso()
        data["filename"] = dest.name
        data["canonical_filename"] = dest.name
        data["source_path"] = str(dest)
        data["path"] = str(dest)
        pending_meta.unlink(missing_ok=True)
        (rejected_dir / f"{doc_id}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _append_index_md(
            project_root,
            {
                "doc_id": doc_id,
                "project_id": project_id,
                "business_domain": str(
                    data.get("business_domain")
                    or data.get("suggested_business_domain")
                    or ""
                ),
                "original_filename": original_filename,
                "canonical_filename": dest.name,
                "decision": "rejected",
                "confidence_score": float(data.get("confidence_score", 0.0)),
                "path": str(dest),
                "naming_pattern": data.get("naming_pattern", ""),
                "sha256": data.get("sha256", ""),
            },
        )
        update_history_item(project_root, doc_id, {
            "business_domain": str(data.get("suggested_business_domain") or ""),
            "decision": "rejected",
        })
        return {"status": "ok", "action": "rejected", "doc_id": doc_id}

    # approve or correct
    target_business_domain = data.get("suggested_business_domain")
    target_document_type = data.get("suggested_document_type") or data.get("document_type")
    if action == "correct":
        target_business_domain = request.target_business_domain
        target_document_type = request.target_document_type or target_document_type
        if not target_business_domain:
            raise HTTPException(status_code=400, detail="target_business_domain obrigatorio para correct")

    if not target_business_domain:
        raise HTTPException(status_code=400, detail="business_domain alvo nao definido para aprovacao/correcao")
    if not target_document_type:
        raise HTTPException(status_code=400, detail="document_type alvo nao definido para aprovacao/correcao")

    original_filename = str(data.get("original_filename") or source_path.name)
    decision_value = "approved" if action == "approve" else "corrected"

    try:
        indexed_payload = _relocate_document(
            project_root=project_root,
            profile=profile,
            project_id=project_id,
            doc_id=doc_id,
            source_path=source_path,
            target_business_domain=target_business_domain,
            target_document_type=target_document_type,
            original_filename=original_filename,
            decision=decision_value,
            existing_canonical_filename=str(data.get("canonical_filename") or "").strip() or None,
            ingested_at=data.get("ingested_at"),
            sha256=data.get("sha256", ""),
            extra_metadata={
                "naming_pattern": data.get("naming_pattern"),
                "source_channel": data.get("source_channel", ""),
                "source_ref": data.get("source_ref", ""),
                "sender": data.get("sender", ""),
                "received_at": data.get("received_at"),
                "confidence_score": data.get("confidence_score", 0.0),
                "entities": data.get("entities", []),
                "topics": data.get("topics", []),
            },
            note=str(request.note or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    data["decision"] = indexed_payload["decision"]
    data["processed_at"] = indexed_payload["processed_at"]
    data["filename"] = indexed_payload["canonical_filename"]
    data["canonical_filename"] = indexed_payload["canonical_filename"]
    data["source_path"] = indexed_payload["path"]
    data["path"] = indexed_payload["path"]
    data["final_path"] = indexed_payload["path"]
    data["business_domain"] = target_business_domain
    data["document_type"] = target_document_type
    data["naming_pattern"] = indexed_payload["naming_pattern"]
    data["training_pool_status"] = indexed_payload.get("training_pool_status", "")
    if indexed_payload.get("training_pool_record_path"):
        data["training_pool_record_path"] = indexed_payload["training_pool_record_path"]
    if indexed_payload.get("training_pool_sha256"):
        data["training_pool_sha256"] = indexed_payload["training_pool_sha256"]
    if indexed_payload.get("training_pool_validation_files"):
        data["training_pool_validation_files"] = indexed_payload["training_pool_validation_files"]

    pending_meta.unlink(missing_ok=True)
    (triage_resolved_dir(project_root) / f"{doc_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    update_history_item(project_root, doc_id, {
        "business_domain": target_business_domain,
        "document_type": target_document_type,
        "decision": decision_value,
    })
    return {"status": "ok", "action": indexed_payload["decision"], "doc_id": doc_id}


@app.get("/api/documents", response_model=ListDocumentsResponse)
def list_documents(
    project_id: str | None = None,
    doc_kind: str | None = None,
    document_type: str | None = None,
    business_domain: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_auth),
) -> ListDocumentsResponse:
    """List/browse documents with optional filters. No text search required."""
    enforce_project_scope(auth, project_id)
    filters: list[dict[str, Any]] = []
    if project_id:
        filters.append(_project_scope_filter(project_id))
    elif not auth.unrestricted:
        filters.append({"terms": {"project_id": list(auth.allowed_projects)}})
    if doc_kind:
        filters.append({"term": {"doc_kind": doc_kind}})
    if document_type:
        filters.append({"term": {"document_type": document_type}})
    if business_domain:
        filters.append({"term": {"business_domain": business_domain}})

    body: dict[str, Any] = {
        "query": {"bool": {"filter": filters}} if filters else {"match_all": {}},
        "sort": [{"ingested_at": {"order": "desc", "unmapped_type": "date"}}],
        "from": (page - 1) * size,
        "size": size,
        "_source": [
            "project_id", "title", "original_filename", "path",
            "doc_kind", "document_type", "business_domain", "tags", "ingested_at",
        ],
    }
    try:
        res = os_client.search(index=settings.opensearch_index, body=body)
    except Exception:
        return ListDocumentsResponse(total=0, page=page, page_size=size, items=[])

    total = res.get("hits", {}).get("total", {}).get("value", 0)
    items: list[ListDocumentItem] = []
    for hit in res.get("hits", {}).get("hits", []):
        src = hit.get("_source", {})
        items.append(ListDocumentItem(
            doc_id=hit["_id"],
            project_id=src.get("project_id", ""),
            title=src.get("title", ""),
            original_filename=src.get("original_filename", ""),
            path=src.get("path", ""),
            doc_kind=src.get("doc_kind"),
            document_type=src.get("document_type"),
            business_domain=src.get("business_domain"),
            tags=src.get("tags") or [],
            ingested_at=src.get("ingested_at"),
        ))
    return ListDocumentsResponse(total=total, page=page, page_size=size, items=items)


def _semantic_snippet(text: str) -> str:
    limit = int(settings.snippet_total_max)
    cleaned = " ".join(str(text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip() + "…"


def _semantic_evidence(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "location": str(chunk.get("location") or ""),
        "snippet": _semantic_snippet(chunk.get("text") or ""),
        "match_count": 0,
        "match_type": "semantic",
    }


def _fetch_hits_for_semantic_docs(
    doc_ids: list[str],
    semantic_by_id: dict[str, dict[str, Any]],
) -> dict[str, SearchHit]:
    """SearchHits para docs achados só via kNN (metadados via mget no índice principal)."""
    if not doc_ids:
        return {}
    try:
        res = os_client.mget(
            index=settings.opensearch_index,
            body={"ids": doc_ids},
            _source=[
                "doc_id", "project_id", "business_domain", "document_type",
                "original_filename", "canonical_filename", "path", "content_type",
            ],
        )
    except Exception:
        _logger.exception("Falha no mget de docs do braço semântico")
        return {}
    out: dict[str, SearchHit] = {}
    for doc in res.get("docs", []):
        if not doc.get("found"):
            continue
        src = doc.get("_source") or {}
        doc_id = str(src.get("doc_id") or doc.get("_id") or "")
        sem = semantic_by_id.get(doc_id) or {}
        chunks = list(sem.get("chunks") or [])
        evidences = [_semantic_evidence(c) for c in chunks]
        out[doc_id] = SearchHit(
            doc_id=doc_id,
            project_id=str(src.get("project_id") or ""),
            business_domain=src.get("business_domain"),
            document_type=src.get("document_type"),
            original_filename=str(src.get("original_filename") or ""),
            canonical_filename=str(src.get("canonical_filename") or ""),
            path=str(src.get("path") or ""),
            score=float(sem.get("score") or 0.0),
            highlights=[],
            match_locations=[str(c.get("location") or "") for c in chunks if c.get("location")],
            evidences=evidences,
            total_evidences=len(evidences),
            omitted_evidences=0,
            content_type=src.get("content_type"),
        )
    return out


def _rerank_hybrid_hits(q: str, hits: list[SearchHit]) -> list[SearchHit]:
    """Rerank opcional (cross-encoder) do top-N fundido; o restante mantém a ordem RRF."""
    top_n = max(1, int(settings.search_rerank_top_n))
    head, tail = hits[:top_n], hits[top_n:]
    texts: list[str] = []
    for hit in head:
        snippet = ""
        if hit.evidences:
            snippet = re.sub(r"</?em>", "", str(hit.evidences[0].get("snippet") or ""))
        texts.append(f"{hit.original_filename}\n{snippet}".strip())
    scores = rerank_pairs(q, texts)
    if not scores or len(scores) != len(head):
        return hits
    order = sorted(range(len(head)), key=lambda i: -scores[i])
    return [head[i] for i in order] + tail


def _build_hybrid_response(
    *,
    q: str,
    page: int,
    page_size: int,
    lexical_hits: list[SearchHit],
    semantic_docs: list[dict[str, Any]],
    mode: str,
) -> SearchResponse:
    """Fusão RRF dos braços lexical e semântico + rerank opcional + paginação em Python.

    O universo do híbrido é o top-N fundido (N = search_knn_k por braço); `total`
    reflete o conjunto fundido, não o total lexical do índice.
    """
    semantic_by_id = {str(d["doc_id"]): d for d in semantic_docs}
    lexical_by_id = {hit.doc_id: hit for hit in lexical_hits}
    if mode == "semantic":
        fused_ids = [str(d["doc_id"]) for d in semantic_docs]
    else:
        fused = rrf_fuse([
            [hit.doc_id for hit in lexical_hits],
            [str(d["doc_id"]) for d in semantic_docs],
        ])
        fused_ids = [doc_id for doc_id, _ in fused]
    missing_ids = [doc_id for doc_id in fused_ids if doc_id not in lexical_by_id]
    fetched = _fetch_hits_for_semantic_docs(missing_ids, semantic_by_id)
    max_ev = int(settings.search_evidences_max_per_hit)
    hits_out: list[SearchHit] = []
    for doc_id in fused_ids:
        hit = lexical_by_id.get(doc_id)
        if hit is not None and doc_id in semantic_by_id:
            existing_locations = {str(e.get("location") or "") for e in hit.evidences}
            for chunk in semantic_by_id[doc_id].get("chunks") or []:
                if len(hit.evidences) >= max_ev:
                    break
                location = str(chunk.get("location") or "")
                if location and location in existing_locations:
                    continue
                hit.evidences.append(_semantic_evidence(chunk))
        if hit is None:
            hit = fetched.get(doc_id)
        if hit is None:
            continue
        hits_out.append(hit)
    if settings.search_rerank_enabled:
        hits_out = _rerank_hybrid_hits(q, hits_out)
    total = len(hits_out)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = max(0, (page - 1) * page_size)
    return SearchResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        hits=hits_out[start : start + page_size],
        search_mode_effective=mode,
    )


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=2),
    project_id: str | None = None,
    business_domain: str | None = None,
    tags: list[str] | None = Query(None, description="Filter by tags (any match)"),
    document_type: str | None = Query(None, description="Filter by document_type"),
    doc_kind: str | None = Query(None, description="Filter by doc_kind (pdf, docx, xlsx, pptx, plain_text, html, msg...)"),
    date_from: str | None = Query(None, description="Filter ingested_at >= (ISO date)"),
    date_to: str | None = Query(None, description="Filter ingested_at <= (ISO date)"),
    page: int = Query(1, ge=1),
    size: int | None = Query(None, ge=1, le=100),
    mode: str | None = Query(None, description="Search mode: hybrid (BM25+kNN+RRF, default) | lexical | semantic"),
    auth: AuthContext = Depends(require_auth),
) -> SearchResponse:
    enforce_project_scope(auth, project_id)
    scope_filter: dict[str, Any] | None = (
        None if (project_id or auth.unrestricted) else {"terms": {"project_id": list(auth.allowed_projects)}}
    )
    page_size = size if size is not None else settings.search_page_size
    requested_mode = (mode or "").strip().lower()
    if requested_mode not in {"lexical", "hybrid", "semantic"}:
        requested_mode = "hybrid" if settings.search_hybrid_enabled else "lexical"
    search_mode_effective = requested_mode
    semantic_docs: list[dict[str, Any]] | None = None
    if requested_mode in {"hybrid", "semantic"}:
        chunk_filters = build_chunk_filters(
            project_id=project_id,
            business_domain=business_domain,
            tags=tags,
            document_type=document_type,
            doc_kind=doc_kind,
            date_from=date_from,
            date_to=date_to,
        )
        if scope_filter:
            chunk_filters.append(scope_filter)
        semantic_docs = semantic_search(os_client, q, filters=chunk_filters)
        if semantic_docs is None:
            # Degrade silencioso: braço semântico indisponível → lexical puro.
            search_mode_effective = "lexical"
    hybrid_active = search_mode_effective in {"hybrid", "semantic"}
    normalized_q = _normalize_query_text(q)
    query_tokens = _tokenize_normalized(q)
    # Strict mode for long natural-language queries: favor continuous coverage over loose token hits.
    strict_mode = len(query_tokens) >= 6 and len(normalized_q) >= 35
    fragment_size = max(
        settings.search_highlight_fragment_size_min,
        min(settings.search_highlight_fragment_size_max, len(q) + settings.search_highlight_fragment_size_min),
    )
    broad_match_raw: dict[str, Any] = {
        "query": q,
        "type": "best_fields",
        "fields": [
            "title^5",
            "original_filename_text^4",
            "canonical_filename_text^3",
            "tags^2",
        ],
        "fuzziness": "AUTO",
        "prefix_length": 1,
        "operator": "or",
    }
    broad_match_normalized: dict[str, Any] = {
        "query": normalized_q,
        "type": "best_fields",
        "fields": [
            "title_normalized^4",
            "title_ocr_folded^5",
            "original_filename_normalized^4",
            "original_filename_ocr_folded^5",
            "canonical_filename_normalized^3",
            "canonical_filename_ocr_folded^4",
        ],
        "fuzziness": "AUTO",
        "prefix_length": 1,
        "operator": "or",
    }
    if strict_mode:
        broad_match_raw["minimum_should_match"] = "75%"
        broad_match_normalized["minimum_should_match"] = "75%"
    inner_hits_size = int(max(settings.search_inner_hits_size, settings.search_evidences_max_per_hit))
    nested_content_query: dict[str, Any] = {
        "nested": {
            "path": "content_chunks",
            "query": {
                "bool": {
                    "should": [
                        {"multi_match": {"query": q, "fields": ["content_chunks.text^2"], "fuzziness": "AUTO", "prefix_length": 1, "operator": "or"}},
                        {"multi_match": {"query": normalized_q, "fields": ["content_chunks.text_normalized^2"], "fuzziness": "AUTO", "prefix_length": 1, "operator": "or"}},
                        {"multi_match": {"query": normalized_q, "fields": ["content_chunks.text_ocr_folded^4"], "fuzziness": "AUTO", "prefix_length": 1, "operator": "or"}},
                        {"match_phrase": {"content_chunks.text_normalized": {"query": normalized_q, "slop": 0, "boost": 6}}},
                        {"match_phrase": {"content_chunks.text_ocr_folded": {"query": normalized_q, "slop": 0, "boost": 8}}},
                        {"match_phrase": {"content_chunks.text_normalized": {"query": normalized_q, "slop": 2, "boost": 4}}},
                        {"match_phrase": {"content_chunks.text_ocr_folded": {"query": normalized_q, "slop": 2, "boost": 6}}},
                        {"match_phrase": {"content_chunks.text": {"query": q, "slop": 2, "boost": 3}}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "score_mode": "max",
            "inner_hits": {
                "name": "chunks",
                "size": inner_hits_size,
                "highlight": {
                    "fields": {
                        "content_chunks.text": {"fragment_size": fragment_size, "number_of_fragments": 2},
                        "content_chunks.text_normalized": {"fragment_size": fragment_size, "number_of_fragments": 2},
                    },
                    "pre_tags": ["<em>"],
                    "post_tags": ["</em>"],
                },
            },
        }
    }
    should: list[dict[str, Any]] = [
        {"multi_match": broad_match_raw},
        {"multi_match": broad_match_normalized},
        {
            "multi_match": {
                "query": q,
                "type": "phrase_prefix",
                "fields": ["title^6", "original_filename_text^5", "canonical_filename_text^3"],
                "boost": 2,
            }
        },
        {"match_phrase": {"title": {"query": q, "slop": 0, "boost": 10}}},
        {"match_phrase": {"original_filename_text": {"query": q, "slop": 0, "boost": 12}}},
        {"match_phrase": {"canonical_filename_text": {"query": q, "slop": 0, "boost": 8}}},
        {"match_phrase": {"title_normalized": {"query": normalized_q, "slop": 0, "boost": 6}}},
        {"match_phrase": {"title_ocr_folded": {"query": normalized_q, "slop": 0, "boost": 7}}},
        {"match_phrase": {"original_filename_normalized": {"query": normalized_q, "slop": 0, "boost": 5}}},
        {"match_phrase": {"original_filename_ocr_folded": {"query": normalized_q, "slop": 0, "boost": 6}}},
        {"match_phrase": {"canonical_filename_normalized": {"query": normalized_q, "slop": 0, "boost": 4}}},
        {"match_phrase": {"canonical_filename_ocr_folded": {"query": normalized_q, "slop": 0, "boost": 5}}},
        nested_content_query,
    ]
    if strict_mode:
        should.append(
            {
                "nested": {
                    "path": "content_chunks",
                    "query": {
                        "multi_match": {
                            "query": normalized_q,
                            "type": "best_fields",
                            "fields": ["content_chunks.text_normalized^6", "content_chunks.text_ocr_folded^8"],
                            "operator": "and",
                            "boost": 10,
                        }
                    },
                    "score_mode": "max",
                }
            }
        )
    filters: list[dict[str, Any]] = []
    if project_id:
        filters.append(_project_scope_filter(project_id))
    if business_domain:
        filters.append({"term": {"business_domain": business_domain}})
    if tags:
        filters.append({"terms": {"tags": tags}})
    if document_type:
        filters.append({"term": {"document_type": document_type}})
    if doc_kind:
        filters.append({"term": {"doc_kind": doc_kind}})
    if date_from:
        filters.append({"range": {"ingested_at": {"gte": date_from}}})
    if date_to:
        filters.append({"range": {"ingested_at": {"lte": date_to}}})
    if scope_filter:
        filters.append(scope_filter)

    query = {"bool": {"should": should, "minimum_should_match": 2 if strict_mode else 1, "filter": filters}}
    # Híbrido: busca top-N fixo (search_knn_k) em cada braço e pagina após a fusão.
    from_ = 0 if hybrid_active else max(0, (page - 1) * page_size)
    fetch_size = max(int(settings.search_knn_k), page_size) if hybrid_active else page_size
    body = {
        "from": from_,
        "size": fetch_size,
        "query": query,
        "highlight": {
            "require_field_match": False,
            "order": "score",
            "max_analyzer_offset": 1_000_000,
            "fields": {
                "title": {},
                "original_filename_text": {},
                "canonical_filename_text": {},
            },
            "fragment_size": fragment_size,
            "number_of_fragments": (
                settings.search_highlight_number_of_fragments_strict
                if strict_mode
                else settings.search_highlight_number_of_fragments
            ),
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        },
    }

    if search_mode_effective == "semantic":
        result = {"hits": {"hits": [], "total": {"value": 0}}}
    else:
        try:
            result = os_client.search(index=settings.opensearch_index, body=body)
        except OSNotFoundError:
            return SearchResponse(
                total=0, page=page, page_size=page_size, total_pages=1, hits=[],
                search_mode_effective=search_mode_effective,
            )
    ranked_hits: list[tuple[tuple[int, int, int, float, int], SearchHit]] = []
    for h in result["hits"]["hits"]:
        src = h["_source"]
        highlighted_by_field = dict(h.get("highlight", {}))
        for nh in (h.get("inner_hits", {}).get("chunks", {}).get("hits", {}).get("hits", [])):
            for fld, snippets in (nh.get("highlight") or {}).items():
                highlighted_by_field.setdefault(fld, []).extend(snippets)
        highlights = _highlights_with_full_phrase_first(_ordered_highlights(highlighted_by_field, q), q)
        inner_chunk_locations: list[str] = []
        for nh in (h.get("inner_hits", {}).get("chunks", {}).get("hits", {}).get("hits", [])):
            loc = (nh.get("_source") or {}).get("location", "")
            if loc:
                inner_chunk_locations.append(loc)
        match_locations = _prioritize_locations(
            inner_chunk_locations
            + _extract_chunk_markers(highlights)
            + list({_field_to_location(field_name) for field_name in highlighted_by_field.keys()})
        )
        evidences: list[dict[str, str]] = []
        total_evidences = 0
        omitted_evidences = 0
        inner = h.get("inner_hits", {}).get("chunks", {})
        if inner:
            ihits = inner.get("hits", {}).get("hits", [])
            total_val = inner.get("hits", {}).get("total")
            total_evidences = total_val["value"] if isinstance(total_val, dict) else len(ihits)
            for nh in ihits:
                loc = (nh.get("_source") or {}).get("location", "")
                raw_text = (nh.get("_source") or {}).get("text", "")
                nh_hl = nh.get("highlight") or {}
                hl_text = nh_hl.get("content_chunks.text", [])
                hl_norm = nh_hl.get("content_chunks.text_normalized", [])
                chosen = hl_text or hl_norm
                if not chosen:
                    continue
                snippet = _trim_highlight(chosen[0])
                match_count = _count_query_occurrences_in_text(raw_text, q)
                if match_count <= 0:
                    match_count = max(1, snippet.lower().count("<em>"))
                evidences.append({"location": loc, "snippet": snippet, "match_count": match_count, "match_type": "lexical"})
            evidences.sort(key=lambda e: _evidence_location_sort_key(e.get("location", "")))
            if evidences:
                best_idx = max(range(len(evidences)), key=lambda i: int(evidences[i].get("match_count", 0)))
                if best_idx > 0:
                    evidences.insert(0, evidences.pop(best_idx))
            max_ev = settings.search_evidences_max_per_hit
            omitted_evidences = max(0, total_evidences - min(len(evidences), max_ev))
            evidences = evidences[:max_ev]
        score = float(h.get("_score", 0.0))
        ranked_hits.append(
            (
                _search_hit_sort_key(q, src, score, total_evidences),
                SearchHit(
                    doc_id=src["doc_id"],
                    project_id=src["project_id"],
                    business_domain=src.get("business_domain"),
                    document_type=src.get("document_type"),
                    original_filename=src["original_filename"],
                    canonical_filename=src["canonical_filename"],
                    path=src["path"],
                    score=score,
                    highlights=highlights,
                    match_locations=match_locations,
                    evidences=evidences,
                    total_evidences=total_evidences,
                    omitted_evidences=omitted_evidences,
                    content_type=src.get("content_type"),
                ),
            )
        )
    ranked_hits.sort(key=lambda item: item[0], reverse=True)
    lexical_hits = [item[1] for item in ranked_hits]
    if not hybrid_active:
        total = result["hits"]["total"]["value"] if isinstance(result["hits"]["total"], dict) else int(result["hits"]["total"])
        total_pages = max(1, (total + page_size - 1) // page_size)
        return SearchResponse(
            total=total, page=page, page_size=page_size, total_pages=total_pages,
            hits=lexical_hits, search_mode_effective="lexical",
        )
    return _build_hybrid_response(
        q=q,
        page=page,
        page_size=page_size,
        lexical_hits=lexical_hits,
        semantic_docs=semantic_docs or [],
        mode=search_mode_effective,
    )


@app.get("/api/search/chunks")
def search_semantic_chunks(
    q: str = Query(..., min_length=2),
    project_id: str | None = None,
    business_domain: str | None = None,
    document_type: str | None = None,
    doc_kind: str | None = None,
    k: int = Query(10, ge=1, le=50),
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Chunks crus por busca semântica (kNN) — base para RAG com citações via MCP."""
    enforce_project_scope(auth, project_id)
    filters = build_chunk_filters(
        project_id=project_id,
        business_domain=business_domain,
        document_type=document_type,
        doc_kind=doc_kind,
    )
    if not project_id and not auth.unrestricted:
        filters.append({"terms": {"project_id": list(auth.allowed_projects)}})
    chunks = semantic_search_chunks(os_client, q, filters=filters, k=k)
    if chunks is None:
        return {
            "available": False,
            "chunks": [],
            "message": "Busca semântica indisponível (embeddings desabilitados ou provider com falha).",
        }
    doc_ids = sorted({str(c["doc_id"]) for c in chunks})
    doc_meta: dict[str, dict[str, Any]] = {}
    if doc_ids:
        try:
            res = os_client.mget(
                index=settings.opensearch_index,
                body={"ids": doc_ids},
                _source=["doc_id", "project_id", "original_filename", "path"],
            )
            for doc in res.get("docs", []):
                if doc.get("found"):
                    src = doc.get("_source") or {}
                    doc_meta[str(src.get("doc_id") or doc.get("_id") or "")] = src
        except Exception:
            _logger.exception("Falha no mget de metadados para /api/search/chunks")
    enriched = []
    for chunk in chunks:
        meta = doc_meta.get(str(chunk["doc_id"]), {})
        enriched.append(
            {
                **chunk,
                "original_filename": str(meta.get("original_filename") or ""),
                "path": str(meta.get("path") or ""),
                "project_id": str(meta.get("project_id") or ""),
            }
        )
    return {"available": True, "chunks": enriched}


@app.get("/api/search/suggest", response_model=SuggestResponse)
def suggest(
    q: str = Query(..., min_length=3),
    project_id: str | None = None,
    size: int | None = None,
    auth: AuthContext = Depends(require_auth)
) -> SuggestResponse:
    suggest_size = size if size is not None else settings.suggest_size
    filters: list[dict[str, Any]] = []
    if project_id:
        filters.append(_project_scope_filter(project_id))

    body = {
        "size": suggest_size,
        "query": {
            "bool": {
                "filter": filters,
                "should": [
                    {
                        "multi_match": {
                            "query": q,
                            "type": "bool_prefix",
                            "fields": [
                                "title_suggest^3",
                                "title_suggest._2gram^2",
                                "title_suggest._3gram^2",
                                "original_filename_suggest^2",
                                "original_filename_suggest._2gram",
                                "original_filename_suggest._3gram",
                            ],
                        }
                    },
                    {
                        "multi_match": {
                            "query": _normalize_query_text(q),
                            "type": "best_fields",
                            "fields": [
                                "title_normalized^2",
                                "title_ocr_folded^3",
                                "original_filename_normalized^2",
                                "original_filename_ocr_folded^3",
                                "canonical_filename_normalized",
                                "canonical_filename_ocr_folded^2",
                            ],
                            "fuzziness": "AUTO",
                            "prefix_length": 1,
                        }
                    },
                    {
                        "multi_match": {
                            "query": q,
                            "type": "phrase_prefix",
                            "fields": ["title^2", "original_filename_text^2", "canonical_filename_text"],
                        }
                    },
                    {
                        "multi_match": {
                            "query": q,
                            "type": "best_fields",
                            "fields": ["title^3", "tags^2"],
                            "fuzziness": "AUTO",
                            "prefix_length": 1,
                            "operator": "or",
                        }
                    },
                    {
                        "nested": {
                            "path": "content_chunks",
                            "query": {
                                "bool": {
                                    "should": [
                                        {"multi_match": {"query": q, "fields": ["content_chunks.text^2"], "fuzziness": "AUTO", "prefix_length": 1, "operator": "or"}},
                                        {"match_phrase_prefix": {"content_chunks.text_normalized": {"query": _normalize_query_text(q)}}},
                                        {"match_phrase_prefix": {"content_chunks.text_ocr_folded": {"query": _normalize_query_text(q)}}},
                                    ],
                                    "minimum_should_match": 1,
                                }
                            },
                            "score_mode": "max",
                        }
                    },
                    {"match_phrase_prefix": {"title_normalized": {"query": _normalize_query_text(q)}}},
                    {"match_phrase_prefix": {"title_ocr_folded": {"query": _normalize_query_text(q)}}},
                    {"match_phrase_prefix": {"original_filename_normalized": {"query": _normalize_query_text(q)}}},
                    {"match_phrase_prefix": {"original_filename_ocr_folded": {"query": _normalize_query_text(q)}}},
                    {"match_phrase_prefix": {"canonical_filename_normalized": {"query": _normalize_query_text(q)}}},
                    {"match_phrase_prefix": {"canonical_filename_ocr_folded": {"query": _normalize_query_text(q)}}},
                ],
                "minimum_should_match": 1,
            }
        },
        "_source": [
            "doc_id",
            "project_id",
            "title",
            "original_filename",
            "canonical_filename",
            "path",
            "content_type",
        ],
        "highlight": {
            "max_analyzer_offset": 1_000_000,
            "fields": {
                "title": {},
                "original_filename_text": {},
                "canonical_filename_text": {},
            },
            "fragment_size": settings.suggest_highlight_fragment_size,
            "number_of_fragments": settings.suggest_highlight_number_of_fragments,
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        },
    }

    try:
        result = os_client.search(index=settings.opensearch_index, body=body)
    except OSNotFoundError:
        return SuggestResponse(items=[])
    items: list[SearchSuggestion] = []
    by_filename: dict[str, SearchSuggestion] = {}
    for h in result.get("hits", {}).get("hits", []):
        src = h.get("_source", {})
        highlighted_by_field = h.get("highlight", {})
        highlights = _highlights_with_full_phrase_first(_ordered_highlights(highlighted_by_field, q), q)
        matched_in = _prioritize_locations(
            list({_field_to_location(field_name) for field_name in highlighted_by_field.keys()})
            + _extract_chunk_markers(highlights)
        )
        if not matched_in:
            q_norm = _normalize_query_text(q)
            if q_norm and q_norm in _normalize_query_text(str(src.get("original_filename", ""))):
                matched_in.append("original_filename")
            elif q_norm and q_norm in _normalize_query_text(str(src.get("title", ""))):
                matched_in.append("title")
            else:
                matched_in.append("content_chunk")
        matched_in = _prioritize_locations(matched_in)
        original_filename = src.get("original_filename", "")
        canonical_filename = src.get("canonical_filename", "")
        confidence = _autocomplete_confidence(
            q,
            src.get("title", ""),
            original_filename,
            canonical_filename,
            "",
        )
        suggestion = SearchSuggestion(
            doc_id=src.get("doc_id", ""),
            project_id=src.get("project_id", ""),
            original_filename=original_filename,
            canonical_filename=canonical_filename,
            path=src.get("path", ""),
            score=confidence,
            matched_in=matched_in,
            highlights=highlights,
            content_type=src.get("content_type"),
        )
        dedupe_key = f"{src.get('project_id', '')}::{_normalize_query_text(original_filename)}"
        existing = by_filename.get(dedupe_key)
        if existing is None or suggestion.score > existing.score:
            by_filename[dedupe_key] = suggestion
        else:
            existing.matched_in = sorted(set(existing.matched_in + suggestion.matched_in))
    items = [item for item in by_filename.values() if item.score > 0]
    items = sorted(items, key=lambda item: item.score, reverse=True)[:suggest_size]
    total = result["hits"]["total"]["value"] if isinstance(result["hits"]["total"], dict) else int(result["hits"]["total"])
    return SuggestResponse(total=max(total, len(items)), items=items)


@app.get("/api/search/benchmark")
def benchmark_search(
    q: list[str] = Query(..., min_length=1),
    project_id: str | None = None,
    size: int = 10,
    auth: AuthContext = Depends(require_auth)
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    durations_ms: list[float] = []

    for term in q:
        started = time.perf_counter()
        response = search(q=term, project_id=project_id, size=size)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        durations_ms.append(elapsed_ms)
        results.append(
            {
                "query": term,
                "latency_ms": elapsed_ms,
                "total": response.total,
                "top_hits": [
                    {
                        "doc_id": hit.doc_id,
                        "project_id": hit.project_id,
                        "filename": hit.original_filename,
                        "score": hit.score,
                        "match_locations": hit.match_locations,
                    }
                    for hit in response.hits[:3]
                ],
            }
        )

    avg_ms = round(sum(durations_ms) / len(durations_ms), 2) if durations_ms else 0.0
    p95_ms = round(sorted(durations_ms)[max(0, int(len(durations_ms) * 0.95) - 1)], 2) if durations_ms else 0.0
    return {
        "queries": len(q),
        "project_id": project_id,
        "average_latency_ms": avg_ms,
        "p95_latency_ms": p95_ms,
        "results": results,
    }
