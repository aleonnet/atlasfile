"""Copia os arquivos da pasta Contrato para corpus/ (idempotente).

Os nomes tem espacos e acentos — usamos pathlib/shutil, nunca shell.
Os arquivos sao contratos reais: corpus/ esta no .gitignore.

Uso:
  python scripts/setup_corpus.py
  python scripts/setup_corpus.py --src "/caminho/alternativo" --dest corpus/
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_SRC = (
    "/Users/alessandro/Library/CloudStorage/OneDrive-Personal/"
    "Área de Trabalho/Contrato"
)

ALLOWED_EXTS = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".doc", ".msg"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Copia corpus de contratos para corpus/")
    parser.add_argument("--src", type=Path, default=Path(DEFAULT_SRC))
    parser.add_argument("--dest", type=Path, default=Path(__file__).resolve().parent.parent / "corpus")
    args = parser.parse_args()

    if not args.src.exists():
        print(f"[ERRO] Pasta de origem nao encontrada: {args.src}", file=sys.stderr)
        sys.exit(1)

    args.dest.mkdir(parents=True, exist_ok=True)

    files = sorted(
        f for f in args.src.iterdir()
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in ALLOWED_EXTS
    )
    if not files:
        print(f"[ERRO] Nenhum arquivo elegivel em {args.src}", file=sys.stderr)
        sys.exit(1)

    copied, skipped = 0, 0
    for f in files:
        target = args.dest / f.name
        if target.exists() and target.stat().st_size == f.stat().st_size:
            print(f"  [skip] {f.name} (ja existe)")
            skipped += 1
            continue
        shutil.copy2(f, target)
        print(f"  [copy] {f.name} ({f.stat().st_size / 1024:.0f} KB)")
        copied += 1

    print(f"\n{copied} copiados, {skipped} pulados. Corpus em {args.dest}/ ({len(files)} arquivos).")


if __name__ == "__main__":
    main()
