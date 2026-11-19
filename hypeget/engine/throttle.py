"""Global token-bucket speed limiter shared by every connection."""
from __future__ import annotations

import threading
import time


class Throttle:
    def __init__(self, bytes_per_sec: int = 0):
        self._lock = threading.Lock()
        self._rate = 0
        self._tokens = 0.0
        self._last = time.monotonic()
        self.set_limit(bytes_per_sec)

    @property
    def limit(self) -> int:
        return self._rate

    def set_limit(self, bytes_per_sec: int) -> None:
        """0 means unlimited."""
        with self._lock:
            self._rate = max(0, int(bytes_per_sec or 0))
            self._tokens = min(self._tokens, float(self._rate))
            self._last = time.monotonic()

    def consume(self, n: int, stop: threading.Event | None = None) -> None:
        """Block until ``n`` bytes may be transferred."""
        while True:
            with self._lock:
                if self._rate <= 0:
                    return
                now = time.monotonic()
                self._tokens = min(float(self._rate), self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= n or self._tokens >= self._rate:
                    self._tokens -= n
                    return
                wait = (n - self._tokens) / self._rate
            if stop is not None and stop.wait(min(wait, 0.2)):
                return
            if stop is None:
                time.sleep(min(wait, 0.2))
