from __future__ import annotations

import asyncio
import html as html_module
import json
import mimetypes
import re
import shutil
import threading
import time
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .area_resolver import resolve_area_path
from .bootstrap import ensure_project_structure
from .config import settings
from .indexer import backfill_search_fields, index_document, read_text_excerpt
from .ingestion import process_inbox_file
from .models import SearchHit, SearchResponse, SearchSuggestion, SuggestResponse, TriageDecisionRequest
from .opensearch_client import ensure_index, get_client
from .project_profile import list_project_roots, load_project_profile
from .reconcile import rebuild_search_index, reconcile_project_index, sync_search_index_for_project
from .triage import (
    ensure_triage_dirs,
    list_pending,
    triage_pending_dir,
    triage_rejected_dir,
    triage_resolved_dir,
)
from .utils import utc_now_iso

os_client = get_client()
_reconcile_lock = threading.Lock()
_reconcile_stop = threading.Event()
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure OpenSearch index and optional auto-reconcile. Shutdown: signal reconcile thread to stop."""
    max_attempts = 30
    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            ensure_index(os_client)
            backfill_search_fields(os_client)
            _start_auto_reconcile_if_enabled()
            break
        except Exception as exc:  # pragma: no cover - startup resiliency
            last_error = exc
            time.sleep(2)
    else:
        if last_error:
            raise last_error
    yield
    _reconcile_stop.set()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_DEFAULT_PROJECT_AREAS: list[tuple[str, int, list[str]]] = [
    ("societario_fiscal", 1, ["societario", "fiscal", "cnpj", "filiais", "incorporacao", "estabelecimentos"]),
    ("juridica", 2, ["juridico", "passivo", "contingencia", "parecer", "juridica"]),
    ("ativos", 3, ["ativo", "imobilizado", "cmdb", "segregacao_ativos", "doacao"]),
    ("financeiro", 4, ["carveout", "cp", "contabil", "seguros", "garantias", "fianca", "fiscal"]),
    ("contratos_comunicacao", 5, ["contrato", "fornecedor", "cliente", "comunicacao", "preambulo", "eml"]),
    ("pessoas", 6, ["colaborador", "rh", "beneficio", "hc", "organograma", "gerencia", "diretoria"]),
    ("sistemas_migracao", 7, ["sistema", "plataforma", "migracao_sistemas", "sap"]),
    ("processos_tsa", 8, ["tsa", "sox", "processo_operacional", "atendimento", "pos-closing"]),
    ("entregaveis", 9, ["output", "visao_consolidada", "framework_3ps", "inventario", "metricas", "escopo"]),
]


def _normalize_query_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower().strip()


def _strip_html_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "")


SNIPPET_TOTAL_MAX = settings.snippet_total_max


def _snippet_word_boundary_before(text: str, from_pos: int, max_chars: int) -> int:
    """Posição inicial para que text[start:from_pos] tenha no máximo max_chars e comece em palavra completa."""
    start = max(0, from_pos - max_chars)
    if start == 0:
        return 0
    if start < from_pos and text[start] not in " \n\t":
        space = text.rfind(" ", 0, start + 1)
        start = (space + 1) if space >= 0 else 0
    return start


def _snippet_word_boundary_after(text: str, from_pos: int, max_chars: int) -> int:
    """Posição final para que text[from_pos:end] tenha no máximo max_chars e termine em palavra completa."""
    end = min(len(text), from_pos + max_chars)
    if end == len(text):
        return end
    if end > from_pos and text[end - 1] not in " \n\t":
        last_space = text.rfind(" ", from_pos, end)
        end = (last_space + 1) if last_space >= 0 else end
    return end


def _build_evidence_snippet(chunk_text: str, query: str) -> str:
    """Snippet com regra única: 80 chars total, subtrai o termo, metade antes/metade depois, palavras completas.
    Se não houver nada à esquerda, usa os caracteres à direita (e vice-versa).
    """
    if not chunk_text:
        return ""
    chunk_text = chunk_text or ""
    query = (query or "").strip()
    if not query:
        return html_module.escape(chunk_text[:SNIPPET_TOTAL_MAX])

    norm_str_parts: list[str] = []
    norm_to_orig: list[tuple[int, int]] = []
    for i, c in enumerate(chunk_text):
        n = unicodedata.normalize("NFKD", c)
        n = "".join(ch for ch in n if not unicodedata.combining(ch)).lower()
        for d in n:
            norm_str_parts.append(d)
            norm_to_orig.append((i, i + 1))
    norm_str = "".join(norm_str_parts)
    norm_q = _normalize_query_text(query)
    if not norm_q:
        return html_module.escape(chunk_text[:SNIPPET_TOTAL_MAX])

    idx = norm_str.find(norm_q)
    if idx < 0:
        return html_module.escape(chunk_text[:SNIPPET_TOTAL_MAX])

    n_end = idx + len(norm_q)
    orig_start = norm_to_orig[idx][0]
    orig_end = norm_to_orig[n_end - 1][1]
    match = chunk_text[orig_start:orig_end]
    remaining = SNIPPET_TOTAL_MAX - len(match)
    if remaining <= 0:
        return "<em>" + html_module.escape(match) + "</em>"

    if orig_start == 0:
        max_before, max_after = 0, remaining
    elif orig_end >= len(chunk_text):
        max_before, max_after = remaining, 0
    else:
        max_before = remaining // 2
        max_after = remaining - max_before

    before_start = _snippet_word_boundary_before(chunk_text, orig_start, max_before) if max_before else orig_start
    after_limit = max(0, max_after - 4) if max_after else 0
    after_end = _snippet_word_boundary_after(chunk_text, orig_end, after_limit) if after_limit else orig_end
    before = chunk_text[before_start:orig_start]
    if max_before and len(before) > max_before:
        before = before[-max_before:]
        if before and before[0] not in " \n\t":
            sp = before.find(" ", 1)
            before = (before[sp + 1 :] if sp >= 0 else before).lstrip()
        before = ("... " + before) if before_start > 0 else before
    after_raw = chunk_text[orig_end:after_end]
    truncated_after = after_end < len(chunk_text)
    if truncated_after and after_limit and len(after_raw) > after_limit:
        after_raw = after_raw[: after_limit]
        if after_raw and after_raw[-1] not in " \n\t":
            sp = after_raw.rfind(" ")
            after_raw = after_raw[: sp + 1] if sp >= 0 else after_raw
    after = after_raw.rstrip() + (" ..." if truncated_after else "")

    return (
        html_module.escape(before)
        + "<em>"
        + html_module.escape(match)
        + "</em>"
        + html_module.escape(after)
    )


def _rehighlight_snippet(snippet: str, query: str) -> str:
    """Reaplica o highlight para a query inteira no snippet (mesmo critério da busca).
    O OpenSearch pode destacar só parte do termo; aqui garantimos a frase completa em <em>.
    """
    if not snippet or not (query or "").strip():
        return _trim_highlight_to_80(snippet)
    plain = _strip_html_tags(snippet)
    if not plain:
        return _trim_highlight_to_80(snippet)
    norm_q = _normalize_query_text(query)
    if not norm_q:
        return _trim_highlight_to_80(snippet)
    norm_parts: list[str] = []
    norm_to_orig: list[tuple[int, int]] = []
    for i, c in enumerate(plain):
        n = unicodedata.normalize("NFKD", c)
        n = "".join(ch for ch in n if not unicodedata.combining(ch)).lower()
        for d in n:
            norm_parts.append(d)
            norm_to_orig.append((i, i + 1))
    norm_str = "".join(norm_parts)
    idx = norm_str.find(norm_q)
    if idx < 0:
        return _trim_highlight_to_80(snippet)
    n_end = idx + len(norm_q)
    orig_start = norm_to_orig[idx][0]
    orig_end = norm_to_orig[n_end - 1][1]
    new_snippet = plain[:orig_start] + "<em>" + plain[orig_start:orig_end] + "</em>" + plain[orig_end:]
    return _trim_highlight_to_80(new_snippet)


def _trim_highlight_to_80(snippet: str) -> str:
    """Aplica a mesma regra de 80 chars aos highlights do OpenSearch (autocomplete e busca)."""
    plain = _strip_html_tags(snippet)
    if not snippet or len(plain) <= SNIPPET_TOTAL_MAX:
        return snippet
    m = re.search(r"<em>(.*?)</em>", snippet, re.DOTALL)
    if not m:
        return plain[:SNIPPET_TOTAL_MAX].rstrip()
    match = m.group(1)
    before_plain = _strip_html_tags(snippet[: m.start()])
    after_plain = _strip_html_tags(snippet[m.end() :])
    remaining = SNIPPET_TOTAL_MAX - len(match)
    if remaining <= 0:
        return "<em>" + match + "</em>"
    budget = remaining - 4  # reservar para " ..."
    if budget <= 0:
        return "<em>" + match + "</em>"
    if not before_plain.strip():
        max_before, max_after = 0, budget
    elif not after_plain.strip():
        max_before, max_after = budget, 0
    else:
        max_before = budget // 2
        max_after = budget - max_before

    if max_before and len(before_plain) > max_before:
        start = max(0, len(before_plain) - max_before)
        if start > 0 and before_plain[start] not in " \n\t":
            space = before_plain.rfind(" ", 0, start)
            start = (space + 1) if space >= 0 else 0
        before_plain = ("... " + before_plain[start :] if start > 0 else before_plain).lstrip()
    if max_after and len(after_plain) > max_after:
        end = max_after
        if end < len(after_plain) and after_plain[end - 1] not in " \n\t":
            last_space = after_plain.rfind(" ", 0, end)
            end = last_space + 1 if last_space >= 0 else end
        after_plain = after_plain[:end].rstrip() + " ..."
    return before_plain + "<em>" + match + "</em>" + after_plain


def _tokenize_normalized(value: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _normalize_query_text(value)) if t]


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
    rehighlighted = [_rehighlight_snippet(s, query) for s in ordered]
    contains_full = [s for s in rehighlighted if norm_q in _normalize_query_text(_strip_html_tags(s))]
    others = [s for s in rehighlighted if s not in contains_full]
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

    for proj in list_project_roots(Path(settings.projects_root)):
        try:
            profile = load_project_profile(proj)
            if profile.get("project_id") == project_id:
                return proj
        except Exception:
            continue
    raise HTTPException(status_code=404, detail=f"Projeto nao encontrado: {project_id}")


def _build_default_profile(project_root: Path) -> dict[str, Any]:
    work_areas = [
        {"key": key, "jd_number": jd_number, "aliases": aliases}
        for key, jd_number, aliases in _DEFAULT_PROJECT_AREAS
    ]
    return {
        "project_id": project_root.name,
        "project_label": project_root.name,
        "project_root": str(project_root),
        "inbox_path": "_INBOX_DROP",
        "triage_path": "_TRIAGE_REVIEW/pending",
        "work_root": "_WORK",
        "work_areas": work_areas,
        "routing_rules": [
            {"when_path_contains": ["output/"], "route_to": "entregaveis", "confidence": 0.98},
            {
                "when_filename_contains": ["contrato", "fornecedor", "cliente", "preambulo"],
                "route_to": "contratos_comunicacao",
                "confidence": 0.9,
            },
            {
                "when_filename_contains": ["filiais", "cnpj", "estabelecimentos"],
                "route_to": "societario_fiscal",
                "confidence": 0.9,
            },
            {
                "when_filename_contains": ["cmdb", "ativo", "imobilizado", "doacao"],
                "route_to": "ativos",
                "confidence": 0.9,
            },
            {
                "when_filename_contains": ["colaboradores", "organograma", "gh_"],
                "route_to": "pessoas",
                "confidence": 0.9,
            },
        ],
        "confidence_thresholds": {"auto_route_min": 0.85, "triage_min": 0.5},
    }


def _render_profile_markdown(profile: dict[str, Any]) -> str:
    frontmatter = yaml.safe_dump(profile, sort_keys=False, allow_unicode=True).strip()
    return (
        f"---\n{frontmatter}\n---\n\n"
        "# Project Profile\n\n"
        "Perfil de classificacao do projeto para uso pelo motor AtlasFile.\n"
    )


def _initialize_project_if_needed(project_root: Path) -> tuple[dict[str, Any], bool]:
    profile_path = project_root / "_PROJECT_PROFILE.md"
    created = False
    if profile_path.exists():
        profile = load_project_profile(project_root)
    else:
        profile = _build_default_profile(project_root)
        profile_path.write_text(_render_profile_markdown(profile), encoding="utf-8")
        created = True
    ensure_project_structure(project_root, profile)
    return profile, created


def _count_rows_to_process(valid_projects: list[tuple[Path, str]]) -> int:
    from .reconcile import _is_ignored_file, _parse_index_rows

    total = 0
    for project_root, _ in valid_projects:
        for row in _parse_index_rows(project_root / "_INDEX.md"):
            if row["decision"] not in {"auto", "approved", "corrected"}:
                continue
            p = Path(row["path"])
            if not p.exists() or not p.is_file():
                continue
            if _is_ignored_file(p):
                continue
            total += 1
    return total


def _run_reconcile(project_roots: list[Path], *, reindex_search: bool, reindex_mode: str = "full") -> dict[str, Any]:
    started_at = utc_now_iso()
    started_ts = time.time()
    with _reconcile_lock:
        _reconcile_status["running"] = True
        _reconcile_status["phase"] = "search_index" if reindex_search else "reconcile_index"
        _reconcile_status["progress_current"] = 0
        _reconcile_status["progress_total"] = 0
        _reconcile_status["progress_file"] = None
        _reconcile_status["progress_project"] = None
        _reconcile_status["progress_skipped"] = 0
        _reconcile_status["progress_file_pct"] = 0
        _reconcile_status["last_failure_message"] = None
        _reconcile_status["last_failed_doc_id"] = None

        project_reports: list[dict[str, Any]] = []
        valid_roots: list[Path] = []
        valid_projects: list[tuple[Path, str]] = []
        skipped: list[dict[str, str]] = []
        for root in project_roots:
            try:
                profile = load_project_profile(root)
            except Exception as exc:
                skipped.append({"project_root": str(root), "reason": str(exc)})
                continue
            ensure_project_structure(root, profile)
            project_reports.append(reconcile_project_index(root, profile))
            valid_roots.append(root)
            valid_projects.append((root, str(profile.get("project_id", root.name))))

        progress_total = _count_rows_to_process(valid_projects) if reindex_search else 0
        _reconcile_status["progress_total"] = progress_total

        search_report = {"indexed_docs": 0, "deleted_docs": 0, "skipped_docs": 0}
        if reindex_search:
            if reindex_mode == "incremental":
                indexed_docs = 0
                deleted_docs = 0
                skipped_docs = 0
                failed_docs = 0
                for root, project_id in valid_projects:
                    _reconcile_status["progress_project"] = project_id
                    report = sync_search_index_for_project(
                        os_client, root, project_id, progress=_reconcile_status
                    )
                    indexed_docs += int(report.get("indexed_docs", 0))
                    deleted_docs += int(report.get("deleted_docs", 0))
                    skipped_docs += int(report.get("skipped_docs", 0))
                    failed_docs += int(report.get("failed_docs", 0))
                search_report = {
                    "indexed_docs": indexed_docs,
                    "deleted_docs": deleted_docs,
                    "skipped_docs": skipped_docs,
                    "failed_docs": failed_docs,
                }
            else:
                search_report = rebuild_search_index(
                    os_client, valid_roots, project_ids=valid_projects, progress=_reconcile_status
                )

        finished_at = utc_now_iso()
        duration_seconds = round(time.time() - started_ts, 3)
        summary = {
            "project_count": len(project_reports),
            "skipped_count": len(skipped),
            "rows_written": sum(int(r.get("rows_written", 0)) for r in project_reports),
            "added_rows": sum(int(r.get("added_rows", 0)) for r in project_reports),
            "removed_rows": sum(int(r.get("removed_rows", 0)) for r in project_reports),
            "adjustments_applied": sum(int(r.get("adjustments_applied", 0)) for r in project_reports),
            "indexed_docs": int(search_report.get("indexed_docs", 0)),
            "skipped_docs": int(search_report.get("skipped_docs", 0)),
            "failed_docs": int(search_report.get("failed_docs", 0)),
        }
        report = {
            "projects": project_reports,
            "skipped_projects": skipped,
            "search": search_report,
            "summary": summary,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration_seconds,
        }
        _reconcile_status.update(
            {
                "last_run_started_at": started_at,
                "last_run_finished_at": finished_at,
                "duration_seconds": duration_seconds,
                "summary": summary,
                "running": False,
                "phase": "idle",
                "progress_current": _reconcile_status.get("progress_current", 0),
                "progress_total": _reconcile_status.get("progress_total", 0),
                "progress_file": None,
                "progress_project": None,
                "progress_skipped": _reconcile_status.get("progress_skipped", 0),
            }
        )
        return report


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
                # Keep service running even if one reconcile cycle fails.
                continue

    thread = threading.Thread(target=loop, name="atlasfile-auto-reconcile", daemon=True)
    thread.start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
def get_projects() -> list[dict[str, Any]]:
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
def initialize_project(project_ref: str) -> dict[str, Any]:
    project_root = _resolve_project_root(project_ref)
    profile, created = _initialize_project_if_needed(project_root)
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


@app.get("/api/projects/{project_ref}/areas")
def get_project_areas(project_ref: str) -> dict[str, Any]:
    project_root = _resolve_project_root(project_ref)
    profile, _ = _initialize_project_if_needed(project_root)
    areas: list[dict[str, str]] = []
    for area in profile.get("work_areas", []):
        key = str(area.get("key", "")).strip()
        if not key:
            continue
        label = str(area.get("label") or key.replace("_", " ").strip().title())
        areas.append({"key": key, "label": label})
    return {
        "project_id": profile.get("project_id", project_root.name),
        "areas": areas,
    }


@app.get("/api/reconcile/status")
def get_reconcile_status() -> dict[str, Any]:
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
async def stream_reconcile_status() -> StreamingResponse:
    """Server-Sent Events: stream do status de reconcile ate running === false."""
    return StreamingResponse(
        _stream_reconcile_status(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _run_reconcile_background(project_roots: list[Path], reindex_search: bool, reindex_mode: str) -> None:
    try:
        _run_reconcile(project_roots, reindex_search=reindex_search, reindex_mode=reindex_mode)
    except Exception:
        _reconcile_status["running"] = False
        _reconcile_status["phase"] = "idle"
        raise


@app.post("/api/reconcile/{project_id}")
def reconcile_project(project_id: str, reindex_search: bool = True):
    if _reconcile_status.get("running"):
        raise HTTPException(status_code=409, detail="Reconcile already in progress")
    project_root = _resolve_project_root(project_id)
    thread = threading.Thread(
        target=_run_reconcile_background,
        args=([project_root], reindex_search, "incremental"),
        name="atlasfile-reconcile-project",
        daemon=True,
    )
    thread.start()
    return JSONResponse(status_code=202, content={"status": "started", "message": "Reconcile started"})


@app.post("/api/reconcile")
def reconcile_all_projects(reindex_search: bool = True):
    if _reconcile_status.get("running"):
        raise HTTPException(status_code=409, detail="Reconcile already in progress")
    roots = list_project_roots(Path(settings.projects_root))
    thread = threading.Thread(
        target=_run_reconcile_background,
        args=(roots, reindex_search, "full"),
        name="atlasfile-reconcile-all",
        daemon=True,
    )
    thread.start()
    return JSONResponse(status_code=202, content={"status": "started", "message": "Reconcile started"})


@app.post("/api/ingest/scan/{project_id}")
def scan_project_inbox(project_id: str) -> dict[str, Any]:
    project_root = _resolve_project_root(project_id)
    profile, _ = _initialize_project_if_needed(project_root)
    inbox = project_root / profile.get("inbox_path", "_INBOX_DROP")
    inbox.mkdir(parents=True, exist_ok=True)

    processed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for f in sorted(inbox.iterdir(), key=lambda p: p.name.lower()):
        if not f.is_file() or f.name.startswith("."):
            continue
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

    return {
        "project_id": project_id,
        "processed_count": len(processed),
        "failed_count": len(failed),
        "items": processed,
        "errors": failed,
    }


@app.get("/api/files/download")
def download_file(path: str = Query(..., description="Caminho do arquivo dentro do projects root")) -> FileResponse:
    """Serve o arquivo para abrir no app associado à extensão (inline)."""
    base = Path(settings.projects_root).resolve()
    requested = Path(path).resolve()
    try:
        requested.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Caminho fora do diretorio de projetos")
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    media_type, _ = mimetypes.guess_type(str(requested), strict=False)
    return FileResponse(
        path=str(requested),
        filename=requested.name,
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{requested.name}"'},
    )


@app.get("/api/triage/{project_id}")
def get_triage(project_id: str) -> list[dict[str, Any]]:
    project_root = _resolve_project_root(project_id)
    ensure_triage_dirs(project_root)
    return [item.model_dump() for item in list_pending(project_root)]


@app.post("/api/triage/{project_id}/{doc_id}/decision")
def decide_triage(project_id: str, doc_id: str, request: TriageDecisionRequest) -> dict[str, Any]:
    project_root = _resolve_project_root(project_id)
    profile = load_project_profile(project_root)
    ensure_project_structure(project_root, profile)

    pending_meta = triage_pending_dir(project_root) / f"{doc_id}.json"
    if not pending_meta.exists():
        raise HTTPException(status_code=404, detail=f"Triage item nao encontrado: {doc_id}")

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
        data["source_path"] = str(dest)
        pending_meta.unlink(missing_ok=True)
        (rejected_dir / f"{doc_id}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"status": "ok", "action": "rejected", "doc_id": doc_id}

    # approve or correct
    target_area = data.get("suggested_area")
    if action == "correct":
        if not request.target_area:
            raise HTTPException(status_code=400, detail="target_area obrigatorio para correct")
        target_area = request.target_area

    if not target_area:
        raise HTTPException(status_code=400, detail="Area alvo nao definida para aprovacao/correcao")

    area_path = resolve_area_path(
        project_root=project_root,
        profile=profile,
        area_key=target_area,
        create_if_missing=True,
    )
    if not area_path:
        raise HTTPException(status_code=400, detail=f"Area invalida: {target_area}")

    canonical_filename = data.get("canonical_filename") or source_path.name
    dest_dir = project_root / area_path
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / canonical_filename
    shutil.move(str(source_path), str(dest_path))

    indexed_payload = {
        "doc_id": doc_id,
        "project_id": project_id,
        "area_key": target_area,
        "title": source_path.stem,
        "content": read_text_excerpt(dest_path),
        "original_filename": data.get("original_filename", source_path.name),
        "canonical_filename": canonical_filename,
        "path": str(dest_path),
        "source_channel": data.get("source_channel", ""),
        "source_ref": data.get("source_ref", ""),
        "sender": data.get("sender", ""),
        "received_at": data.get("received_at"),
        "ingested_at": data.get("ingested_at"),
        "processed_at": utc_now_iso(),
        "decision": "approved" if action == "approve" else "corrected",
        "confidence_score": float(data.get("confidence_score", 0.0)),
        "sha256": data.get("sha256", ""),
        "tags": [target_area],
    }
    index_document(os_client, indexed_payload)

    data["decision"] = indexed_payload["decision"]
    data["processed_at"] = indexed_payload["processed_at"]
    data["final_path"] = str(dest_path)
    data["area_key"] = target_area

    pending_meta.unlink(missing_ok=True)
    (triage_resolved_dir(project_root) / f"{doc_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"status": "ok", "action": indexed_payload["decision"], "doc_id": doc_id}


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=2),
    project_id: str | None = None,
    area_key: str | None = None,
    page: int = Query(1, ge=1),
    size: int | None = Query(None, ge=1, le=100),
) -> SearchResponse:
    page_size = size if size is not None else settings.search_page_size
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
            "content_chunks_text^2",
            "content",
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
            "original_filename_normalized^4",
            "canonical_filename_normalized^3",
            "content_chunks_normalized^2",
            "content_normalized",
        ],
        "fuzziness": "AUTO",
        "prefix_length": 1,
        "operator": "or",
    }
    if strict_mode:
        broad_match_raw["minimum_should_match"] = "75%"
        broad_match_normalized["minimum_should_match"] = "75%"
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
        {"match_phrase": {"content_chunks_normalized": {"query": normalized_q, "slop": 0, "boost": 12}}},
        {"match_phrase": {"content_chunks_normalized": {"query": normalized_q, "slop": 2, "boost": 8}}},
        {"match_phrase": {"content_normalized": {"query": normalized_q, "slop": 0, "boost": 8}}},
        {"match_phrase": {"title_normalized": {"query": normalized_q, "slop": 0, "boost": 6}}},
        {"match_phrase": {"original_filename_normalized": {"query": normalized_q, "slop": 0, "boost": 5}}},
        {"match_phrase": {"canonical_filename_normalized": {"query": normalized_q, "slop": 0, "boost": 4}}},
        {
            "nested": {
                "path": "content_chunks",
                "query": {
                    "bool": {
                        "should": [
                            {"match_phrase": {"content_chunks.text_normalized": {"query": normalized_q, "slop": 0}}},
                            {"match_phrase": {"content_chunks.text": {"query": q, "slop": 2}}},
                        ],
                        "minimum_should_match": 1,
                    }
                },
                "inner_hits": {
                    "name": "chunks",
                    "size": int(max(settings.search_inner_hits_size, settings.search_evidences_max_per_hit)),
                },
            }
        },
    ]
    if strict_mode:
        should.append(
            {
                "multi_match": {
                    "query": normalized_q,
                    "type": "best_fields",
                    "fields": [
                        "content_chunks_normalized^6",
                        "content_normalized^4",
                        "title_normalized^2",
                    ],
                    "operator": "and",
                    "boost": 10,
                }
            }
        )
    filters: list[dict[str, Any]] = []
    if project_id:
        filters.append({"term": {"project_id": project_id}})
    if area_key:
        filters.append({"term": {"area_key": area_key}})

    query = {"bool": {"should": should, "minimum_should_match": 2 if strict_mode else 1, "filter": filters}}
    from_ = max(0, (page - 1) * page_size)
    body = {
        "from": from_,
        "size": page_size,
        "query": query,
        "highlight": {
            "require_field_match": False,
            "order": "score",
            "fields": {
                "title": {},
                "content": {},
                "content_chunks_text": {},
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

    result = os_client.search(index=settings.opensearch_index, body=body)
    hits: list[SearchHit] = []
    for h in result["hits"]["hits"]:
        src = h["_source"]
        highlighted_by_field = h.get("highlight", {})
        highlights = _highlights_with_full_phrase_first(_ordered_highlights(highlighted_by_field, q), q)
        match_locations = _prioritize_locations(
            _extract_locations_from_chunk_text(str(src.get("content_chunks_text", "")), q)
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
                snippet = _build_evidence_snippet(raw_text, q)
                match_count = _count_query_occurrences_in_text(raw_text, q)
                if match_count <= 0:
                    match_count = max(1, snippet.lower().count("<em>"))
                evidences.append({"location": loc, "snippet": snippet, "match_count": match_count})
            evidences.sort(key=lambda e: _evidence_location_sort_key(e.get("location", "")))
            max_ev = settings.search_evidences_max_per_hit
            omitted_evidences = max(0, total_evidences - min(len(evidences), max_ev))
            evidences = evidences[:max_ev]
        hits.append(
            SearchHit(
                doc_id=src["doc_id"],
                project_id=src["project_id"],
                area_key=src["area_key"],
                original_filename=src["original_filename"],
                canonical_filename=src["canonical_filename"],
                path=src["path"],
                score=float(h.get("_score", 0.0)),
                highlights=highlights,
                match_locations=match_locations,
                evidences=evidences,
                total_evidences=total_evidences,
                omitted_evidences=omitted_evidences,
                content_type=src.get("content_type"),
            )
        )
    total = result["hits"]["total"]["value"] if isinstance(result["hits"]["total"], dict) else int(result["hits"]["total"])
    total_pages = max(1, (total + page_size - 1) // page_size)
    hits.sort(key=lambda h: (-h.total_evidences, -h.score))
    return SearchResponse(total=total, page=page, page_size=page_size, total_pages=total_pages, hits=hits)


@app.get("/api/search/suggest", response_model=SuggestResponse)
def suggest(
    q: str = Query(..., min_length=3),
    project_id: str | None = None,
    size: int | None = None,
) -> SuggestResponse:
    suggest_size = size if size is not None else settings.suggest_size
    filters: list[dict[str, Any]] = []
    if project_id:
        filters.append({"term": {"project_id": project_id}})

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
                                "original_filename_normalized^2",
                                "canonical_filename_normalized",
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
                            "fields": ["title^3", "content_chunks_text^2", "content", "tags^2"],
                            "fuzziness": "AUTO",
                            "prefix_length": 1,
                            "operator": "or",
                        }
                    },
                    {"match_phrase_prefix": {"title_normalized": {"query": _normalize_query_text(q)}}},
                    {"match_phrase_prefix": {"original_filename_normalized": {"query": _normalize_query_text(q)}}},
                    {"match_phrase_prefix": {"canonical_filename_normalized": {"query": _normalize_query_text(q)}}},
                    {"match_phrase_prefix": {"content_chunks_normalized": {"query": _normalize_query_text(q)}}},
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
            "content_chunks_text",
            "content_type",
        ],
        "highlight": {
            "fields": {
                "title": {},
                "original_filename_text": {},
                "canonical_filename_text": {},
                "content_chunks_text": {},
            },
            "fragment_size": settings.suggest_highlight_fragment_size,
            "number_of_fragments": settings.suggest_highlight_number_of_fragments,
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        },
    }

    result = os_client.search(index=settings.opensearch_index, body=body)
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
            elif q_norm and q_norm in _normalize_query_text(str(src.get("content_chunks_text", ""))):
                matched_in.append("content_chunk")
        matched_in = _prioritize_locations(matched_in)
        original_filename = src.get("original_filename", "")
        canonical_filename = src.get("canonical_filename", "")
        confidence = _autocomplete_confidence(
            q,
            src.get("title", ""),
            original_filename,
            canonical_filename,
            src.get("content_chunks_text", ""),
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
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    durations_ms: list[float] = []

    for term in q:
        started = time.perf_counter()
        response = search(q=term, project_id=project_id, area_key=None, size=size)
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
