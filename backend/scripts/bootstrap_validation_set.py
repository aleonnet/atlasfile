from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation_dataset import stage_validation_files


def _iter_candidates(source: Path, extensions: set[str]) -> list[Path]:
    if source.is_file():
        return [source] if not extensions or source.suffix.lower() in extensions else []
    if not source.exists():
        return []
    files: list[Path] = []
    for path in sorted(source.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if extensions and path.suffix.lower() not in extensions:
            continue
        files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copia arquivos reais para o validation_set operacional e sincroniza expected.json."
    )
    parser.add_argument("source", help="Arquivo ou diretório-fonte com documentos candidatos")
    parser.add_argument("--limit", type=int, default=50, help="Máximo de arquivos a copiar")
    parser.add_argument(
        "--extensions",
        default=".pdf,.pptx,.msg,.xlsx,.docx",
        help="Lista separada por vírgula das extensões aceitas",
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    extensions = {item.strip().lower() for item in args.extensions.split(",") if item.strip()}
    candidates = _iter_candidates(source, extensions)[: max(0, args.limit)]
    staged = stage_validation_files(candidates)

    print(f"staged_files={len(staged)}")
    for path in staged:
        print(path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
