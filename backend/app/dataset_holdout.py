"""
Hold-out operacional dos datasets do classificador.

Fecha o gap "Validation set has no labeled entries": as decisões HUMANAS
(triagem approve/correct e move) deixam de alimentar só o training pool — uma
fração determinística (por SHA256) vira validação JÁ ROTULADA, com regra
semente para o primeiro ciclo e warm-up por classe para não drenar a
elegibilidade do sparse. Docs auto-roteados ficam fora dos dois datasets
(rótulo de máquina: self-training congela erros e infla métrica).
"""
from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path
from typing import Any

from .classifier_supervised import compute_supervised_gate
from .config import settings
from .evaluation_dataset import (
    TrainingPoolRecord,
    ValidationSetEntry,
    append_training_pool_record,
    classifier_datasets_root,
    dataset_relative_path,
    load_split_as_validation_entries,
    load_training_pool_records,
    load_validation_set,
    materialize_training_pool_snapshot,
    save_training_pool_records,
    save_validation_set,
    splits_available,
    stage_validation_files,
    training_pool_files_dir,
    validation_sha_index,
)
from .utils import sha256_file

# Serializa read-modify-write de expected.json / records.jsonl entre triagem
# concorrente e backfill (o ciclo apenas lê).
_DATASET_LOCK = threading.Lock()


def _holdout_modulus() -> int:
    return int(getattr(settings, "classifier_holdout_modulus", 5) or 0)


def _min_train_per_class() -> int:
    return int(getattr(settings, "classifier_holdout_min_train_per_class", 3) or 0)


def should_hold_out(sha256_hex: str, *, modulus: int | None = None) -> bool:
    """Determinístico por conteúdo: o mesmo arquivo cai sempre no mesmo lado."""
    mod = _holdout_modulus() if modulus is None else modulus
    if mod <= 0:
        return False
    try:
        return int(sha256_hex, 16) % mod == 0
    except (TypeError, ValueError):
        return False


def training_pool_sha_index() -> set[str]:
    return {r.sha256 for r in load_training_pool_records() if r.sha256}


def _labeled_validation_count(entries: list[ValidationSetEntry]) -> int:
    return sum(1 for e in entries if e.is_labeled())


def add_labeled_validation_entry(
    *,
    source_path: Path,
    business_domain: str,
    document_type: str,
    topics: list[str] | None = None,
    entities: list[dict] | None = None,
    notes: str = "",
) -> ValidationSetEntry:
    """Copia o arquivo para validation_set/files/ e grava a entry rotulada."""
    staged = stage_validation_files([source_path])
    if not staged:
        raise FileNotFoundError(source_path)
    staged_name = staged[0].name
    entries = load_validation_set()
    # Constructor valida (entities podem chegar como dicts); model_copy não validaria.
    updated = ValidationSetEntry(
        file=staged_name,
        business_domain=business_domain,
        document_type=document_type,
        topics=list(topics or []),
        entities=list(entities or []),
        notes=notes,
    )
    for i, entry in enumerate(entries):
        if entry.file == staged_name:
            entries[i] = updated
            break
    else:
        entries.append(updated)
    save_validation_set(entries)
    return updated


def _update_validation_labels_by_sha(
    sha: str, *, business_domain: str, document_type: str, notes: str
) -> list[str]:
    """Decisão humana sobre arquivo já reservado à validação atualiza o ground truth."""
    files = validation_sha_index(include_unlabeled=True).get(sha, [])
    if not files:
        return []
    entries = load_validation_set()
    for i, entry in enumerate(entries):
        if entry.file in files:
            entries[i] = entry.model_copy(
                update={"business_domain": business_domain, "document_type": document_type, "notes": notes}
            )
    save_validation_set(entries)
    return sorted(files)


