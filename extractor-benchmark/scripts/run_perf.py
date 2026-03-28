"""Benchmark de performance (latencia e memoria) por provider.

Incremental: grava resultado parcial apos cada documento.
Retoma de onde parou em reexecucao.

Uso:
  python scripts/run_perf.py \
    --corpus-dir corpus/ \
    --providers atlasfile_pypdf,pymupdf_spatial,pdfplumber \
    --output-dir results/run1/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from providers.base import BaseProvider


def _log(msg: str) -> None:
    print(msg, flush=True)


def _load_providers(names: list[str]) -> list[BaseProvider]:
    from providers.atlasfile_pypdf import AtlasFilePyPDFProvider
    from providers.pymupdf_spatial import PyMuPDFSpatialProvider
    from providers.pdfplumber_provider import PDFPlumberProvider

    registry: dict[str, type[BaseProvider]] = {
        "atlasfile_pypdf": AtlasFilePyPDFProvider,
        "pymupdf_spatial": PyMuPDFSpatialProvider,
        "pdfplumber": PDFPlumberProvider,
    }

    providers = []
    for name in names:
        cls = registry.get(name)
        if cls is None:
            _log(f"Provider desconhecido: {name}. Disponiveis: {list(registry)}")
            sys.exit(1)
        providers.append(cls())
    return providers


def _file_id(path: Path) -> str:
    return hashlib.sha256(str(path).encode()).hexdigest()[:16]


def _partial_key(provider_name: str, file_id: str) -> str:
    return f"perf__{provider_name}__{file_id}"


def _load_partial_results(output_dir: Path) -> dict[str, dict]:
    partial_dir = output_dir / "partial_perf"
    results: dict[str, dict] = {}
    if not partial_dir.exists():
        return results
    for f in partial_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            key = _partial_key(data["provider"], data["file_id"])
            results[key] = data
        except Exception:
            pass
    return results


def _save_partial_result(output_dir: Path, result: dict) -> None:
    partial_dir = output_dir / "partial_perf"
    partial_dir.mkdir(parents=True, exist_ok=True)
    key = _partial_key(result["provider"], result["file_id"])
    path = partial_dir / f"{key}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _bench_single(
    provider: BaseProvider,
    pdf_path: Path,
    runs: int = 2,
    warmup: int = 1,
    max_pages: int | None = 20,
) -> dict[str, Any]:
    total_pages = 0
    results = []

    for _ in range(warmup):
        results = provider.extract(pdf_path, max_pages=max_pages)
        total_pages = len(results)

    latencies: list[float] = []
    memory_peaks: list[float] = []

    for _ in range(runs):
        tracemalloc.start()
        t0 = time.perf_counter()
        results = provider.extract(pdf_path, max_pages=max_pages)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        latencies.append(elapsed * 1000)
        memory_peaks.append(peak / (1024 * 1024))
        total_pages = len(results)

    text_length = sum(len(r.text) for r in results)

    return {
        "latency_avg_ms": round(statistics.mean(latencies), 1),
        "latency_median_ms": round(statistics.median(latencies), 1),
        "latency_min_ms": round(min(latencies), 1),
        "latency_max_ms": round(max(latencies), 1),
        "memory_peak_avg_mb": round(statistics.mean(memory_peaks), 1),
        "memory_peak_max_mb": round(max(memory_peaks), 1),
        "pages_extracted": total_pages,
        "text_length": text_length,
    }


def _aggregate_perf(partial_results: dict[str, dict], provider_names: list[str]) -> list[dict]:
    all_results = []
    for pname in provider_names:
        docs = [v for v in partial_results.values() if v["provider"] == pname and "latency_avg_ms" in v]
        agg = {}
        if docs:
            agg = {
                "avg_latency_ms": round(statistics.mean(d["latency_avg_ms"] for d in docs), 1),
                "avg_memory_peak_mb": round(statistics.mean(d["memory_peak_avg_mb"] for d in docs), 1),
                "total_pages": sum(d["pages_extracted"] for d in docs),
                "avg_latency_per_page_ms": round(
                    sum(d["latency_avg_ms"] for d in docs) / max(1, sum(d["pages_extracted"] for d in docs)),
                    2,
                ),
            }
        all_results.append({
            "provider": pname,
            "summary": agg,
            "documents": docs,
        })
    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark de performance de extracao PDF")
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--providers", type=str, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=20, help="Max paginas por documento (default: 20)")
    args = parser.parse_args()

    pdfs = sorted(args.corpus_dir.rglob("*.pdf"))
    if not pdfs:
        _log(f"Nenhum PDF em {args.corpus_dir}")
        sys.exit(1)

    provider_names = [n.strip() for n in args.providers.split(",")]
    providers = _load_providers(provider_names)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    partial_results = _load_partial_results(args.output_dir)
    total_combos = len(providers) * len(pdfs)
    cached = len(partial_results)
    _log(f"{len(pdfs)} PDFs, {len(providers)} providers ({total_combos} combinacoes).")
    if cached:
        _log(f"Resultados parciais: {cached}/{total_combos} — retomando.")

    for provider in providers:
        _log(f"\n=== Provider: {provider.name} ===")

        for pi, pdf_path in enumerate(pdfs, start=1):
            fid = _file_id(pdf_path)
            key = _partial_key(provider.name, fid)

            if key in partial_results:
                pr = partial_results[key]
                _log(f"  [{pi}/{len(pdfs)}] {pdf_path.name} — cached ({pr.get('latency_avg_ms', '?')}ms)")
                continue

            _log(f"  [{pi}/{len(pdfs)}] {pdf_path.name}...", )
            try:
                metrics = _bench_single(provider, pdf_path, runs=args.runs, warmup=args.warmup, max_pages=args.max_pages)
                result = {
                    "provider": provider.name,
                    "file": str(pdf_path),
                    "file_id": fid,
                    **metrics,
                }
                _save_partial_result(args.output_dir, result)
                partial_results[key] = result
                _log(f"    {metrics['latency_avg_ms']:.0f}ms, {metrics['memory_peak_avg_mb']:.1f}MB, {metrics['pages_extracted']}p")
            except Exception as exc:
                _log(f"    [ERRO] {exc}")
                result = {"provider": provider.name, "file": str(pdf_path), "file_id": fid, "error": str(exc)}
                _save_partial_result(args.output_dir, result)
                partial_results[key] = result

    # Agregacao final.
    all_results = _aggregate_perf(partial_results, provider_names)
    output_file = args.output_dir / "perf.json"
    output_file.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"\nResultados salvos em {output_file}")

    # Tabela resumo.
    _log("\n" + "=" * 80)
    _log(f"{'Provider':<25} {'Avg ms':>10} {'Avg MB':>10} {'ms/page':>10} {'Pages':>8}")
    _log("-" * 80)
    for r in all_results:
        s = r.get("summary", {})
        if s:
            _log(
                f"{r['provider']:<25} "
                f"{s['avg_latency_ms']:>9.0f} "
                f"{s['avg_memory_peak_mb']:>9.1f} "
                f"{s['avg_latency_per_page_ms']:>9.1f} "
                f"{s['total_pages']:>8}"
            )


if __name__ == "__main__":
    main()
