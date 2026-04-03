#!/usr/bin/env python3
"""Label corpus documents via LLM (GPT-4o-mini).

Extracts text from each document, sends to LLM with project taxonomy,
and stores classification results. Supports resume — skips already-labeled docs.

Usage:
    PROJECTS_ROOT=/path/to/projects OPENAI_API_KEY=sk-... \
        python -m scripts.label_corpus_llm [--dry-run] [--limit N]

Output: corpus_llm_labels.jsonl in datasets/ dir (one result per line).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.document_extractor import extract_document_content
from app.evaluation_dataset import classifier_datasets_root
from app.training_usage import generate_run_id, persist_training_usage
from app.usage_costs import estimate_usage_cost
from app.utils import utc_now_iso

_PROFILE_PATH = Path(__file__).resolve().parents[2] / "config" / "templates" / "default.json"

_SYSTEM_PROMPT = """\
Você é um especialista em classificação de documentos corporativos de M&A e carve-out.

Analise o trecho do documento e classifique-o nos dois eixos abaixo.

## business_domain (obrigatório)
Escolha o domínio que MELHOR descreve a função de negócio do documento.
Se nenhum se encaixar, use "outro" e explique na justificativa.

{domain_list}

## document_type (obrigatório)
Escolha o tipo documental que MELHOR descreve a natureza do documento.
Se nenhum se encaixar, use "outro" e explique na justificativa.

{type_list}

## Regras
- Analise o CONTEÚDO do documento, não apenas o nome do arquivo.
- confidence: 0.0 a 1.0. Use < 0.6 se ambíguo, > 0.85 com forte evidência.
- Se o documento não se encaixa em nenhum domínio ou tipo, use "outro".
- justificativa: obrigatória sempre. Explique em 1-2 frases.

