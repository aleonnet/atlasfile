from __future__ import annotations

import os
import uuid
from collections import Counter
from typing import Any

from .evaluation_dataset import TrainingPoolRecord
from .utils import utc_now_iso


def analyze_training_gaps(
    *,
    training_records: list[TrainingPoolRecord],
    profile: dict[str, Any],
    min_per_class: int = 8,
) -> dict[str, Any]:
    """Analyze which (business_domain, document_type) combinations are underrepresented."""
    classification = profile.get("classification") or {}

    all_domains = [
        str(d.get("key") or "").strip()
        for d in (classification.get("business_domains") or [])
        if str(d.get("key") or "").strip()
    ]
    all_doc_types = [
        str(d.get("key") or "").strip()
        for d in (classification.get("document_types") or [])
        if str(d.get("key") or "").strip()
    ]

    domain_counts = Counter(
        str(r.business_domain).strip()
        for r in training_records
        if str(r.business_domain).strip()
    )
    doc_type_counts = Counter(
        str(r.document_type).strip()
        for r in training_records
        if str(r.document_type).strip()
    )
    pair_counts = Counter(
        (str(r.business_domain).strip(), str(r.document_type).strip())
        for r in training_records
        if str(r.business_domain).strip() and str(r.document_type).strip()
    )

    domain_gaps: list[dict[str, Any]] = []
    for domain in all_domains:
        count = domain_counts.get(domain, 0)
        if count < min_per_class:
            domain_gaps.append({
                "business_domain": domain,
                "current_count": count,
                "deficit": min_per_class - count,
            })

    doc_type_gaps: list[dict[str, Any]] = []
    for doc_type in all_doc_types:
        count = doc_type_counts.get(doc_type, 0)
        if count < min_per_class:
            doc_type_gaps.append({
                "document_type": doc_type,
                "current_count": count,
                "deficit": min_per_class - count,
            })

    return {
        "total_records": len(training_records),
        "min_per_class": min_per_class,
        "domain_counts": dict(sorted(domain_counts.items())),
        "doc_type_counts": dict(sorted(doc_type_counts.items())),
        "domain_gaps": domain_gaps,
        "doc_type_gaps": doc_type_gaps,
        "all_domains": all_domains,
        "all_doc_types": all_doc_types,
    }


