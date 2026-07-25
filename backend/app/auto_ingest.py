"""Auto-ingest: a inbox processa sozinha, sem botão.

Desenho (v0.50.0, decisão do usuário: eliminar o "Processar INBOX"):

- Um watcher por inbox de projeto (watchdog; escuta ampla — ver watcher.py)
  marca o projeto como "sujo". O manager espera QUIESCÊNCIA (sem eventos novos
  por N s) e então dispara o scan — o mesmo núcleo do endpoint manual.
- Guarda de estabilidade: o scan do caminho automático pula arquivo com mtime
  mais novo que `min_file_age_seconds` (OneDrive/sync progressivo ainda
  escrevendo); o arquivo maduro entra no próximo tick.
- Sweep periódico: além dos eventos, cada `sweep_interval_seconds` o manager
  relista as inboxes — cobre plataformas onde o inotify não propaga pelo bind
  mount (WSL2/Windows), arquivos que caíram com a API desligada e projetos
  criados em runtime (watchers são registrados/removidos aqui).
- Anti-loop de falha: arquivo que falhou na ingestão PERMANECE na inbox (fato
  do pipeline); o manager memoriza (nome, size, mtime) do que sobrou após um
  scan e só tenta de novo se o arquivo mudar — sem isso, retry infinito.

Todos os parâmetros têm base medida (2026-07-25): rajadas de eventos VirtioFS
chegam com <1s de intervalo → quiescência 4s (4× margem); estabilidade 5s
cobre o flush entre rajadas; sweep 60s é o custo de uma listagem de diretório
pequena por minuto.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from watchdog.observers import Observer

from .watcher import schedule_inbox_watch

_logger = logging.getLogger("atlasfile.auto_ingest")

# (project_id, inbox_dir) por projeto inicializado
ListProjectInboxes = Callable[[], list[tuple[str, Path]]]
# Executa o scan de um projeto; None = ocupado (lock em uso), tenta no próximo tick
RunScan = Callable[[str], dict[str, Any] | None]


class AutoIngestManager:
    def __init__(
        self,
        *,
        list_project_inboxes: ListProjectInboxes,
        run_scan: RunScan,
        quiescence_seconds: float = 4.0,
        sweep_interval_seconds: float = 60.0,
        min_file_age_seconds: float = 5.0,
        tick_seconds: float = 1.0,
    ) -> None:
        self._list_project_inboxes = list_project_inboxes
        self._run_scan = run_scan
        self._quiescence = quiescence_seconds
        self._sweep_interval = sweep_interval_seconds
        self._min_file_age = min_file_age_seconds
        self._tick = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._observer: Observer | None = None
        self._watches: dict[str, Any] = {}
        self._inboxes: dict[str, Path] = {}
        # project_id -> monotonic do último evento (projeto "sujo")
        self._dirty: dict[str, float] = {}
        self._dirty_lock = threading.Lock()
        # project_id -> {filename: (size, mtime)} do que sobrou após scan (falhas)
        self._leftover_seen: dict[str, dict[str, tuple[int, float]]] = {}

    # ── ciclo de vida ─────────────────────────────────────────────────────

    def start(self) -> None:
        self._observer = Observer(timeout=self._tick)
        self._observer.daemon = True
        self._observer.start()
        self._refresh_watchers()
        # Boot: tudo que já estava na inbox conta como "sujo" e maduro — a
        # quiescência começa do zero, o min_file_age filtra o que ainda sincroniza
        now = time.monotonic()
        with self._dirty_lock:
            for project_id, inbox in self._inboxes.items():
                if self._scan_inbox_state(project_id, inbox)[1]:
                    self._dirty[project_id] = now - self._quiescence
        self._thread = threading.Thread(target=self._loop, name="atlasfile-auto-ingest", daemon=True)
        self._thread.start()
        _logger.info("Auto-ingest ligado: %d inbox(es) observada(s)", len(self._inboxes))

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)

    # ── watchers ──────────────────────────────────────────────────────────

    def _mark_dirty(self, project_id: str) -> None:
        with self._dirty_lock:
            self._dirty[project_id] = time.monotonic()

    def _refresh_watchers(self) -> None:
        try:
            current = dict(self._list_project_inboxes())
        except Exception:
            _logger.exception("Auto-ingest: falha listando projetos (raiz indisponível?); mantendo watchers atuais")
            return
        assert self._observer is not None
        for project_id, inbox in current.items():
            if project_id in self._watches:
                continue
            try:
                self._watches[project_id] = schedule_inbox_watch(
                    self._observer, inbox, lambda pid=project_id: self._mark_dirty(pid)
                )
                self._inboxes[project_id] = inbox
            except Exception:
                _logger.exception("Auto-ingest: falha registrando watcher de %s", project_id)
        for project_id in list(self._watches):
            if project_id not in current:
                try:
                    self._observer.unschedule(self._watches.pop(project_id))
                except Exception:
                    self._watches.pop(project_id, None)
                self._inboxes.pop(project_id, None)
                self._leftover_seen.pop(project_id, None)

    # ── elegibilidade ─────────────────────────────────────────────────────

    def _scan_inbox_state(self, project_id: str, inbox: Path) -> tuple[bool, bool]:
        """(ready, pending): ready = há arquivo MADURO que não é sobra de falha
        inalterada → pode disparar scan; pending = há qualquer candidato,
        inclusive imaturo (sync em curso) → projeto continua sujo."""
        seen = self._leftover_seen.get(project_id, {})
        now = time.time()
        ready = False
        pending = False
        try:
            for f in inbox.iterdir():
                if not f.is_file() or f.name.startswith("."):
                    continue
                stat = f.stat()
                if seen.get(f.name) == (stat.st_size, stat.st_mtime):
                    continue
                pending = True
                if self._min_file_age <= 0 or (now - stat.st_mtime) >= self._min_file_age:
                    ready = True
                    break
        except OSError:
            return (False, False)
        return (ready, pending)

    def _record_leftovers(self, project_id: str, inbox: Path) -> None:
        """Memoriza o que o scan deixou para trás (falhas) — mas NUNCA arquivo
        imaturo: ele não foi tentado (o scan o pulou pela guarda de idade) e
        precisa continuar elegível quando amadurecer."""
        seen: dict[str, tuple[int, float]] = {}
        now = time.time()
        try:
            for f in inbox.iterdir():
                if not f.is_file() or f.name.startswith("."):
                    continue
                stat = f.stat()
                if self._min_file_age > 0 and (now - stat.st_mtime) < self._min_file_age:
                    continue
                seen[f.name] = (stat.st_size, stat.st_mtime)
        except OSError:
            pass
        self._leftover_seen[project_id] = seen

    # ── loop principal ────────────────────────────────────────────────────

    def _loop(self) -> None:
        last_sweep = time.monotonic()
        while not self._stop.wait(self._tick):
            now = time.monotonic()
            if now - last_sweep >= self._sweep_interval:
                last_sweep = now
                self._refresh_watchers()
                with self._dirty_lock:
                    for project_id, inbox in self._inboxes.items():
                        if project_id not in self._dirty and self._scan_inbox_state(project_id, inbox)[1]:
                            self._dirty[project_id] = now - self._quiescence
            self._process_quiet_projects(now)

    def _process_quiet_projects(self, now: float) -> None:
        with self._dirty_lock:
            quiet = [pid for pid, ts in self._dirty.items() if (now - ts) >= self._quiescence]
        for project_id in quiet:
            inbox = self._inboxes.get(project_id)
            if inbox is None:
                with self._dirty_lock:
                    self._dirty.pop(project_id, None)
                continue
            ready, pending = self._scan_inbox_state(project_id, inbox)
            if not ready:
                # Só imaturos (sync em curso): segue sujo e reavalia no próximo
                # tick; nada de candidato: limpa
                if not pending:
                    with self._dirty_lock:
                        self._dirty.pop(project_id, None)
                continue
            try:
                result = self._run_scan(project_id)
            except Exception:
                _logger.exception("Auto-ingest: scan de %s falhou", project_id)
                result = {}
            if result is None:
                # Ocupado (scan manual/outro projeto em curso): segue sujo,
                # tenta no próximo tick
                continue
            self._record_leftovers(project_id, inbox)
            with self._dirty_lock:
                if self._scan_inbox_state(project_id, inbox)[1]:
                    # sobrou candidato (ex.: arquivo imaturo): re-arma quiescência
                    self._dirty[project_id] = time.monotonic()
                else:
                    self._dirty.pop(project_id, None)
