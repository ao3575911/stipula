"""Injectable clock so tests do not depend on wall time."""

from __future__ import annotations

import time
from datetime import datetime, timezone


class Clock:
    def now(self) -> int:
        raise NotImplementedError


class SystemClock(Clock):
    def now(self) -> int:
        return int(time.time())


def month_start(timestamp: int) -> int:
    moment = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    start = datetime(moment.year, moment.month, 1, tzinfo=timezone.utc)
    return int(start.timestamp())
