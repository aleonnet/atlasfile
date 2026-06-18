"""Wrapper do extrator real de producao do AtlasFile.

Importa `extract_document_content` de `backend/app/document_extractor.py` adicionando
o diretorio do backend ao sys.path (mesmo padrao usado por backend/scripts/label_corpus_llm.py).
O OCR de PDF liga sozinho via app.config.settings (default pdf_ocr_enabled=True), usando
tesseract/poppler do sistema.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

NAME = "atlasfile"

# .../extractor-benchmark_mdxaf/extractors/atlasfile_extractor.py
#   parents[2] == raiz do repo AtlasFile
_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def run(path: Path, max_chars: int | None = None) -> dict[str, Any]:
    """Extrai um documento com o extrator do AtlasFile.

    Retorna {"text", "status", "error", "meta"}. O timing e medido pelo chamador.
    """
    from app.document_extractor import extract_document_content

    try:
        result = extract_document_content(path, max_chars=max_chars)
    except Exception as exc:  # noqa: BLE001 — qualquer falha vira status de erro
        return {"text": "", "status": "error", "error": repr(exc), "meta": {}}

    meta = {
        "content_type": result.content_type,
        "extraction_status": result.extraction_status,
        "n_chunks": len(result.chunks),
    }
    # metadata especifico por formato (pages, sheets, paragraphs, etc.)
    if isinstance(result.metadata, dict):
        for key in ("extension", "pages", "sheets", "paragraphs",
                    "docx_pages_detected", "slides", "error"):
            if key in result.metadata:
                meta[key] = result.metadata[key]

    status = "error" if result.extraction_status in ("error", "unsupported") else "ok"
    return {
        "text": result.chunk_text or "",
        "status": status,
        "error": result.metadata.get("error") if isinstance(result.metadata, dict) else None,
        "meta": meta,
    }
