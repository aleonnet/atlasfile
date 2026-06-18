"""Comparacao lado-a-lado: MarkItDown vanilla vs extrator do AtlasFile.

Para cada arquivo do corpus, roda os dois extratores, mede latencia (mediana de N
runs apos 1 warmup) e pico de memoria Python (tracemalloc), grava o texto/markdown
completo de cada um e calcula metricas objetivas deterministicas (sem LLM, sem custo
de API). Produz results/<run>/summary.json e summary.md para inspecao humana.

Uso:
  python scripts/run_compare.py --corpus-dir corpus/ --output-dir results/run1/ --runs 3

Padrao de medicao reaproveitado de ../extractor-benchmark/scripts/run_perf.py.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from extractors import atlasfile_extractor, markitdown_extractor  # noqa: E402

EXT_TO_FORMAT = {
    ".pdf": "pdf", ".docx": "docx", ".doc": "doc",
    ".xlsx": "xlsx", ".xls": "xls", ".pptx": "pptx", ".msg": "msg",
}

# Linha separadora de tabela markdown: so | : - e espacos, com pelo menos um '-'.
_MD_SEP_RE = re.compile(r"^[\s|:\-]+$")
_PIPE_ROW_RE = re.compile(r"^\s*\|.*\|")


def _log(msg: str) -> None:
    print(msg, flush=True)


def _slug(name: str) -> str:
    s = re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("_")
    return s or "file"


def _compute_metrics(text: str) -> dict[str, Any]:
    lines = text.split("\n")
    nonblank = [l for l in lines if l.strip()]
    pipe_rows = sum(1 for l in lines if _PIPE_ROW_RE.match(l))
    md_table_seps = sum(1 for l in lines if "|" in l and "-" in l and _MD_SEP_RE.match(l))
    digits = sum(c.isdigit() for c in text)
    return {
        "char_count": len(text),
        "word_count": len(text.split()),
        "line_count": len(lines),
        "nonblank_line_count": len(nonblank),
        "pipe_table_rows": pipe_rows,
        "md_table_blocks": md_table_seps,
        "digit_count": digits,
        "numeric_density": round(digits / len(text), 4) if text else 0.0,
    }


def _measure(extract_fn: Callable[[], dict], runs: int, warmup: int) -> tuple[dict, float, float]:
    """Roda extract_fn warmup+runs vezes. Retorna (ultimo_resultado, latency_ms, peak_mb)."""
    for _ in range(warmup):
        extract_fn()

    latencies: list[float] = []
    peak_mb = 0.0
    last: dict = {}
    for i in range(runs):
        if i == 0:
            tracemalloc.start()
        t0 = time.perf_counter()
        last = extract_fn()
        elapsed = (time.perf_counter() - t0) * 1000.0
        if i == 0:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_mb = peak / (1024 * 1024)
        latencies.append(elapsed)

    return last, statistics.median(latencies), peak_mb


def _run_tool(name: str, extract_fn: Callable[[], dict], runs: int, warmup: int) -> tuple[dict[str, Any], str]:
    last, latency_ms, peak_mb = _measure(extract_fn, runs, warmup)
    text = last.get("text", "")
    record = {
        "tool": name,
        "status": last.get("status", "error"),
        "error": last.get("error"),
        "latency_ms": round(latency_ms, 1),
        "peak_memory_mb": round(peak_mb, 1),
        "meta": last.get("meta", {}),
        "metrics": _compute_metrics(text),
    }
    return record, text


def _write_output(out_dir: Path, slug: str, tool: str, ext: str, text: str) -> str:
    outputs_dir = out_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{slug}__{tool}{ext}"
    (outputs_dir / fname).write_text(text, encoding="utf-8")
    return f"outputs/{fname}"


def _preview(text: str, n: int = 600) -> str:
    snippet = text[:n].strip()
    return snippet.replace("```", "`​``")  # neutraliza fences no preview


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara MarkItDown vs extrator AtlasFile")
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--atlas-max-chars", type=int, default=None,
                        help="Cap de caracteres no extrator AtlasFile (default: doc inteiro). "
                             "Escape hatch para PDFs gigantes; MarkItDown sempre processa o doc todo.")
    args = parser.parse_args()

    if not args.corpus_dir.exists():
        _log(f"[ERRO] corpus-dir nao encontrado: {args.corpus_dir}")
        sys.exit(1)

    files = sorted(
        f for f in args.corpus_dir.iterdir()
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in EXT_TO_FORMAT
    )
    if not files:
        _log(f"[ERRO] Nenhum arquivo elegivel em {args.corpus_dir}")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _log(f"{len(files)} arquivos. runs={args.runs} warmup={args.warmup}\n")

    summary: list[dict[str, Any]] = []

    for i, f in enumerate(files, start=1):
        ext = f.suffix.lower()
        fmt = EXT_TO_FORMAT.get(ext, "?")
        slug = _slug(f.stem)
        _log(f"[{i}/{len(files)}] {f.name} ({fmt})")

        # AtlasFile
        atlas_rec, atlas_text = _run_tool(
            "atlasfile",
            lambda: atlasfile_extractor.run(f, max_chars=args.atlas_max_chars),
            args.runs, args.warmup,
        )
        atlas_rec["output_file"] = _write_output(args.output_dir, slug, "atlasfile", ".txt", atlas_text)
        _log(f"    atlasfile : {atlas_rec['status']:5} "
             f"{atlas_rec['metrics']['char_count']:>8} chars  "
             f"{atlas_rec['latency_ms']:>8.0f} ms")

        # MarkItDown
        md_rec, md_text = _run_tool(
            "markitdown",
            lambda: markitdown_extractor.run(f),
            args.runs, args.warmup,
        )
        md_rec["output_file"] = _write_output(args.output_dir, slug, "markitdown", ".md", md_text)
        _log(f"    markitdown: {md_rec['status']:5} "
             f"{md_rec['metrics']['char_count']:>8} chars  "
             f"{md_rec['latency_ms']:>8.0f} ms")

        a_len = atlas_rec["metrics"]["char_count"]
        m_len = md_rec["metrics"]["char_count"]
        ratio = round(m_len / a_len, 2) if a_len else None

        summary.append({
            "file": f.name,
            "format": fmt,
            "slug": slug,
            "text_length_ratio_md_over_atlas": ratio,
            "atlasfile": atlas_rec,
            "markitdown": md_rec,
            "previews": {
                "atlasfile": _preview(atlas_text),
                "markitdown": _preview(md_text),
            },
        })

    # summary.json
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # summary.md
    _write_summary_md(args.output_dir / "summary.md", summary, args)
    _log(f"\nResultados em {args.output_dir}/ (summary.json, summary.md, outputs/)")


def _write_summary_md(path: Path, summary: list[dict], args) -> None:
    lines: list[str] = []
    lines.append("# MarkItDown (vanilla) vs Extrator AtlasFile — comparacao lado-a-lado\n")
    lines.append(f"- Corpus: `{args.corpus_dir}` ({len(summary)} arquivos)")
    lines.append(f"- Runs: {args.runs} (warmup {args.warmup}); latencia = mediana, memoria = pico tracemalloc (1o run)")
    lines.append("- MarkItDown **vanilla** (sem OCR de PDF). AtlasFile com OCR Tesseract no fallback.")
    lines.append("- Sem LLM-judge: metricas abaixo sao objetivas; a qualidade real exige inspecao dos `outputs/`.\n")

    # Tabela resumo
    lines.append("## Resumo por arquivo\n")
    lines.append("| Arquivo | Fmt | Ferramenta | Status | Chars | Palavras | Linhas | Tab.MD | Densid.num | Latencia(ms) | Mem(MB) |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in summary:
        for tool in ("atlasfile", "markitdown"):
            r = s[tool]
            m = r["metrics"]
            lines.append(
                f"| {s['file']} | {s['format']} | {tool} | {r['status']} | "
                f"{m['char_count']} | {m['word_count']} | {m['nonblank_line_count']} | "
                f"{m['pipe_table_rows']} | {m['numeric_density']} | "
                f"{r['latency_ms']:.0f} | {r['peak_memory_mb']:.1f} |"
            )
    lines.append("")
    lines.append("> `Tab.MD` = linhas de tabela markdown (`| ... |`); so o MarkItDown produz markdown nativo.")
    lines.append("> `Densid.num` = fracao de digitos no texto (sinal de captura de valores/tabelas).")
    lines.append("> `text_length_ratio (md/atlas)` por arquivo esta no summary.json.\n")

    # Previews
    lines.append("## Previews (primeiros ~600 chars)\n")
    for s in summary:
        lines.append(f"### {s['file']} ({s['format']})\n")
        lines.append(f"**AtlasFile** → `{s['atlasfile']['output_file']}`")
        lines.append("```\n" + s["previews"]["atlasfile"] + "\n```\n")
        lines.append(f"**MarkItDown** → `{s['markitdown']['output_file']}`")
        lines.append("```\n" + s["previews"]["markitdown"] + "\n```\n")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
