"""Benchmark de retrieval contra um golden set de queries pt-BR.

Mede Recall@5, MRR@10 e NDCG@10 por modo de busca (lexical | hybrid | semantic)
chamando o GET /api/search da API real. Serve para decidir com dados: se o modo
híbrido supera o lexical no corpus real, se o rerank compensa (habilite
SEARCH_RERANK_ENABLED no serviço e rode de novo) e para calibrar k do RRF.

Golden set (JSONL, 1 query por linha; fora do git — contém termos do corpus real):
    {"query": "contrato de aluguel", "expected_files": ["Contrato_Locacao_2024.pdf"], "project_id": "opcional"}
    {"query": "…", "expected_doc_ids": ["abc123"]}

Template versionado: config/retrieval_golden_set.example.jsonl
Local default do golden set real: <projects_root>/_ATLASFILE/retrieval_golden_set.jsonl

Uso:
    cd backend && .venv/bin/python scripts/benchmark_retrieval.py
    cd backend && .venv/bin/python scripts/benchmark_retrieval.py --modes lexical hybrid semantic
    cd backend && .venv/bin/python scripts/benchmark_retrieval.py --golden /path/golden.jsonl --api-base http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load .env from project root (two levels up from scripts/)
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            value = value.strip()
            if "  #" in value:
                value = value[:value.index("  #")].strip()
            os.environ.setdefault(key.strip(), value)

import httpx  # noqa: E402

from app.classifier_registry import classifier_state_base_root  # noqa: E402

RECALL_AT = 5
RANK_AT = 10


def default_golden_path() -> Path:
    return classifier_state_base_root() / "_ATLASFILE" / "retrieval_golden_set.jsonl"


def load_golden(path: Path) -> list[dict]:
    entries: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry = json.loads(line)
        if not str(entry.get("query") or "").strip():
            raise ValueError(f"linha {line_number}: campo 'query' obrigatório")
        if not (entry.get("expected_files") or entry.get("expected_doc_ids")):
            raise ValueError(f"linha {line_number}: informe expected_files ou expected_doc_ids")
        entries.append(entry)
    return entries


def hit_expected_key(hit: dict, entry: dict) -> str | None:
    """Chave do item esperado que este hit satisfaz, ou None."""
    expected_ids = {str(v) for v in (entry.get("expected_doc_ids") or [])}
    expected_files = {str(v) for v in (entry.get("expected_files") or [])}
    doc_id = str(hit.get("doc_id") or "")
    filename = str(hit.get("original_filename") or "")
    if doc_id in expected_ids:
        return f"id:{doc_id}"
    if filename in expected_files:
        return f"file:{filename}"
    return None


def evaluate_query(client: httpx.Client, api_base: str, entry: dict, mode: str) -> dict:
    params: dict = {"q": entry["query"], "mode": mode, "size": RANK_AT, "page": 1}
    if entry.get("project_id"):
        params["project_id"] = entry["project_id"]
    response = client.get(f"{api_base}/api/search", params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    hits = payload.get("hits") or []
    # Cada item esperado conta 1 vez (corpus pode ter o mesmo arquivo em N projetos).
    relevance: list[int] = []
    matched_keys: set[str] = set()
    for hit in hits[:RANK_AT]:
        key = hit_expected_key(hit, entry)
        if key and key not in matched_keys:
            matched_keys.add(key)
            relevance.append(1)
        else:
            relevance.append(0)
    expected_total = len(entry.get("expected_doc_ids") or []) + len(entry.get("expected_files") or [])

    found_at_recall = sum(relevance[:RECALL_AT])
    recall = found_at_recall / expected_total if expected_total else 0.0

    reciprocal_rank = 0.0
    for index, rel in enumerate(relevance, start=1):
        if rel:
            reciprocal_rank = 1.0 / index
            break

    dcg = sum(rel / math.log2(index + 1) for index, rel in enumerate(relevance, start=1))
    ideal_hits = min(expected_total, RANK_AT)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    ndcg = dcg / idcg if idcg else 0.0

    return {
        "query": entry["query"],
        "mode_effective": payload.get("search_mode_effective"),
        f"recall@{RECALL_AT}": round(recall, 4),
        "mrr": round(reciprocal_rank, 4),
        f"ndcg@{RANK_AT}": round(ndcg, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark de retrieval (golden set) por modo de busca")
    parser.add_argument("--golden", default=None, help=f"Path do golden set JSONL (default: {default_golden_path()})")
    parser.add_argument("--api-base", default=os.environ.get("ATLASFILE_API_BASE", "http://localhost:8000"))
    parser.add_argument("--modes", nargs="+", default=["lexical", "hybrid"], choices=["lexical", "hybrid", "semantic"])
    parser.add_argument("--out", default=None, help="Salvar relatório JSON neste path (opcional)")
    args = parser.parse_args()

    golden_path = Path(args.golden) if args.golden else default_golden_path()
    if not golden_path.exists():
        print(f"Golden set não encontrado: {golden_path}")
        print("Crie a partir do template: config/retrieval_golden_set.example.jsonl")
        return 1
    entries = load_golden(golden_path)
    print(f"Golden set: {golden_path} ({len(entries)} queries) | API: {args.api_base}\n")

    report: dict = {"golden_set": str(golden_path), "queries": len(entries), "modes": {}}
    with httpx.Client() as client:
        for mode in args.modes:
            rows = [evaluate_query(client, args.api_base, entry, mode) for entry in entries]
            effective = {row["mode_effective"] for row in rows}
            aggregate = {
                f"recall@{RECALL_AT}": round(sum(r[f"recall@{RECALL_AT}"] for r in rows) / len(rows), 4),
                "mrr": round(sum(r["mrr"] for r in rows) / len(rows), 4),
                f"ndcg@{RANK_AT}": round(sum(r[f"ndcg@{RANK_AT}"] for r in rows) / len(rows), 4),
                "mode_effective": sorted(e for e in effective if e),
            }
            report["modes"][mode] = {"aggregate": aggregate, "per_query": rows}
            print(
                f"[{mode:>8}] recall@{RECALL_AT}={aggregate[f'recall@{RECALL_AT}']:.4f}  "
                f"mrr={aggregate['mrr']:.4f}  ndcg@{RANK_AT}={aggregate[f'ndcg@{RANK_AT}']:.4f}  "
                f"(servido como: {', '.join(aggregate['mode_effective']) or '—'})"
            )

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nRelatório salvo em {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
