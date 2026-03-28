"""Parsing espacial via pymupdf — equivalente Python do PDF.js usado pelo LiteParse.

Reconstroi layout 2D usando bounding boxes de cada span de texto,
agrupando por linhas (coordenada Y) e preservando alinhamento de colunas
via padding com espacos.
"""

from __future__ import annotations

import math
from pathlib import Path

import pymupdf

from .base import BaseProvider, PageResult

OCR_MIN_CHARS = 50
OCR_DPI = 150
OCR_LANG = "por+eng"

# Spans com diferenca vertical menor que este limiar (em pontos)
# sao considerados na mesma linha.
LINE_TOLERANCE_PT = 3.0

# Largura de um caractere "medio" para calcular padding de colunas.
CHAR_WIDTH_PT = 6.0


def _ocr_page_image(pdf_path: Path, page_number_0based: int) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        return ""
    try:
        images = convert_from_path(
            str(pdf_path),
            first_page=page_number_0based + 1,
            last_page=page_number_0based + 1,
            dpi=OCR_DPI,
        )
        if not images:
            return ""
        return (pytesseract.image_to_string(images[0], lang=OCR_LANG) or "").strip()
    except Exception:
        return ""


def _spatial_extract_page(page: pymupdf.Page) -> str:
    """Extrai texto de uma pagina preservando layout espacial via bounding boxes."""
    data = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    spans: list[dict] = []

    for block in data.get("blocks", []):
        if block.get("type") != 0:  # text block only
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = (span.get("text") or "").strip()
                if not text:
                    continue
                bbox = span.get("bbox", (0, 0, 0, 0))
                spans.append({
                    "text": text,
                    "x0": bbox[0],
                    "y0": bbox[1],
                    "x1": bbox[2],
                    "y1": bbox[3],
                })

    if not spans:
        return ""

    # Agrupar spans em linhas por proximidade vertical (centro Y).
    spans.sort(key=lambda s: (s["y0"], s["x0"]))

    lines: list[list[dict]] = []
    current_line: list[dict] = []
    current_y = -999.0

    for span in spans:
        center_y = (span["y0"] + span["y1"]) / 2
        if current_line and abs(center_y - current_y) > LINE_TOLERANCE_PT:
            lines.append(current_line)
            current_line = []
        current_line.append(span)
        # Media ponderada do centro Y para a linha corrente.
        current_y = sum((s["y0"] + s["y1"]) / 2 for s in current_line) / len(current_line)

    if current_line:
        lines.append(current_line)

    # Reconstruir texto com alinhamento espacial.
    page_width = page.rect.width or 612  # fallback letter size
    output_lines: list[str] = []

    for line_spans in lines:
        line_spans.sort(key=lambda s: s["x0"])
        chars: list[str] = []
        cursor_x = 0.0

        for span in line_spans:
            # Calcular quantos espacos inserir para alinhar a coluna.
            gap_pts = span["x0"] - cursor_x
            if gap_pts > CHAR_WIDTH_PT * 1.5:
                num_spaces = max(1, math.floor(gap_pts / CHAR_WIDTH_PT))
                chars.append(" " * num_spaces)
            elif chars:
                # Garantir pelo menos um espaco entre spans adjacentes.
                chars.append(" ")

            chars.append(span["text"])
            cursor_x = span["x1"]

        output_lines.append("".join(chars))

    return "\n".join(output_lines)


class PyMuPDFSpatialProvider(BaseProvider):
    name = "pymupdf_spatial"

    def extract(self, path: Path, max_pages: int | None = None) -> list[PageResult]:
        doc = pymupdf.open(str(path))
        results: list[PageResult] = []

        page_count = len(doc)
        limit = page_count if max_pages is None else min(max_pages, page_count)

        for idx in range(limit):
            page = doc[idx]
            text = _spatial_extract_page(page)
            method = "spatial"

            if len(text.strip()) < OCR_MIN_CHARS:
                ocr_text = _ocr_page_image(path, idx)
                if ocr_text:
                    text = ocr_text
                    method = "ocr"

            if text.strip():
                results.append(PageResult(page_number=idx + 1, text=text, method=method))

        doc.close()
        return results
