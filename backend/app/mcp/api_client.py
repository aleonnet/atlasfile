"""HTTP client to call AtlasFile backend API. Used by MCP tool handlers."""
from __future__ import annotations

import os
from typing import Any

import httpx

ATLASFILE_API_BASE = os.environ.get("ATLASFILE_API_BASE", "http://localhost:8000")
API_TOKEN = os.environ.get("ATLASFILE_API_TOKEN", "")


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json", "Content-Type": "application/json"}
    if API_TOKEN:
        h["Authorization"] = f"Bearer {API_TOKEN}"
    return h


def _url(path: str) -> str:
    base = ATLASFILE_API_BASE.rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{base}{p}"


def get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
    with httpx.Client(timeout=60.0) as client:
        r = client.get(_url(path), params=params or {}, headers=_headers())
        r.raise_for_status()
        return r.json()


def post(path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=60.0) as client:
        r = client.post(_url(path), json=json or {}, headers=_headers())
        r.raise_for_status()
        return r.json()


def patch(path: str, json: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=60.0) as client:
        r = client.patch(_url(path), json=json, headers=_headers())
        r.raise_for_status()
        return r.json()
