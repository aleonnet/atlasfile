"""Gera ground truth para benchmark de extracao PDF.

Pipeline:
  PDF -> screenshot das N primeiras paginas (via pymupdf) -> Claude Vision -> QA pairs JSON

Uso:
  python scripts/generate_ground_truth.py --corpus-dir corpus/ --output-dir ground_truth/ --max-pages 5
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic
import pymupdf

DEFAULT_MAX_PAGES = 5
SCREENSHOT_DPI = 150
MODEL = "claude-sonnet-4-5-20250929"

VISION_PROMPT = """\
Analise esta pagina de documento e gere de 3 a 5 pares pergunta/resposta (QA pairs) sobre o conteudo visivel.

Regras:
- As perguntas devem ser factuais e objetivas, respondidas exclusivamente pelo conteudo visivel na pagina.
- As respostas devem ser curtas e precisas (valores, nomes, datas, etc).
- Priorize dados tabulares, numeros, nomes proprios e informacoes especificas.
- Se a pagina contem tabelas, pelo menos 2 perguntas devem ser sobre valores da tabela.
- Se a pagina tem pouco conteudo textual (ex: capa, pagina em branco), retorne um array vazio.

Responda APENAS com JSON valido no formato:
[
  {"q": "pergunta aqui", "a": "resposta aqui"},
  ...
]
"""


def _render_page_to_png(page: pymupdf.Page, dpi: int = SCREENSHOT_DPI) -> bytes:
    zoom = dpi / 72
    mat = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


def _encode_image_base64(png_bytes: bytes) -> str:
    return base64.standard_b64encode(png_bytes).decode("ascii")


def _doc_id(file_path: Path) -> str:
    rel = str(file_path)
    return hashlib.sha256(rel.encode()).hexdigest()[:16]


def _category_from_path(file_path: Path, corpus_dir: Path) -> str:
    try:
        relative = file_path.relative_to(corpus_dir)
        parts = relative.parts
        if len(parts) > 1:
            return parts[0]
    except ValueError:
        pass
    return "unknown"


def _generate_qa_pairs(client: anthropic.Anthropic, png_bytes: bytes) -> list[dict]:
    b64 = _encode_image_base64(png_bytes)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                },
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
    )

    text = response.content[0].text.strip()
    # Extrair JSON do response (pode vir com markdown fences).
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(json_lines)

    try:
        pairs = json.loads(text)
        if isinstance(pairs, list):
            return [p for p in pairs if isinstance(p, dict) and "q" in p and "a" in p]
    except json.JSONDecodeError:
        print(f"  [WARN] Falha ao parsear JSON do Claude: {text[:200]}", file=sys.stderr)
    return []


def process_pdf(
    client: anthropic.Anthropic,
    pdf_path: Path,
    corpus_dir: Path,
    max_pages: int,
) -> dict:
    doc = pymupdf.open(str(pdf_path))
    total_pages = len(doc)
    limit = min(max_pages, total_pages)

    pages_data = []
    for idx in range(limit):
        page = doc[idx]
        png_bytes = _render_page_to_png(page)
        print(f"  Pagina {idx + 1}/{limit} — gerando QA pairs...")

        qa_pairs = _generate_qa_pairs(client, png_bytes)
        if qa_pairs:
            pages_data.append({
                "page": idx + 1,
                "qa_pairs": qa_pairs,
            })
        # Rate limit: 1 segundo entre chamadas.
        time.sleep(1)

    doc.close()

    return {
        "file": str(pdf_path),
        "doc_id": _doc_id(pdf_path),
        "category": _category_from_path(pdf_path, corpus_dir),
        "total_pages": total_pages,
        "pages_processed": limit,
        "pages": pages_data,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera ground truth QA para benchmark PDF")
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    args = parser.parse_args()

    if not args.corpus_dir.exists():
        print(f"Corpus dir nao encontrado: {args.corpus_dir}", file=sys.stderr)
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(args.corpus_dir.rglob("*.pdf"))
    if not pdfs:
        print(f"Nenhum PDF encontrado em {args.corpus_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Encontrados {len(pdfs)} PDFs. Max {args.max_pages} paginas por documento.")
    client = anthropic.Anthropic()

    for i, pdf_path in enumerate(pdfs, start=1):
        print(f"\n[{i}/{len(pdfs)}] {pdf_path.name}")
        doc_id = _doc_id(pdf_path)
        output_file = args.output_dir / f"{doc_id}.json"

        if output_file.exists():
            print(f"  Ja existe ground truth, pulando.")
            continue

        result = process_pdf(client, pdf_path, args.corpus_dir, args.max_pages)
        total_qa = sum(len(p["qa_pairs"]) for p in result["pages"])
        print(f"  {len(result['pages'])} paginas com {total_qa} QA pairs total.")

        output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nGround truth salvo em {args.output_dir}/")


if __name__ == "__main__":
    main()
