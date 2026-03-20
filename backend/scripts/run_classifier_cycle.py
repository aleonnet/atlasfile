from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.classifier_cycle import run_classifier_cycle  # noqa: E402
from app.classifier_supervised import (  # noqa: E402
    SPARSE_MIN_DOCS_PER_CLASS,
    SPARSE_MIN_TRAINING_DOCS,
)


def resolve_profile_arg(raw_value: str) -> str:
    candidate = Path(raw_value).expanduser()
    if candidate.exists():
        return str(candidate)

    repo_root = Path(__file__).resolve().parents[2]
    repo_relative_candidate = (repo_root / candidate).resolve()
    if not candidate.is_absolute() and repo_relative_candidate.exists():
        return str(repo_relative_candidate)

    templates_dir = repo_root / "config" / "templates"
    if candidate.suffix:
        template_candidate = templates_dir / candidate.name
    else:
        template_candidate = templates_dir / f"{raw_value}.json"
    if template_candidate.exists():
        return str(template_candidate)

    return raw_value


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa o ciclo oficial de treino + benchmark + promoção do classificador.")
    parser.add_argument("--profile", default="config/templates/default.json", help="Template/profile usado como referência")
    parser.add_argument("--min-training-docs", type=int, default=SPARSE_MIN_TRAINING_DOCS)
    parser.add_argument("--min-docs-per-class", type=int, default=SPARSE_MIN_DOCS_PER_CLASS)
    args = parser.parse_args()

    payload = run_classifier_cycle(
        profile_path=resolve_profile_arg(args.profile),
        min_training_docs=args.min_training_docs,
        min_docs_per_class=args.min_docs_per_class,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
