"""Prova o caminho REAL de OCR de PDF — sem monkeypatch.

Até a v0.57.0 o OCR de PDF nunca foi exercido em bancada: o único teste do
fluxo (test_document_extractor.py::test_extract_pdf_ocr_fallback_called)
substitui _ocr_pdf_page por stub. Este teste fecha o buraco com a fixture
sintética de tests/fixtures/ocr/ (proveniência no gerador ao lado dela):
PDF de 1 página só-imagem, que _extract_pdf só consegue ler via
pdf2image (poppler) + tesseract de verdade.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.document_extractor import extract_document_content

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "ocr"
    / "Relatório Escaneado — Prova de OCR.pdf"
)
_HAS_TESSERACT = shutil.which("tesseract") is not None
# pdf2image usa o pdftoppm do poppler; sem ele o OCR devolve "" silencioso.
_HAS_POPPLER = shutil.which("pdftoppm") is not None


def test_fixture_continua_sem_camada_de_texto() -> None:
    """Âncora da fixture: se alguém regenerá-la COM camada de texto, o teste
    de OCR abaixo passaria sem exercer o OCR — este aqui reprova antes."""
    import pymupdf

    doc = pymupdf.open(str(_FIXTURE))
    try:
        assert len(doc) == 1
        assert doc[0].get_text().strip() == ""
    finally:
        doc.close()


@pytest.mark.skipif(
    not (_HAS_TESSERACT and _HAS_POPPLER),
    reason="tesseract e/ou poppler (pdftoppm) não instalados no host",
)
def test_pdf_escaneado_extrai_pela_via_de_ocr() -> None:
    result = extract_document_content(_FIXTURE)
    assert result.content_type == "pdf"
    assert result.extraction_status == "ok"
    texto = " ".join(result.chunk_text.upper().split())
    assert "SENTINELA QUARENTA E DOIS" in texto
    assert result.chunk_locations, "OCR deveria produzir chunks de página"
