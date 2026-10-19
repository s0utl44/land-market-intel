"""Stan zadań na bieżąco w scrape.job_status: start, postęp (ostatnia linia logu), wynik.

Zapis idzie osobnym połączeniem w trybie autocommit, więc postęp widać od razu, niezależnie od transakcji
zadania. Każdy błąd zapisu jest połykany: raport stanu nigdy nie może przerwać pobierania.
"""
from __future__ import annotations

import logging
import time

import psycopg

log = logging.getLogger(__name__)
PROGRESS_EVERY_S = 20  # nie częściej niż co tyle sekund zapisujemy postęp


class Job:
    def __init__(self, conn, name: str):
        self.name = name
        self._last = 0.0
        try:
            self._db = psycopg.connect(conn.info.dsn, password=conn.info.password, autocommit=True)
        except Exception as exc:  # noqa: BLE001
            log.debug("job_status niedostępny: %s", exc)
            self._db = None

    def _exec(self, sql: str, params: tuple) -> None:
        if self._db is None:
            return
        try:
            self._db.execute(sql, params)
        except Exception as exc:  # noqa: BLE001 - np. tabela jeszcze nie istnieje
            log.debug("job_status: %s", exc)

    def start(self, message: str = "start") -> "Job":
        self._exec("""INSERT INTO scrape.job_status (job, state, started_at, updated_at, finished_at, message)
                      VALUES (%s, 'running', now(), now(), NULL, %s)
                      ON CONFLICT (job) DO UPDATE SET state = 'running', started_at = now(), updated_at = now(),
                                                      finished_at = NULL, message = EXCLUDED.message""",
                   (self.name, message[:500]))
        return self

    def progress(self, message: str, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last < PROGRESS_EVERY_S:
            return
        self._last = now
        self._exec("UPDATE scrape.job_status SET updated_at = now(), message = %s WHERE job = %s",
                   (message[:500], self.name))

    def finish(self, state: str, message: str = "") -> None:
        self._exec("""UPDATE scrape.job_status SET state = %s, updated_at = now(), finished_at = now(), message = %s
                      WHERE job = %s""", (state, message[:500], self.name))
        if self._db is not None:
            try:
                self._db.close()
            except Exception:  # noqa: BLE001
                pass


class JobLogHandler(logging.Handler):
    """Ostatnia linia INFO z modułów pobierania trafia jako postęp zadania."""

    def __init__(self, job: Job, prefixes=("lmi.scrapers", "lmi.rcn", "lmi.backfill")):
        super().__init__(level=logging.INFO)
        self.job, self.prefixes = job, prefixes

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(self.prefixes):
            try:
                self.job.progress(record.getMessage(), force=record.levelno >= logging.WARNING)
            except Exception:  # noqa: BLE001
                pass


class tracked:
    """with tracked(conn, "gratka") as job: ...  — start, postęp z logów, a przy wyjątku stan 'error'."""

    def __init__(self, conn, name: str, start_message: str = "start"):
        self.job = Job(conn, name)
        self.start_message = start_message
        self.handler = JobLogHandler(self.job)

    def __enter__(self) -> Job:
        self.job.start(self.start_message)
        logging.getLogger("lmi").addHandler(self.handler)
        return self.job

    def __exit__(self, exc_type, exc, tb):
        logging.getLogger("lmi").removeHandler(self.handler)
        if exc is not None:
            self.job.finish("error", f"{type(exc).__name__}: {exc}")
        return False
