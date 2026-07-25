"""v0.46.1 (incidente 2026-07-25): os DOIS 429 do OpenSearch têm tratamentos opostos."""
from __future__ import annotations

import pytest
from opensearchpy.exceptions import TransportError

from app.indexer import IndexWriteBlockedError, _os_write_with_retry


def test_circuit_breaking_faz_retry_e_recupera(monkeypatch) -> None:
    monkeypatch.setattr("app.indexer._time.sleep", lambda _s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransportError(429, "circuit_breaking_exception", "[parent] Data too large")
        return "ok"

    assert _os_write_with_retry(flaky) == "ok"
    assert calls["n"] == 3


def test_circuit_breaking_persistente_estoura_apos_tentativas(monkeypatch) -> None:
    monkeypatch.setattr("app.indexer._time.sleep", lambda _s: None)

    def always_breaker():
        raise TransportError(429, "circuit_breaking_exception", "[parent] Data too large")

    with pytest.raises(TransportError):
        _os_write_with_retry(always_breaker)


def test_cluster_block_vira_erro_legivel_sem_retry(monkeypatch) -> None:
    calls = {"n": 0}

    def blocked():
        calls["n"] += 1
        raise TransportError(429, "cluster_block_exception", "disk usage exceeded flood-stage watermark")

    with pytest.raises(IndexWriteBlockedError, match="Disco cheio"):
        _os_write_with_retry(blocked)
    assert calls["n"] == 1  # sem retry: disco cheio não melhora esperando


def test_outros_erros_propagam_intactos() -> None:
    def not_found():
        raise TransportError(404, "index_not_found_exception", "no such index")

    with pytest.raises(TransportError):
        _os_write_with_retry(not_found)
