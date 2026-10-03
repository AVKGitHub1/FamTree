"""The daily snapshot job (see `famtree.domain.snapshots`)."""

from __future__ import annotations

import logging
import threading

from famtree.domain import snapshots
from famtree.storage.database import Database

log = logging.getLogger(__name__)


class DailySnapshots:
    """Takes the day's snapshot at start-up, then checks every `interval`
    seconds whether a new day has begun."""

    def __init__(self, database: Database, interval: float = 3600) -> None:
        self._db = database
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> str | None:
        try:
            # Checked in a read first, so the hourly checks write nothing.
            with self._db.read() as conn:
                if not snapshots.daily_due(conn):
                    return None
            with self._db.write() as conn:
                outcome = snapshots.take_daily(conn)
        except Exception:
            log.exception("The daily snapshot failed; it is tried again in an hour")
            return None
        if outcome:
            log.info("Daily snapshot %s", outcome)
        return outcome

    def start(self) -> None:
        self.run_once()
        self._thread = threading.Thread(target=self._loop, name="daily-snapshots", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self.run_once()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
            self._thread = None
