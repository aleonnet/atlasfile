"""Auto-ingest (v0.50.0): inbox processa sozinha — quiescência, estabilidade,
anti-loop de falha, lock ocupado e descoberta de projetos no sweep.

Os testes usam o manager real com timings curtos e marcam sujeira via
`_mark_dirty` (o caminho do evento) em vez de depender de eventos de
filesystem reais — determinístico em qualquer CI. A propagação de eventos do
watchdog em si foi validada ao vivo no container (VirtioFS, 2026-07-25)."""
from __future__ import annotations

import os
import time
from pathlib import Path

from app.auto_ingest import AutoIngestManager


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class _Harness:
    def __init__(self, tmp_path: Path, projects: list[str], **overrides):
        self.inboxes = {pid: tmp_path / pid / "_INBOX_DROP" for pid in projects}
        for inbox in self.inboxes.values():
            inbox.mkdir(parents=True)
        self.scans: list[str] = []
        self.busy = False
        self.consume = True  # scan "processa" = remove os arquivos da inbox
        params = dict(
            quiescence_seconds=0.08,
            sweep_interval_seconds=0.15,
            min_file_age_seconds=0.0,
            tick_seconds=0.02,
        )
        params.update(overrides)
        self.manager = AutoIngestManager(
            list_project_inboxes=lambda: list(self.inboxes.items()),
            run_scan=self._run_scan,
            **params,
        )

    def _run_scan(self, project_id: str):
        if self.busy:
            return None
        self.scans.append(project_id)
        if self.consume:
            for f in self.inboxes[project_id].iterdir():
                if f.is_file() and not f.name.startswith("."):
                    f.unlink()
        return {"project_id": project_id}


def test_boot_sweep_processa_arquivo_preexistente(tmp_path: Path) -> None:
    h = _Harness(tmp_path, ["proj_a"])
    (h.inboxes["proj_a"] / "doc.txt").write_text("conteúdo")
    h.manager.start()
    try:
        assert _wait_until(lambda: h.scans == ["proj_a"])
        # inbox vazia: não pode ficar re-escaneando
        time.sleep(0.3)
        assert h.scans == ["proj_a"]
    finally:
        h.manager.stop()


def test_evento_dispara_scan_apos_quiescencia(tmp_path: Path) -> None:
    h = _Harness(tmp_path, ["proj_a"])
    h.manager.start()
    try:
        time.sleep(0.2)
        assert h.scans == []  # inbox vazia no boot: nada
        (h.inboxes["proj_a"] / "novo.txt").write_text("x")
        h.manager._mark_dirty("proj_a")
        assert _wait_until(lambda: h.scans == ["proj_a"])
    finally:
        h.manager.stop()


def test_arquivo_imaturo_espera_estabilidade(tmp_path: Path) -> None:
    h = _Harness(tmp_path, ["proj_a"], min_file_age_seconds=0.5)
    f = h.inboxes["proj_a"] / "sincronizando.pdf"
    f.write_text("parcial")
    h.manager.start()
    try:
        time.sleep(0.25)
        assert h.scans == []  # mtime recente: guarda de estabilidade segura
        # Envelhece o arquivo artificialmente além da janela
        old = time.time() - 5
        os.utime(f, (old, old))
        assert _wait_until(lambda: h.scans == ["proj_a"])
    finally:
        h.manager.stop()


def test_sobra_de_falha_nao_vira_loop_de_retry(tmp_path: Path) -> None:
    h = _Harness(tmp_path, ["proj_a"])
    h.consume = False  # simula falha: arquivo permanece na inbox após o scan
    f = h.inboxes["proj_a"] / "quebrado.pdf"
    f.write_text("ilegível")
    h.manager.start()
    try:
        assert _wait_until(lambda: len(h.scans) == 1)
        time.sleep(0.4)  # vários sweeps depois...
        assert len(h.scans) == 1, "sobra inalterada não pode re-disparar scan"
        # Arquivo MUDOU (usuário substituiu): tenta de novo
        f.write_text("ilegível v2 com mais bytes")
        h.manager._mark_dirty("proj_a")
        assert _wait_until(lambda: len(h.scans) == 2)
    finally:
        h.manager.stop()


def test_lock_ocupado_reagenda_sem_perder(tmp_path: Path) -> None:
    h = _Harness(tmp_path, ["proj_a"])
    h.busy = True  # scan manual em curso: run_scan devolve None
    (h.inboxes["proj_a"] / "doc.txt").write_text("x")
    h.manager.start()
    try:
        time.sleep(0.3)
        assert h.scans == []
        h.busy = False
        assert _wait_until(lambda: h.scans == ["proj_a"])
    finally:
        h.manager.stop()


def test_sweep_descobre_projeto_novo_em_runtime(tmp_path: Path) -> None:
    h = _Harness(tmp_path, ["proj_a"])
    h.manager.start()
    try:
        inbox_b = tmp_path / "proj_b" / "_INBOX_DROP"
        inbox_b.mkdir(parents=True)
        (inbox_b / "primeiro.txt").write_text("x")
        h.inboxes["proj_b"] = inbox_b  # projeto criado em runtime
        assert _wait_until(lambda: "proj_b" in h.scans)
    finally:
        h.manager.stop()


def test_dotfile_nao_conta_como_candidato(tmp_path: Path) -> None:
    h = _Harness(tmp_path, ["proj_a"])
    (h.inboxes["proj_a"] / ".DS_Store").write_text("lixo")
    h.manager.start()
    try:
        time.sleep(0.3)
        assert h.scans == []
    finally:
        h.manager.stop()
