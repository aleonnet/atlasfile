"""Migração e remoção governada de taxonomia (document_type / business_domain).

Uma key de taxonomia vive em 9 lugares: template default + user templates,
profiles (classification + layout.business_domain_folders + routing_rules),
pastas físicas 02_AREAS/{bd}/{dt}, índice OpenSearch, os 4 arquivos de dataset
do classificador, o artifact sparse (classes assadas — não editado, só avisado),
_INDEX.md, e sugestões pendentes de triagem. Este módulo cobre todos com dois
princípios:

- **dry-run primeiro**: `plan_taxonomy_migration` conta tudo sem tocar nada.
- **sem contaminar o hold-out**: o move em massa NÃO passa por
  `route_labeled_document` (seriam "decisões humanas" falsas em lote); os
  datasets são reescritos in-place por rótulo antigo, zero registros novos.

A key antiga vira alias da nova por default — o bootstrap continua
reconhecendo documentos legados imediatamente.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .classifier_registry import classifier_state_root
from .config import settings
from .evaluation_dataset import (
    classifier_datasets_root,
    load_training_pool_records,
    load_validation_set,
    save_training_pool_records,
    save_validation_set,
)
from .profile_store import load_profile, save_profile
from .project_profile import list_project_roots
from .taxonomy import VALID_KINDS, _slugify_key
from .template_store import get_template, list_templates, save_template
from .triage import triage_pending_dir
from .utils import utc_now_iso

# Enumeração de docs no índice: paginação from/size respeitando o max_result_window
_SEARCH_PAGE_SIZE = 500
_MAX_DOCS_PER_MIGRATION = 9_500

RelocateFn = Callable[..., dict[str, Any]]


class TaxonomyMigrationError(ValueError):
    """Erro de uso (key inexistente, destino inválido, uso ativo na remoção)."""


def _label_field(kind: str) -> str:
    return "document_type" if kind == "document_type" else "business_domain"


def _bucket_name(kind: str) -> str:
    return "document_types" if kind == "document_type" else "business_domains"


def _validate_kind_and_keys(kind: str, from_key: str, to_key: str | None) -> tuple[str, str | None]:
    if kind not in VALID_KINDS:
        raise TaxonomyMigrationError(f"kind inválido: {kind} (use document_type ou business_domain)")
    from_key = _slugify_key(from_key)
    if not from_key:
        raise TaxonomyMigrationError("key de origem vazia")
    if to_key is None:
        return from_key, None
    to_key = _slugify_key(to_key)
    if not to_key or to_key == "outro":
        raise TaxonomyMigrationError("key de destino inválida (vazia ou 'outro')")
    if to_key == from_key:
        raise TaxonomyMigrationError("origem e destino são a mesma key")
    return from_key, to_key


def _find_entry(raw: dict[str, Any], kind: str, key: str) -> dict[str, Any] | None:
    for item in (raw.get("classification") or {}).get(_bucket_name(kind), []) or []:
        if item.get("key") == key:
            return item
    return None


def _default_template_raw() -> dict[str, Any]:
    return get_template("default")["profile"]


# ── Contagens (dry-run e guarda de remoção) ─────────────────────────────────


def _count_index_docs(os_client: Any, kind: str, key: str) -> dict[str, int]:
    """Documentos no índice com a key, agregados por projeto."""
    body = {
        "size": 0,
        "query": {"bool": {"filter": [{"term": {_label_field(kind): key}}]}},
        "aggs": {"por_projeto": {"terms": {"field": "project_id", "size": 200}}},
    }
    try:
        response = os_client.search(index=settings.opensearch_index, body=body)
    except Exception:
        return {}
    buckets = ((response.get("aggregations") or {}).get("por_projeto") or {}).get("buckets", [])
    return {str(b["key"]): int(b["doc_count"]) for b in buckets}


def _count_dataset_records(kind: str, key: str) -> dict[str, int]:
    field = _label_field(kind)
    counts = {
        "training_pool": sum(1 for r in load_training_pool_records() if getattr(r, field) == key),
        "validation_set": sum(
            1 for e in load_validation_set() if getattr(e, field) == key
        ),
    }
    ds_root = classifier_datasets_root()
    for name, path in [
        ("corpus", ds_root / "corpus.jsonl"),
        ("split_train", ds_root / "splits" / "train.jsonl"),
        ("split_validation", ds_root / "splits" / "validation.jsonl"),
        ("split_test", ds_root / "splits" / "test.jsonl"),
    ]:
        total = 0
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip() and json.loads(line).get(field) == key:
                    total += 1
        counts[name] = total
    return counts


def _iter_pending_metas() -> list[tuple[Path, dict[str, Any]]]:
    metas: list[tuple[Path, dict[str, Any]]] = []
    for project_root in list_project_roots(Path(settings.projects_root)):
        pending_dir = triage_pending_dir(project_root)
        if not pending_dir.exists():
            continue
        for meta_path in sorted(pending_dir.glob("*.json")):
            try:
                metas.append((meta_path, json.loads(meta_path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                continue
    return metas


_PENDING_FIELDS = {
    "document_type": ("document_type", "suggested_document_type"),
    "business_domain": ("business_domain", "suggested_business_domain", "llm_proposed_business_domain"),
}


def _count_pending_suggestions(kind: str, key: str) -> int:
    fields = _PENDING_FIELDS[kind]
    return sum(
        1 for _, data in _iter_pending_metas() if any(data.get(f) == key for f in fields)
    )


def _templates_containing(kind: str, key: str) -> list[str]:
    slugs: list[str] = []
    for meta in list_templates():
        slug = str(meta.get("slug") or "")
        if not slug:
            continue
        try:
            raw = get_template(slug)["profile"]
        except Exception:
            continue
        if _find_entry(raw, kind, key) is not None:
            slugs.append(slug)
    return slugs


def _routing_rules_pointing(key: str) -> int:
    """routing_rules com route_to == key (só business_domain) no template default + profiles."""
    total = 0
    sources: list[dict[str, Any]] = []
    try:
        sources.append(_default_template_raw())
    except Exception:
        pass
    for project_root in list_project_roots(Path(settings.projects_root)):
        try:
            sources.append(load_profile(project_root).model_dump(mode="json"))
        except Exception:
            continue
    for raw in sources:
        for rule in (raw.get("classification") or {}).get("routing_rules", []) or []:
            if isinstance(rule, dict) and str(rule.get("route_to") or "") == key:
                total += 1
    return total


def _sparse_champion_has_class(kind: str, key: str) -> bool:
    """True se o artifact sparse atual contém a classe — aviso 'rode um ciclo'."""
    try:
        from .classifier_supervised import load_sparse_artifact

        artifact_path = classifier_state_root() / "models" / "sparse_logreg.pkl"
        if not artifact_path.exists():
            return False
        artifact = load_sparse_artifact(artifact_path)
        model = artifact.get(f"{_label_field(kind)}_model")
        classes = [str(c) for c in getattr(model, "classes_", [])]
        return key in classes
    except Exception:
        return False


def plan_taxonomy_migration(
    *, kind: str, from_key: str, to_key: str, os_client: Any
) -> dict[str, Any]:
    """Dry-run: valida e conta tudo que a migração tocaria. Não muta nada."""
    from_key, to_key = _validate_kind_and_keys(kind, from_key, to_key)
    default_raw = _default_template_raw()
    if _find_entry(default_raw, kind, to_key) is None:
        raise TaxonomyMigrationError(
            f"destino '{to_key}' não existe na taxonomia — crie primeiro (Novo tipo/domínio)"
        )
    templates = _templates_containing(kind, from_key)
    documents = _count_index_docs(os_client, kind, from_key)
    total_docs = sum(documents.values())
    if total_docs > _MAX_DOCS_PER_MIGRATION:
        raise TaxonomyMigrationError(
            f"migração de {total_docs} documentos excede o limite de {_MAX_DOCS_PER_MIGRATION} por execução"
        )

    warnings: list[str] = []
    if not templates and total_docs == 0:
        warnings.append(f"origem '{from_key}' não encontrada em templates nem em documentos")
    if _sparse_champion_has_class(kind, from_key):
        warnings.append(
            "o modelo sparse campeão contém a classe antiga — rode um ciclo do classificador após a migração"
        )

    return {
        "kind": kind,
        "from_key": from_key,
        "to_key": to_key,
        "documents_by_project": documents,
        "documents_total": total_docs,
        "datasets": _count_dataset_records(kind, from_key),
        "pending_triage": _count_pending_suggestions(kind, from_key),
        "templates": templates,
        "routing_rules_pointing": _routing_rules_pointing(from_key) if kind == "business_domain" else 0,
        "warnings": warnings,
    }


# ── Reescritas ──────────────────────────────────────────────────────────────


def _rewrite_jsonl_field(path: Path, field: str, from_key: str, to_key: str) -> int:
    if not path.exists():
        return 0
    changed = 0
    lines_out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get(field) == from_key:
            record[field] = to_key
            changed += 1
        lines_out.append(json.dumps(record, ensure_ascii=False))
    if changed:
        path.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    return changed


def rewrite_dataset_labels(kind: str, from_key: str, to_key: str) -> dict[str, int]:
    """Troca o rótulo antigo pelo novo em TODOS os datasets, in-place por rótulo —
    sem novos registros e sem passar pelo hold-out (não são decisões novas)."""
    field = _label_field(kind)
    counts: dict[str, int] = {}

    records = load_training_pool_records()
    changed = 0
    for record in records:
        if getattr(record, field) == from_key:
            setattr(record, field, to_key)
            record.notes = (record.notes + f" | taxonomy-migrated:{from_key}->{to_key}").strip(" |")
            changed += 1
    if changed:
        save_training_pool_records(records)
    counts["training_pool"] = changed

    entries = load_validation_set()
    changed = 0
    for entry in entries:
        if getattr(entry, field) == from_key:
            setattr(entry, field, to_key)
            entry.notes = (entry.notes + f" | taxonomy-migrated:{from_key}->{to_key}").strip(" |")
            changed += 1
    if changed:
        save_validation_set(entries)
    counts["validation_set"] = changed

    ds_root = classifier_datasets_root()
    counts["corpus"] = _rewrite_jsonl_field(ds_root / "corpus.jsonl", field, from_key, to_key)
    for split in ("train", "validation", "test"):
        counts[f"split_{split}"] = _rewrite_jsonl_field(
            ds_root / "splits" / f"{split}.jsonl", field, from_key, to_key
        )
    return counts


def rewrite_pending_suggestions(kind: str, from_key: str, to_key: str) -> int:
    """Sugestões pendentes de triagem com a key antiga — sem isso, aprovar um
    pendente pós-migração explode no _ensure_*_in_profile."""
    fields = _PENDING_FIELDS[kind]
    changed = 0
    for meta_path, data in _iter_pending_metas():
        touched = False
        for field in fields:
            if data.get(field) == from_key:
                data[field] = to_key
                touched = True
        if touched:
            data["taxonomy_migrated_at"] = utc_now_iso()
            meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            changed += 1
    return changed


def _rename_in_raw(
    raw: dict[str, Any], kind: str, from_key: str, to_key: str, *, remove_old: bool
) -> bool:
    """Remove a entrada antiga (herdando aliases no destino), ajusta layout e
    routing_rules. Retorna True se algo mudou."""
    classification = raw.get("classification") or {}
    bucket = classification.get(_bucket_name(kind), []) or []
    from_entry = next((i for i in bucket if i.get("key") == from_key), None)
    to_entry = next((i for i in bucket if i.get("key") == to_key), None)
    changed = False

    if from_entry is not None and to_entry is not None:
        # Destino herda aliases da origem (a própria key antiga incluída):
        # o bootstrap continua reconhecendo o legado imediatamente.
        merged = {str(a).strip().lower() for a in (to_entry.get("aliases") or []) if str(a).strip()}
        merged |= {str(a).strip().lower() for a in (from_entry.get("aliases") or []) if str(a).strip()}
        merged.add(from_key)
        if sorted(merged) != sorted(to_entry.get("aliases") or []):
            to_entry["aliases"] = sorted(merged)
            changed = True
        if kind == "document_type":
            extensions = {str(e).strip().lstrip(".").lower() for e in (to_entry.get("extensions") or []) if str(e).strip()}
            extensions |= {str(e).strip().lstrip(".").lower() for e in (from_entry.get("extensions") or []) if str(e).strip()}
            if sorted(extensions) != sorted(to_entry.get("extensions") or []):
                to_entry["extensions"] = sorted(extensions)
                changed = True

    if remove_old and from_entry is not None:
        classification[_bucket_name(kind)] = [i for i in bucket if i.get("key") != from_key]
        changed = True

    if kind == "business_domain":
        # routing_rules apontando para a origem → destino (ANTES do filtro
        # silencioso do template_store descartá-las)
        for rule in classification.get("routing_rules", []) or []:
            if isinstance(rule, dict) and str(rule.get("route_to") or "") == from_key:
                rule["route_to"] = to_key
                changed = True
        if remove_old:
            layout = raw.get("layout") or {}
            folders = layout.get("business_domain_folders", []) or []
            kept = [f for f in folders if f.get("business_domain") != from_key]
            if len(kept) != len(folders):
                layout["business_domain_folders"] = kept
                changed = True
    return changed


def rename_in_templates_and_profiles(
    kind: str, from_key: str, to_key: str, *, remove_old: bool
) -> dict[str, list[str]]:
    provenance = f"taxonomy:migrate:{kind}:{from_key}->{to_key} em {utc_now_iso()}"
    updated_templates: list[str] = []
    for meta in list_templates():
        slug = str(meta.get("slug") or "")
        if not slug:
            continue
        try:
            raw = get_template(slug)["profile"]
        except Exception:
            continue
        if _rename_in_raw(raw, kind, from_key, to_key, remove_old=remove_old):
            template_meta = raw.setdefault("template_meta", {})
            template_meta["updated_at"] = utc_now_iso()
            template_meta["notes"] = ((template_meta.get("notes") or "") + " | " + provenance).strip(" |")
            save_template(slug, raw)
            updated_templates.append(slug)

    updated_projects: list[str] = []
    for project_root in list_project_roots(Path(settings.projects_root)):
        try:
            profile = load_profile(project_root)
        except Exception:
            continue
        raw = profile.model_dump(mode="json")
        if _rename_in_raw(raw, kind, from_key, to_key, remove_old=remove_old):
            save_profile(project_root=project_root, profile=raw, updated_by=f"taxonomy:migrate:{from_key}->{to_key}")
            updated_projects.append(raw.get("project_id") or project_root.name)
    return {"templates": updated_templates, "projects": updated_projects}


# ── Apply ───────────────────────────────────────────────────────────────────


def _iter_index_docs(os_client: Any, kind: str, key: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    offset = 0
    while True:
        body = {
            "size": _SEARCH_PAGE_SIZE,
            "from": offset,
            "query": {"bool": {"filter": [{"term": {_label_field(kind): key}}]}},
            "sort": [{"_id": "asc"}],
            "_source": [
                "project_id",
                "path",
                "original_filename",
                "canonical_filename",
                "ingested_at",
                "sha256",
                "business_domain",
                "document_type",
                "source_channel",
                "source_ref",
                "sender",
                "received_at",
                "confidence_score",
                "naming_pattern",
                "entities",
            ],
        }
        response = os_client.search(index=settings.opensearch_index, body=body)
        page = response.get("hits", {}).get("hits", [])
        if not page:
            break
        hits.extend(page)
        offset += len(page)
        if len(page) < _SEARCH_PAGE_SIZE:
            break
    return hits


def apply_taxonomy_migration(
    *,
    kind: str,
    from_key: str,
    to_key: str,
    remove_old: bool = True,
    os_client: Any,
    relocate: RelocateFn,
    load_project_context: Callable[[str], tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    """Executa a migração completa. `relocate` é o _relocate_document do main com
    dataset_routing=False (move físico + reindex + _INDEX.md, SEM hold-out);
    `load_project_context(project_id) -> (project_root, profile_dict)`."""
    plan = plan_taxonomy_migration(kind=kind, from_key=from_key, to_key=to_key, os_client=os_client)
    from_key, to_key = plan["from_key"], plan["to_key"]

    # 1. Taxonomia primeiro: o destino precisa existir em cada profile antes do
    # move (o _ensure_*_in_profile valida) e as regras/aliases já migram juntas.
    taxonomy_result = rename_in_templates_and_profiles(kind, from_key, to_key, remove_old=remove_old)

    # 2. Documentos: move físico + reindex, sem hold-out
    moved: dict[str, int] = {}
    index_only: list[str] = []
    errors: list[dict[str, str]] = []
    contexts: dict[str, tuple[Path, dict[str, Any]]] = {}
    for hit in _iter_index_docs(os_client, kind, from_key):
        doc_id = hit["_id"]
        src = hit.get("_source", {})
        project_id = str(src.get("project_id") or "")
        target_bd = to_key if kind == "business_domain" else str(src.get("business_domain") or "")
        target_dt = to_key if kind == "document_type" else str(src.get("document_type") or "")
        path_str = str(src.get("path") or "")
        source_path = Path(path_str) if path_str else None
        try:
            if project_id not in contexts:
                contexts[project_id] = load_project_context(project_id)
            project_root, profile = contexts[project_id]
            areas_root = str((profile.get("layout") or {}).get("areas_root") or "02_AREAS")
            under_areas = (
                source_path is not None
                and source_path.is_file()
                and str(source_path).startswith(str(project_root / areas_root))
            )
            if under_areas:
                relocate(
                    project_root=project_root,
                    profile=profile,
                    project_id=project_id,
                    doc_id=doc_id,
                    source_path=source_path,
                    target_business_domain=target_bd,
                    target_document_type=target_dt,
                    original_filename=str(src.get("original_filename") or source_path.name),
                    decision="moved",
                    existing_canonical_filename=str(src.get("canonical_filename") or ""),
                    ingested_at=src.get("ingested_at"),
                    sha256=str(src.get("sha256") or ""),
                    extra_metadata={
                        "source_channel": src.get("source_channel", ""),
                        "source_ref": src.get("source_ref", ""),
                        "sender": src.get("sender", ""),
                        "received_at": src.get("received_at"),
                        "confidence_score": src.get("confidence_score", 0.0),
                        "naming_pattern": src.get("naming_pattern"),
                        "entities": src.get("entities", []),
                    },
                    note=f"taxonomy-migrated:{from_key}->{to_key}",
                )
                moved[project_id] = moved.get(project_id, 0) + 1
            else:
                # Fora de 02_AREAS (ex.: 04_ARCHIVE) ou arquivo ausente: só metadados
                os_client.update(
                    index=settings.opensearch_index,
                    id=doc_id,
                    body={"doc": {
                        "business_domain": target_bd,
                        "document_type": target_dt,
                        "tags": [target_bd, target_dt],
                    }},
                )
                index_only.append(doc_id)
        except Exception as exc:  # continua o lote; erros reportados por doc
            errors.append({"doc_id": doc_id, "error": str(exc)[:200]})

    # 3. Datasets por rótulo antigo (in-place, sem hold-out)
    dataset_counts = rewrite_dataset_labels(kind, from_key, to_key)

    # 4. Sugestões pendentes de triagem
    pending_rewritten = rewrite_pending_suggestions(kind, from_key, to_key)

    warnings = list(plan["warnings"])
    if index_only:
        warnings.append(
            f"{len(index_only)} documento(s) fora da área de trabalho (ex.: arquivo/archive) "
            "atualizados só no índice — arquivo físico não movido"
        )

    return {
        "kind": kind,
        "from_key": from_key,
        "to_key": to_key,
        "moved_by_project": moved,
        "moved_total": sum(moved.values()),
        "index_only": len(index_only),
        "errors": errors,
        "datasets": dataset_counts,
        "pending_rewritten": pending_rewritten,
        "templates_updated": taxonomy_result["templates"],
        "projects_updated": taxonomy_result["projects"],
        "warnings": warnings,
    }


# ── Remoção guardada ────────────────────────────────────────────────────────


def remove_taxonomy_entry(*, kind: str, key: str, os_client: Any) -> dict[str, Any]:
    """Remove a entrada dos templates e profiles APENAS quando nada mais a usa —
    documentos, datasets ou pendências apontam para migração antes."""
    key, _ = _validate_kind_and_keys(kind, key, None)
    documents = _count_index_docs(os_client, kind, key)
    datasets = _count_dataset_records(kind, key)
    pending = _count_pending_suggestions(kind, key)
    usage_total = sum(documents.values()) + sum(datasets.values()) + pending
    if usage_total > 0:
        raise TaxonomyMigrationError(
            f"'{key}' ainda é usada por {sum(documents.values())} documento(s), "
            f"{sum(datasets.values())} registro(s) de dataset e {pending} pendência(s) de triagem — "
            "migre para outra key antes de remover"
        )

    updated_templates: list[str] = []
    for meta in list_templates():
        slug = str(meta.get("slug") or "")
        if not slug:
            continue
        try:
            raw = get_template(slug)["profile"]
        except Exception:
            continue
        classification = raw.get("classification") or {}
        bucket = classification.get(_bucket_name(kind), []) or []
        if not any(i.get("key") == key for i in bucket):
            continue
        classification[_bucket_name(kind)] = [i for i in bucket if i.get("key") != key]
        if kind == "business_domain":
            layout = raw.get("layout") or {}
            layout["business_domain_folders"] = [
                f for f in (layout.get("business_domain_folders") or []) if f.get("business_domain") != key
            ]
        template_meta = raw.setdefault("template_meta", {})
        template_meta["updated_at"] = utc_now_iso()
        template_meta["notes"] = (
            (template_meta.get("notes") or "") + f" | taxonomy:removed:{kind}:{key} em {utc_now_iso()}"
        ).strip(" |")
        save_template(slug, raw)
        updated_templates.append(slug)

    updated_projects: list[str] = []
    for project_root in list_project_roots(Path(settings.projects_root)):
        try:
            profile = load_profile(project_root)
        except Exception:
            continue
        raw = profile.model_dump(mode="json")
        classification = raw.get("classification") or {}
        bucket = classification.get(_bucket_name(kind), []) or []
        if not any(i.get("key") == key for i in bucket):
            continue
        classification[_bucket_name(kind)] = [i for i in bucket if i.get("key") != key]
        if kind == "business_domain":
            layout = raw.get("layout") or {}
            layout["business_domain_folders"] = [
                f for f in (layout.get("business_domain_folders") or []) if f.get("business_domain") != key
            ]
        save_profile(project_root=project_root, profile=raw, updated_by=f"taxonomy:remove:{key}")
        updated_projects.append(raw.get("project_id") or project_root.name)

    return {
        "kind": kind,
        "key": key,
        "templates_updated": updated_templates,
        "projects_updated": updated_projects,
    }
