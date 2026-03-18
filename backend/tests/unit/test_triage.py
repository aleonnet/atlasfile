from __future__ import annotations

import json
from pathlib import Path

from app.triage import list_pending


def test_list_pending_ignores_real_json_documents_in_pending(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    pending_dir = project_root / "_TRIAGE_REVIEW" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    real_json_doc = pending_dir / "mapeamento_visoes_analiticas.json"
    real_json_doc.write_text(
        json.dumps({"descricao": "documento json real", "campos": ["a", "b"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    metadata_path = pending_dir / "doc-1.json"
    metadata_path.write_text(
        json.dumps(
            {
                "doc_id": "doc-1",
                "filename": real_json_doc.name,
                "project_id": "proj",
                "suggested_business_domain": "operacoes",
                "suggested_document_type": "relatorio",
                "confidence_score": 0.72,
                "reason": "triage_pending",
                "top_candidates": [{"business_domain": "operacoes", "score": 0.72}],
                "source_path": str(real_json_doc),
                "metadata_path": str(metadata_path),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    items = list_pending(project_root)

    assert len(items) == 1
    assert items[0].doc_id == "doc-1"
    assert items[0].filename == "mapeamento_visoes_analiticas.json"
    assert real_json_doc.exists()
