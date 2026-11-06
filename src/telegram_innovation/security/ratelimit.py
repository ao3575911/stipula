"""In-process sliding window. One bot process is the supported deployment."""

from __future__ import annotations

from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[int, deque[int]] = defaultdict(deque)

    def allow(self, key: int, now: int) -> bool:
        hits = self._hits[key]
        cutoff = now - self.window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True
