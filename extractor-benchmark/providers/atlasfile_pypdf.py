"""Replica da logica de extracao PDF do AtlasFile (pypdf + Tesseract OCR)."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from .base import BaseProvider, PageResult

OCR_MIN_CHARS = 50
OCR_DPI = 150
OCR_LANG = "por+eng"


def _ocr_page(pdf_path: Path, page_number_1based: int) -> str:
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


class AtlasFilePyPDFProvider(BaseProvider):
    name = "atlasfile_pypdf"

    def extract(self, path: Path, max_pages: int | None = None) -> list[PageResult]:
        reader = PdfReader(str(path))
        results: list[PageResult] = []

        pages = reader.pages
        if max_pages is not None:
            pages = pages[:max_pages]

        for idx, page in enumerate(pages, start=1):
            text = (page.extract_text() or "").strip()
            method = "native"

            if len(text) < OCR_MIN_CHARS:
                ocr_text = _ocr_page(path, idx)
                if ocr_text:
                    text = ocr_text
                    method = "ocr"

            if text:
                results.append(PageResult(page_number=idx, text=text, method=method))

        return results
