"""Gera a fixture "Relatório Escaneado — Prova de OCR.pdf" (PDF só-imagem).

Proveniência: arquivo SINTÉTICO, criado na Fase 3 do plano de distribuição
(2026-07-30) exclusivamente para provar o caminho real de OCR de PDF — na
bancada local (tests/unit/test_pdf_ocr_fixture.py) e no smoke de release
contra a imagem publicada (scripts/smoke-e2e.sh). Não contém dado real.

Técnica: PIL desenha parágrafos ASCII (mesma abordagem de
_make_paragraph_image em tests/unit/test_embedded_image_ocr.py) e pymupdf
monta um PDF de 1 página contendo APENAS a imagem — zero camada de texto,
obrigando _extract_pdf a cair no OCR (page_text < pdf_ocr_min_chars).

O texto embute a frase de controle "SENTINELA QUARENTA E DOIS" (4 tokens,
de propósito: ≥6 tokens ligariam o strict_mode da busca). ASCII puro para
não depender do modelo por/eng do tesseract; o acento fica no NOME do
arquivo, cobrindo multipart e filesystem.

Rodar de backend/:  .venv/bin/python tests/fixtures/ocr/gerar_pdf_escaneado.py
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

FIXTURE_NAME = "Relatório Escaneado — Prova de OCR.pdf"

# Linhas <= 75 chars: com font_size 40 (~22 px/char) cabem nos 1750 px de
# largura; a 150 dpi do _ocr_pdf_page a página renderiza ~2x, texto ~80 px.
LINES = [
    "RELATORIO DE VISTORIA TECNICA - DOCUMENTO DIGITALIZADO SEM CAMADA DE TEXTO",
    "Este arquivo e um PDF de imagem, gerado sinteticamente pela bancada do",
    "AtlasFile para provar o caminho completo de OCR do produto: extracao por",
    "tesseract, classificacao automatica e busca com destaque de trechos.",
    "FRASE DE CONTROLE DA PROVA: SENTINELA QUARENTA E DOIS",
    "A vistoria concluiu que os equipamentos do local operam normalmente e",
    "dentro dos parametros nominais registrados no laudo tecnico anterior.",
]


def _render_page_image(path: Path, lines: list[str]) -> None:
    # JPEG de propósito: o stream DCT entra as-is no PDF (PNG viraria raster
    # não-comprimido de ~4 MB); grayscale q85 fica ~100 KB e OCRiza limpo.
    img = Image.new("L", (1750, 120 + 90 * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((40, 60 + 90 * i), line, fill="black", font_size=40)
    img.save(path, format="JPEG", quality=85)


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    jpg = out_dir / "_pagina_escaneada.tmp.jpg"
    _render_page_image(jpg, LINES)
    with Image.open(jpg) as im:
        width, height = im.size
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(pymupdf.Rect(0, 0, width, height), filename=str(jpg))
    doc.save(str(out_dir / FIXTURE_NAME))
    doc.close()
    jpg.unlink()
    print(f"fixture gerada: {out_dir / FIXTURE_NAME}")


if __name__ == "__main__":
    main()
