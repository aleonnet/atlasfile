from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.classifier_registry import load_classifier_registry, load_classifier_report  # noqa: E402


def main() -> int:
    registry = load_classifier_registry()
    report = load_classifier_report(registry.latest_report_id)
    payload = {
        "registry": registry.model_dump(mode="json"),
        "latest_report_summary": ((report or {}).get("champion") or {}).get("summary"),
        "latest_report_id": registry.latest_report_id,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
