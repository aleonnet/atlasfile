"""v0.46.1 (incidente 2026-07-25): dedup por SHA256 só contra documento VIVO.

Cenários reais do usuário:
1. Doc vivo em TI (resolvido) + tombstone rejected antigo do mesmo sha (429) →
   dedup deve devolver o RESOLVIDO (TI), nunca o tombstone (compliance).
2. Arquivo deletado + reconciliado + re-drop → deve REPROCESSAR (não DUP).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ingestion import _find_original_in_triage

SHA = "a" * 64
PROFILE = {
    "paths": {
        "triage": {
            "pending": "_TRIAGE_REVIEW/pending",
            "resolved": "_TRIAGE_REVIEW/resolved",
            "rejected": "_TRIAGE_REVIEW/rejected",
        }
    }
}


def _write_meta(root: Path, state: str, name: str, payload: dict) -> Path:
    d = root / "_TRIAGE_REVIEW" / state
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_tombstone_rejected_nunca_vale_como_original(tmp_path: Path) -> None:
    _write_meta(tmp_path, "rejected", "tomb.json", {
        "sha256": SHA, "suggested_business_domain": "compliance",
        "business_domain": None, "decision": "orphaned_missing_source",
    })
    assert _find_original_in_triage(tmp_path, PROFILE, SHA) is None


def test_resolved_vivo_ecoa_estado_final(tmp_path: Path) -> None:
    final = tmp_path / "02_AREAS" / "ti" / "relatorio" / "doc__v02.png"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"x")
    # tombstone do mesmo sha convive com o doc vivo — o vivo vence
    _write_meta(tmp_path, "rejected", "tomb.json", {"sha256": SHA, "suggested_business_domain": "compliance"})
    _write_meta(tmp_path, "resolved", "ok.json", {
        "sha256": SHA, "business_domain": "ti", "suggested_business_domain": "compliance",
        "final_path": str(final),
    })
    original = _find_original_in_triage(tmp_path, PROFILE, SHA)
    assert original is not None
    assert original["business_domain"] == "ti"


def test_resolvido_com_arquivo_deletado_reprocessa(tmp_path: Path) -> None:
    """O teste do usuário: deletou o físico, reconciliou, re-drop → não é DUP."""
    _write_meta(tmp_path, "resolved", "ok.json", {
        "sha256": SHA, "business_domain": "ti",
        "final_path": str(tmp_path / "02_AREAS" / "ti" / "apagado.png"),
    })
    assert _find_original_in_triage(tmp_path, PROFILE, SHA) is None


def test_pending_soh_vale_com_arquivo_na_fila(tmp_path: Path) -> None:
    _write_meta(tmp_path, "pending", "meta.json", {"sha256": SHA, "filename": "doc.png"})
    assert _find_original_in_triage(tmp_path, PROFILE, SHA) is None  # meta órfã

    (tmp_path / "_TRIAGE_REVIEW" / "pending" / "doc.png").write_bytes(b"x")
    original = _find_original_in_triage(tmp_path, PROFILE, SHA)
    assert original is not None and original["filename"] == "doc.png"