def compute_augmentation_plan(
    *,
    gaps: dict[str, Any],
    profile: dict[str, Any],
    min_synthetic_per_class: int = 8,
    max_synthetic_per_class: int = 20,
    target_combinations: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Produce a list of (business_domain, document_type, count) records to generate.

    If *target_combinations* is given, only those (domain, doc_type) pairs are
    considered. This allows focusing on combinations that actually appear in the
    validation set instead of the full cartesian product.
    """
    classification = profile.get("classification") or {}
    domains_meta = {
        str(d.get("key") or "").strip(): d
        for d in (classification.get("business_domains") or [])
    }
    doc_types_meta = {
        str(d.get("key") or "").strip(): d
        for d in (classification.get("document_types") or [])
    }

    domain_deficit = {g["business_domain"]: g["deficit"] for g in gaps.get("domain_gaps", [])}
    doc_type_deficit = {g["document_type"]: g["deficit"] for g in gaps.get("doc_type_gaps", [])}

    if target_combinations is not None:
        candidates = target_combinations
    else:
        # Cartesian product of all domains × doc_types from profile
        candidates = [
            (domain, doc_type)
            for domain in gaps.get("all_domains", [])
            for doc_type in gaps.get("all_doc_types", [])
        ]

    plan: list[dict[str, Any]] = []
    for domain, doc_type in candidates:
        d_deficit = domain_deficit.get(domain, 0)
        t_deficit = doc_type_deficit.get(doc_type, 0)
        # Skip if both domain and doc_type already have enough data
        if d_deficit <= 0 and t_deficit <= 0:
            continue

        needed = max(d_deficit, t_deficit)
        needed = max(2, min(max_synthetic_per_class, needed))

        domain_meta = domains_meta.get(domain, {})
        doc_type_meta = doc_types_meta.get(doc_type, {})

        plan.append({
            "business_domain": domain,
            "document_type": doc_type,
            "count": needed,
            "domain_aliases": domain_meta.get("aliases", []),
            "domain_scope": domain_meta.get("primary_scope", ""),
            "domain_topics": domain_meta.get("subfunction_topics", []),
            "doc_type_aliases": doc_type_meta.get("aliases", []),
        })

    return plan


# Semantic affinity: which domains naturally produce which doc_types.
# Used by compute_fill_classes_plan() to avoid nonsensical combinations.
_DOC_TYPE_DOMAIN_AFFINITY: dict[str, list[str]] = {
    "parecer": ["juridico", "regulatorio", "compliance", "fiscal"],
    "procuracao": ["juridico", "societario", "financeiro"],
    "ata": ["societario", "juridico", "operacoes"],
    "nota_fiscal": ["fiscal", "financeiro", "suprimentos"],
    "fato_relevante": ["societario", "regulatorio", "financeiro"],
    "edital": ["suprimentos", "juridico", "operacoes"],
    "contrato": ["juridico", "societario", "suprimentos", "ti"],
    "aditivo": ["juridico", "societario", "ti"],
    "relatorio": ["financeiro", "operacoes", "regulatorio", "compliance"],
    "especificacao": ["ti", "operacoes", "regulatorio"],
    "plano": ["operacoes", "financeiro", "ti", "juridico"],
    "apresentacao": ["operacoes", "financeiro", "societario"],
    "planilha": ["financeiro", "fiscal", "suprimentos", "ativos"],
    "email": ["operacoes", "financeiro", "suprimentos", "pessoas"],
}

# Reverse: which doc_types are natural for each domain.
_DOMAIN_DOC_TYPE_AFFINITY: dict[str, list[str]] = {
    "compliance": ["relatorio", "parecer", "plano", "email", "apresentacao"],
}


def compute_fill_classes_plan(
    *,
    gaps: dict[str, Any],
    profile: dict[str, Any],
    min_per_class: int = 8,
) -> list[dict[str, Any]]:
    """Generate the minimum records so every individual class has ≥ min_per_class.

    Uses semantic affinity tables to pick coherent (domain, doc_type) pairs.
    Resume-safe: the caller re-runs ``analyze_training_gaps`` with the updated
    pool each time, so deficits already reflect all existing records.  No
    per-pair deduction is needed here — the gap analysis handles it.
    """
    classification = profile.get("classification") or {}
    domains_meta = {
        str(d.get("key") or "").strip(): d
        for d in (classification.get("business_domains") or [])
    }
    doc_types_meta = {
        str(d.get("key") or "").strip(): d
        for d in (classification.get("document_types") or [])
    }
    all_domains = gaps.get("all_domains", [])
    all_doc_types = gaps.get("all_doc_types", [])

    domain_deficit = {g["business_domain"]: g["deficit"] for g in gaps.get("domain_gaps", [])}
    doc_type_deficit = {g["document_type"]: g["deficit"] for g in gaps.get("doc_type_gaps", [])}

    planned_domain: Counter[str] = Counter()
    planned_doc_type: Counter[str] = Counter()
    plan: list[dict[str, Any]] = []

    def _add(domain: str, doc_type: str, count: int) -> None:
        domain_meta = domains_meta.get(domain, {})
        doc_type_meta = doc_types_meta.get(doc_type, {})
        plan.append({
            "business_domain": domain,
            "document_type": doc_type,
            "count": count,
            "domain_aliases": domain_meta.get("aliases", []),
            "domain_scope": domain_meta.get("primary_scope", ""),
            "domain_topics": domain_meta.get("subfunction_topics", []),
            "doc_type_aliases": doc_type_meta.get("aliases", []),
        })
        planned_domain[domain] += count
        planned_doc_type[doc_type] += count

    # Phase 1: fill doc_type deficits, distributing across affinity domains
    for doc_type in all_doc_types:
        deficit = doc_type_deficit.get(doc_type, 0)
        if deficit <= 0:
            continue
        affinity = _DOC_TYPE_DOMAIN_AFFINITY.get(doc_type, all_domains[:3])
        n = len(affinity)
        base, extra = divmod(deficit, n)
        for i, domain in enumerate(affinity):
            count = base + (1 if i < extra else 0)
            if count > 0:
                _add(domain, doc_type, count)

    # Phase 2: fill domain deficits not yet covered by phase 1
    used_pairs = {(p["business_domain"], p["document_type"]) for p in plan}
    for domain in all_domains:
        remaining = domain_deficit.get(domain, 0) - planned_domain[domain]
        if remaining <= 0:
            continue
        affinity = _DOMAIN_DOC_TYPE_AFFINITY.get(domain, ["relatorio", "email", "plano"])
        available = [t for t in affinity if (domain, t) not in used_pairs]
        if not available:
            available = affinity
        n = len(available)
        base, extra = divmod(remaining, n)
        for i, doc_type in enumerate(available):
            still_needed = domain_deficit.get(domain, 0) - planned_domain[domain]
            if still_needed <= 0:
                break
            count = min(base + (1 if i < extra else 0), still_needed)
            if count > 0:
                _add(domain, doc_type, count)

    return plan


def build_synthetic_prompt(
    *,
    business_domain: str,
    document_type: str,
    domain_aliases: list[str] | None = None,
    domain_scope: str = "",
    domain_topics: list[str] | None = None,
    doc_type_aliases: list[str] | None = None,
    language: str = "pt-BR",
) -> str:
    """Build a prompt for the LLM to generate synthetic document text."""
    aliases_str = ", ".join(domain_aliases or [])
    topics_str = ", ".join(domain_topics or [])
    doc_aliases_str = ", ".join(doc_type_aliases or [])

    return (
        f"Gere um trecho realista de ~400 palavras de um documento corporativo brasileiro.\n\n"
        f"Tipo do documento: {document_type}\n"
        f"Domínio de negócio: {business_domain}\n"
        f"{'Escopo do domínio: ' + domain_scope + chr(10) if domain_scope else ''}"
        f"{'Termos típicos do domínio: ' + aliases_str + chr(10) if aliases_str else ''}"
        f"{'Tópicos relacionados: ' + topics_str + chr(10) if topics_str else ''}"
        f"{'Termos típicos do tipo documental: ' + doc_aliases_str + chr(10) if doc_aliases_str else ''}"
        f"\nRegras:\n"
        f"- Escreva APENAS o conteúdo textual do documento, como se fosse extraído por OCR.\n"
        f"- NÃO inclua instruções, comentários ou metadados — apenas o texto do documento.\n"
        f"- Use vocabulário, estrutura e formatação típicos de documentos reais desse tipo.\n"
        f"- Inclua cabeçalhos, cláusulas, referências a partes, datas fictícias e valores quando apropriado.\n"
        f"- Idioma: {language}.\n"
    )


async def generate_synthetic_text(
    *,
    business_domain: str,
    document_type: str,
    domain_aliases: list[str] | None = None,
    domain_scope: str = "",
    domain_topics: list[str] | None = None,
    doc_type_aliases: list[str] | None = None,
    provider: str = "openai",
    model: str = "gpt-4.1",
    api_key: str | None = None,
) -> tuple[str, dict[str, int]]:
    """Call LLM to generate a single synthetic document excerpt.

    Returns (text, usage_dict) where usage_dict has input_tokens/output_tokens.
    """
    prompt = build_synthetic_prompt(
        business_domain=business_domain,
        document_type=document_type,
        domain_aliases=domain_aliases,
        domain_scope=domain_scope,
        domain_topics=domain_topics,
        doc_type_aliases=doc_type_aliases,
    )

    resolved_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

    if provider == "openai":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=resolved_key or api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Você é um gerador de dados de treinamento para classificação de documentos corporativos. Gere textos realistas e variados."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            max_tokens=1000,
        )
        text = str(resp.choices[0].message.content or "").strip()
        usage = {
            "input_tokens": getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
            "output_tokens": getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
        }
        return text, usage

    elif provider == "anthropic":
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=resolved_key or api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
            system="Você é um gerador de dados de treinamento para classificação de documentos corporativos. Gere textos realistas e variados.",
            temperature=0.9,
        )
        text = str(resp.content[0].text if resp.content else "").strip()
        usage = {
            "input_tokens": getattr(resp.usage, "input_tokens", 0) if resp.usage else 0,
            "output_tokens": getattr(resp.usage, "output_tokens", 0) if resp.usage else 0,
        }
        return text, usage

    else:
        raise ValueError(f"unsupported provider: {provider}")


def build_synthetic_record(
    *,
    business_domain: str,
    document_type: str,
    synthetic_text: str,
    project_id: str = "llm_augmentation",
) -> TrainingPoolRecord:
    """Create a TrainingPoolRecord for synthetic data (no physical file)."""
    doc_id = str(uuid.uuid4())
    return TrainingPoolRecord(
        doc_id=doc_id,
        project_id=project_id,
        original_filename=f"synthetic_{business_domain}_{document_type}_{doc_id[:8]}.txt",
        path="",
        business_domain=business_domain,
        document_type=document_type,
        decision="llm_synthetic",
        synthetic_text=synthetic_text,
        reviewed_at=utc_now_iso(),
        notes="generated by LLM augmentation",
    )


def adjust_plan_for_existing(
    plan: list[dict[str, Any]],
    existing_records: list[TrainingPoolRecord],
) -> list[dict[str, Any]]:
    """Subtract already-generated llm_synthetic records from the plan (resume support)."""
    existing_counts: Counter[tuple[str, str]] = Counter()
    for r in existing_records:
        if r.decision == "llm_synthetic":
            existing_counts[(r.business_domain, r.document_type)] += 1

    adjusted: list[dict[str, Any]] = []
    for item in plan:
        key = (item["business_domain"], item["document_type"])
        remaining = item["count"] - existing_counts.get(key, 0)
        if remaining > 0:
            adjusted.append({**item, "count": remaining})
    return adjusted


async def generate_synthetic_records(
    *,
    plan: list[dict[str, Any]],
    provider: str = "openai",
    model: str = "gpt-4.1",
    api_key: str | None = None,
    progress_callback: Any | None = None,
    on_record: Any | None = None,
    concurrency: int = 10,
) -> tuple[list[TrainingPoolRecord], dict[str, int]]:
    """Execute an augmentation plan, generating synthetic records via LLM.

    *on_record*: optional ``Callable[[TrainingPoolRecord], None]`` invoked
    immediately after each successful generation — use it for incremental
    persistence so progress is never lost on timeout/crash.

    *concurrency*: max parallel LLM calls (default 10).

    Returns (records, usage_totals) where usage_totals has accumulated tokens.
    """
    import asyncio as _asyncio

    records: list[TrainingPoolRecord] = []
    usage_totals: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    total_items = sum(item["count"] for item in plan)
    generated = 0
    lock = _asyncio.Lock()
    sem = _asyncio.Semaphore(concurrency)

    async def _generate_one(item: dict[str, Any]) -> None:
        nonlocal generated
        domain = item["business_domain"]
        doc_type = item["document_type"]
        async with sem:
            try:
                text, usage = await generate_synthetic_text(
                    business_domain=domain,
                    document_type=doc_type,
                    domain_aliases=item.get("domain_aliases"),
                    domain_scope=item.get("domain_scope", ""),
                    domain_topics=item.get("domain_topics"),
                    doc_type_aliases=item.get("doc_type_aliases"),
                    provider=provider,
                    model=model,
                    api_key=api_key,
                )
                if text:
                    record = build_synthetic_record(
                        business_domain=domain,
                        document_type=doc_type,
                        synthetic_text=text,
                    )
                    async with lock:
                        records.append(record)
                        usage_totals["input_tokens"] += usage.get("input_tokens", 0)
                        usage_totals["output_tokens"] += usage.get("output_tokens", 0)
                    if on_record:
                        on_record(record)
            except Exception:
                pass  # skip failed generations, don't break the batch
            async with lock:
                generated += 1
            if progress_callback:
                progress_callback({
                    "phase": "augmentation",
                    "progress_current": generated,
                    "progress_total": total_items,
                })

    # Flatten plan into individual tasks
    tasks: list[_asyncio.Task[None]] = []
    for item in plan:
        for _ in range(item["count"]):
            tasks.append(_asyncio.create_task(_generate_one(item)))

    await _asyncio.gather(*tasks)
    return records, usage_totals
