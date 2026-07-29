"""Reconcile de setup: a janela que o laço periódico deixa aberta.

`_start_auto_reconcile_if_enabled` faz `_reconcile_stop.wait(interval)` ANTES do
corpo do laço, então o primeiro ciclo só sai `interval` depois da subida — 600s
no default do compose (`AUTO_RECONCILE_INTERVAL_SECONDS:-600`, e não o 0 do
settings, que o compose sobrescreve). Numa instalação nova apontada para uma
pasta que JÁ tem documentos, a UI mostrava zero por 10 minutos e "Reconciliar
agora" era o único caminho.

A guarda que dá valor a este arquivo é o segundo teste: a condição tem de ser
FALSA quando o índice já tem documentos, senão todo `docker compose restart` de
rotina passaria a pagar um reconcile completo.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import app.main as main


class _ThreadSpy:
    """Substitui threading.Thread para provar o disparo sem rodar reconcile."""

    def __init__(self) -> None:
        self.started: list[dict] = []

    def __call__(self, *, target=None, args=(), name=None, daemon=None):
        spy = self
        registro = {"target": target, "args": args, "name": name, "daemon": daemon}

        class _Fake:
            def start(self_inner) -> None:
                spy.started.append(registro)

        return _Fake()


def _run(*, roots: list[Path], index_has_docs: bool) -> _ThreadSpy:
    spy = _ThreadSpy()
    with patch.object(main, "list_project_roots", return_value=roots), patch.object(
        main, "_index_has_documents", return_value=index_has_docs
    ), patch.object(main.threading, "Thread", spy):
        main._start_setup_reconcile_if_needed()
    return spy


def test_projeto_no_disco_com_indice_vazio_dispara():
    """O cenário do defeito: instalação nova sobre pasta de documentos existente."""
    spy = _run(roots=[Path("/projects/acme")], index_has_docs=False)
    assert len(spy.started) == 1
    disparo = spy.started[0]
    assert disparo["target"] is main._run_reconcile_background
    assert disparo["args"][0] == [Path("/projects/acme")]
    assert disparo["daemon"] is True


def test_indice_ja_povoado_nao_dispara():
    """A guarda: sem ela, todo `docker compose restart` pagaria um reconcile
    completo — caro em corpus grande. É o mutante que este arquivo protege."""
    spy = _run(roots=[Path("/projects/acme")], index_has_docs=True)
    assert spy.started == []


def test_sem_projeto_no_disco_nao_dispara():
    spy = _run(roots=[], index_has_docs=False)
    assert spy.started == []


def test_falha_ao_decidir_nao_derruba_o_boot():
    """O reconcile de setup roda dentro do lifespan: uma exceção aqui levaria a
    API inteira junto. Indisponibilidade vira 'não dispara', nunca um crash."""
    spy = _ThreadSpy()
    with patch.object(main, "list_project_roots", side_effect=OSError("mount sumiu")), patch.object(
        main.threading, "Thread", spy
    ):
        main._start_setup_reconcile_if_needed()  # não pode levantar
    assert spy.started == []
