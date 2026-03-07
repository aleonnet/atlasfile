"""
MCP Server for AtlasFile. Exposes tools for document search, get, tags, metadata, review.
Run: python -m app.mcp.server (or uv run python -m app.mcp.server)
Uses ATLASFILE_API_BASE (default http://localhost:8000) to call the backend.
Host/port for streamable-http: via FastMCP settings (env FASTMCP_HOST, FASTMCP_PORT) or defaults below.
"""
from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .api_client import get, patch, post

# host/port vêm de Settings (env FASTMCP_* ou defaults). run() não aceita host/port.
mcp = FastMCP(
    "AtlasFile MCP",
    json_response=True,
    host=os.environ.get("FASTMCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("FASTMCP_PORT", "8001")),
)


@mcp.tool()
def list_documents(
    project_id: str | None = None,
    doc_kind: str | None = None,
    document_type: str | None = None,
    area_key: str | None = None,
    page: int = 1,
    size: int = 20,
) -> str:
    """List/browse documents with optional filters (no text search required). Returns doc_id, title, filename, project_id, doc_kind, document_type, area_key, tags, ingested_at for each document. Use to enumerate documents in a project or browse by type/area. For text search use search_documents instead."""
    params: dict[str, Any] = {"page": page, "size": size}
    if project_id:
        params["project_id"] = project_id
    if doc_kind:
        params["doc_kind"] = doc_kind
    if document_type:
        params["document_type"] = document_type
    if area_key:
        params["area_key"] = area_key
    data = get("/api/documents", params=params)
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def search_documents(
    query: str,
    project_id: str | None = None,
    area_key: str | None = None,
    document_type: str | None = None,
    doc_kind: str | None = None,
    tags: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    size: int = 20,
) -> str:
    """Search documents by full-text query with optional filters: project_id, area_key, document_type, doc_kind (pdf, docx, xlsx, pptx, plain_text, html, msg, archive_listing), tags, date_from, date_to (ISO dates). Returns JSON with total, page, and hits (doc_id, title, path, score, highlights, evidences)."""
    if len(query.strip()) < 2:
        return json.dumps(
            {"error": "query must have at least 2 characters. Use list_documents to browse without a text query."},
            ensure_ascii=False,
        )
    params: dict[str, Any] = {"q": query, "page": page, "size": size}
    if project_id:
        params["project_id"] = project_id
    if area_key:
        params["area_key"] = area_key
    if document_type:
        params["document_type"] = document_type
    if doc_kind:
        params["doc_kind"] = doc_kind
    if tags:
        params["tags"] = tags
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    data = get("/api/search", params=params)
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def get_stats(project_id: str | None = None) -> str:
    """Get document statistics and counts. Returns total_documents and breakdowns by doc_kind (pdf, docx, xlsx, pptx, plain_text...), area_key, document_type, extension, and tags. Each breakdown has key and count. Use this to answer quantity questions like 'how many PDFs?' or 'document distribution by area'."""
    params: dict[str, Any] = {}
    if project_id:
        params["project_id"] = project_id
    data = get("/api/stats", params=params or None)
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def get_document(doc_id: str) -> str:
    """Get a document by doc_id. Returns metadata, content excerpt, and content_chunks (location + text) for evidence. For long documents the response may be truncated to fit the model context; when so, the JSON includes _truncated: true, _total_chunks, _returned_chunks, and _message explaining the truncation. Prefer search_documents with specific terms to retrieve targeted excerpts from very long documents."""
    data = get(f"/api/documents/{doc_id}")
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def get_document_chunks(doc_id: str, locations: list[str]) -> str:
    """Return only the requested chunks of a document. Pass doc_id and a list of chunk locations (e.g. from search_documents match_locations or evidences[].location). Returns JSON with document metadata and content_chunks containing only those locations (location + text). Use this after search_documents to get the full text of matched chunks without loading the full document."""
    if not locations:
        return json.dumps({"error": "locations must contain at least one chunk location"}, ensure_ascii=False)
    # httpx serializes list as repeated query params: ?locations=a&locations=b
    params: dict[str, Any] = {"locations": [loc for loc in locations if (loc or "").strip()]}
    if not params["locations"]:
        return json.dumps({"error": "locations must contain at least one non-empty chunk location"}, ensure_ascii=False)
    data = get(f"/api/documents/{doc_id}/chunks", params=params)
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def apply_tags(
    doc_id: str,
    tags_to_add: list[str],
    tags_to_remove: list[str] | None = None,
) -> str:
    """Add and/or remove tags for a document. Idempotent."""
    payload: dict[str, Any] = {"add": tags_to_add}
    if tags_to_remove:
        payload["remove"] = tags_to_remove
    data = post(f"/api/documents/{doc_id}/tags", json=payload)
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def set_metadata(
    doc_id: str,
    document_type: str | None = None,
    correspondent: str | None = None,
    area_key: str | None = None,
    review_status: str | None = None,
) -> str:
    """Update document metadata: document_type, correspondent, area_key, review_status. Pass only fields to update."""
    payload: dict[str, Any] = {}
    if document_type is not None:
        payload["document_type"] = document_type
    if correspondent is not None:
        payload["correspondent"] = correspondent
    if area_key is not None:
        payload["area_key"] = area_key
    if review_status is not None:
        payload["review_status"] = review_status
    if not payload:
        return json.dumps({"status": "ok", "doc_id": doc_id})
    data = patch(f"/api/documents/{doc_id}", payload)
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def list_tags(project_id: str | None = None) -> str:
    """List all unique tags in the index, optionally filtered by project_id."""
    params = {}
    if project_id:
        params["project_id"] = project_id
    data = get("/api/tags", params=params if params else None)
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def create_review_marker(doc_id: str, kind: str = "legal_review") -> str:
    """Mark a document for review: applies tag REVIEW_LEGAL or REVIEW_FINANCE or REVIEW_REQUIRED and sets review_status. kind: legal_review | finance_review | needs_review."""
    tag_map = {
        "legal_review": "REVIEW_LEGAL",
        "finance_review": "REVIEW_FINANCE",
        "needs_review": "REVIEW_REQUIRED",
    }
    tag = tag_map.get(kind, "REVIEW_REQUIRED")
    post(f"/api/documents/{doc_id}/tags", json={"add": [tag]})
    patch(f"/api/documents/{doc_id}", {"review_status": kind})
    return json.dumps({"status": "ok", "doc_id": doc_id, "tag": tag, "review_status": kind})


@mcp.tool()
def submit_classification(
    document_type: str | None = None,
    tags: list[str] | None = None,
    confidence: float = 0.0,
    area_key: str | None = None,
    topics: list[str] | None = None,
    explanation: str | None = None,
) -> str:
    """Used by the classification flow only: submit suggested metadata for ingest policy."""
    return json.dumps({
        "status": "ok",
        "document_type": document_type,
        "tags": tags or [],
        "confidence": confidence,
        "area_key": area_key,
        "topics": topics or [],
        "explanation": explanation,
    })


def run_server() -> None:
    """Run MCP server with streamable HTTP transport. Host/port via mcp.settings (FASTMCP_HOST/FASTMCP_PORT)."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    run_server()
