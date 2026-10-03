"""In-memory sliding-window rate limiting for authentication attempts."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(
        self,
        max_events: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.max_events = max_events
        self.window = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Record an attempt. Returns seconds to wait if the key is over its limit."""
        now = self._clock()
        with self._lock:
            events = self._events.get(key)
            if events is None:
                if len(self._events) >= self._max_keys:
                    self._prune(now)
                events = self._events[key] = deque()
            while events and events[0] <= now - self.window:
                events.popleft()
            if len(events) >= self.max_events:
                return max(1.0, math.ceil(events[0] + self.window - now))
            events.append(now)
            return None

    def _prune(self, now: float) -> None:
        stale = [k for k, ev in self._events.items() if not ev or ev[-1] <= now - self.window]
        for key in stale:
            del self._events[key]
        if len(self._events) >= self._max_keys:  # still full: drop the oldest half
            for key in sorted(self._events, key=lambda k: self._events[k][-1])[
                : self._max_keys // 2
            ]:
                del self._events[key]


class LoginThrottle:
    """Per-client and global limits; the global one bounds distributed guessing."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_client = SlidingWindowLimiter(10, 300, clock)
        self.global_ = SlidingWindowLimiter(60, 300, clock)

    def check(self, client: str) -> float | None:
        return self.per_client.hit(client) or self.global_.hit("*")
