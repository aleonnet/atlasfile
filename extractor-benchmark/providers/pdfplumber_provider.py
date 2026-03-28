"""Extracao via pdfplumber com layout preservado e deteccao de tabelas."""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from .base import BaseProvider, PageResult

OCR_MIN_CHARS = 50
OCR_DPI = 150
OCR_LANG = "por+eng"


def _ocr_page_image(pdf_path: Path, page_number_1based: int) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        return ""
    try:
        images = convert_from_path(
            str(pdf_path),
            first_page=page_number_1based,
            last_page=page_number_1based,
            dpi=OCR_DPI,
        )
        if not images:
            return ""
        return (pytesseract.image_to_string(images[0], lang=OCR_LANG) or "").strip()
    except Exception:
        return ""


def _format_table(table: list[list[str | None]]) -> str:
    """Formata tabela extraida como texto alinhado."""
    if not table:
        return ""
    # Limpar celulas None.
    clean = [[str(cell or "").strip() for cell in row] for row in table]
    if not clean:
        return ""
    # Calcular largura maxima por coluna.
    col_count = max(len(row) for row in clean)
    widths = [0] * col_count
    for row in clean:
        for i, cell in enumerate(row):
            if i < col_count:
                widths[i] = max(widths[i], len(cell))
    # Formatar linhas com padding.
    lines: list[str] = []
    for row in clean:
        parts = []
        for i in range(col_count):
            cell = row[i] if i < len(row) else ""
            parts.append(cell.ljust(widths[i]))
        lines.append("  ".join(parts).rstrip())
    return "\n".join(lines)


def _extract_page(page: pdfplumber.page.Page) -> str:
    """Extrai texto com layout preservado + tabelas estruturadas."""
    # Texto com layout espacial preservado.
    layout_text = (page.extract_text(layout=True) or "").strip()

    # Tabelas detectadas e formatadas.
    tables = page.extract_tables() or []
    table_texts = [_format_table(t) for t in tables if t]
    table_section = "\n\n".join(t for t in table_texts if t)

    # Se ha tabelas e texto, combinar. Se tabelas acrescentam informacao
    # que o layout_text ja contem (comum), o LLM-as-judge avaliara qual
    # output responde melhor as perguntas.
    if layout_text and table_section:
        return f"{layout_text}\n\n[TABLES]\n{table_section}"
    return layout_text or table_section


class PDFPlumberProvider(BaseProvider):
    name = "pdfplumber"

    def extract(self, path: Path, max_pages: int | None = None) -> list[PageResult]:
        results: list[PageResult] = []

        with pdfplumber.open(str(path)) as pdf:
            pages = pdf.pages
            if max_pages is not None:
                pages = pages[:max_pages]

            for page in pages:
                text = _extract_page(page)
                method = "table_aware"

                if len(text.strip()) < OCR_MIN_CHARS:
                    ocr_text = _ocr_page_image(path, page.page_number)
                    if ocr_text:
                        text = ocr_text
                        method = "ocr"

                if text.strip():
                    results.append(PageResult(
                        page_number=page.page_number,
                        text=text,
                        method=method,
                    ))

        return results
