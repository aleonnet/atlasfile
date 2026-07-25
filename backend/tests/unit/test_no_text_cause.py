"""Causa REAL de "sem texto extraível" (v0.52.0).

Antes: a triagem mostrava sempre "(OCR vazio)" — genérico e às vezes falso (o
OCR podia nem ter rodado, ou o formato nem ter extrator). O `ExtractionResult`
já sabia a resposta; agora ela vira um código estável no meta da triagem e a
tradução vive no i18n.
"""
from __future__ import annotations

import pytest

from app.document_extractor import ExtractionResult
from app.ingestion import _no_text_cause


def _result(**kwargs) -> ExtractionResult:
    base = dict(
        text_excerpt="",
        chunk_text="",
        chunk_locations=[],
        chunks=[],
        content_type="docx",
        extraction_status="partial",
        metadata={},
    )
    base.update(kwargs)
    return ExtractionResult(**base)


@pytest.mark.parametrize(
    ("result", "esperado"),
    [
        # Office "envelope": o OCR rodou nas imagens embutidas e não achou texto
        (_result(metadata={"embedded_images_found": 1, "embedded_images_ocr": 0}), "only_embedded_image"),
        # Imagem solta sem texto
        (_result(content_type="image", extraction_status="no_text"), "image_without_text"),
        # PDF escaneado que o OCR não leu
        (_result(content_type="pdf"), "scan_unreadable"),
        # Tesseract ausente no servidor — não é "OCR vazio", é OCR que não rodou
        (_result(content_type="image", extraction_status="ocr_unavailable"), "ocr_unavailable"),
        (_result(metadata={"embedded_images_ocr_status": "ocr_unavailable"}), "ocr_unavailable"),
        # Formato sem extrator
        (_result(content_type="unsupported", extraction_status="unsupported"), "unsupported_format"),
        # Arquivo ilegível/corrompido
        (_result(content_type="error", extraction_status="error", metadata={"error": "boom"}), "extraction_error"),
        # Documento de texto genuinamente vazio
        (_result(content_type="plain_text"), "empty_document"),
    ],
)
def test_causa_derivada_do_resultado_da_extracao(result: ExtractionResult, esperado: str) -> None:
    assert _no_text_cause(result) == esperado


def test_ocr_indisponivel_tem_precedencia_sobre_imagem_embutida() -> None:
    """Com o OCR fora do ar, dizer "só imagem embutida" mentiria sobre a causa:
    o que impediu o texto foi o motor ausente."""
    result = _result(metadata={"embedded_images_found": 3, "embedded_images_ocr_status": "ocr_unavailable"})
    assert _no_text_cause(result) == "ocr_unavailable"
