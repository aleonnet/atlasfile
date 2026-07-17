#!/usr/bin/env python3
"""Reconcilia rótulos de classificação por SHA256 (consenso + arbitragem).

Motivação: o mesmo arquivo (SHA) pode ter rótulos divergentes entre
training_pool, validation_set e as árvores 02_AREAS dos projetos — hoje o
build_corpus resolve silenciosamente ("último ganha"). Este script torna o
conflito explícito e o resolve com proveniência registrada:

- unanimidade entre as fontes           → canônico direto  (labeled_by=consensus)
- conflito + LLM concorda com 1 fonte   → canônico         (labeled_by=llm_consensus)
- conflito + LLM diverge de todas       → pending_human    (arbitragem no relatório)

O LLM é PROPONENTE com justificativa, nunca ground truth cego.

Uso:
    PROJECTS_ROOT=/path OPENAI_API_KEY=sk-... \
        python scripts/reconcile_labels.py                 # detecta + propõe (sem gravar datasets)
    python scripts/reconcile_labels.py --apply             # aplica canônicos aos datasets + regenera corpus/splits
    python scripts/reconcile_labels.py --rehome-projects   # dry-run dos moves em 02_AREAS
    python scripts/reconcile_labels.py --rehome-apply      # executa os moves via API (índice + training pool)

Outputs em {datasets}/: label_reconciliation.jsonl, label_conflicts_report.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.document_extractor import extract_document_content
from app.evaluation_dataset import (
    classifier_datasets_root,
    load_training_pool_records,
    load_validation_set,
    save_validation_set,
    training_pool_files_dir,
    training_pool_records_path,
    validation_set_files_dir,
)
from app.training_usage import generate_run_id, persist_training_usage
from app.utils import sha256_file, utc_now_iso

DEFAULT_MODEL = "gpt-5.1"


# ── Núcleo puro (testável sem I/O) ──────────────────────────────────────────


@dataclass
class LabelObservation:
    sha256: str
    business_domain: str
    document_type: str
    source: str  # training_pool | validation_set | project_tree
    ref: str  # filename / path / project
    authoritative: bool = True  # project_tree é observacional (peso menor)


@dataclass
class ShaResolution:
    sha256: str
    refs: list[str]
    options: list[tuple[str, str]]  # pares (bd, dt) distintos observados
    canonical_business_domain: str = ""
    canonical_document_type: str = ""
    labeled_by: str = ""  # consensus | llm_consensus | pending_human | human
    llm_proposal: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)


def group_observations(observations: list[LabelObservation]) -> dict[str, list[LabelObservation]]:
    grouped: dict[str, list[LabelObservation]] = defaultdict(list)
    for obs in observations:
        if obs.sha256 and obs.business_domain and obs.document_type:
            grouped[obs.sha256].append(obs)
    return dict(grouped)


def distinct_options(group: list[LabelObservation]) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    for obs in group:
        pair = (obs.business_domain, obs.document_type)
        if pair not in seen:
            seen.append(pair)
    return seen


def resolve_sha(sha: str, group: list[LabelObservation], llm_fn) -> ShaResolution:
    """Resolve um SHA: unanimidade → consensus; conflito → LLM propõe.

    `llm_fn(sha, group) -> dict` com business_domain/document_type/confidence/
    justificativa (ou {} para pular). Injetável para teste.
    """
    resolution = ShaResolution(
        sha256=sha,
        refs=sorted({obs.ref for obs in group}),
        options=distinct_options(group),
        sources=[
            {
                "source": obs.source,
                "ref": obs.ref,
                "business_domain": obs.business_domain,
                "document_type": obs.document_type,
                "authoritative": obs.authoritative,
            }
            for obs in group
        ],
    )

    # Unanimidade entre fontes AUTORITATIVAS decide; observacionais só
    # participam quando não há fonte autoritativa para o SHA.
    authoritative = [o for o in group if o.authoritative]
    deciding = authoritative or group
    deciding_options = distinct_options(deciding)

    if len(deciding_options) == 1:
        bd, dt = deciding_options[0]
        resolution.canonical_business_domain = bd
        resolution.canonical_document_type = dt
        resolution.labeled_by = "consensus"
        return resolution

    proposal = llm_fn(sha, group) or {}
    resolution.llm_proposal = proposal
    llm_pair = (proposal.get("business_domain", ""), proposal.get("document_type", ""))
    if llm_pair in deciding_options:
        resolution.canonical_business_domain = llm_pair[0]
        resolution.canonical_document_type = llm_pair[1]
        resolution.labeled_by = "llm_consensus"
    else:
        resolution.labeled_by = "pending_human"
    return resolution


# ── Coleta de fontes ────────────────────────────────────────────────────────


def collect_training_observations() -> list[LabelObservation]:
    observations: list[LabelObservation] = []
    for record in load_training_pool_records():
        sha = record.sha256
        if not sha:
            candidate = training_pool_files_dir() / Path(record.path or "").name
            if candidate.exists():
                sha = sha256_file(candidate)
        if sha:
            observations.append(
                LabelObservation(
                    sha256=sha,
                    business_domain=record.business_domain,
                    document_type=record.document_type,
                    source="training_pool",
                    ref=record.original_filename or record.doc_id,
                )
            )
    return observations


def collect_validation_observations() -> list[LabelObservation]:
    observations: list[LabelObservation] = []
    files_dir = validation_set_files_dir()
    for entry in load_validation_set():
        if not entry.is_labeled():
            continue
        path = files_dir / entry.file
        if not path.exists():
            continue
        observations.append(
            LabelObservation(
                sha256=sha256_file(path),
                business_domain=entry.business_domain,
                document_type=entry.document_type,
                source="validation_set",
                ref=entry.file,
            )
        )
    return observations


def collect_project_tree_observations(projects_root: Path) -> list[LabelObservation]:
    """Rótulos implícitos nos paths 02_AREAS/{bd}/{dt}/ (observacional)."""
    observations: list[LabelObservation] = []
    if not projects_root.is_dir():
        return observations
    for project_dir in sorted(projects_root.iterdir()):
        areas = project_dir / "02_AREAS"
        if project_dir.name.startswith("_") or not areas.is_dir():
            continue
        for file_path in areas.rglob("*"):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            relative = file_path.relative_to(areas)
            if len(relative.parts) < 3:  # {bd}/{dt}/arquivo
                continue
            observations.append(
                LabelObservation(
                    sha256=sha256_file(file_path),
                    business_domain=relative.parts[0],
                    document_type=relative.parts[1],
                    source="project_tree",
                    ref=f"{project_dir.name}/{relative}",
                    authoritative=False,
                )
            )
    return observations


# ── LLM proponente (reusa plumbing do label_corpus_llm) ─────────────────────


def _classify_with_model(client, model: str, system_prompt: str, filename: str, text_excerpt: str) -> dict:
    """Como label_corpus_llm._classify_one, mas compatível com modelos reasoning
    (gpt-5.x exige max_completion_tokens e temperature default)."""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Documento: {filename}\n\nConteúdo extraído:\n{text_excerpt[:20000]}"},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=2000,
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


def make_llm_resolver(model: str, dry_run: bool):
    from label_corpus_llm import _SYSTEM_PROMPT, _build_taxonomy

    if dry_run:
        return lambda sha, group: {}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY não definido (necessário para arbitrar conflitos)", file=sys.stderr)
        sys.exit(1)
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    domain_list, type_list = _build_taxonomy()
    system_prompt = _SYSTEM_PROMPT.format(domain_list=domain_list, type_list=type_list)
    run_id = generate_run_id()

    def _find_file(group: list[LabelObservation]) -> Path | None:
        for obs in group:
            if obs.source == "training_pool":
                for candidate in training_pool_files_dir().glob(f"*{Path(obs.ref).stem}*"):
                    return candidate
            if obs.source == "validation_set":
                candidate = validation_set_files_dir() / obs.ref
                if candidate.exists():
                    return candidate
            if obs.source == "project_tree":
                projects_root = Path(os.environ.get("PROJECTS_ROOT") or os.environ.get("PROJECTS_HOST_ROOT") or "")
                candidate = projects_root / obs.ref.split("/", 1)[0] / "02_AREAS" / obs.ref.split("/", 1)[1]
                if candidate.exists():
                    return candidate
        return None

    def resolver(sha: str, group: list[LabelObservation]) -> dict:
        file_path = _find_file(group)
        if file_path is None:
            return {}
        try:
            extracted = extract_document_content(file_path, max_chars=20000)
        except Exception:
            return {}
        result = _classify_with_model(client, model, system_prompt, file_path.name, extracted.text_excerpt or "")
        usage = result.pop("_usage", {})
        try:
            persist_training_usage(
                script_name="reconcile_labels",
                run_id=run_id,
                provider="openai",
                model=model,
                usage=usage,
                records_processed=1,
            )
        except Exception:
            pass  # fora do container o OpenSearch pode não estar acessível; custo não bloqueia
        return result

    return resolver


# ── Outputs ─────────────────────────────────────────────────────────────────


def write_outputs(resolutions: list[ShaResolution]) -> tuple[Path, Path]:
    ds_root = classifier_datasets_root()
    jsonl_path = ds_root / "label_reconciliation.jsonl"
    report_path = ds_root / "label_conflicts_report.md"

    with jsonl_path.open("w", encoding="utf-8") as fh:
        for res in resolutions:
            fh.write(
                json.dumps(
                    {
                        "sha256": res.sha256,
                        "refs": res.refs,
                        "canonical_business_domain": res.canonical_business_domain,
                        "canonical_document_type": res.canonical_document_type,
                        "labeled_by": res.labeled_by,
                        "llm_proposal": res.llm_proposal,
                        "sources": res.sources,
                        "reconciled_at": utc_now_iso(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    pending = [r for r in resolutions if r.labeled_by == "pending_human"]
    resolved_llm = [r for r in resolutions if r.labeled_by == "llm_consensus"]
    lines = [
        "# Relatório de conflitos de rótulo (reconciliação por SHA256)",
        "",
        f"Gerado em {utc_now_iso()}. Total de SHAs: {len(resolutions)} — "
        f"consenso: {sum(1 for r in resolutions if r.labeled_by == 'consensus')}, "
        f"resolvidos pelo LLM: {len(resolved_llm)}, pendentes de arbitragem humana: {len(pending)}.",
        "",
    ]
    if resolved_llm:
        lines += ["## Resolvidos por LLM (concordou com uma das fontes)", ""]
        for res in resolved_llm:
            lines += [
                f"### `{res.refs[0]}`",
                f"- opções observadas: {', '.join(f'`{bd}/{dt}`' for bd, dt in res.options)}",
                f"- canônico: **`{res.canonical_business_domain}/{res.canonical_document_type}`** "
                f"(conf {res.llm_proposal.get('confidence', '—')})",
                f"- justificativa: {res.llm_proposal.get('justificativa', '—')}",
                "",
            ]
    if pending:
        lines += [
            "## Pendentes de arbitragem humana",
            "",
            "Edite `resolution:` com `business_domain/document_type` e rode `--apply`.",
            "",
        ]
        for res in pending:
            lines += [
                f"### sha `{res.sha256[:12]}` — `{res.refs[0]}`",
                f"- fontes: "
                + "; ".join(f"{s['source']}({s['ref']})=`{s['business_domain']}/{s['document_type']}`" for s in res.sources),
                f"- proposta LLM: `{res.llm_proposal.get('business_domain', '—')}/{res.llm_proposal.get('document_type', '—')}` "
                f"(conf {res.llm_proposal.get('confidence', '—')}) — {res.llm_proposal.get('justificativa', 'sem proposta')}",
                "- resolution: ",
                "",
            ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jsonl_path, report_path


def parse_human_resolutions(report_path: Path) -> dict[str, tuple[str, str]]:
    """Lê `resolution: bd/dt` preenchidos no relatório (por prefixo de sha)."""
    if not report_path.exists():
        return {}
    resolutions: dict[str, tuple[str, str]] = {}
    current_sha = ""
    for line in report_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### sha `"):
            current_sha = line.split("`")[1]
        elif line.strip().startswith("- resolution:") and current_sha:
            value = line.split(":", 1)[1].strip().strip("`")
            if "/" in value:
                bd, dt = value.split("/", 1)
                resolutions[current_sha] = (bd.strip(), dt.strip())
    return resolutions


# ── Apply ───────────────────────────────────────────────────────────────────


def apply_canonical(resolutions: list[ShaResolution]) -> None:
    canonical = {r.sha256: r for r in resolutions if r.canonical_business_domain}

    # validation_set/expected.json
    files_dir = validation_set_files_dir()
    entries = load_validation_set()
    changed_validation = 0
    for entry in entries:
        path = files_dir / entry.file
        if not path.exists():
            continue
        res = canonical.get(sha256_file(path))
        if not res:
            continue
        if (entry.business_domain, entry.document_type) != (
            res.canonical_business_domain,
            res.canonical_document_type,
        ):
            entry.business_domain = res.canonical_business_domain
            entry.document_type = res.canonical_document_type
            entry.notes = (entry.notes + f" | reconciled:{res.labeled_by}").strip(" |")
            changed_validation += 1
    if changed_validation:
        save_validation_set(entries)
    print(f"validation_set: {changed_validation} rótulo(s) atualizado(s)")

    # training_pool/records.jsonl — reescreve records divergentes
    records = load_training_pool_records()
    changed_training = 0
    for record in records:
        res = canonical.get(record.sha256)
        if not res:
            continue
        if (record.business_domain, record.document_type) != (
            res.canonical_business_domain,
            res.canonical_document_type,
        ):
            record.business_domain = res.canonical_business_domain
            record.document_type = res.canonical_document_type
            record.notes = (record.notes + f" | reconciled:{res.labeled_by}").strip(" |")
            changed_training += 1
    if changed_training:
        with training_pool_records_path().open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(record.model_dump_json() + "\n")
    print(f"training_pool: {changed_training} record(s) atualizado(s)")

    # Regenera derivados
    scripts_dir = Path(__file__).resolve().parent
    for script in ("build_corpus.py", "build_splits.py"):
        print(f"Regenerando via {script}...")
        subprocess.run([sys.executable, str(scripts_dir / script)], check=True)


# ── Rehome (02_AREAS ↔ canônico) ────────────────────────────────────────────


def rehome_projects(resolutions: list[ShaResolution], projects_root: Path, api_base: str, apply: bool) -> None:
    canonical = {r.sha256: r for r in resolutions if r.canonical_business_domain}
    moves: list[dict] = []
    for obs in collect_project_tree_observations(projects_root):
        res = canonical.get(obs.sha256)
        if not res:
            continue
        if (obs.business_domain, obs.document_type) == (
            res.canonical_business_domain,
            res.canonical_document_type,
        ):
            continue
        project_id, rel = obs.ref.split("/", 1)
        moves.append(
            {
                "project_id": project_id,
                "file": rel,
                "from": f"{obs.business_domain}/{obs.document_type}",
                "to": f"{res.canonical_business_domain}/{res.canonical_document_type}",
                "sha256": obs.sha256,
            }
        )
    if not moves:
        print("rehome: nenhum arquivo divergente do canônico nos projetos")
        return
    print(f"rehome: {len(moves)} arquivo(s) divergente(s):")
    for move in moves:
        print(f"  [{move['project_id']}] {move['file']}: {move['from']} → {move['to']}")
    if not apply:
        print("(dry-run — use --rehome-apply para executar via API)")
        return

    for move in moves:
        # resolve doc_id pelo índice (basename do path canônico) e usa o endpoint
        # move (atualiza filesystem + índice + training pool)
        query = urllib.parse.urlencode({"project_id": move["project_id"], "page_size": 200})
        with urllib.request.urlopen(f"{api_base}/api/documents?{query}") as resp:
            docs = json.load(resp)
        target_name = Path(move["file"]).name
        doc = next(
            (d for d in docs.get("items", []) if Path(d.get("path", "")).name == target_name),
            None,
        )
        if not doc:
            print(f"  SKIP (doc não indexado): {move['file']}")
            continue
        bd, dt = move["to"].split("/", 1)
        payload = json.dumps({"target_business_domain": bd, "target_document_type": dt}).encode()
        req = urllib.request.Request(
            f"{api_base}/api/documents/{move['project_id']}/{doc['doc_id']}/move",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.load(resp)
            print(f"  MOVED {move['file']} → {move['to']} ({result.get('status', '?')})")
        except Exception as exc:  # noqa: BLE001 — reporta e segue para os demais
            print(f"  ERRO  {move['file']}: {exc}")


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconciliação de rótulos por SHA256")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Modelo proponente (default {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true", help="Só detectar conflitos (sem LLM)")
    parser.add_argument("--apply", action="store_true", help="Aplicar canônicos aos datasets + regenerar derivados")
    parser.add_argument("--rehome-projects", action="store_true", help="Dry-run dos moves em 02_AREAS")
    parser.add_argument("--rehome-apply", action="store_true", help="Executar os moves via API")
    parser.add_argument("--api-base", default="http://localhost:8000", help="API para o rehome")
    args = parser.parse_args()

    projects_root = Path(os.environ.get("PROJECTS_ROOT") or os.environ.get("PROJECTS_HOST_ROOT") or "")

    observations = (
        collect_training_observations()
        + collect_validation_observations()
        + collect_project_tree_observations(projects_root)
    )
    grouped = group_observations(observations)
    conflicts = {sha: group for sha, group in grouped.items() if len(distinct_options(group)) > 1}
    print(f"SHAs observados: {len(grouped)} | em conflito: {len(conflicts)}")

    # Preserva resoluções já feitas (UI/humano/LLM) — re-executar nunca
    # reabre nem re-arbitra o que já foi decidido.
    prior_path = classifier_datasets_root() / "label_reconciliation.jsonl"
    prior: dict[str, dict] = {}
    if prior_path.exists():
        for line in prior_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                if entry.get("labeled_by") in {"human", "human_confirmed_llm", "llm_consensus"}:
                    prior[entry["sha256"]] = entry

    llm_fn = make_llm_resolver(args.model, dry_run=args.dry_run)

    def resolve_or_preserve(sha: str, group: list[LabelObservation]) -> ShaResolution:
        kept = prior.get(sha)
        if kept and kept.get("canonical_business_domain"):
            res = ShaResolution(
                sha256=sha,
                refs=sorted({obs.ref for obs in group}),
                options=distinct_options(group),
                canonical_business_domain=kept["canonical_business_domain"],
                canonical_document_type=kept["canonical_document_type"],
                labeled_by=kept["labeled_by"],
                llm_proposal=kept.get("llm_proposal", {}),
                sources=[
                    {
                        "source": obs.source,
                        "ref": obs.ref,
                        "business_domain": obs.business_domain,
                        "document_type": obs.document_type,
                        "authoritative": obs.authoritative,
                    }
                    for obs in group
                ],
            )
            return res
        return resolve_sha(sha, group, llm_fn)

    resolutions = [resolve_or_preserve(sha, group) for sha, group in sorted(grouped.items())]

    # Arbitragens humanas previamente preenchidas no relatório
    report_path = classifier_datasets_root() / "label_conflicts_report.md"
    human = parse_human_resolutions(report_path)
    for res in resolutions:
        if res.labeled_by == "pending_human":
            for sha_prefix, (bd, dt) in human.items():
                if res.sha256.startswith(sha_prefix):
                    res.canonical_business_domain = bd
                    res.canonical_document_type = dt
                    res.labeled_by = "human"

    jsonl_path, report_path = write_outputs(resolutions)
    print(f"→ {jsonl_path}\n→ {report_path}")
    for res in resolutions:
        if res.labeled_by in {"llm_consensus", "pending_human", "human"}:
            print(
                f"  [{res.labeled_by}] {res.refs[0][:60]}: "
                f"{' | '.join(f'{bd}/{dt}' for bd, dt in res.options)}"
                + (
                    f" → {res.canonical_business_domain}/{res.canonical_document_type}"
                    if res.canonical_business_domain
                    else ""
                )
            )

    if args.apply:
        apply_canonical(resolutions)
    if args.rehome_projects or args.rehome_apply:
        rehome_projects(resolutions, projects_root, args.api_base, apply=args.rehome_apply)


if __name__ == "__main__":
    main()
