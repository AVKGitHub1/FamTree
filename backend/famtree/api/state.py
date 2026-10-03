"""Per-process application state shared by request handlers."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import IO

from famtree.config import Settings
from famtree.daily import DailySnapshots
from famtree.domain import repository
from famtree.domain.model import FamilyGraph
from famtree.domain.visibility import Audience, authorize
from famtree.layout import Layout, compute_layout
from famtree.security.ratelimit import LoginThrottle
from famtree.storage.bootstrap import StorageUnavailable
from famtree.storage.database import Database


class GraphViews:
    """Authorized graphs and their default layouts, cached per data version.

    There are exactly two audiences (public and full), so the cache is tiny;
    it is invalidated whenever a write transaction commits.
    """

    def __init__(self, database: Database) -> None:
        self._db = database
        self._lock = threading.Lock()
        self._version = -1
        self._graphs: dict[Audience, FamilyGraph] = {}
        self._layouts: dict[Audience, Layout] = {}

    def _graph(self, audience: Audience) -> FamilyGraph:
        """The current graph for `audience`; the caller holds the lock."""
        version = self._db.version
        if version != self._version:
            with self._db.read() as conn:
                full = repository.load_graph(conn)
            self._graphs = {Audience.FULL: full}
            self._layouts = {}
            self._version = version
        if audience not in self._graphs:
            self._graphs[audience] = authorize(self._graphs[Audience.FULL], audience)
        return self._graphs[audience]

    def graph(self, audience: Audience) -> FamilyGraph:
        with self._lock:
            return self._graph(audience)

    def layout(self, audience: Audience) -> tuple[FamilyGraph, Layout]:
        """A graph and the layout of that same graph. Both are read under one
        hold of the lock, so a write cannot slip in between them and leave a
        layout cached under a version whose graph it was not computed from."""
        with self._lock:
            graph = self._graph(audience)
            if audience not in self._layouts:
                self._layouts[audience] = compute_layout(graph)
            return graph, self._layouts[audience]


@dataclass
class AppState:
    settings: Settings
    database: Database | None = None
    storage_error: StorageUnavailable | None = None
    lock_handle: IO[bytes] | None = None
    views: GraphViews | None = None
    daily_snapshots: DailySnapshots | None = None
    throttle: LoginThrottle = field(default_factory=LoginThrottle)
    # Exports are CPU- and memory-heavy; keep a small host responsive.
    export_slots: threading.BoundedSemaphore = field(
        default_factory=lambda: threading.BoundedSemaphore(2)
    )

    def attach(self, database: Database) -> None:
        self.database = database
        self.views = GraphViews(database)
