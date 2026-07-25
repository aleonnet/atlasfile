"""Bancada de diagnóstico do classificador bootstrap (v0.44.0).

Mostra, para UM arquivo contra UM projeto, exatamente o que o runtime vê:
- caminho vencedor do document_type (extension / structural / alias / fallback),
  e no caminho alias: quais termos casaram, o N do √N e a conta da confiança;
- por business_domain: aliases carregados, aliases FILTRADOS por colisão com o
  léxico de document_types, hits por campo (filename/texto/entidades) com os
  termos que casaram, score ponderado e a conta da confiança;
- resultado final do classify_bootstrap real (cross-check) e o min() que define
  a confiança global.

Usa os MESMOS helpers do runtime (nada de lógica paralela além da inspeção).

Uso:
  cd backend && .venv/bin/python scripts/trace_classification.py \
      --project-root "/caminho/da/raiz/do/projeto" --file "/caminho/arquivo.pdf"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            value = value.strip()
            if "  #" in value:  # comentário inline (mesma regra do run_classifier_cycle)
                value = value[: value.index("  #")].strip()
            os.environ.setdefault(key.strip(), value)

from app.classification_bootstrap import (  # noqa: E402
    _DOMAIN_DOCUMENT_TYPE_HIT_WEIGHT,
    _DOMAIN_ENTITY_HIT_WEIGHT,
    _DOMAIN_FILENAME_HIT_WEIGHT,
    _DOMAIN_TEXT_HIT_WEIGHT,
    _alias_hits,
    _alias_specificity,
    _business_domains,
    _document_type_lexicon,
    _document_types,
    _document_types_by_key,
    _domain_confidence,
    _match_score,
    _normalized_aliases,
    classify_bootstrap,
    detect_document_type,
    extract_entities,
)
from app.indexer import read_text_excerpt  # noqa: E402
from app.project_profile import load_project_profile  # noqa: E402
from app.utils import fold_ocr_spacing  # noqa: E402


def trace_document_type(profile: dict, source_path: Path, text_excerpt: str) -> None:
    result = detect_document_type(profile=profile, source_path=source_path, text_excerpt=text_excerpt)
    print(f"\n== document_type: {result['document_type']} "
          f"(confiança {result['document_type_confidence']}, caminho: {result['document_type_reason']})")
    if result["document_type_reason"] == "alias_structure":
        combined = fold_ocr_spacing(f"{source_path.name}\n{text_excerpt[:4000]}".strip())
        print("   caminho alias (score = hits/√N, cap 1.0):")
        for row in _document_types(profile):
            key = str(row.get("key") or "").strip()
            if not key:
                continue
            aliases = [key] + [str(a).strip() for a in (row.get("aliases") or []) if str(a).strip()]
            hits = sorted(_alias_hits(aliases, combined))
            score = _match_score(aliases, combined)
            if hits or score:
                print(f"   - {key}: N={len(aliases)} aliases, hits={hits} -> score={score:.4f}")


def trace_business_domain(profile: dict, source_path: Path, text_excerpt: str, document_type: str, entities: list) -> None:
    text = fold_ocr_spacing(text_excerpt[:4000])
    filename_text = fold_ocr_spacing(source_path.stem)
    entity_text = fold_ocr_spacing("\n".join(e.get("value", "") for e in entities))
    document_type_row = _document_types_by_key(profile).get(document_type, {})
    document_type_tokens = _normalized_aliases(
        [document_type] + [str(a).strip() for a in (document_type_row.get("aliases") or []) if str(a).strip()]
    )
    lexicon = _document_type_lexicon(profile)

    print(f"\n== business_domain (pesos: filename×{_DOMAIN_FILENAME_HIT_WEIGHT} "
          f"texto×{_DOMAIN_TEXT_HIT_WEIGHT} entidades×{_DOMAIN_ENTITY_HIT_WEIGHT} "
          f"doc_type×{_DOMAIN_DOCUMENT_TYPE_HIT_WEIGHT})")
    rows = []
    for domain in _business_domains(profile):
        key = str(domain.get("key") or "").strip()
        if not key:
            continue
        raw_aliases = [str(a).strip() for a in (domain.get("aliases") or []) if str(a).strip()]
        filtered = sorted(a for a in raw_aliases if fold_ocr_spacing(a) in lexicon)
        aliases = [key] + [a for a in raw_aliases if fold_ocr_spacing(a) not in lexicon]
        f_hits = sorted(_alias_hits(aliases, filename_text))
        t_hits = sorted(_alias_hits(aliases, text))
        e_hits = sorted(_alias_hits(aliases, entity_text))
        dt_overlap = sorted(_normalized_aliases(aliases) & document_type_tokens)
        # espelho da regra do runtime: overlap com o tipo só pontua com hit de conteúdo
        dt_hits = dt_overlap if (f_hits or t_hits or e_hits) else []
        score = (
            len(f_hits) * _DOMAIN_FILENAME_HIT_WEIGHT
            + len(t_hits) * _DOMAIN_TEXT_HIT_WEIGHT
            + len(e_hits) * _DOMAIN_ENTITY_HIT_WEIGHT
            + len(dt_hits) * _DOMAIN_DOCUMENT_TYPE_HIT_WEIGHT
        )
        spec = (
            _alias_specificity(set(f_hits)) * _DOMAIN_FILENAME_HIT_WEIGHT
            + _alias_specificity(set(t_hits)) * _DOMAIN_TEXT_HIT_WEIGHT
            + _alias_specificity(set(e_hits)) * _DOMAIN_ENTITY_HIT_WEIGHT
        )
        rows.append((key, score, spec, len(aliases), f_hits, t_hits, e_hits, dt_hits, dt_overlap, filtered))

    rows.sort(key=lambda r: (-r[1], -r[2], r[0]))
    best_score = rows[0][1] if rows else 0
    second_score = rows[1][1] if len(rows) > 1 else 0
    for key, score, spec, n_aliases, f_hits, t_hits, e_hits, dt_hits, dt_overlap, filtered in rows:
        print(f"   - {key}: score={score} spec={spec} ({n_aliases} aliases ativos)")
        if f_hits:
            print(f"       filename: {f_hits}")
        if t_hits:
            print(f"       texto:    {t_hits}")
        if e_hits:
            print(f"       entidades:{e_hits}")
        if dt_hits:
            print(f"       doc_type: {dt_hits}")
        elif dt_overlap:
            print(f"       doc_type IGNORADO (sem hit de conteúdo): {dt_overlap}")
        if filtered:
            print(f"       FILTRADOS (colisão com léxico de tipos): {filtered}")
    if rows:
        print(f"   confiança do vencedor: 0.18 + 0.08·min(best={best_score},7) + 0.06·min(margem={max(0, best_score - second_score)},3) "
              f"= {_domain_confidence(best_score, second_score)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace do classificador bootstrap para um arquivo")
    parser.add_argument("--project-root", required=True, help="raiz do projeto (pasta que contém o profile)")
    parser.add_argument("--file", required=True, help="arquivo a classificar")
    parser.add_argument("--json", action="store_true", help="imprime também o resultado bruto do classify_bootstrap")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser()
    source_path = Path(args.file).expanduser()
    if not source_path.exists():
        sys.exit(f"arquivo não existe: {source_path}")

    profile = load_project_profile(project_root)
    text_excerpt = read_text_excerpt(source_path)
    print(f"projeto: {profile.get('project_id')} | arquivo: {source_path.name} | texto extraído: {len(text_excerpt)} chars")

    result = classify_bootstrap(profile=profile, source_path=source_path, text_excerpt=text_excerpt)
    trace_document_type(profile, source_path, text_excerpt)
    entities = result.get("entities") or []
    trace_business_domain(profile, source_path, text_excerpt, str(result["document_type"]), entities)

    print(f"\n== resultado final (classify_bootstrap real)")
    print(f"   business_domain={result['business_domain']} ({result['business_domain_confidence']}) | "
          f"document_type={result['document_type']} ({result['document_type_confidence']})")
    print(f"   confiança GLOBAL = min(tipo, domínio) = {result['confidence']} | reason={result['reason']}")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
