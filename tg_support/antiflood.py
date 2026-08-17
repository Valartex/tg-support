"""In-memory sliding-window rate limiter."""
from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    """Allows `count` events per `seconds` per key. Resets on restart."""

    def __init__(self, count: int, seconds: int) -> None:
        self._count = count
        self._seconds = seconds
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, key: int) -> bool:
        """Register an event and report whether it fits inside the window."""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self._seconds:
            hits.popleft()
        if len(hits) >= self._count:
            return False
        hits.append(now)
        return True