def route_labeled_document(
    *,
    source_path: Path,
    doc_id: str,
    project_id: str,
    original_filename: str,
    business_domain: str,
    document_type: str,
    decision: str,
    topics: list,
    entities: list,
    notes: str = "",
) -> dict[str, Any]:
    """Roteia uma decisão humana para treino OU validação. Retorna payload com
    as chaves training_pool_* existentes + dataset_route."""
    with _DATASET_LOCK:
        sha = sha256_file(source_path)

        # 1. Já reservado à validação → atualizar labels (humano é ground truth)
        validation_files = _update_validation_labels_by_sha(
            sha, business_domain=business_domain, document_type=document_type, notes=notes
        )
        if validation_files:
            return {
                "dataset_route": "validation_updated",
                "training_pool_status": "skipped_overlap_with_validation_set",
                "training_pool_validation_files": validation_files,
            }

        def _append_training() -> dict[str, Any]:
            snapshot_path, snapshot_sha = materialize_training_pool_snapshot(
                source_path=source_path, doc_id=doc_id, original_filename=original_filename
            )
            append_training_pool_record(
                TrainingPoolRecord(
                    doc_id=doc_id,
                    project_id=project_id,
                    original_filename=original_filename,
                    path=dataset_relative_path(snapshot_path),
                    source_path=str(source_path),
                    business_domain=business_domain,
                    document_type=document_type,
                    decision=decision,
                    sha256=snapshot_sha,
                    topics=list(topics or []),
                    entities=list(entities or []),
                    notes=notes,
                )
            )
            return {
                "dataset_route": "training",
                "training_pool_status": "appended",
                "training_pool_record_path": dataset_relative_path(snapshot_path),
                "training_pool_sha256": snapshot_sha,
            }

        records = load_training_pool_records()

        # 2. Já no treino → permanece (migrar para validação seria leakage)
        if sha in {r.sha256 for r in records if r.sha256}:
            return _append_training()

        # 3. Semente ANTES do warm-up: o primeiro ciclo só precisa de 1 doc rotulado
        # na validação, e o warm-up protege o sparse — que exige 100 docs e é
        # irrelevante em coleções pequenas. A partir da 2ª decisão humana, uma vai
        # para a validação. (modulus <= 0 desliga o hold-out inteiro, semente incluída.)
        if _holdout_modulus() > 0 and records and _labeled_validation_count(load_validation_set()) == 0:
            entry = add_labeled_validation_entry(
                source_path=source_path,
                business_domain=business_domain,
                document_type=document_type,
                topics=list(topics or []),
                entities=[e if isinstance(e, dict) else dict(e) for e in (entities or [])],
                notes=notes,
            )
            return {
                "dataset_route": "validation",
                "training_pool_status": "held_out_for_validation",
                "training_pool_validation_files": [entry.file],
            }

        # 4. Warm-up: primeiros N por classe alimentam a elegibilidade do sparse
        min_per_class = _min_train_per_class()
        if min_per_class > 0:
            bd_counts = Counter(r.business_domain.strip() for r in records if r.business_domain.strip())
            dt_counts = Counter(r.document_type.strip() for r in records if r.document_type.strip())
            if bd_counts.get(business_domain.strip(), 0) < min_per_class or dt_counts.get(
                document_type.strip(), 0
            ) < min_per_class:
                return _append_training()

        # 5. Módulo determinístico → validação
        if _holdout_modulus() > 0 and should_hold_out(sha):
            entry = add_labeled_validation_entry(
                source_path=source_path,
                business_domain=business_domain,
                document_type=document_type,
                topics=list(topics or []),
                entities=[e if isinstance(e, dict) else dict(e) for e in (entities or [])],
                notes=notes,
            )
            return {
                "dataset_route": "validation",
                "training_pool_status": "held_out_for_validation",
                "training_pool_validation_files": [entry.file],
            }

        return _append_training()


def backfill_validation_from_training_pool(
    *,
    dry_run: bool = False,
    target_fraction: float = 0.2,
    min_remaining_per_class: int = 2,
) -> dict[str, Any]:
    """Move ~target_fraction do training pool para o validation set (estratificado
    por business_domain), sem nunca deixar classe elegível abaixo de
    min_remaining_per_class no treino. Idempotente: SHAs já na validação são pulados."""
    with _DATASET_LOCK:
        records = load_training_pool_records()
        validation_shas = set(validation_sha_index(include_unlabeled=True))
        # Idempotência: a quota mira a fração do TOTAL da classe (treino + já em
        # validação) — senão cada chamada drenaria ~20% do restante.
        validation_bd_counts = Counter(
            e.business_domain.strip() for e in load_validation_set() if e.is_labeled()
        )

        by_bd: dict[str, list[TrainingPoolRecord]] = {}
        for record in records:
            by_bd.setdefault(record.business_domain.strip(), []).append(record)

        dt_counts = Counter(r.document_type.strip() for r in records if r.document_type.strip())

        selected: list[TrainingPoolRecord] = []
        skipped: list[dict[str, str]] = []
        per_class: dict[str, int] = {}
        for bd, group in sorted(by_bd.items()):
            if len(group) < 3:
                continue  # classes pequenas não cedem nada
            already_held = validation_bd_counts.get(bd, 0)
            quota = int((len(group) + already_held) * target_fraction) - already_held
            quota = min(quota, max(0, len(group) - min_remaining_per_class))
            if quota <= 0:
                continue
            # Determinístico: primeiro quem o módulo escolheria, depois SHA lex.
            candidates = sorted(
                (r for r in group if r.sha256 and r.sha256 not in validation_shas),
                key=lambda r: (not should_hold_out(r.sha256), r.sha256),
            )
            taken = 0
            for record in candidates:
                if taken >= quota:
                    break
                # Não drenar document_type abaixo do mínimo de elegibilidade
                if dt_counts.get(record.document_type.strip(), 0) <= min_remaining_per_class:
                    continue
                selected.append(record)
                dt_counts[record.document_type.strip()] -= 1
                taken += 1
            if taken:
                per_class[bd] = taken

        # Fallback de emergência: validação rotulada vazia e nenhuma classe cede
        # (todas pequenas) → mover 1 registro mesmo assim destrava o primeiro ciclo
        # (bootstrap/llm avaliam com 1; o gate do sparse é irrelevante nessa escala).
        if not selected and sum(validation_bd_counts.values()) == 0 and len(records) >= 2:
            candidates = sorted(
                (r for r in records if r.sha256 and r.sha256 not in validation_shas),
                key=lambda r: (not should_hold_out(r.sha256), r.sha256),
            )
            if candidates:
                fallback = candidates[0]
                selected.append(fallback)
                per_class[fallback.business_domain.strip()] = 1

        moved = 0
        if not dry_run:
            moved_ids: set[str] = set()
            for record in selected:
                source = classifier_datasets_root() / record.path
                if not source.is_file():
                    fallback = Path(record.source_path) if record.source_path else None
                    if fallback is None or not fallback.is_file():
                        skipped.append({"doc_id": record.doc_id, "reason": "arquivo não encontrado (snapshot e source_path)"})
                        continue
                    source = fallback
                add_labeled_validation_entry(
                    source_path=source,
                    business_domain=record.business_domain,
                    document_type=record.document_type,
                    topics=list(record.topics or []),
                    entities=[e.model_dump() for e in (record.entities or [])],
                    notes=(record.notes + " | backfill:validation").strip(" |"),
                )
                snapshot = classifier_datasets_root() / record.path
                if snapshot.is_file() and snapshot.resolve().is_relative_to(training_pool_files_dir().resolve()):
                    snapshot.unlink(missing_ok=True)
                moved_ids.add(record.doc_id + record.sha256)
                moved += 1
            if moved_ids:
                remaining = [r for r in records if (r.doc_id + r.sha256) not in moved_ids]
                save_training_pool_records(remaining)
        else:
            moved = len(selected)

        entries = load_validation_set()
        return {
            "dry_run": dry_run,
            "moved": moved,
            "per_class": per_class,
            "skipped": skipped,
            "validation_labeled_total": _labeled_validation_count(entries),
            "training_total": len(load_training_pool_records()),
        }


