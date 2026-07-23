"""Auto-import do conjunto "AtlasFile — Operação" no OpenSearch Dashboards.

O boot da API dispara uma thread daemon que espera o serviço Dashboards ficar
disponível e importa `app/data/dashboards.ndjson` (gerado por
`scripts/build_dashboards_ndjson.py`) via `POST /api/saved_objects/_import`
com `overwrite=true` — idempotente porque todos os objetos têm ids fixos.

Falha aqui NUNCA afeta o startup: o dashboard é conveniência, não dependência.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

NDJSON_PATH = Path(__file__).parent / "data" / "dashboards.ndjson"
IMPORT_ATTEMPTS = 30
IMPORT_DELAY_SECONDS = 5.0


def import_dashboards_once() -> dict[str, Any] | None:
    """Uma tentativa de import. Retorna o resultado do Dashboards, ou None se o
    serviço ainda não respondeu saudável. Exceções sobem para o retry decidir."""
    import httpx

    base = settings.dashboards_url.rstrip("/")
    auth = (settings.opensearch_user, settings.opensearch_password)
    with httpx.Client(auth=auth, timeout=15.0) as client:
        status = client.get(f"{base}/api/status")
        if status.status_code != 200:
            return None
        resp = client.post(
            f"{base}/api/saved_objects/_import",
            params={"overwrite": "true"},
            headers={"osd-xsrf": "true"},
            files={"file": ("dashboards.ndjson", NDJSON_PATH.read_bytes(), "application/ndjson")},
        )
        resp.raise_for_status()
        _ensure_dark_theme_default(client, base)
        return resp.json()


def _ensure_dark_theme_default(client: Any, base: str) -> None:
    """Tema escuro como default de fábrica (identidade dark-first do AtlasFile) —
    mas SÓ quando o usuário nunca mexeu no tema: escolha explícita é respeitada
    em todos os boots seguintes. Falha aqui nunca afeta o import."""
    try:
        current = client.get(f"{base}/api/opensearch-dashboards/settings")
        dark = (current.json().get("settings") or {}).get("theme:darkMode")
        if dark is not None:  # userValue presente = alguém já decidiu — respeitar
            return
        client.post(
            f"{base}/api/opensearch-dashboards/settings",
            headers={"osd-xsrf": "true"},
            json={"changes": {"theme:darkMode": True}},
        )
        logger.info("Tema escuro definido como default do Dashboards")
    except Exception:
        logger.debug("Não foi possível definir o tema default do Dashboards", exc_info=True)


def start_dashboards_import_background() -> threading.Thread | None:
    """Agenda o import em background (o Dashboards sobe mais devagar que a API)."""
    if not settings.dashboards_auto_import:
        return None

    def _run() -> None:
        for attempt in range(1, IMPORT_ATTEMPTS + 1):
            try:
                result = import_dashboards_once()
                if result is not None:
                    logger.info(
                        "Dashboards do AtlasFile importados (%s objetos, tentativa %s)",
                        result.get("successCount"), attempt,
                    )
                    return
            except Exception as exc:  # serviço reiniciando, auth, rede — retry
                logger.debug("Import de dashboards falhou (tentativa %s): %s", attempt, exc)
            time.sleep(IMPORT_DELAY_SECONDS)
        logger.warning(
            "Auto-import de dashboards desistiu após %s tentativas — importe manualmente "
            "(Management → Saved Objects → Import → app/data/dashboards.ndjson)",
            IMPORT_ATTEMPTS,
        )

    thread = threading.Thread(target=_run, name="atlasfile-dashboards-import", daemon=True)
    thread.start()
    return thread
