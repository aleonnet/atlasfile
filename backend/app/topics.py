from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .utils import normalize_text

_TOPICS_CACHE_BY_PATH: dict[str, dict[str, Any]] = {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_topics_path() -> Path:
    return _repo_root() / "config" / "topics_v1.yaml"


def _plan_topics_path() -> Path:
    return _repo_root() / "docs" / "plano_profile" / "topics_v1.yaml"


def resolve_topics_path(profile: Any | None) -> Path:
    env_path = os.environ.get("ATLASFILE_TOPICS_V1_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        return p if p.is_absolute() else (_repo_root() / p)

    topics_path = None
    try:
        topics_path = getattr(getattr(profile, "indexing", None), "topics_path", None)
    except Exception:
        topics_path = None
    if not topics_path and isinstance(profile, dict):
        topics_path = (profile.get("indexing") or {}).get("topics_path")

    if isinstance(topics_path, str) and topics_path.strip():
        p = Path(topics_path.strip())
        resolved = p if p.is_absolute() else (_repo_root() / p)
        # Keep a single physical source in config/ while preserving old references.
        if resolved.resolve() == _plan_topics_path().resolve():
            return _default_topics_path()
        return resolved
    return _default_topics_path()


def _load_topics_config(profile: Any | None = None) -> dict[str, Any]:
    path = resolve_topics_path(profile)
    key = str(path.resolve())
    cached = _TOPICS_CACHE_BY_PATH.get(key)
    if cached is not None:
        return cached

    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    topics = cfg.get("topics") or []
    normalized_topics: list[dict[str, Any]] = []
    if isinstance(topics, list):
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            topic_key = str(topic.get("key", "")).strip()
            if not topic_key:
                continue
            surface_forms = topic.get("surface_forms") or topic.get("synonyms") or []
            if not isinstance(surface_forms, list):
                surface_forms = []
            normalized_topics.append(
                {
                    "key": topic_key,
                    "surface_forms_norm": [normalize_text(str(s).strip()) for s in surface_forms if str(s).strip()],
                }
            )

    cfg["_topics_norm"] = normalized_topics
    _TOPICS_CACHE_BY_PATH[key] = cfg
    return cfg


def get_topic_keys(profile: Any | None = None) -> list[str]:
    """Return the list of valid topic keys from the topics config."""
    cfg = _load_topics_config(profile)
    return [t["key"] for t in (cfg.get("_topics_norm") or []) if t.get("key")]


def match_topics(
    *,
    text: str,
    business_domain: str | None,
    profile: Any | None = None,
) -> tuple[list[str], str]:
    cfg = _load_topics_config(profile)
    topics_norm = cfg.get("_topics_norm") or []
    if not topics_norm:
        return ([], "none")

    text_norm = normalize_text(text or "")
    if not text_norm:
        return ([], "none")

    max_topics = 8
    mt = cfg.get("max_topics_per_document")
    if isinstance(mt, int) and 1 <= mt <= 50:
        max_topics = mt

    def hit(syn: str) -> int:
        if not syn:
            return 0
        if len(syn) <= 4:
            return 1 if re.search(rf"(^|[^a-z0-9]){re.escape(syn)}([^a-z0-9]|$)", text_norm) else 0
        return 1 if syn in text_norm else 0

    scored: list[tuple[int, str]] = []
    for t in topics_norm:
        score = 0
        for syn in t.get("surface_forms_norm") or []:
            score += hit(syn)
        if score <= 0:
            continue
        scored.append((score, t["key"]))

    scored.sort(key=lambda x: (-x[0], x[1]))
    keys = [k for _, k in scored[:max_topics]]
    return (keys, "surface_form_match")