Responda SOMENTE com JSON válido no formato:
{{"business_domain": "...", "document_type": "...", "confidence": 0.0, "justificativa": "..."}}
"""


def _build_taxonomy() -> tuple[str, str]:
    """Build domain and type lists from default profile."""
    profile = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    classification = profile.get("classification", {})

    domain_lines = []
    for d in classification.get("business_domains", []):
        key = d["key"]
        scope = d.get("primary_scope", "")
        aliases = ", ".join(d.get("aliases", [])[:5])
        domain_lines.append(f"- **{key}**: {scope} (aliases: {aliases})")

    type_lines = []
    for t in classification.get("document_types", []):
        key = t["key"]
        label = t.get("label", key)
        aliases = ", ".join(t.get("aliases", [])[:5])
        exts = ", ".join(t.get("extensions", []))
        type_lines.append(f"- **{key}** ({label}): aliases: {aliases}. Extensões típicas: {exts}")

    return "\n".join(domain_lines), "\n".join(type_lines)


def _classify_one(
    client: "openai.OpenAI",
    model: str,
    system_prompt: str,
    filename: str,
    text_excerpt: str,
) -> dict:
    """Call LLM to classify a single document."""
    user_content = f"Documento: {filename}\n\nConteúdo extraído:\n{text_excerpt[:20000]}"

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
        max_tokens=300,
    )

    usage = resp.usage
    raw_text = resp.choices[0].message.content or "{}"
    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        result = {"error": "invalid_json", "raw": raw_text}

    result["_usage"] = {
        "input_tokens": getattr(usage, "prompt_tokens", 0),
        "output_tokens": getattr(usage, "completion_tokens", 0),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Label corpus via LLM")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N documents (0=all)")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    ds_root = classifier_datasets_root()
    corpus_jsonl = ds_root / "corpus.jsonl"
    labels_path = ds_root / "corpus_llm_labels.jsonl"
    corpus_dir = ds_root / "corpus_files"

    if not corpus_jsonl.exists():
        print("ERROR: corpus.jsonl not found. Run build_corpus.py first.", file=sys.stderr)
        sys.exit(1)

    # Load corpus
    corpus = [json.loads(l) for l in corpus_jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Corpus: {len(corpus)} documents")

    # Load existing labels (resume support)
    already_done: dict[str, dict] = {}
    if labels_path.exists():
        for line in labels_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                already_done[record["doc_id"]] = record
    print(f"Already labeled: {len(already_done)}")

    # Build prompt
    domain_list, type_list = _build_taxonomy()
    system_prompt = _SYSTEM_PROMPT.format(domain_list=domain_list, type_list=type_list)

    if args.dry_run:
        todo = [e for e in corpus if e["doc_id"] not in already_done]
        if args.limit:
            todo = todo[:args.limit]
        print(f"\n[DRY-RUN] Would classify {len(todo)} documents")
        for e in todo[:5]:
            print(f"  {e['doc_id']}: {e['original_filename']}")
        if len(todo) > 5:
            print(f"  ... and {len(todo) - 5} more")
        est_tokens = len(todo) * 4000
        est_cost = est_tokens * 0.15 / 1_000_000 + len(todo) * 100 * 0.60 / 1_000_000
        print(f"\nEstimated cost: ~${est_cost:.2f} ({est_tokens:,} input tokens)")
        return

    # Initialize OpenAI client
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    todo = [e for e in corpus if e["doc_id"] not in already_done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"To classify: {len(todo)}")

    run_id = generate_run_id()
    total_input = 0
    total_output = 0
    errors = 0

    for i, entry in enumerate(todo):
        doc_id = entry["doc_id"]
        corpus_file = corpus_dir / entry["corpus_file"]

        if not corpus_file.exists():
            print(f"  [{i+1}/{len(todo)}] SKIP (file missing): {entry['corpus_file']}")
            errors += 1
            continue

        # Extract text
        try:
            extracted = extract_document_content(corpus_file, max_chars=20000)
            text = extracted.text_excerpt
        except Exception as exc:
            print(f"  [{i+1}/{len(todo)}] SKIP (extraction error): {entry['corpus_file']}: {exc}")
            result_record = {
                "doc_id": doc_id,
                "original_filename": entry["original_filename"],
                "error": f"extraction_error: {exc}",
                "labeled_at": utc_now_iso(),
            }
            with labels_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result_record, ensure_ascii=False) + "\n")
            errors += 1
            continue

        if not text or len(text.strip()) < 20:
            print(f"  [{i+1}/{len(todo)}] SKIP (empty/tiny text): {entry['corpus_file']}")
            result_record = {
                "doc_id": doc_id,
                "original_filename": entry["original_filename"],
                "error": "empty_or_tiny_text",
                "labeled_at": utc_now_iso(),
            }
            with labels_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result_record, ensure_ascii=False) + "\n")
            errors += 1
            continue

        # Call LLM
        try:
            result = _classify_one(client, args.model, system_prompt, entry["original_filename"], text)
        except Exception as exc:
            print(f"  [{i+1}/{len(todo)}] ERROR (LLM call): {exc}")
            result_record = {
                "doc_id": doc_id,
                "original_filename": entry["original_filename"],
                "error": f"llm_error: {exc}",
                "labeled_at": utc_now_iso(),
            }
            with labels_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result_record, ensure_ascii=False) + "\n")
            errors += 1
            time.sleep(2)
            continue

        usage = result.pop("_usage", {})
        total_input += usage.get("input_tokens", 0)
        total_output += usage.get("output_tokens", 0)

        persist_training_usage(
            script_name="label_corpus_llm",
            run_id=run_id,
            provider="openai",
            model=args.model,
            usage=usage,
            records_processed=1,
        )

        # Compare with existing label
        existing_bd = entry.get("business_domain", "")
        existing_dt = entry.get("document_type", "")
        llm_bd = result.get("business_domain", "")
        llm_dt = result.get("document_type", "")
        divergence = ""
        if existing_bd and existing_bd != llm_bd:
            divergence += f"domain:{existing_bd}→{llm_bd} "
        if existing_dt and existing_dt != llm_dt:
            divergence += f"type:{existing_dt}→{llm_dt}"

        result_record = {
            "doc_id": doc_id,
            "original_filename": entry["original_filename"],
            "existing_business_domain": existing_bd,
            "existing_document_type": existing_dt,
            "llm_business_domain": llm_bd,
            "llm_document_type": llm_dt,
            "llm_confidence": result.get("confidence", 0.0),
            "llm_justificativa": result.get("justificativa", ""),
            "divergence": divergence.strip(),
            "labeled_at": utc_now_iso(),
        }

        # Write immediately (resume support)
        with labels_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result_record, ensure_ascii=False) + "\n")

        status = "DIVERGE" if divergence else "OK"
        conf = result.get("confidence", 0)
        print(f"  [{i+1}/{len(todo)}] {status} {doc_id}: {llm_bd}/{llm_dt} (conf={conf:.2f}) {divergence}")

        # Rate limiting
        time.sleep(0.2)

    # Summary
    total_cost = estimate_usage_cost(
        {"input_tokens": total_input, "output_tokens": total_output},
        "openai",
        args.model,
    )
    print(f"\nDone: {len(todo) - errors} classified, {errors} errors")
    print(f"Tokens: {total_input:,} input + {total_output:,} output")
    print(f"Cost: ${total_cost:.4f}")

    # Load all labels and generate divergence report
    all_labels = []
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            all_labels.append(json.loads(line))

    divergences = [r for r in all_labels if r.get("divergence")]
    new_domains = set()
    new_types = set()
    for r in all_labels:
        bd = r.get("llm_business_domain", "")
        dt = r.get("llm_document_type", "")
        if bd == "outro":
            new_domains.add(r.get("llm_justificativa", "")[:100])
        if dt == "outro":
            new_types.add(r.get("llm_justificativa", "")[:100])

    print(f"\nDivergences (LLM vs existing): {len(divergences)}")
    print(f"LLM suggested 'outro' for domain: {len(new_domains)}")
    print(f"LLM suggested 'outro' for type: {len(new_types)}")
    if new_domains:
        print("  New domain suggestions:")
        for s in new_domains:
            print(f"    {s}")
    if new_types:
        print("  New type suggestions:")
        for s in new_types:
            print(f"    {s}")


if __name__ == "__main__":
    main()
