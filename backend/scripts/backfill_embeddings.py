"""Backfill de embeddings do corpus já indexado para o índice de vetores.

Faz scroll no índice principal (atlasfile_documents), embeda os content_chunks
de cada documento e indexa no atlasfile_chunk_vectors. Idempotente: documentos
com vetores já gravados para o mesmo sha256+provider+modelo são pulados
(use --force para re-embedar tudo).

Uso (dentro do venv do backend):
    cd backend && .venv/bin/python scripts/backfill_embeddings.py
    cd backend && .venv/bin/python scripts/backfill_embeddings.py --project meu-projeto
    cd backend && .venv/bin/python scripts/backfill_embeddings.py --force
"""

from __future__ import annotations

import argparse
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

from opensearchpy.helpers import scan  # noqa: E402

from app.config import settings  # noqa: E402
from app.embeddings import get_embedding_provider  # noqa: E402
from app.indexer import index_document_chunks_embeddings  # noqa: E402
from app.opensearch_client import ensure_chunk_vectors_index, get_client  # noqa: E402
from app.training_usage import generate_run_id, persist_training_usage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill de embeddings por chunk no índice de vetores")
    parser.add_argument("--project", default=None, help="Restringir a um project_id")
    parser.add_argument("--force", action="store_true", help="Re-embedar mesmo se sha256+modelo já indexados")
    args = parser.parse_args()

    if not getattr(settings, "embedding_enabled", False):
        print("embedding_enabled=false — nada a fazer.")
        return 0

    client = get_client()
    provider = get_embedding_provider()
    ensure_chunk_vectors_index(client, provider)
    print(f"Provider: {provider.provider_name} / {provider.model_name} (dim {provider.dimension})")

    query = {"term": {"project_id": args.project}} if args.project else {"match_all": {}}
    run_id = generate_run_id()
    processed = indexed = skipped = failed = 0

    for hit in scan(
        client,
        index=settings.opensearch_index,
        query={"query": query},
        _source=True,
        scroll="10m",
    ):
        src = hit.get("_source") or {}
        if not src.get("doc_id"):
            src["doc_id"] = hit.get("_id")
        result = index_document_chunks_embeddings(
            client,
            src,
            provider,
            usage_script_name="embeddings_backfill",
            force=args.force,
            record_usage=False,  # uso agregado gravado uma vez ao final do run
        )
        processed += 1
        status = result.get("status")
        if status == "indexed":
            indexed += 1
        elif status == "failed":
            failed += 1
        else:
            skipped += 1
        if processed % 20 == 0:
            print(f"  {processed} docs processados ({indexed} embedados, {skipped} skip, {failed} falhas)...")

    try:
        client.indices.refresh(index=settings.opensearch_chunk_vectors_index)
    except Exception:
        pass

    total_tokens = int(getattr(provider, "total_tokens_used", 0) or 0)
    if processed:
        persist_training_usage(
            script_name="embeddings_backfill",
            run_id=run_id,
            provider=provider.provider_name,
            model=provider.model_name,
            usage={"input_tokens": total_tokens},
            records_processed=processed,
            error_count=failed,
        )

    print(
        f"Concluído: {processed} docs ({indexed} embedados, {skipped} skip, {failed} falhas), "
        f"{total_tokens} tokens, run_id={run_id}"
    )
    return 1 if failed and not indexed else 0


if __name__ == "__main__":
    raise SystemExit(main())
