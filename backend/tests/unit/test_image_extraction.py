"""OCR real de imagens soltas + proteção sem-texto na classificação.

Estes testes usam o Tesseract de verdade (mesmo motor do PDF escaneado):
uma imagem gerada com texto legível deve produzir texto via OCR; uma imagem
em branco deve produzir vazio — e a ingestão não pode fabricar sugestão.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.document_extractor import extract_document_content

_HAS_TESSERACT = shutil.which("tesseract") is not None


def _make_text_image(path: Path, text: str) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 200), "white")
    draw = ImageDraw.Draw(img)
    # Fonte default em tamanho grande o suficiente para o OCR ler sem ambiguidade
    draw.text((20, 60), text, fill="black", font_size=48)
    img.save(path)


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract não instalado no host")
def test_ocr_real_extrai_texto_de_imagem(tmp_path: Path) -> None:
    img_path = tmp_path / "contrato_escaneado.png"
    _make_text_image(img_path, "CONTRATO DE PRESTACAO")
    result = extract_document_content(img_path)
    assert result.content_type == "image"
    assert result.extraction_status == "ok_ocr"
    assert "CONTRATO" in result.text_excerpt.upper()
    assert result.chunks, "texto OCR deve gerar chunks indexáveis"


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract não instalado no host")
def test_imagem_sem_texto_produz_vazio_sem_erro(tmp_path: Path) -> None:
    from PIL import Image

    img_path = tmp_path / "foto_sem_texto.jpg"
    Image.new("RGB", (400, 300), "white").save(img_path)
    result = extract_document_content(img_path)
    assert result.content_type == "image"
    assert result.extraction_status == "no_text"
    assert result.text_excerpt == ""


def test_extensao_de_imagem_nao_e_mais_unsupported(tmp_path: Path) -> None:
    """Mesmo sem tesseract, .jpg entra no caminho de imagem (não 'unsupported')."""
    from PIL import Image

    img_path = tmp_path / "qualquer.jpg"
    Image.new("RGB", (10, 10), "white").save(img_path)
    result = extract_document_content(img_path)
    assert result.content_type == "image"
