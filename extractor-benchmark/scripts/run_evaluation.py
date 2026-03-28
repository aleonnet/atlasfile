"""Avaliacao de qualidade de extracao PDF via LLM-as-judge.

Pipeline incremental — processa um documento por vez, grava resultado parcial
apos cada documento, e retoma de onde parou em caso de erro ou reexecucao.

Uso:
  python scripts/run_evaluation.py \
    --ground-truth-dir ground_truth/ \
    --corpus-dir corpus/ \
    --providers atlasfile_pypdf,pymupdf_spatial,pdfplumber \
    --output-dir results/run1/
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")
sys.path.insert(0, str(_project_root))

import anthropic

from providers.base import BaseProvider

MODEL = "claude-sonnet-4-5-20250929"

ANSWER_PROMPT = """\
Voce recebera o texto extraido de uma pagina de documento e uma pergunta.
Responda a pergunta usando APENAS informacoes presentes no texto fornecido.
Se a informacao nao estiver no texto, responda exatamente: "NAO_ENCONTRADO".
Seja conciso e preciso.

Texto da pagina:
---
{text}
---

Pergunta: {question}

Resposta:"""

JUDGE_PROMPT = """\
Voce e um avaliador. Compare a resposta dada com a resposta esperada para a pergunta abaixo.

Pergunta: {question}
Resposta esperada: {expected}
Resposta dada: {predicted}

A resposta dada esta correta? Ela contem a informacao essencial da resposta esperada?
Tolere diferencas de formatacao, abreviacoes e ordem das palavras desde que o conteudo factual seja equivalente.

