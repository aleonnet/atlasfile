"""Sugeridor de aliases do bootstrap: minera n-gramas discriminativos das
CORREÇÕES humanas da triagem e propõe termos para a taxonomia — sempre com
aprovação humana (nunca auto-aplica).

Fonte da evidência: JSONs de `triage_resolved_dir` — cada um guarda a sugestão
original do classificador (`suggested_business_domain`/`suggested_document_type`)
E o rótulo final humano. Uma correção é `suggested_* != final`: o texto desse
documento contém o vocabulário que o bootstrap não conhecia.

Garantias de compatibilidade com o matching do bootstrap
(classification_bootstrap._word_pattern + fold_ocr_spacing):
- candidatos são tokens `[a-z0-9]+` (1-gramas e 2-gramas) do MESMO texto que o
  bootstrap vê (`extract_feature_text`), portanto casam com word boundary;
- cada termo é verificado de volta contra o texto-fonte com o próprio
  `_word_pattern` antes de ser proposto;
- aliases de domínio não podem colidir com o léxico de document_types (o
  bootstrap descarta essas colisões em runtime).

Corte estatístico (contrastivo, sem stopwords artesanais): um termo só é
proposto se aparece em ≥ MIN_SUPPORT docs corrigidos da classe-alvo E com
precisão ≥ MIN_PRECISION sobre TODOS os docs resolvidos analisados — palavras
genéricas aparecem em várias classes e morrem na precisão. Exige ≥ 2 rótulos
distintos no corpus (sem contraste não há sinal).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .classification_bootstrap import _document_type_lexicon, _word_pattern
from .classifier_cycle import extract_feature_text
from .triage import triage_resolved_dir
from .utils import fold_ocr_spacing

MIN_SUPPORT = 2          # docs corrigidos da classe-alvo contendo o termo
MIN_PRECISION = 0.8      # fração dos docs (todas as classes) com o termo que são da classe-alvo
MAX_TERMS_PER_TARGET = 5
_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Marcadores estruturais do extrator ("[page 1]", "[sheet X row 1 col A]") não são
# conteúdo do documento — jamais viram alias.
_EXTRACTOR_MARKER_RE = re.compile(r"\[[^\]]*\]")
_MIN_TOKEN_LEN = 3

_KIND_FIELDS = {
    "business_domain": ("suggested_business_domain", "business_domain"),
    "document_type": ("suggested_document_type", "document_type"),
}


def _candidate_terms(text: str) -> set[str]:
    tokens = _TOKEN_RE.findall(_EXTRACTOR_MARKER_RE.sub(" ", text))
    terms: set[str] = set()
    for i, tok in enumerate(tokens):
        if len(tok) >= _MIN_TOKEN_LEN and not tok.isdigit():
            terms.add(tok)
        if i + 1 < len(tokens):
            nxt = tokens[i + 1]
            # TODO tokens do bigrama com ≥3 letras: mata bordas funcionais
            # ("partes e", "junto ao") sem lista de stopwords arbitrária
            if len(tok) >= _MIN_TOKEN_LEN and len(nxt) >= _MIN_TOKEN_LEN                     and not (tok.isdigit() or nxt.isdigit()):
                terms.add(f"{tok} {nxt}")
    return terms


def _load_resolved_docs(project_root: Path) -> list[dict[str, Any]]:
    resolved_dir = triage_resolved_dir(project_root)
    docs: list[dict[str, Any]] = []
    if not resolved_dir.exists():
        return docs
    for meta_path in sorted(resolved_dir.glob("*.json")):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        docs.append(data)
    return docs


def _doc_text(data: dict[str, Any]) -> tuple[str, list[str]] | None:
    """Retorna (texto completo foldado — o MESMO que o bootstrap vê, para a
    auto-verificação do matching) e as PARTES para mineração de candidatos:
    stem do nome original (sem extensão — 'txt'/'pdf' não é alias) e o excerpt,
    separadas para n-gramas não atravessarem a fronteira nome→texto."""
    original_name = str(data.get("original_filename") or "")
    for field in ("final_path", "path", "source_path"):
        raw = str(data.get(field) or "").strip()
        if not raw:
            continue
        path = Path(raw)
        if path.exists():
            try:
                full = extract_feature_text(path, original_name=original_name)
            except Exception:
                return None
            name_part = fold_ocr_spacing(Path(original_name or path.name).stem)
            # o excerpt é o texto completo sem a linha do nome (prefixada pelo extractor)
            folded_name_line = fold_ocr_spacing(original_name or path.name)
            excerpt_part = full[len(folded_name_line):].strip() if full.startswith(folded_name_line) else full
            return full, [name_part, excerpt_part]
    return None


def suggest_aliases(
    project_root: Path,
    profile: dict[str, Any],
    *,
    dismissed: set[str] | None = None,
    min_support: int = MIN_SUPPORT,
    min_precision: float = MIN_PRECISION,
) -> dict[str, Any]:
    """Analisa os docs resolvidos do projeto e retorna sugestões de aliases.

    Retorno: {"suggestions": [{kind, key, label, terms: [{term, support, precision,
    sample_docs}]}], "corpus": {resolved_total, corrected_total, distinct_labels,
    analyzed_total}} — análise pura, nada é persistido."""
    dismissed = dismissed or set()
    docs = _load_resolved_docs(project_root)

    analyzed: list[dict[str, Any]] = []
    for data in docs:
        extracted = _doc_text(data)
        if extracted is None:
            continue
        full_text, parts = extracted
        terms: set[str] = set()
        for part in parts:
            terms |= _candidate_terms(part)
        analyzed.append({"data": data, "text": full_text, "terms": terms})

    corrected_total = 0
    # targets[(kind, final_key)] = [docs corrigidos para essa classe]
    targets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in analyzed:
        data = item["data"]
        is_corrected = False
        for kind, (suggested_field, final_field) in _KIND_FIELDS.items():
            suggested = str(data.get(suggested_field) or "").strip()
            final = str(data.get(final_field) or "").strip()
            if final and suggested and suggested != final:
                targets.setdefault((kind, final), []).append(item)
                is_corrected = True
        if is_corrected:
            corrected_total += 1

    classification = profile.get("classification") or {}
    existing_aliases: set[str] = set()
    labels_by_key: dict[tuple[str, str], str] = {}
    for kind, bucket_name in (("business_domain", "business_domains"), ("document_type", "document_types")):
        for entry in classification.get(bucket_name) or []:
            labels_by_key[(kind, str(entry.get("key") or ""))] = str(entry.get("label") or entry.get("key") or "")
            for alias in [entry.get("key") or "", *(entry.get("aliases") or [])]:
                cleaned = str(alias).strip().lower()
                if cleaned:
                    existing_aliases.add(cleaned)
    doc_type_lexicon = _document_type_lexicon(profile)

    corpus_info = {
        "resolved_total": len(docs),
        "analyzed_total": len(analyzed),
        "corrected_total": corrected_total,
        "distinct_labels": 0,
    }

    # Contraste por kind: precisão medida sobre os rótulos FINAIS de cada doc
    suggestions: list[dict[str, Any]] = []
    for kind, (_suggested_field, final_field) in _KIND_FIELDS.items():
        labeled = [item for item in analyzed if str(item["data"].get(final_field) or "").strip()]
        labels = {str(item["data"].get(final_field)).strip() for item in labeled}
        corpus_info["distinct_labels"] = max(corpus_info["distinct_labels"], len(labels))
        if len(labels) < 2:
            continue  # sem contraste não há termo "discriminativo"


        for (t_kind, target_key), corrected_items in sorted(targets.items()):
            if t_kind != kind:
                continue
            # precisão só significa algo com contraste real: ≥2 docs de OUTRAS classes
            others = [i for i in labeled if str(i["data"].get(final_field)).strip() != target_key]
            if len(others) < 2:
                continue
            term_support: dict[str, list[str]] = {}
            for item in corrected_items:
                for term in item["terms"]:
                    term_support.setdefault(term, []).append(
                        str(item["data"].get("original_filename") or item["data"].get("doc_id") or "")
                    )
            proposals: list[dict[str, Any]] = []
            for term, sample_docs in term_support.items():
                if len(sample_docs) < min_support:
                    continue
                if term in existing_aliases:
                    continue
                if kind == "business_domain" and term in doc_type_lexicon:
                    continue  # bootstrap descartaria a colisão em runtime
                if f"{kind}:{target_key}:{term}" in dismissed:
                    continue
                in_class = sum(
                    1 for item in labeled
                    if str(item["data"].get(final_field)).strip() == target_key and term in item["terms"]
                )
                total_with_term = sum(1 for item in labeled if term in item["terms"])
                if total_with_term == 0:
                    continue
                precision = in_class / total_with_term
                if precision < min_precision:
                    continue
                # auto-verificação: o termo casa nos textos-fonte pelo matching real
                pattern = _word_pattern(term)
                if not all(pattern.search(item["text"]) for item in corrected_items if term in item["terms"]):
                    continue
                proposals.append({
                    "term": term,
                    "support": len(sample_docs),
                    "precision": round(precision, 3),
                    "sample_docs": sorted(set(sample_docs))[:3],
                })
            if not proposals:
                continue
            # mais específico primeiro: precisão, suporte, termos longos (2-gramas)
            proposals.sort(key=lambda p: (-p["precision"], -p["support"], -len(p["term"])))
            deduped = _drop_redundant_unigrams(proposals)[:MAX_TERMS_PER_TARGET]
            suggestions.append({
                "kind": kind,
                "key": target_key,
                "label": labels_by_key.get((kind, target_key), target_key),
                "terms": deduped,
            })

    suggestions.sort(key=lambda s: (s["kind"], s["key"]))
    return {"suggestions": suggestions, "corpus": corpus_info}


def _drop_redundant_unigrams(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Se um 2-grama proposto contém um 1-grama com o MESMO suporte, o 1-grama é
    redundante (sempre co-ocorre) — fica só o termo mais específico."""
    bigrams = [p for p in proposals if " " in p["term"]]
    out: list[dict[str, Any]] = []
    for p in proposals:
        if " " not in p["term"]:
            covered = any(
                p["term"] in bg["term"].split(" ") and bg["support"] == p["support"]
                for bg in bigrams
            )
            if covered:
                continue
        out.append(p)
    return out