def dataset_readiness() -> dict[str, Any]:
    """Prontidão dos datasets para o ciclo — consumido pela UI e pelo pré-check do POST."""
    use_splits = splits_available()
    if use_splits:
        split_entries = load_split_as_validation_entries("validation")
        validation_labeled = sum(1 for e in split_entries if e.is_labeled())
        validation_unlabeled = len(split_entries) - validation_labeled
    else:
        entries = load_validation_set()
        validation_labeled = _labeled_validation_count(entries)
        validation_unlabeled = len(entries) - validation_labeled

    records = load_training_pool_records()
    bd_counts = Counter(r.business_domain.strip() for r in records if r.business_domain.strip())
    dt_counts = Counter(r.document_type.strip() for r in records if r.document_type.strip())
    gate = compute_supervised_gate(records)

    cycle_ready = validation_labeled > 0
    blockers: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []

    if not cycle_ready:
        preview = backfill_validation_from_training_pool(dry_run=True)
        would_move = int(preview.get("moved", 0))
        if would_move > 0:
            # Auto-cura: o POST do ciclo reserva sozinho antes de rodar — não há
            # decisão do usuário aqui, então nada de botão extra nem bloqueio.
            cycle_ready = True
            suggestions.append(
                {
                    "code": "auto_backfill_on_run",
                    "params": {"would_move": would_move},
                    "message": (
                        f"Ao rodar o ciclo, {would_move} documento(s) do treino serão reservados "
                        "automaticamente para validação."
                    ),
                }
            )
        else:
            blockers.append(
                {
                    "code": "validation_empty",
                    "message": (
                        "O conjunto de validação não tem documentos rotulados. Aprove ou corrija "
                        "documentos na triagem — a partir da 2ª decisão, uma passa a compor a "
                        "validação automaticamente."
                    ),
                }
            )

    if not gate.get("eligible", False) and records:
        suggestions.append(
            {
                "code": "sparse_gate_not_met",
                "message": (
                    f"Benchmark sparse será pulado: são necessários 100 documentos de treino "
                    f"(há {len(records)})."
                ),
            }
        )

    return {
        "cycle_ready": cycle_ready,
        "splits_available": use_splits,
        "validation": {"labeled": validation_labeled, "unlabeled": validation_unlabeled},
        "training": {
            "records": len(records),
            "business_domain_classes": dict(bd_counts),
            "document_type_classes": dict(dt_counts),
        },
        "supervised_gate": {
            "eligible": bool(gate.get("eligible", False)),
            "reasons": list(gate.get("reasons", [])),
            "warnings": list(gate.get("warnings", [])),
        },
        "holdout": {
            "enabled": _holdout_modulus() > 0,
            "modulus": _holdout_modulus(),
            "min_train_per_class": _min_train_per_class(),
        },
        "blockers": blockers,
        "suggestions": suggestions,
    }
