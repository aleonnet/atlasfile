from __future__ import annotations

import json
from pathlib import Path

from app.classification_bootstrap import classify_bootstrap
from app.profile_schema_v2 import ProjectProfileV2
from app.project_profile import profile_v2_to_runtime

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = REPO_ROOT / "config" / "templates"

SPA_EXCERPT = (
    "SHARE PURCHASE AGREEMENT\n"
    "This Share Purchase Agreement is entered into by and between the Sellers "
    "and the Purchaser, for the sale and purchase of all shares of the Company."
)

MINUTES_EXCERPT = (
    "MINUTES OF THE BOARD OF DIRECTORS MEETING\n"
    "Held at the registered office of the Company, the board of directors "
    "approved the corporate governance agenda."
)


def _load_runtime_profile(template_file: str) -> dict:
    raw = json.loads((TEMPLATES_DIR / template_file).read_text(encoding="utf-8"))
    model = ProjectProfileV2.model_validate(raw)
    return profile_v2_to_runtime(model, Path(raw["project_root"]))


def test_default_template_classifies_english_spa_as_contrato() -> None:
    profile = _load_runtime_profile("default.json")

    result = classify_bootstrap(
        profile=profile,
        source_path=Path("Project Neptune - Share Purchase Agreement.pdf"),
        text_excerpt=SPA_EXCERPT,
    )

    assert result["document_type"] == "contrato"
    assert result["confidence"] > 0


def test_default_template_classifies_english_board_minutes_as_ata() -> None:
    profile = _load_runtime_profile("default.json")

    result = classify_bootstrap(
        profile=profile,
        source_path=Path("Board Meeting Minutes 2026-07.pdf"),
        text_excerpt=MINUTES_EXCERPT,
    )

    assert result["document_type"] == "ata"
    assert result["confidence"] > 0


def test_default_en_template_classifies_english_spa_as_contract() -> None:
    profile = _load_runtime_profile("default-en.json")

    result = classify_bootstrap(
        profile=profile,
        source_path=Path("Project Neptune - Share Purchase Agreement.pdf"),
        text_excerpt=SPA_EXCERPT,
    )

    assert result["document_type"] == "contract"
    assert result["confidence"] > 0


def test_default_en_template_classifies_english_board_minutes_as_minutes() -> None:
    profile = _load_runtime_profile("default-en.json")

    result = classify_bootstrap(
        profile=profile,
        source_path=Path("Board Meeting Minutes 2026-07.pdf"),
        text_excerpt=MINUTES_EXCERPT,
    )

    assert result["document_type"] == "minutes"
    assert result["confidence"] > 0
