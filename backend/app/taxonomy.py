"""Criação governada de entradas de taxonomia (document_type / business_domain).

Fluxo: uma sugestão aprovada pelo humano (triagem ou conflito de rótulo) pode
criar o tipo/domínio que ainda não existe — atualizando o template `default`
(persistido em `_ATLASFILE/templates/`, sobrepõe o builtin) e propagando aos
profiles dos projetos inicializados. Proveniência gravada em ambos.

Efeito imediato nos classificadores: `bootstrap` e `llm` leem a taxonomia do
profile em runtime — o novo tipo com aliases já classifica na próxima
ingestão; `sparse_logreg` o aprende no ciclo seguinte, com exemplos.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import settings
from .profile_store import load_profile, save_profile
from .project_profile import list_project_roots
from .template_store import get_template, save_template
from .utils import utc_now_iso

VALID_KINDS = ("document_type", "business_domain")


def _slugify_key(key: str) -> str:
    normalized = key.strip().lower().replace(" ", "_")
    return "".join(ch for ch in normalized if ch.isalnum() or ch == "_")


def _entry_exists(items: list[dict[str, Any]], key: str) -> bool:
    return any(item.get("key") == key for item in items)


def _build_entry(kind: str, key: str, label: str, aliases: list[str], extensions: list[str]) -> dict[str, Any]:
    clean_aliases = sorted({a.strip().lower() for a in [key, *aliases] if a.strip()})
    if kind == "document_type":
        return {
            "key": key,
            "label": label or key,
            "aliases": clean_aliases,
            "extensions": [e.strip().lstrip(".").lower() for e in extensions if e.strip()],
            "folder": key,
            "fallback_priority": 100,
        }
    return {
        "key": key,
        "label": label or key,
        "aliases": clean_aliases,
    }


def _apply_to_classification(raw: dict[str, Any], kind: str, entry: dict[str, Any]) -> bool:
    classification = raw.setdefault("classification", {})
    bucket_name = "document_types" if kind == "document_type" else "business_domains"
    bucket = classification.setdefault(bucket_name, [])
    if _entry_exists(bucket, entry["key"]):
        return False
    bucket.append(entry)
    if kind == "business_domain":
        layout = raw.setdefault("layout", {})
        folders = layout.setdefault("business_domain_folders", [])
        if not any(f.get("business_domain") == entry["key"] for f in folders):
            folders.append({"business_domain": entry["key"], "folder": entry["key"]})
    return True


def create_taxonomy_entry(
    *,
    kind: str,
    key: str,
    label: str = "",
    aliases: list[str] | None = None,
    extensions: list[str] | None = None,
    created_from: str = "",
) -> dict[str, Any]:
    """Cria a entrada no template `default` e propaga aos profiles dos projetos.

    Idempotente por key: onde já existir, não duplica. Retorna o resumo com a
    lista de projetos atualizados.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"kind inválido: {kind} (use document_type ou business_domain)")
    key = _slugify_key(key)
    if not key or key == "outro":
        raise ValueError("key inválida para taxonomia (vazia ou 'outro')")

    entry = _build_entry(kind, key, label.strip(), aliases or [], extensions or [])
    provenance = f"taxonomy:{kind}:{key} criado em {utc_now_iso()}" + (f" a partir de {created_from}" if created_from else "")

    # 1. Template default (persistido no volume; sobrepõe o builtin).
    # get_template retorna {meta..., profile: raw} — o template editável é o "profile".
    template_raw = get_template("default")["profile"]
    template_updated = _apply_to_classification(template_raw, kind, entry)
    if template_updated:
        meta = template_raw.setdefault("template_meta", {})
        meta["updated_at"] = utc_now_iso()
        notes = meta.get("notes") or ""
        meta["notes"] = (notes + " | " + provenance).strip(" |")
        save_template("default", template_raw)

    # 2. Profiles dos projetos inicializados
    updated_projects: list[str] = []
    projects_root = Path(settings.projects_root)
    for project_root in list_project_roots(projects_root):
        try:
            profile = load_profile(project_root)
        except Exception:
            continue
        raw = profile.model_dump(mode="json")
        if not _apply_to_classification(raw, kind, entry):
            continue
        save_profile(project_root=project_root, profile=raw, updated_by=f"taxonomy:{created_from or 'ui'}")
        updated_projects.append(raw.get("project_id") or project_root.name)

    return {
        "kind": kind,
        "key": key,
        "entry": entry,
        "template_updated": template_updated,
        "updated_projects": updated_projects,
    }
