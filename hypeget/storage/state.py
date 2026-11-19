"""Persist the download list (with segment progress) so downloads survive restarts."""
from __future__ import annotations

import json
import os
import threading

from ..engine.download import Download


class StateStore:
    def __init__(self, home: str):
        self.path = os.path.join(home, "downloads.json")
        self._lock = threading.Lock()

    def load(self) -> list[Download]:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        out = []
        for item in data.get("downloads", []):
            try:
                out.append(Download.from_state(item))
            except TypeError:
                continue
        return out

    def save(self, downloads: list[Download]) -> None:
        payload = {"version": 1, "downloads": []}
        for d in downloads:
            with d.lock:
                payload["downloads"].append(d.to_state())
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, self.path)