Responda APENAS com JSON: {{"pass": true}} ou {{"pass": false}}"""


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


def _ask_llm(client: anthropic.Anthropic, prompt: str) -> str:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _answer_question(client: anthropic.Anthropic, text: str, question: str) -> str:
    prompt = ANSWER_PROMPT.format(text=text[:15000], question=question)
    return _ask_llm(client, prompt)


def _judge_answer(client: anthropic.Anthropic, question: str, expected: str, predicted: str) -> bool:
    prompt = JUDGE_PROMPT.format(question=question, expected=expected, predicted=predicted)
    response = _ask_llm(client, prompt)

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.startswith("```"))

    try:
        data = json.loads(text)
        return bool(data.get("pass", False))
    except json.JSONDecodeError:
        return "true" in text.lower()


def _resolve_pdf_path(file_ref: str, corpus_dir: Path) -> Path | None:
    pdf_path = Path(file_ref)
    if pdf_path.is_absolute() and pdf_path.exists():
        return pdf_path
    candidate = _project_root / pdf_path
    if candidate.exists():
        return candidate
    candidate = corpus_dir / pdf_path
    if candidate.exists():
        return candidate
    return None


def _partial_key(provider_name: str, doc_id: str) -> str:
    return f"{provider_name}__{doc_id}"


def _load_partial_results(output_dir: Path) -> dict[str, dict]:
    """Carrega resultados parciais ja gravados (1 JSON por provider+doc)."""
    partial_dir = output_dir / "partial"
    results: dict[str, dict] = {}
    if not partial_dir.exists():
        return results
    for f in partial_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            key = _partial_key(data["provider"], data["doc_id"])
            results[key] = data
        except Exception:
            pass
    return results


def _save_partial_result(output_dir: Path, result: dict) -> None:
    """Grava resultado parcial de um provider+doc."""
    partial_dir = output_dir / "partial"
    partial_dir.mkdir(parents=True, exist_ok=True)
    key = _partial_key(result["provider"], result["doc_id"])
    path = partial_dir / f"{key}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _evaluate_single_doc(
    client: anthropic.Anthropic,
    provider: BaseProvider,
    gt: dict,
    corpus_dir: Path,
) -> dict[str, Any] | None:
    """Avalia um unico documento com um provider. Retorna resultado ou None se PDF nao encontrado."""
    pdf_path = _resolve_pdf_path(gt["file"], corpus_dir)
    if pdf_path is None:
        _log(f"  [SKIP] Arquivo nao encontrado: {gt['file']}")
        return None

    category = gt.get("category", "unknown")
    gt_pages = {p["page"]: p["qa_pairs"] for p in gt.get("pages", [])}
    max_page = max(gt_pages.keys()) if gt_pages else 0

    _log(f"  Extraindo {pdf_path.name} (max {max_page} paginas)...")
    page_results = provider.extract(pdf_path, max_pages=max_page)
    page_text_map = {pr.page_number: pr.text for pr in page_results}
    total_text_len = sum(len(t) for t in page_text_map.values())

    doc_pass = 0
    doc_total = 0
    qa_details: list[dict] = []

    for page_num, qa_pairs in gt_pages.items():
        text = page_text_map.get(page_num, "")
        for qa in qa_pairs:
            predicted = _answer_question(client, text, qa["q"])
            time.sleep(0.3)
            passed = _judge_answer(client, qa["q"], qa["a"], predicted)
            time.sleep(0.3)

            qa_details.append({
                "page": page_num,
                "question": qa["q"],
                "expected": qa["a"],
                "predicted": predicted,
                "pass": passed,
            })

            if passed:
                doc_pass += 1
            doc_total += 1

            _log(f"    p{page_num} Q{doc_total}: {'PASS' if passed else 'FAIL'}")

    return {
        "provider": provider.name,
        "doc_id": gt["doc_id"],
        "file": gt["file"],
        "category": category,
        "pass": doc_pass,
        "total": doc_total,
        "pass_rate": doc_pass / doc_total if doc_total else 0.0,
        "text_length": total_text_len,
        "qa_details": qa_details,
    }


def _aggregate_results(partial_results: dict[str, dict], provider_names: list[str]) -> list[dict]:
    """Agrega resultados parciais em resumo por provider."""
    all_results = []

    for pname in provider_names:
        docs = [v for k, v in partial_results.items() if v["provider"] == pname]
        total_pass = sum(d["pass"] for d in docs)
        total_questions = sum(d["total"] for d in docs)

        by_category: dict[str, dict[str, int]] = {}
        for d in docs:
            cat = d.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = {"pass": 0, "total": 0}
            by_category[cat]["pass"] += d["pass"]
            by_category[cat]["total"] += d["total"]

        category_rates = {
            cat: vals["pass"] / vals["total"] if vals["total"] else 0.0
            for cat, vals in by_category.items()
        }

        all_results.append({
            "provider": pname,
            "overall_pass_rate": total_pass / total_questions if total_questions else 0.0,
            "total_pass": total_pass,
            "total_questions": total_questions,
            "by_category": category_rates,
            "by_document": [
                {k: v for k, v in d.items() if k != "qa_details"}
                for d in docs
            ],
            "text_lengths": [{"doc_id": d["doc_id"], "text_length": d["text_length"]} for d in docs],
        })

    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliacao de qualidade de extracao PDF")
    parser.add_argument("--ground-truth-dir", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--providers", type=str, required=True, help="Nomes separados por virgula")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    gt_files = sorted(args.ground_truth_dir.glob("*.json"))
    if not gt_files:
        _log(f"Nenhum ground truth em {args.ground_truth_dir}")
        sys.exit(1)

    ground_truths = []
    for f in gt_files:
        gt = json.loads(f.read_text(encoding="utf-8"))
        if gt.get("pages"):
            ground_truths.append(gt)

    provider_names = [n.strip() for n in args.providers.split(",")]
    providers = _load_providers(provider_names)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Carregar resultados parciais existentes (resume).
    partial_results = _load_partial_results(args.output_dir)
    cached = len(partial_results)
    total_combos = len(providers) * len(ground_truths)
    _log(f"Carregados {len(ground_truths)} docs, {len(providers)} providers ({total_combos} combinacoes).")
    if cached:
        _log(f"Resultados parciais encontrados: {cached}/{total_combos} — retomando de onde parou.")

    client = anthropic.Anthropic()

    for provider in providers:
        _log(f"\n=== Provider: {provider.name} ===")

        for gi, gt in enumerate(ground_truths, start=1):
            key = _partial_key(provider.name, gt["doc_id"])
            if key in partial_results:
                pr = partial_results[key]
                _log(f"  [{gi}/{len(ground_truths)}] {gt['file']} — cached ({pr['pass']}/{pr['total']})")
                continue

            _log(f"  [{gi}/{len(ground_truths)}] {gt['file']}")
            try:
                result = _evaluate_single_doc(client, provider, gt, args.corpus_dir)
                if result:
                    _save_partial_result(args.output_dir, result)
                    partial_results[key] = result
                    _log(f"  Resultado: {result['pass']}/{result['total']} ({result['pass_rate']:.0%})")
            except Exception as exc:
                _log(f"  [ERRO] {exc}")
                _log(f"  Resultados parciais preservados. Reexecute para retomar.")
                # Agregar o que temos ate agora e salvar.
                all_results = _aggregate_results(partial_results, provider_names)
                output_file = args.output_dir / "quality.json"
                output_file.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
                _log(f"  Resultados parciais agregados em {output_file}")
                raise

    # Agregacao final.
    all_results = _aggregate_results(partial_results, provider_names)
    output_file = args.output_dir / "quality.json"
    output_file.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"\nResultados salvos em {output_file}")

    # Tabela resumo.
    _log("\n" + "=" * 70)
    _log(f"{'Provider':<25} {'Pass Rate':>10} {'Pass':>6} {'Total':>6}")
    _log("-" * 70)
    for r in all_results:
        _log(f"{r['provider']:<25} {r['overall_pass_rate']:>9.1%} {r['total_pass']:>6} {r['total_questions']:>6}")

    baseline = next((r for r in all_results if r["provider"] == "atlasfile_pypdf"), None)
    if baseline and len(all_results) > 1:
        _log("\n--- Delta vs atlasfile_pypdf ---")
        for r in all_results:
            if r["provider"] == "atlasfile_pypdf":
                continue
            delta = r["overall_pass_rate"] - baseline["overall_pass_rate"]
            sign = "+" if delta >= 0 else ""
            _log(f"  {r['provider']}: {sign}{delta:.1%}")


if __name__ == "__main__":
    main()
