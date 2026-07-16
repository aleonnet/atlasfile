from __future__ import annotations

import argparse
import asyncio
import json
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
            # Strip inline comments (unquoted # followed by space)
            if "  #" in value:
                value = value[:value.index("  #")].strip()
            os.environ.setdefault(key.strip(), value)

from app.classifier_augmentation import (  # noqa: E402
    adjust_plan_for_existing,
    analyze_training_gaps,
    compute_augmentation_plan,
    compute_fill_classes_plan,
    generate_synthetic_records,
)
from app.classifier_cycle import load_profile_runtime  # noqa: E402
from app.evaluation_dataset import (  # noqa: E402
    append_training_pool_record,
    load_training_pool_records,
    load_validation_set,
)
from app.orchestrator import get_llm_config  # noqa: E402
from app.training_usage import generate_run_id, persist_training_usage  # noqa: E402
from scripts.run_classifier_cycle import resolve_profile_arg  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analisa gaps no training pool e gera dados sintéticos via LLM para balanceamento."
    )
    parser.add_argument("--profile", default="config/templates/default.json", help="Template/profile de referência")
    parser.add_argument("--min-per-class", type=int, default=8, help="Mínimo de exemplos por classe")
    parser.add_argument("--max-per-class", type=int, default=20, help="Máximo de exemplos sintéticos por combinação")
    parser.add_argument("--all-combinations", action="store_true", help="Gerar para todas as combinações domain×type (default: apenas combinações do validation set)")
    parser.add_argument("--fill-classes", action="store_true", help="Preencher classes sub-representadas com pares semanticamente coerentes")
    parser.add_argument("--dry-run", action="store_true", help="Apenas analisa gaps e mostra plano, sem gerar dados")
    parser.add_argument("--provider", default=None, help="LLM provider (openai/anthropic). Default: config.")
    parser.add_argument("--model", default=None, help="LLM model. Default: config.")
    args = parser.parse_args()

    profile_path = Path(resolve_profile_arg(args.profile))
    profile = load_profile_runtime(profile_path)
    training_records = load_training_pool_records()

    gaps = analyze_training_gaps(
        training_records=training_records,
        profile=profile,
        min_per_class=args.min_per_class,
    )

    print("=== Gap Analysis ===")
    print(f"Total training records: {gaps['total_records']}")
    print(f"Min per class: {gaps['min_per_class']}")
    print(f"\nBusiness domain gaps ({len(gaps['domain_gaps'])}):")
    for gap in gaps["domain_gaps"]:
        print(f"  {gap['business_domain']:20s} current={gap['current_count']} deficit={gap['deficit']}")
    print(f"\nDocument type gaps ({len(gaps['doc_type_gaps'])}):")
    for gap in gaps["doc_type_gaps"]:
        print(f"  {gap['document_type']:20s} current={gap['current_count']} deficit={gap['deficit']}")

    if args.fill_classes:
        print("\nModo --fill-classes: preenchendo classes sub-representadas com pares semânticos.")
        plan = compute_fill_classes_plan(
            gaps=gaps,
            profile=profile,
            min_per_class=args.min_per_class,
        )
    else:
        target_combinations: list[tuple[str, str]] | None = None
        if not args.all_combinations:
            validation_entries = [e for e in load_validation_set() if e.is_labeled()]
            target_combinations = list({
                (e.business_domain, e.document_type) for e in validation_entries
            })
            print(f"\nFocando em {len(target_combinations)} combinações do validation set.")

        plan = compute_augmentation_plan(
            gaps=gaps,
            profile=profile,
            min_synthetic_per_class=args.min_per_class,
            max_synthetic_per_class=args.max_per_class,
            target_combinations=target_combinations,
        )

    # --- Resume support: subtract already-generated synthetic records ---
    if not args.fill_classes:
        plan = adjust_plan_for_existing(plan, training_records)

    total_to_generate = sum(item["count"] for item in plan)
    print(f"\n=== Augmentation Plan (adjusted for existing synthetic records) ===")
    print(f"Combinations to augment: {len(plan)}")
    print(f"Total records to generate: {total_to_generate}")
    for item in plan:
        print(f"  {item['business_domain']:20s} × {item['document_type']:20s} → {item['count']} records")

    if args.dry_run:
        print("\n[dry-run] Nenhum dado gerado.")
        return 0

    if total_to_generate == 0:
        print("\nTraining pool já está balanceado. Nenhum dado a gerar.")
        return 0

    provider = args.provider
    model = args.model
    if not provider or not model:
        config_provider, config_model = get_llm_config("classification")
        provider = provider or config_provider
        model = model or config_model

    print(f"\nGerando {total_to_generate} records via {provider}/{model}...")
    print("(gravação incremental — progresso preservado em caso de interrupção)\n")

    saved_count = 0

    def _on_record(record: object) -> None:
        """Persist each record immediately to the training pool JSONL."""
        nonlocal saved_count
        append_training_pool_record(record)  # type: ignore[arg-type]
        saved_count += 1

    def _progress(payload: dict) -> None:
        current = payload.get("progress_current", 0)
        total = payload.get("progress_total", 0)
        print(f"  [{current}/{total}] saved={saved_count}", end="\r", flush=True)

    records, usage_totals = asyncio.run(generate_synthetic_records(
        plan=plan,
        provider=provider,
        model=model,
        progress_callback=_progress,
        on_record=_on_record,
    ))

    # Persist accumulated usage
    run_id = generate_run_id()
    persist_training_usage(
        script_name="run_augmentation",
        run_id=run_id,
        provider=provider,
        model=model,
        usage=usage_totals,
        records_processed=saved_count,
    )

    print(f"\n\nGerados e salvos {saved_count} records sintéticos (incrementalmente).")
    print(f"Tokens: {usage_totals.get('input_tokens', 0):,} input + {usage_totals.get('output_tokens', 0):,} output")
    print(json.dumps(
        {"generated": saved_count, "plan_items": len(plan), "total_planned": total_to_generate},
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
