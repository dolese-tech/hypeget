"""Daily start/stop window for the download queue."""
from __future__ import annotations

import datetime as dt


def _parse(hhmm: str) -> dt.time | None:
    try:
        h, m = hhmm.split(":")
        return dt.time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def in_window(start: str, end: str, now: dt.datetime | None = None) -> bool:
    """Is the clock inside [start, end)? Windows may wrap midnight (22:00-06:00)."""
    a, b = _parse(start), _parse(end)
    if a is None or b is None or a == b:
        return False
    t = (now or dt.datetime.now()).time()
    return a <= t < b if a < b else (t >= a or t < b)


class Scheduler:
    def __init__(self):
        self._last_minute: str | None = None

    def check(self, enabled: bool, start: str, stop: str, now: dt.datetime | None = None) -> str | None:
        """Return "start" / "stop" exactly once when the clock hits a boundary."""
        if not enabled:
            self._last_minute = None
            return None
        now = now or dt.datetime.now()
        key = now.strftime("%Y%m%d%H%M")
        if key == self._last_minute:
            return None
        self._last_minute = key
        t = now.time().replace(second=0, microsecond=0)
        if _parse(start) == t:
            return "start"
        if _parse(stop) == t:
            return "stop"
        return None

    @staticmethod
    def describe(enabled: bool, start: str, stop: str) -> str:
        if not enabled:
            return "Scheduler off"
        return f"Scheduler {start}–{stop}"
