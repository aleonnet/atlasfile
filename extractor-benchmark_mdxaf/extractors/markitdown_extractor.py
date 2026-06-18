"""Wrapper do MarkItDown (Microsoft) em modo vanilla.

Sem LLM captioning, sem Azure Document Intelligence, sem plugins. Comparacao do
parsing base. Importante: o MarkItDown NAO faz OCR de PDF por default — PDFs
escaneados/imagem virao quase vazios (vide README).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

NAME = "markitdown"


def _make_converter():
    from markitdown import MarkItDown

    # enable_plugins=False e o default em versoes recentes; passamos explicito,
    # com fallback para construtores mais antigos que nao aceitam o kwarg.
    try:
        return MarkItDown(enable_plugins=False)
    except TypeError:
        return MarkItDown()


def run(path: Path) -> dict[str, Any]:
    """Converte um documento para Markdown via MarkItDown vanilla.

    Retorna {"text", "status", "error", "meta"}. O timing e medido pelo chamador.
    """
    try:
        md = _make_converter()
        result = md.convert(str(path))
        text = result.text_content or ""
    except Exception as exc:  # noqa: BLE001
        return {"text": "", "status": "error", "error": repr(exc), "meta": {}}

    return {
        "text": text,
        "status": "ok" if text.strip() else "error",
        "error": None if text.strip() else "saida vazia (possivel PDF escaneado sem OCR)",
        "meta": {"extension": path.suffix.lower()},
    }
