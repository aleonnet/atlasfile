"""Atualiza o snapshot LiteLLM embarcado (app/data/llm_catalog_snapshot.json).

Uso (dentro do venv do backend):
    .venv/bin/python scripts/update_catalog_snapshot.py [--url URL]

Semântica de merge (decisão de produto):
- As seções `models`/`costs` são REESCRITAS com o LiteLLM do dia (linhas que
  existem em ambos são atualizadas; linhas novas do LiteLLM entram).
- As seções `user_models`/`user_costs` (mantidas à mão) são PRESERVADAS —
  exceto entradas que o LiteLLM passou a cobrir: essas são removidas da seção
  user (promovidas — a linha passa a ser gerida pela fonte).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.llm_catalog import SNAPSHOT_PATH
from app.llm_catalog_refresh import LITELLM_CATALOG_URL, parse_litellm_catalog
from app.utils import utc_now_iso


def merge_snapshot(current: dict, models: list, costs: dict, *, source_url: str) -> tuple[dict, dict]:
    """Retorna (snapshot novo, resumo). Puro para testes."""
    litellm_model_keys = {(m.provider, m.model) for m in models}
    kept_models = [
        raw for raw in current.get("user_models", [])
        if (raw.get("provider"), raw.get("model")) not in litellm_model_keys
    ]
    promoted_models = len(current.get("user_models", [])) - len(kept_models)

    kept_costs: dict = {}
    promoted_costs = 0
    for provider, entries in (current.get("user_costs") or {}).items():
        for model, cost in entries.items():
            if costs.get(provider, {}).get(model) is not None:
                promoted_costs += 1
            else:
                kept_costs.setdefault(provider, {})[model] = cost

    snapshot = {
        "source_url": source_url,
        "fetched_at": utc_now_iso(),
        "models": [m.model_dump() for m in models],
        "costs": costs,
        "user_models": kept_models,
        "user_costs": kept_costs,
    }
    summary = {
        "litellm_models": len(models),
        "user_models_kept": len(kept_models),
        "user_models_promoted": promoted_models,
        "user_costs_kept": sum(len(v) for v in kept_costs.values()),
        "user_costs_promoted": promoted_costs,
    }
    return snapshot, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=LITELLM_CATALOG_URL)
    args = parser.parse_args()

    current: dict = {}
    if SNAPSHOT_PATH.exists():
        current = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    response = httpx.get(args.url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    models, costs = parse_litellm_catalog(response.json())
    if not models:
        raise SystemExit("A fonte retornou 0 modelos compatíveis — snapshot NÃO atualizado.")

    snapshot, summary = merge_snapshot(current, models, costs, source_url=args.url)
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Snapshot atualizado: {SNAPSHOT_PATH}")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
