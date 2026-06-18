"""Tipos compartilhados dos extratores (whole-document, multi-formato).

Diferente do benchmark page-scoped em ../extractor-benchmark, aqui cada extrator
processa o documento inteiro e devolve um unico texto/markdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractResult:
    tool: str  # "atlasfile" | "markitdown"
    text: str  # texto/markdown completo extraido
    status: str  # "ok" | "error"
    error: str | None = None
    latency_ms: float = 0.0
    peak_memory_mb: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)
